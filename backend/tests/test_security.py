import jwt
import pytest

from app.core.security import (
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)


def test_hash_and_verify_password():
    hashed = hash_password("s3cret-pass")

    assert hashed != "s3cret-pass"
    assert verify_password("s3cret-pass", hashed) is True
    assert verify_password("wrong-pass", hashed) is False


def test_create_and_decode_token():
    token = create_access_token("42")
    payload = decode_access_token(token)

    assert payload["sub"] == "42"
    assert "exp" in payload
    assert "iat" in payload


def test_decode_invalid_token_raises():
    with pytest.raises(jwt.InvalidTokenError):
        decode_access_token("not-a-valid-token")
