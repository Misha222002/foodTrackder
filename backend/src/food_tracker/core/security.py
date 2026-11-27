import hashlib
import hmac
import secrets
from datetime import datetime
from typing import Any, Literal
from uuid import UUID, uuid4

import anyio
import jwt
from argon2 import PasswordHasher, Type
from argon2.exceptions import InvalidHashError, VerificationError

from food_tracker.core.config import Settings
from food_tracker.core.errors import DomainError

PASSWORD_HASHER = PasswordHasher(
    time_cost=3, memory_cost=65536, parallelism=4, hash_len=32, salt_len=16, type=Type.ID
)


DUMMY_PASSWORD_HASH = PASSWORD_HASHER.hash("a fixed dummy password for timing")


def secret(settings: Settings, name: str) -> str:
    value = getattr(settings, name)
    if value is None:
        raise DomainError(503, "AUTH_NOT_CONFIGURED", "Авторизация ещё не настроена на сервере")
    return value.get_secret_value()


async def hash_password(password: str) -> str:
    return await anyio.to_thread.run_sync(PASSWORD_HASHER.hash, password)


async def verify_password(password_hash: str, password: str) -> bool:
    def verify():
        try:
            return PASSWORD_HASHER.verify(password_hash, password)
        except (VerificationError, InvalidHashError):
            return False

    return await anyio.to_thread.run_sync(verify)


def digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def keyed_digest(key: str, value: str) -> str:
    return hmac.new(key.encode(), value.encode(), hashlib.sha256).hexdigest()


def code_digest(
    settings: Settings, challenge_id: UUID, user_id: UUID | None, purpose: str, code: str
):
    return keyed_digest(
        secret(settings, "code_hmac_secret"), f"{challenge_id}:{user_id}:{purpose}:{code}"
    )


def encode_token(
    settings: Settings,
    kind: Literal["access", "refresh"],
    user_id: UUID,
    session_id: UUID,
    now: datetime,
    expires_at: datetime,
    *,
    jti: UUID | None = None,
    role: str | None = None,
) -> tuple[str, UUID]:
    token_id = jti or uuid4()
    payload: dict[str, Any] = {
        "sub": str(user_id),
        "sid": str(session_id),
        "jti": str(token_id),
        "iat": int(now.timestamp()),
        "exp": int(expires_at.timestamp()),
        "iss": settings.jwt_issuer,
        "aud": settings.access_audience if kind == "access" else settings.refresh_audience,
        "token_type": kind,
    }
    if kind == "access":
        payload["role"] = role
    token = jwt.encode(payload, secret(settings, f"{kind}_jwt_secret"), algorithm="HS256")
    return token, token_id


def decode_token(settings: Settings, token: str, kind: Literal["access", "refresh"], now: datetime):
    try:
        payload = jwt.decode(
            token,
            secret(settings, f"{kind}_jwt_secret"),
            algorithms=["HS256"],
            issuer=settings.jwt_issuer,
            audience=settings.access_audience if kind == "access" else settings.refresh_audience,
            options={
                "require": ["sub", "sid", "jti", "iat", "exp", "iss", "aud", "token_type"],
                "verify_exp": False,
                "verify_iat": False,
                "strict_aud": True,
            },
        )
        if payload["token_type"] != kind:
            raise ValueError("Wrong token purpose")
        for field in ("sub", "sid", "jti"):
            if not isinstance(payload[field], str):
                raise ValueError("Invalid identifier")
            UUID(payload[field])
        if type(payload["iat"]) is not int or type(payload["exp"]) is not int:
            raise ValueError("Invalid timestamps")
        if payload["iat"] > now.timestamp() or payload["exp"] <= now.timestamp():
            raise ValueError("Inactive token")
        if payload["exp"] <= payload["iat"]:
            raise ValueError("Invalid lifetime")
        if kind == "access" and payload.get("role") not in ("USER", "ADMIN"):
            raise ValueError("Invalid role")
        return payload
    except (jwt.PyJWTError, ValueError, TypeError, KeyError) as error:
        raise DomainError(401, "SESSION_EXPIRED", "Войдите в аккаунт заново") from error


def create_csrf(settings: Settings, now: datetime) -> str:
    body = f"{secrets.token_urlsafe(32)}.{int(now.timestamp())}"
    return f"{body}.{keyed_digest(secret(settings, 'csrf_secret'), body)}"


def valid_csrf(settings: Settings, token: str, now: datetime) -> bool:
    try:
        nonce, timestamp, signature = token.split(".")
        age = now.timestamp() - int(timestamp)
        return (
            len(nonce) >= 32
            and 0 <= age < settings.csrf_ttl_seconds
            and hmac.compare_digest(
                signature, keyed_digest(secret(settings, "csrf_secret"), f"{nonce}.{timestamp}")
            )
        )
    except (ValueError, TypeError):
        return False
