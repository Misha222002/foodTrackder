import hmac
import secrets
from contextlib import asynccontextmanager
from datetime import timedelta
from uuid import UUID, uuid4

from sqlalchemy import select, text, update

from food_tracker.core.errors import DomainError
from food_tracker.core.security import (
    code_digest,
    decode_token,
    digest,
    encode_token,
    hash_password,
    keyed_digest,
    secret,
    verify_password,
)
from food_tracker.modules.auth.mail import enqueue
from food_tracker.modules.auth.models import (
    AuthRateLimit,
    AuthSession,
    EmailChallenge,
    RefreshToken,
)
from food_tracker.modules.auth.schemas import ChallengeResponse, TokenResponse
from food_tracker.modules.users.models import User


def normalize_email(email):
    # MVP treats both parts case-insensitively; no provider-specific dot/plus rewriting.
    return str(email).strip().casefold()


class AuthService:
    def __init__(self, session, settings, clock):
        self.db, self.settings, self.clock = session, settings, clock
        for name in (
            "access_jwt_secret",
            "refresh_jwt_secret",
            "code_hmac_secret",
            "csrf_secret",
            "mail_encryption_key",
        ):
            secret(settings, name)

    def account_key(self, email):
        return keyed_digest(secret(self.settings, "code_hmac_secret"), normalize_email(email))

    @asynccontextmanager
    async def transaction(self, account_key, ip):
        """Serialize account/IP mutations, and commit failed-attempt counters too."""
        failure = None
        async with self.db.begin():
            keys = [f"account:{account_key}", f"ip:{ip}"]
            lock_ids = sorted(
                {
                    int(keyed_digest(secret(self.settings, "code_hmac_secret"), key)[:16], 16)
                    % (2**63 - 1)
                    for key in keys
                }
            )
            for lock_id in lock_ids:
                await self.db.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": lock_id})
            try:
                await self.limit("request:ip", ip, self.settings.auth_request_ip_limit, 3600)
                yield
            except DomainError as error:
                failure = error
        if failure:
            raise failure

    async def limit(self, scope, identity, maximum, seconds):
        now = self.clock()
        bucket = keyed_digest(secret(self.settings, "code_hmac_secret"), f"{scope}:{identity}")
        row = await self.db.get(AuthRateLimit, bucket, with_for_update=True)
        if row is None:
            row = AuthRateLimit(
                bucket=bucket,
                window_started_at=now,
                expires_at=now + timedelta(seconds=seconds),
                count=0,
            )
            self.db.add(row)
        elif row.expires_at <= now:
            row.count, row.window_started_at = 0, now
            row.expires_at = now + timedelta(seconds=seconds)
        if row.count >= maximum:
            raise DomainError(
                429,
                "RATE_LIMITED",
                "Слишком много попыток. Попробуйте позже",
                {"retryAfterSeconds": max(1, int((row.expires_at - now).total_seconds()))},
            )
        row.count += 1
        await self.db.flush()

    async def send_limits(self, account, ip, *, check_interval=True):
        last_sent = await self.db.scalar(
            select(EmailChallenge.sent_at)
            .where(EmailChallenge.account_key == account)
            .order_by(EmailChallenge.sent_at.desc())
            .limit(1)
        )
        if check_interval and last_sent:
            remaining = (
                last_sent + timedelta(seconds=self.settings.resend_interval_seconds) - self.clock()
            ).total_seconds()
            if remaining > 0:
                raise DomainError(
                    429,
                    "RESEND_TOO_SOON",
                    "Повторите отправку позже",
                    {"retryAfterSeconds": max(1, int(remaining))},
                )
        await self.limit("send:account", account, self.settings.code_send_account_limit, 3600)
        await self.limit("send:ip", ip, self.settings.code_send_ip_limit, 3600)

    def challenge_response(self, challenge):
        return ChallengeResponse(
            challenge_id=challenge.id,
            expires_at=challenge.expires_at,
            resend_available_at=challenge.sent_at
            + timedelta(seconds=self.settings.resend_interval_seconds),
        )

    def set_code(self, challenge, user):
        now = self.clock()
        code = f"{secrets.randbelow(1000000):06d}"
        challenge.code_digest = code_digest(
            self.settings, challenge.id, challenge.user_id, challenge.purpose, code
        )
        challenge.sent_at = now
        challenge.expires_at = now + timedelta(seconds=self.settings.code_ttl_seconds)
        challenge.attempts = 0
        enqueue(
            self.db,
            self.settings,
            now,
            user_id=challenge.user_id,
            recipient=user.email if user else None,
            subject="Код Ем по плану",
            body=f"Ваш код: {code}\nДействует 10 минут. Никому его не сообщайте.",
            challenge=challenge,
        )

    async def new_challenge(self, user, account, purpose):
        now = self.clock()
        # One active challenge per account/purpose; resend cannot restore old codes.
        await self.db.execute(
            update(EmailChallenge)
            .where(
                EmailChallenge.account_key == account,
                EmailChallenge.purpose == purpose,
                EmailChallenge.consumed_at.is_(None),
            )
            .values(consumed_at=now)
        )
        challenge = EmailChallenge(
            id=uuid4(),
            user_id=user.id if user else None,
            account_key=account,
            purpose=purpose,
            created_at=now,
        )
        self.db.add(challenge)
        self.set_code(challenge, user)
        await self.db.flush()
        return challenge

    async def register(self, email, password, ip):
        account = self.account_key(email)
        async with self.transaction(account, ip):
            user = await self.db.scalar(
                select(User).where(User.email == normalize_email(email)).with_for_update()
            )
            if user is not None and user.email_verified_at is not None:
                # This is a refusal, not a code resend: apply budgets without the
                # 60-second send interval, including immediately after verification.
                await self.send_limits(account, ip, check_interval=False)
                raise DomainError(
                    409,
                    "EMAIL_ALREADY_REGISTERED",
                    "Аккаунт с таким email уже зарегистрирован",
                    {
                        "fields": [
                            {
                                "path": "email",
                                "type": "email_already_registered",
                                "message": "Войдите в аккаунт или восстановите пароль",
                            }
                        ]
                    },
                )
            await self.send_limits(account, ip)
            password_hash = await hash_password(password)
            if user is None:
                user = User(id=uuid4(), email=normalize_email(email), password_hash=password_hash)
                self.db.add(user)
                await self.db.flush()
                challenge = await self.new_challenge(user, account, "verify_email")
            elif user.email_verified_at is None and await verify_password(
                user.password_hash, password
            ):
                # Resume only after proving knowledge of the original password.
                # Never replace the account or its password during re-registration.
                challenge = await self.new_challenge(user, account, "verify_email")
            else:
                # A repeated public registration never modifies another account/password,
                # nor issues a code that could authenticate a different chosen password.
                challenge = EmailChallenge(
                    id=uuid4(),
                    user_id=None,
                    account_key=account,
                    purpose="verify_email",
                    created_at=self.clock(),
                )
                self.db.add(challenge)
                self.set_code(challenge, None)
                await self.db.flush()
            result = self.challenge_response(challenge)
        return result

    async def lookup_challenge(self, challenge_id, purpose):
        # Read key without holding a row lock; all writes take advisory account lock first.
        row = await self.db.get(EmailChallenge, challenge_id)
        account = row.account_key if row else str(challenge_id)
        await self.db.rollback()
        return account

    async def resend(self, challenge_id, ip):
        account = await self.lookup_challenge(challenge_id, "verify_email")
        async with self.transaction(account, ip):
            row = await self.db.get(EmailChallenge, challenge_id, with_for_update=True)
            if row is None or row.purpose != "verify_email" or row.consumed_at:
                raise DomainError(400, "CODE_INVALID", "Запросите новый код")
            now = self.clock()
            wait = (
                row.sent_at + timedelta(seconds=self.settings.resend_interval_seconds) - now
            ).total_seconds()
            if wait > 0:
                raise DomainError(
                    429,
                    "RESEND_TOO_SOON",
                    "Повторите отправку позже",
                    {"retryAfterSeconds": max(1, int(wait))},
                )
            await self.send_limits(account, ip)
            user = await self.db.get(User, row.user_id) if row.user_id else None
            self.set_code(row, user)
            result = self.challenge_response(row)
        return result

    async def check_code(self, challenge_id, code, purpose, account, ip):
        await self.limit("guess:account", account, self.settings.code_attempt_account_limit, 3600)
        await self.limit("guess:ip", ip, self.settings.code_attempt_ip_limit, 3600)
        row = await self.db.get(EmailChallenge, challenge_id, with_for_update=True)
        if not row or row.purpose != purpose or row.consumed_at:
            raise DomainError(400, "CODE_INVALID", "Код недействителен. Запросите новый код")
        if row.expires_at <= self.clock():
            raise DomainError(400, "CODE_EXPIRED", "Срок кода истёк. Запросите новый код")
        if row.attempts >= self.settings.code_max_attempts:
            raise DomainError(
                429, "CODE_ATTEMPTS_EXCEEDED", "Попытки исчерпаны. Запросите новый код"
            )
        row.attempts += 1
        expected = code_digest(self.settings, row.id, row.user_id, row.purpose, code)
        if not hmac.compare_digest(row.code_digest, expected) or row.user_id is None:
            raise DomainError(400, "CODE_INVALID", "Неверный код")
        row.consumed_at = self.clock()
        return row

    async def issue_tokens(self, user, auth_session=None):
        now = self.clock()
        if auth_session is None:
            auth_session = AuthSession(
                id=uuid4(),
                user_id=user.id,
                created_at=now,
                expires_at=now + timedelta(seconds=self.settings.session_ttl_seconds),
            )
            self.db.add(auth_session)
            await self.db.flush()
        access_expiry = min(
            auth_session.expires_at, now + timedelta(seconds=self.settings.access_ttl_seconds)
        )
        access, _ = encode_token(
            self.settings, "access", user.id, auth_session.id, now, access_expiry, role=user.role
        )
        refresh, jti = encode_token(
            self.settings, "refresh", user.id, auth_session.id, now, auth_session.expires_at
        )
        self.db.add(
            RefreshToken(
                jti=jti,
                session_id=auth_session.id,
                token_digest=digest(refresh),
                expires_at=auth_session.expires_at,
            )
        )
        response = TokenResponse(
            access_token=access,
            expires_at=access_expiry,
            expires_in=int(access_expiry.timestamp()) - int(now.timestamp()),
            user_id=user.id,
        )
        return response, refresh, auth_session.expires_at

    async def verify_email(self, challenge_id, code, ip):
        account = await self.lookup_challenge(challenge_id, "verify_email")
        async with self.transaction(account, ip):
            row = await self.check_code(challenge_id, code, "verify_email", account, ip)
            user = await self.db.get(User, row.user_id, with_for_update=True)
            if user.email_verified_at is not None:
                raise DomainError(400, "CODE_INVALID", "Код уже использован")
            user.email_verified_at = self.clock()
            user.updated_at = self.clock()
            # Invalidate every outstanding registration challenge for this user.
            await self.db.execute(
                update(EmailChallenge)
                .where(
                    EmailChallenge.user_id == user.id,
                    EmailChallenge.purpose == "verify_email",
                    EmailChallenge.consumed_at.is_(None),
                )
                .values(consumed_at=self.clock())
            )
            result = await self.issue_tokens(user)
        return result

    async def current_user(self, access):
        claims = decode_token(self.settings, access, "access", self.clock())
        row = await self.db.scalar(
            select(User)
            .join(AuthSession, AuthSession.user_id == User.id)
            .where(
                User.id == UUID(claims["sub"]),
                AuthSession.id == UUID(claims["sid"]),
                AuthSession.revoked_at.is_(None),
                AuthSession.expires_at > self.clock(),
                User.email_verified_at.is_not(None),
            )
        )
        if row is None:
            raise DomainError(401, "SESSION_EXPIRED", "Войдите в аккаунт заново")
        return row

    async def login(self, email, password, ip):
        from food_tracker.core.security import DUMMY_PASSWORD_HASH, verify_password
        from food_tracker.modules.auth.schemas import VerificationRequired

        account = self.account_key(email)
        async with self.transaction(account, ip):
            await self.limit("login:account", account, self.settings.login_account_limit, 900)
            await self.limit("login:ip", ip, self.settings.login_ip_limit, 900)
            user = await self.db.scalar(
                select(User).where(User.email == normalize_email(email)).with_for_update()
            )
            correct = await verify_password(
                user.password_hash if user else DUMMY_PASSWORD_HASH, password
            )
            if not correct or user is None:
                raise DomainError(401, "INVALID_CREDENTIALS", "Неверный email или пароль")
            if user.email_verified_at is None:
                challenge = await self.db.scalar(
                    select(EmailChallenge)
                    .where(
                        EmailChallenge.user_id == user.id,
                        EmailChallenge.purpose == "verify_email",
                        EmailChallenge.consumed_at.is_(None),
                    )
                    .order_by(EmailChallenge.created_at.desc())
                    .limit(1)
                    .with_for_update()
                )
                if challenge is None:
                    await self.send_limits(account, ip)
                    challenge = await self.new_challenge(user, account, "verify_email")
                result = VerificationRequired(**self.challenge_response(challenge).model_dump())
            else:
                result = await self.issue_tokens(user)
        return result

    async def session_claims(self, raw_refresh):
        if not raw_refresh:
            raise DomainError(401, "SESSION_EXPIRED", "Войдите в аккаунт заново")
        claims = decode_token(self.settings, raw_refresh, "refresh", self.clock())
        user = await self.db.get(User, UUID(claims["sub"]))
        account = self.account_key(user.email) if user else claims["sub"]
        await self.db.rollback()
        return claims, account

    async def refresh(self, raw_refresh, ip):
        claims, account = await self.session_claims(raw_refresh)
        async with self.transaction(account, ip):
            user = await self.db.get(User, UUID(claims["sub"]), with_for_update=True)
            auth_session = await self.db.get(AuthSession, UUID(claims["sid"]), with_for_update=True)
            token = await self.db.get(RefreshToken, UUID(claims["jti"]), with_for_update=True)
            if (
                not user
                or not user.email_verified_at
                or not auth_session
                or auth_session.user_id != user.id
                or auth_session.revoked_at
                or auth_session.expires_at <= self.clock()
                or not token
                or token.session_id != auth_session.id
                or token.expires_at <= self.clock()
                or not hmac.compare_digest(token.token_digest, digest(raw_refresh))
            ):
                raise DomainError(401, "SESSION_EXPIRED", "Войдите в аккаунт заново")
            if token.used_at:
                auth_session.revoked_at = self.clock()
                raise DomainError(401, "REFRESH_REUSED", "Сессия отозвана. Войдите заново")
            token.used_at = self.clock()
            result = await self.issue_tokens(user, auth_session)
            token.replaced_by_jti = decode_token(self.settings, result[1], "refresh", self.clock())[
                "jti"
            ]
            token.replaced_by_jti = UUID(token.replaced_by_jti)
        return result

    async def logout(self, raw_refresh, ip):
        try:
            claims, account = await self.session_claims(raw_refresh)
        except DomainError as error:
            if error.status == 401:
                return
            raise
        async with self.transaction(account, ip):
            auth_session = await self.db.get(AuthSession, UUID(claims["sid"]), with_for_update=True)
            token = await self.db.get(RefreshToken, UUID(claims["jti"]))
            if (
                auth_session
                and auth_session.user_id == UUID(claims["sub"])
                and token
                and token.session_id == auth_session.id
                and hmac.compare_digest(token.token_digest, digest(raw_refresh))
            ):
                auth_session.revoked_at = self.clock()

    async def forgot_password(self, email, ip):
        account = self.account_key(email)
        async with self.transaction(account, ip):
            await self.send_limits(account, ip)
            user = await self.db.scalar(
                select(User).where(User.email == normalize_email(email)).with_for_update()
            )
            if user is None:
                raise DomainError(
                    404,
                    "EMAIL_NOT_FOUND",
                    "Аккаунт с таким email не найден",
                    {
                        "fields": [
                            {
                                "path": "email",
                                "type": "email_not_found",
                                "message": "Проверьте адрес или зарегистрируйтесь",
                            }
                        ]
                    },
                )
            if user.email_verified_at is None:
                raise DomainError(
                    409,
                    "EMAIL_NOT_VERIFIED",
                    "Сначала подтвердите почту аккаунта",
                    {
                        "fields": [
                            {
                                "path": "email",
                                "type": "email_not_verified",
                                "message": (
                                    "Войдите с паролем регистрации и запросите код подтверждения"
                                ),
                            }
                        ]
                    },
                )
            challenge = await self.new_challenge(user, account, "reset_password")
            result = self.challenge_response(challenge)
        return result

    async def reset_password(self, challenge_id, code, password, ip):
        account = await self.lookup_challenge(challenge_id, "reset_password")
        async with self.transaction(account, ip):
            row = await self.check_code(challenge_id, code, "reset_password", account, ip)
            user = await self.db.get(User, row.user_id, with_for_update=True)
            if not user or not user.email_verified_at:
                raise DomainError(400, "CODE_INVALID", "Неверный код")
            user.password_hash = await hash_password(password)
            user.updated_at = self.clock()
            await self.db.execute(
                update(AuthSession)
                .where(AuthSession.user_id == user.id, AuthSession.revoked_at.is_(None))
                .values(revoked_at=self.clock())
            )
            await self.db.execute(
                update(EmailChallenge)
                .where(
                    EmailChallenge.user_id == user.id,
                    EmailChallenge.purpose == "reset_password",
                    EmailChallenge.consumed_at.is_(None),
                )
                .values(consumed_at=self.clock())
            )
            enqueue(
                self.db,
                self.settings,
                self.clock(),
                user_id=user.id,
                recipient=user.email,
                subject="Пароль Ем по плану изменён",
                body=(
                    "Ваш пароль изменён. Все сеансы завершены. "
                    "Если это были не вы, восстановите доступ."
                ),
            )
