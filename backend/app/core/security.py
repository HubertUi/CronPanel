"""Password hashing and JWT token handling.

Passwords are hashed with bcrypt (salted, slow by design). Tokens are signed
JWTs using the algorithm configured in settings. No secrets are ever logged.
"""

import uuid
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt

from app.core.config import settings

ACCESS_TOKEN_TYPE = "access"
TOKEN_TYPE_CLAIM = "type"


def hash_password(password: str) -> str:
    password_bytes = password.encode("utf-8")
    salt = bcrypt.gensalt(rounds=settings.BCRYPT_ROUNDS)
    return bcrypt.hashpw(password_bytes, salt).decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    try:
        return bcrypt.checkpw(
            plain_password.encode("utf-8"),
            hashed_password.encode("utf-8"),
        )
    except ValueError:
        # Malformed hash stored in database; treat as failed verification.
        return False


def create_access_token(
    subject: str,
    extra_claims: dict | None = None,
    expires_delta: timedelta | None = None,
) -> tuple[str, int]:
    """Return (token, expires_in_seconds)."""
    if expires_delta is None:
        expires_delta = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)

    issued_at = datetime.now(timezone.utc)
    expires_at = issued_at + expires_delta

    payload = {
        "sub": subject,
        "iat": issued_at,
        "exp": expires_at,
        "jti": uuid.uuid4().hex,
        TOKEN_TYPE_CLAIM: ACCESS_TOKEN_TYPE,
    }
    if extra_claims:
        payload.update(extra_claims)

    token = jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    return token, int(expires_delta.total_seconds())


def decode_token(token: str) -> dict:
    """Decode and validate a JWT.

    Raises jwt.PyJWTError subclasses on invalid signature, expired token,
    malformed token, etc. Callers must translate these into HTTP errors.
    """
    payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
    if payload.get(TOKEN_TYPE_CLAIM) != ACCESS_TOKEN_TYPE:
        raise jwt.InvalidTokenError("Invalid token type.")
    return payload
