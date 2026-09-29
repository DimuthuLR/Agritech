"""
Security utilities: password hashing and JWT tokens.

Nothing else in the app should call bcrypt/argon2/jose directly.
Everything routes through this module. If we ever rotate algorithms,
this is the one file to change.
"""
from datetime import datetime, timedelta, timezone
from typing import Any

from jose import jwt, JWTError
from passlib.context import CryptContext

from app.core.config import settings


# --- Password hashing ---------------------------------------------------------
#
# Argon2 is the modern standard: memory-hard, resistant to GPU cracking.
# The `deprecated="auto"` line lets us migrate algorithms later without
# invalidating existing password hashes.
#
pwd_context = CryptContext(
    schemes=["argon2"],
    deprecated="auto",
    argon2__time_cost=2,
    argon2__memory_cost=65536,
    argon2__parallelism=2,
)


def hash_password(plain: str) -> str:
    """Hash a plaintext password. Store the result in the DB."""
    return pwd_context.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    """
    Check a plaintext password against a stored hash.
    Returns True on match, False otherwise. Never raises on bad input —
    we don't want an attacker to distinguish "wrong format" from "wrong password".
    """
    try:
        return pwd_context.verify(plain, hashed)
    except Exception:
        return False


# --- JWT tokens ---------------------------------------------------------------


class TokenError(Exception):
    """Raised when a token is missing, malformed, expired, or tampered with."""


def create_access_token(
    subject: str,
    extra_claims: dict[str, Any] | None = None,
    ttl_minutes: int | None = None,
) -> str:
    """
    Create a signed JWT access token.

    subject: the user's UUID (as a string). Goes into the standard `sub` claim.
    extra_claims: anything else to embed — role, tenant_id, etc.
    ttl_minutes: token lifetime. Defaults to settings.jwt_access_ttl_min.
    """
    now = datetime.now(timezone.utc)
    ttl = ttl_minutes if ttl_minutes is not None else settings.jwt_access_ttl_min

    payload: dict[str, Any] = {
        "sub": subject,
        "iat": now,
        "exp": now + timedelta(minutes=ttl),
        "typ": "access",
    }
    if extra_claims:
        payload.update(extra_claims)

    return jwt.encode(payload, settings.jwt_secret, algorithm="HS256")


def decode_token(token: str) -> dict[str, Any]:
    """
    Decode and validate a JWT. Raises TokenError on any problem:
    bad signature, expired, wrong algorithm, missing required claim.
    """
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=["HS256"],
            options={"require": ["exp", "iat", "sub", "typ"]},
        )
    except JWTError as e:
        raise TokenError(str(e)) from e

    if payload.get("typ") != "access":
        raise TokenError(f"Unexpected token type: {payload.get('typ')!r}")

    return payload