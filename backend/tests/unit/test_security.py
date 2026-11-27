from datetime import UTC, datetime, timedelta
from uuid import uuid4

import jwt
import pytest

from food_tracker.core.config import Settings
from food_tracker.core.errors import DomainError
from food_tracker.core.security import create_csrf, decode_token, encode_token, valid_csrf


def settings():
    return Settings(
        _env_file=None,
        access_jwt_secret="a" * 32,
        refresh_jwt_secret="r" * 32,
        csrf_secret="s" * 32,
    )


@pytest.mark.parametrize(
    "change",
    [
        {"aud": "wrong"},
        {"iss": "wrong"},
        {"token_type": "refresh"},
        {"exp": 0},
        {"sid": []},
        {"role": "OWNER"},
        {"iat": 9999999999},
        {"jti": None},
    ],
)
def test_jwt_checks_claims_purpose_and_identifiers(change):
    now = datetime(2026, 11, 27, tzinfo=UTC)
    config = settings()
    token, _ = encode_token(
        config, "access", uuid4(), uuid4(), now, now + timedelta(minutes=15), role="USER"
    )
    claims = jwt.decode(token, options={"verify_signature": False})
    altered = jwt.encode({**claims, **change}, "a" * 32, algorithm="HS256")
    with pytest.raises(DomainError) as error:
        decode_token(config, altered, "access", now)
    assert error.value.status == 401


def test_refresh_is_not_access_and_csrf_expires():
    now = datetime(2026, 11, 27, tzinfo=UTC)
    config = settings()
    token, _ = encode_token(config, "refresh", uuid4(), uuid4(), now, now + timedelta(days=30))
    with pytest.raises(DomainError):
        decode_token(config, token, "access", now)
    csrf = create_csrf(config, now)
    assert valid_csrf(config, csrf, now)
    assert not valid_csrf(config, csrf + "x", now)
    assert not valid_csrf(config, csrf, now + timedelta(days=1))
