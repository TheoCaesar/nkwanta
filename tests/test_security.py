"""Password hashing and tokens.

Written now rather than at B03 because the passlib/bcrypt incompatibility that
prompted this module was only found by running it.
"""

from __future__ import annotations

import pytest

from app.security import (
    PasswordTooLongError,
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)

# At least 32 bytes. HS256 keys shorter than the hash output are weaker than the
# algorithm they protect, and PyJWT warns about it — RFC 7518 section 3.2.
SECRET = "test-secret-not-used-in-production-0123456789abcdef"


def test_hash_then_verify() -> None:
    hashed = hash_password("kofi-2026")
    assert hashed != "kofi-2026"
    assert verify_password("kofi-2026", hashed)


def test_wrong_password_rejected() -> None:
    assert not verify_password("wrong", hash_password("kofi-2026"))


def test_same_password_hashes_differently() -> None:
    """Salted, so two hashes of one password must not match."""
    assert hash_password("same") != hash_password("same")


def test_password_over_72_bytes_is_rejected_not_truncated() -> None:
    """bcrypt truncates silently. A truncated password that still authenticates
    is a security bug, so it is refused instead."""
    with pytest.raises(PasswordTooLongError):
        hash_password("a" * 73)


def test_long_password_never_verifies() -> None:
    assert not verify_password("a" * 100, hash_password("a" * 72))


def test_malformed_hash_returns_false_rather_than_raising() -> None:
    assert not verify_password("anything", "not-a-real-bcrypt-hash")


def test_token_round_trip() -> None:
    token = create_access_token("user-123", "officer", SECRET)
    claims = decode_access_token(token, SECRET)
    assert claims["sub"] == "user-123"
    assert claims["role"] == "officer"


def test_token_signed_with_another_secret_is_rejected() -> None:
    import jwt

    token = create_access_token("user-123", "officer", SECRET)
    with pytest.raises(jwt.InvalidSignatureError):
        decode_access_token(token, "a-different-secret-also-at-least-32-bytes-long")


def test_expired_token_is_rejected() -> None:
    import jwt

    token = create_access_token("user-123", "commuter", SECRET, expires_minutes=-1)
    with pytest.raises(jwt.ExpiredSignatureError):
        decode_access_token(token, SECRET)
