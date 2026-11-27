import re
from datetime import UTC, datetime, timedelta

import pytest
from cryptography.fernet import Fernet
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from food_tracker.core.config import Settings
from food_tracker.main import create_app
from food_tracker.modules.auth.mail import MemoryMailer, deliver_pending
from food_tracker.modules.auth.models import EmailChallenge, EmailOutbox
from food_tracker.modules.users.models import User


@pytest.fixture
async def auth_env(migrated_database_url):
    url, _ = migrated_database_url
    settings = Settings(
        database_url=url,
        access_jwt_secret="a" * 32,
        refresh_jwt_secret="r" * 32,
        code_hmac_secret="c" * 32,
        csrf_secret="s" * 32,
        mail_encryption_key=Fernet.generate_key().decode(),
        mail_worker_enabled=False,
        auth_min_response_seconds=0,
        auth_allowed_origins=["https://test"],
    )
    now = [datetime(2026, 11, 27, 12, tzinfo=UTC)]
    app = create_app(settings)
    app.state.clock = lambda: now[0]
    mailer = MemoryMailer([])
    async with (
        app.router.lifespan_context(app),
        AsyncClient(
            transport=ASGITransport(app=app),
            base_url="https://test",
            headers={"Origin": "https://test"},
        ) as client,
    ):
        csrf = (await client.get("/api/v1/auth/csrf")).json()["csrfToken"]
        client.headers["X-CSRF-Token"] = csrf

        async def code():
            await deliver_pending(app.state.session_factory, settings, mailer, app.state.clock)
            return re.search(r"\b[0-9]{6}\b", mailer.messages[-1][2])[0]

        yield app, client, now, mailer, code


async def register(client, email="Person@example.org"):
    response = await client.post(
        "/api/v1/auth/register", json={"email": email, "password": "a long password 123"}
    )
    assert response.status_code == 202, response.text
    assert "accessToken" not in response.json()
    return response.json()["challengeId"]


@pytest.mark.anyio
async def test_registration_verification_secure_cookie_and_no_public_role(auth_env):
    app, client, _, mailer, code = auth_env
    challenge = await register(client)
    assert (await client.get("/api/v1/users/me")).status_code == 401
    async with app.state.session_factory() as db:
        user = await db.scalar(select(User))
        outbox = await db.scalar(select(EmailOutbox))
        assert user.email == "person@example.org" and user.role == "USER"
        assert user.password_hash.startswith("$argon2id$")
        assert "Ваш код" not in outbox.encrypted_payload
    value = await code()
    response = await client.post(
        "/api/v1/auth/verify-email", json={"challengeId": challenge, "code": value}
    )
    assert response.status_code == 200, response.text
    assert "refreshToken" not in response.json()
    cookie = response.headers["set-cookie"]
    assert "HttpOnly" in cookie and "Secure" in cookie and "SameSite=lax" in cookie
    assert "Path=/api/v1/auth" in cookie and "Domain=" not in cookie
    assert response.headers["cache-control"] == "no-store"
    token = response.json()["accessToken"]
    profile = await client.get("/api/v1/users/me", headers={"Authorization": f"Bearer {token}"})
    assert profile.status_code == 200 and profile.json()["emailVerifiedAt"]
    assert "password" not in profile.text.lower()
    assert len(mailer.messages) == 1
    assert (
        await client.post(
            "/api/v1/auth/verify-email", json={"challengeId": challenge, "code": value}
        )
    ).status_code == 400
    invalid = await client.post(
        "/api/v1/auth/register",
        json={"email": "admin@example.org", "password": "long secret password", "role": "ADMIN"},
    )
    assert invalid.status_code == 422 and "long secret password" not in invalid.text


@pytest.mark.anyio
async def test_attempts_resend_expiry_and_password_not_replaced(auth_env):
    app, client, now, _, code = auth_env
    challenge = await register(client)
    original = await code()
    now[0] += timedelta(seconds=61)
    repeated_response = await client.post(
        "/api/v1/auth/register",
        json={"email": "person@example.org", "password": "a different password 456"},
    )
    assert repeated_response.status_code == 202
    repeated = repeated_response.json()["challengeId"]
    assert repeated != challenge
    async with app.state.session_factory() as db:
        assert len((await db.scalars(select(User))).all()) == 1
        row = await db.get(EmailChallenge, challenge)
        assert row.consumed_at is None
    assert (
        await client.post("/api/v1/auth/verification/resend", json={"challengeId": challenge})
    ).status_code == 429
    wrong = "000000" if original != "000000" else "000001"
    for _ in range(5):
        response = await client.post(
            "/api/v1/auth/verify-email", json={"challengeId": challenge, "code": wrong}
        )
        assert response.status_code == 400
    assert (
        await client.post(
            "/api/v1/auth/verify-email", json={"challengeId": challenge, "code": original}
        )
    ).status_code == 429
    now[0] += timedelta(seconds=61)
    assert (
        await client.post("/api/v1/auth/verification/resend", json={"challengeId": challenge})
    ).status_code == 200
    new = await code()
    if original != new:
        assert (
            await client.post(
                "/api/v1/auth/verify-email", json={"challengeId": challenge, "code": original}
            )
        ).status_code == 400
    now[0] += timedelta(seconds=601)
    response = await client.post(
        "/api/v1/auth/verify-email", json={"challengeId": challenge, "code": new}
    )
    assert response.json()["code"] == "CODE_EXPIRED"


@pytest.mark.anyio
async def test_csrf_origin_and_uniform_validation(auth_env):
    _, client, _, _, _ = auth_env
    body = {"email": "me@example.org", "password": "sufficient password"}
    response = await client.post(
        "/api/v1/auth/register", json=body, headers={"Origin": "https://evil.test"}
    )
    assert response.status_code == 403
    response = await client.post(
        "/api/v1/auth/register", json=body, headers={"X-CSRF-Token": "wrong"}
    )
    assert response.status_code == 403
    response = await client.post(
        "/api/v1/auth/register", json={"email": "invalid", "password": "123"}
    )
    assert response.status_code == 422
    assert response.json()["details"]["fields"]
    assert response.json()["requestId"] == response.headers["X-Request-ID"]


async def verified(client, code, email="Person@example.org"):
    challenge = await register(client, email)
    response = await client.post(
        "/api/v1/auth/verify-email", json={"challengeId": challenge, "code": await code()}
    )
    assert response.status_code == 200, response.text
    return response.json()["accessToken"]


@pytest.mark.anyio
async def test_login_unverified_refresh_absolute_expiry_and_logout(auth_env):
    app, client, now, _, code = auth_env
    challenge = await register(client)
    credentials = {"email": "PERSON@example.org", "password": "a long password 123"}
    response = await client.post("/api/v1/auth/login", json={**credentials, "password": "wrong"})
    assert response.status_code == 401
    response = await client.post("/api/v1/auth/login", json=credentials)
    assert response.json()["status"] == "email_verification_required"
    assert response.json()["challengeId"] == challenge
    assert "ft_refresh" not in client.cookies
    response = await client.post(
        "/api/v1/auth/verify-email", json={"challengeId": challenge, "code": await code()}
    )
    old_access = response.json()["accessToken"]
    from food_tracker.core.security import decode_token

    first = client.cookies["ft_refresh"]
    first_exp = decode_token(app.state.settings, first, "refresh", now[0])["exp"]
    now[0] += timedelta(seconds=901)
    assert (
        await client.get("/api/v1/users/me", headers={"Authorization": f"Bearer {old_access}"})
    ).status_code == 401
    response = await client.post("/api/v1/auth/refresh")
    assert response.status_code == 200, response.text
    assert (
        decode_token(app.state.settings, client.cookies["ft_refresh"], "refresh", now[0])["exp"]
        == first_exp
    )
    fresh_access = response.json()["accessToken"]
    assert (
        await client.get("/api/v1/users/me", headers={"Authorization": f"Bearer {fresh_access}"})
    ).status_code == 200
    response = await client.post(
        "/api/v1/auth/logout", headers={"Authorization": f"Bearer {old_access}"}
    )
    assert response.status_code == 204
    assert "ft_refresh" not in client.cookies
    assert (
        await client.get("/api/v1/users/me", headers={"Authorization": f"Bearer {fresh_access}"})
    ).status_code == 401
    assert (await client.post("/api/v1/auth/login", json=credentials)).status_code == 200


@pytest.mark.anyio
async def test_concurrent_refresh_replay_revokes_session_and_access(auth_env):
    import asyncio

    from food_tracker.modules.auth.models import AuthSession, RefreshToken

    _, client, _, _, code = auth_env
    access = await verified(client, code)
    original = client.cookies["ft_refresh"]
    cookie = f"ft_refresh={original}; ft_csrf={client.cookies['ft_csrf']}"
    responses = await asyncio.gather(
        *[client.post("/api/v1/auth/refresh", headers={"Cookie": cookie}) for _ in range(2)]
    )
    assert sorted(r.status_code for r in responses) == [200, 401]
    assert (
        await client.get("/api/v1/users/me", headers={"Authorization": f"Bearer {access}"})
    ).status_code == 401
    app = auth_env[0]
    async with app.state.session_factory() as db:
        assert (await db.scalar(select(AuthSession))).revoked_at
        tokens = (await db.scalars(select(RefreshToken))).all()
        assert len(tokens) == 2
        assert all(t.token_digest != original for t in tokens)
        assert len([t for t in tokens if t.used_at]) == 1


@pytest.mark.anyio
async def test_reset_revokes_all_sessions_and_requires_normal_login(auth_env):
    app, client, now, mailer, code = auth_env
    first_access = await verified(client, code)
    second = await client.post(
        "/api/v1/auth/login",
        json={"email": "person@example.org", "password": "a long password 123"},
    )
    second_access = second.json()["accessToken"]
    old_refresh = client.cookies["ft_refresh"]
    now[0] += timedelta(seconds=61)
    response = await client.post(
        "/api/v1/auth/password/forgot", json={"email": "person@example.org"}
    )
    assert response.status_code == 202
    reset_challenge = response.json()["challengeId"]
    reset_code = await code()
    # Registration and recovery challenges cannot be exchanged.
    assert (
        await client.post(
            "/api/v1/auth/verify-email", json={"challengeId": reset_challenge, "code": reset_code}
        )
    ).status_code == 400
    response = await client.post(
        "/api/v1/auth/password/reset",
        json={
            "challengeId": reset_challenge,
            "code": reset_code,
            "newPassword": "a new long password 456",
        },
    )
    assert response.status_code == 200, response.text
    assert response.json() == {"status": "password_reset"}
    assert "ft_refresh" not in client.cookies
    for access in (first_access, second_access):
        assert (
            await client.get("/api/v1/users/me", headers={"Authorization": f"Bearer {access}"})
        ).status_code == 401
    assert (
        await client.post(
            "/api/v1/auth/refresh",
            headers={"Cookie": f"ft_refresh={old_refresh}; ft_csrf={client.cookies['ft_csrf']}"},
        )
    ).status_code == 401
    assert (
        await client.post(
            "/api/v1/auth/login",
            json={"email": "person@example.org", "password": "a long password 123"},
        )
    ).status_code == 401
    assert (
        await client.post(
            "/api/v1/auth/login",
            json={"email": "person@example.org", "password": "a new long password 456"},
        )
    ).status_code == 200
    assert (
        await client.post(
            "/api/v1/auth/password/reset",
            json={
                "challengeId": reset_challenge,
                "code": reset_code,
                "newPassword": "other password 123",
            },
        )
    ).status_code == 400
    await deliver_pending(app.state.session_factory, app.state.settings, mailer, app.state.clock)
    assert "изменён" in mailer.messages[-1][1]


@pytest.mark.anyio
async def test_forgot_unknown_returns_error_without_challenge_or_mail(auth_env):
    app, client, now, mailer, code = auth_env
    response = await client.post(
        "/api/v1/auth/password/forgot", json={"email": "absent@example.org"}
    )
    assert response.status_code == 404
    assert response.json()["code"] == "EMAIL_NOT_FOUND"
    assert response.json()["message"] == "Аккаунт с таким email не найден"
    assert response.json()["details"]["fields"][0]["path"] == "email"
    assert response.json()["requestId"] == response.headers["X-Request-ID"]
    assert "challengeId" not in response.json()
    assert "ft_refresh" not in client.cookies
    async with app.state.session_factory() as db:
        assert (await db.scalars(select(EmailChallenge))).all() == []
        assert (await db.scalars(select(EmailOutbox))).all() == []
    assert mailer.messages == []
    # Existing verified accounts keep the normal recovery flow.
    await verified(client, code)
    now[0] += timedelta(seconds=61)
    response = await client.post(
        "/api/v1/auth/password/forgot", json={"email": "PERSON@example.org"}
    )
    assert response.status_code == 202
    assert response.json()["challengeId"]
    await code()
    assert len(mailer.messages) == 2


@pytest.mark.anyio
async def test_forgot_unverified_requires_confirmation_without_recovery_mail(auth_env):
    app, client, now, mailer, code = auth_env
    challenge = await register(client)
    await code()
    now[0] += timedelta(seconds=61)
    response = await client.post(
        "/api/v1/auth/password/forgot", json={"email": "person@example.org"}
    )
    assert response.status_code == 409
    assert response.json()["code"] == "EMAIL_NOT_VERIFIED"
    assert "challengeId" not in response.json()
    async with app.state.session_factory() as db:
        rows = (await db.scalars(select(EmailChallenge))).all()
        assert len(rows) == 1 and str(rows[0].id) == challenge
        assert rows[0].purpose == "verify_email" and rows[0].consumed_at is None
        assert (await db.scalar(select(User))).email_verified_at is None
    await deliver_pending(app.state.session_factory, app.state.settings, mailer, app.state.clock)
    assert len(mailer.messages) == 1


@pytest.mark.anyio
async def test_forgot_missing_account_requests_still_consume_rate_budget(auth_env):
    app, client, _, mailer, _ = auth_env
    app.state.settings.code_send_account_limit = 2
    for _ in range(2):
        response = await client.post(
            "/api/v1/auth/password/forgot", json={"email": "absent@example.org"}
        )
        assert response.status_code == 404
    response = await client.post(
        "/api/v1/auth/password/forgot", json={"email": "absent@example.org"}
    )
    assert response.status_code == 429 and response.json()["code"] == "RATE_LIMITED"
    assert mailer.messages == []


@pytest.mark.anyio
async def test_single_use_code_under_concurrency_and_aggregate_limit(auth_env):
    import asyncio

    app, client, now, _, code = auth_env
    challenge = await register(client)
    value = await code()
    responses = await asyncio.gather(
        *[
            client.post("/api/v1/auth/verify-email", json={"challengeId": challenge, "code": value})
            for _ in range(2)
        ]
    )
    assert sorted(r.status_code for r in responses) == [200, 400]
    app.state.settings.code_attempt_account_limit = 2
    now[0] += timedelta(seconds=61)
    response = await client.post(
        "/api/v1/auth/password/forgot", json={"email": "person@example.org"}
    )
    # The two prior attempts consumed the account budget, independent of challenge/purpose.
    response = await client.post(
        "/api/v1/auth/password/reset",
        json={
            "challengeId": response.json()["challengeId"],
            "code": "000000",
            "newPassword": "new password sufficiently long",
        },
    )
    assert response.status_code == 429
    assert response.json()["code"] == "RATE_LIMITED"


@pytest.mark.anyio
async def test_profile_validation_revision_isolation_and_current_role(auth_env):
    app, client, _, _, code = auth_env
    access = await verified(client, code)
    headers = {"Authorization": f"Bearer {access}"}
    first = await client.get("/api/v1/users/me", headers=headers)
    user_id = first.json()["id"]
    profile = {
        "displayName": "  Михаил  ",
        "timezone": "Europe/Moscow",
        "mealTimes": {"breakfast": "08:30", "lunch": "13:00", "dinner": "19:00", "snack": "16:00"},
    }
    assert (await client.put("/api/v1/users/me", headers=headers, json=profile)).status_code == 428
    match = {**headers, "If-Match": first.headers["etag"]}
    updated = await client.put("/api/v1/users/me", headers=match, json=profile)
    assert updated.status_code == 200, updated.text
    assert updated.json()["revision"] == 2 and updated.json()["displayName"] == "Михаил"
    assert (await client.put("/api/v1/users/me", headers=match, json=profile)).status_code == 412
    for invalid in (
        {"role": "ADMIN"},
        {"userId": "another"},
        {"timezone": "Mars/Olympus"},
        {"mealTimes": {**profile["mealTimes"], "lunch": "25:00"}},
    ):
        response = await client.put("/api/v1/users/me", headers=match, json={**profile, **invalid})
        assert response.status_code == 422
    # A second verified user cannot select the first via a public identifier.
    second_access = await verified(client, code, "second@example.org")
    second = await client.get(
        "/api/v1/users/me", headers={"Authorization": f"Bearer {second_access}"}
    )
    assert second.json()["id"] != user_id and second.json()["timezone"] == "UTC"
    assert (
        await client.get(
            f"/api/v1/users/{user_id}", headers={"Authorization": f"Bearer {second_access}"}
        )
    ).status_code == 404
    async with app.state.session_factory() as db, db.begin():
        from uuid import UUID

        user = await db.get(User, UUID(user_id))
        user.role = "ADMIN"
    # The access JWT still says USER. The API uses the trusted current database role.
    current = await client.get("/api/v1/users/me", headers=headers)
    assert current.json()["role"] == "ADMIN"


@pytest.mark.anyio
async def test_mail_retry_cleanup_and_refresh_history_retention(auth_env):
    from food_tracker.modules.auth.cleanup import cleanup
    from food_tracker.modules.auth.models import AuthSession, RefreshToken

    app, client, now, mailer, code = auth_env
    challenge = await register(client)

    class UnavailableMailer:
        async def send(self, *args):
            raise OSError("temporary provider failure")

    await deliver_pending(
        app.state.session_factory, app.state.settings, UnavailableMailer(), app.state.clock
    )
    async with app.state.session_factory() as db:
        row = await db.scalar(select(EmailOutbox))
        assert row.sent_at is None and row.attempts == 1
    now[0] += timedelta(seconds=11)
    value = await code()
    assert len(mailer.messages) == 1
    response = await client.post(
        "/api/v1/auth/verify-email", json={"challengeId": challenge, "code": value}
    )
    assert response.status_code == 200
    await client.post("/api/v1/auth/refresh")
    await cleanup(app.state.session_factory, now[0])
    async with app.state.session_factory() as db:
        assert len((await db.scalars(select(RefreshToken))).all()) == 2
    now[0] += timedelta(days=31)
    await cleanup(app.state.session_factory, now[0])
    async with app.state.session_factory() as db:
        assert (await db.scalars(select(AuthSession))).all() == []
        assert (await db.scalars(select(RefreshToken))).all() == []
        assert (await db.scalars(select(EmailChallenge))).all() == []
        assert (await db.scalar(select(User))).email_verified_at


@pytest.mark.anyio
async def test_signed_access_cannot_bypass_confirmation_and_absolute_session_expiry(auth_env):
    from uuid import uuid4

    from food_tracker.core.security import encode_token
    from food_tracker.modules.auth.models import AuthSession

    app, client, now, _, _ = auth_env
    await register(client)
    async with app.state.session_factory() as db, db.begin():
        user = await db.scalar(select(User))
        user_id = user.id
        session_id = uuid4()
        db.add(
            AuthSession(
                id=session_id,
                user_id=user.id,
                created_at=now[0],
                expires_at=now[0] + timedelta(days=30),
            )
        )
    token, _ = encode_token(
        app.state.settings,
        "access",
        user_id,
        session_id,
        now[0],
        now[0] + timedelta(minutes=15),
        role="ADMIN",
    )
    headers = {"Authorization": f"Bearer {token}"}
    assert (await client.get("/api/v1/users/me", headers=headers)).status_code == 401
    async with app.state.session_factory() as db, db.begin():
        user = await db.get(User, user_id)
        user.email_verified_at = now[0]
    response = await client.get("/api/v1/users/me", headers=headers)
    assert response.status_code == 200 and response.json()["role"] == "USER"
    async with app.state.session_factory() as db, db.begin():
        session = await db.get(AuthSession, session_id)
        session.expires_at = now[0] - timedelta(seconds=1)
    assert (await client.get("/api/v1/users/me", headers=headers)).status_code == 401


@pytest.mark.anyio
async def test_registration_resumes_unverified_account_after_initial_code_expired(auth_env):
    from uuid import UUID

    app, client, now, mailer, code = auth_env
    first = await register(client)
    old_code = await code()
    async with app.state.session_factory() as db:
        user = await db.scalar(select(User))
        original_id, original_hash = user.id, user.password_hash
    now[0] += timedelta(seconds=601)
    resumed = await register(client)
    assert resumed != first
    assert len(mailer.messages) == 1
    fresh_code = await code()
    assert len(mailer.messages) == 2
    async with app.state.session_factory() as db:
        users = (await db.scalars(select(User))).all()
        assert len(users) == 1
        assert users[0].id == original_id and users[0].password_hash == original_hash
        assert (await db.get(EmailChallenge, UUID(first))).consumed_at
    assert (
        await client.post(
            "/api/v1/auth/verify-email", json={"challengeId": first, "code": old_code}
        )
    ).status_code == 400
    response = await client.post(
        "/api/v1/auth/verify-email", json={"challengeId": resumed, "code": fresh_code}
    )
    assert response.status_code == 200
    assert response.json()["userId"] == str(original_id)
    assert (
        await client.post(
            "/api/v1/auth/login",
            json={"email": "person@example.org", "password": "a long password 123"},
        )
    ).status_code == 200


@pytest.mark.anyio
async def test_repeated_registration_preserves_unverified_password_and_refuses_verified_email(
    auth_env,
):
    from uuid import UUID

    app, client, now, mailer, code = auth_env
    first = await register(client)
    original_code = await code()
    async with app.state.session_factory() as db:
        user = await db.scalar(select(User))
        original_hash = user.password_hash
    now[0] += timedelta(seconds=61)
    response = await client.post(
        "/api/v1/auth/register",
        json={"email": "person@example.org", "password": "a different password 456"},
    )
    assert response.status_code == 202 and "accessToken" not in response.json()
    await deliver_pending(app.state.session_factory, app.state.settings, mailer, app.state.clock)
    assert len(mailer.messages) == 1
    async with app.state.session_factory() as db:
        assert (await db.get(EmailChallenge, UUID(first))).consumed_at is None
        assert (await db.scalar(select(User))).password_hash == original_hash
    assert (
        await client.post(
            "/api/v1/auth/verify-email", json={"challengeId": first, "code": original_code}
        )
    ).status_code == 200
    now[0] += timedelta(seconds=61)
    response = await client.post(
        "/api/v1/auth/register",
        json={"email": "person@example.org", "password": "a long password 123"},
    )
    assert response.status_code == 409
    assert response.json()["code"] == "EMAIL_ALREADY_REGISTERED"
    await deliver_pending(app.state.session_factory, app.state.settings, mailer, app.state.clock)
    assert len(mailer.messages) == 1


async def auth_data_snapshot(app):
    from food_tracker.modules.auth.models import AuthSession, RefreshToken

    async with app.state.session_factory() as db:
        snapshot = {}
        for model in (User, EmailChallenge, EmailOutbox, AuthSession, RefreshToken):
            table = model.__table__
            snapshot[table.name] = (
                await db.execute(select(table).order_by(*table.primary_key.columns))
            ).all()
        return snapshot


@pytest.mark.anyio
@pytest.mark.parametrize("email", ["person@example.org", "PERSON@EXAMPLE.ORG"])
@pytest.mark.parametrize("attempted_password", ["a long password 123", "a different password 456"])
async def test_confirmed_email_registration_is_rejected_without_changing_account(
    auth_env,
    email,
    attempted_password,
):
    app, client, _, mailer, code = auth_env
    access = await verified(client, code)
    original_refresh = client.cookies["ft_refresh"]
    before = await auth_data_snapshot(app)
    response = await client.post(
        "/api/v1/auth/register", json={"email": email, "password": attempted_password}
    )
    assert response.status_code == 409, response.text
    error = response.json()
    assert error["code"] == "EMAIL_ALREADY_REGISTERED"
    assert error["message"] == "Аккаунт с таким email уже зарегистрирован"
    assert error["details"]["fields"][0]["path"] == "email"
    assert error["requestId"] == response.headers["X-Request-ID"]
    assert response.headers["Cache-Control"] == "no-store"
    assert not {"accessToken", "refreshToken", "challengeId"}.intersection(error)
    assert "set-cookie" not in response.headers
    assert client.cookies["ft_refresh"] == original_refresh
    assert await auth_data_snapshot(app) == before
    await deliver_pending(app.state.session_factory, app.state.settings, mailer, app.state.clock)
    assert len(mailer.messages) == 1
    assert (
        await client.get("/api/v1/users/me", headers={"Authorization": f"Bearer {access}"})
    ).status_code == 200
    wrong = await client.post(
        "/api/v1/auth/login", json={"email": email, "password": "a definitely wrong password"}
    )
    assert wrong.status_code == 401 and wrong.json()["code"] == "INVALID_CREDENTIALS"
    normal_login = await client.post(
        "/api/v1/auth/login", json={"email": email, "password": "a long password 123"}
    )
    assert normal_login.status_code == 200
    assert normal_login.json()["status"] == "authenticated"
    assert "accessToken" in normal_login.json()
    assert len(mailer.messages) == 1
    async with app.state.session_factory() as db:
        assert len((await db.scalars(select(EmailChallenge))).all()) == 1
        assert len((await db.scalars(select(EmailOutbox))).all()) == 1


@pytest.mark.anyio
async def test_concurrent_confirmed_registrations_both_refuse_without_side_effects(auth_env):
    import asyncio

    app, client, _, mailer, code = auth_env
    await verified(client, code)
    before = await auth_data_snapshot(app)
    responses = await asyncio.gather(
        *[
            client.post(
                "/api/v1/auth/register",
                json={"email": email, "password": "a different password 456"},
            )
            for email in ("person@example.org", "PERSON@example.org")
        ]
    )
    assert all(response.status_code == 409 for response in responses)
    assert all(response.json()["code"] == "EMAIL_ALREADY_REGISTERED" for response in responses)
    assert await auth_data_snapshot(app) == before
    assert len(mailer.messages) == 1


@pytest.mark.anyio
async def test_confirmed_registration_errors_still_consume_rate_budget(auth_env):
    app, client, _, _, code = auth_env
    await verified(client, code)
    # Initial registration consumed one send budget item.
    app.state.settings.code_send_account_limit = 3
    before = await auth_data_snapshot(app)
    for _ in range(2):
        response = await client.post(
            "/api/v1/auth/register",
            json={"email": "PERSON@example.org", "password": "a different password 456"},
        )
        assert response.status_code == 409
    response = await client.post(
        "/api/v1/auth/register",
        json={"email": "person@example.org", "password": "a different password 456"},
    )
    assert response.status_code == 429 and response.json()["code"] == "RATE_LIMITED"
    assert int(response.headers["Retry-After"]) > 0
    assert await auth_data_snapshot(app) == before
