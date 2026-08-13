"""Password hashing and token issuing.

bcrypt is used directly rather than through passlib. passlib 1.7.4 reads
``bcrypt.__about__.__version__``, an attribute bcrypt removed in 4.1, so the pairing
fails on every call. Verified against bcrypt 5.0.0 on 12 August 2026.

bcrypt silently truncates anything past 72 bytes, so passwords are rejected above
that length rather than accepted and quietly shortened — a truncated password that
still authenticates is worse than an error.
"""

from __future__ import annotations

import datetime as dt
from typing import Any

import bcrypt
import jwt

_MAX_PASSWORD_BYTES = 72
_ALGORITHM = "HS256"


class PasswordTooLongError(ValueError):
    """Raised rather than letting bcrypt truncate silently."""


def hash_password(plain: str) -> str:
    encoded = plain.encode("utf-8")
    if len(encoded) > _MAX_PASSWORD_BYTES:
        raise PasswordTooLongError(
            f"password must be at most {_MAX_PASSWORD_BYTES} bytes, got {len(encoded)}"
        )
    return bcrypt.hashpw(encoded, bcrypt.gensalt(rounds=12)).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    encoded = plain.encode("utf-8")
    if len(encoded) > _MAX_PASSWORD_BYTES:
        return False
    try:
        return bcrypt.checkpw(encoded, hashed.encode("utf-8"))
    except ValueError:
        # Malformed hash in the database. Treat as a failed login, not a crash.
        return False


def create_access_token(
    subject: str, role: str, secret: str, expires_minutes: int = 720
) -> str:
    now = dt.datetime.now(dt.timezone.utc)
    payload: dict[str, Any] = {
        "sub": subject,
        "role": role,
        "iat": now,
        "exp": now + dt.timedelta(minutes=expires_minutes),
    }
    return jwt.encode(payload, secret, algorithm=_ALGORITHM)


def decode_access_token(token: str, secret: str) -> dict[str, Any]:
    return jwt.decode(token, secret, algorithms=[_ALGORITHM])
