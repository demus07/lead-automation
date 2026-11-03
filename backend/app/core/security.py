"""Password hashing, session tokens and CSRF tokens.

Sessions: a signed JWT stored in an httpOnly, SameSite=Lax cookie. State-changing requests must also
send the ``X-CSRF-Token`` header matching the (non-httpOnly) ``csrf_token`` cookie (double-submit) —
the CSRF token is bound to the session via an HMAC so it cannot be forged by a sibling subdomain.
API clients may alternatively use ``Authorization: Bearer <token>`` (no cookie → no CSRF exposure).
"""
from __future__ import annotations

import hashlib
import hmac
import secrets
import uuid
from datetime import UTC, datetime, timedelta

import bcrypt
import jwt

from app.core.config import get_settings

ALGORITHM = "HS256"
SESSION_COOKIE = "age_session"
CSRF_COOKIE = "csrf_token"
CSRF_HEADER = "X-CSRF-Token"


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode()[:72], bcrypt.gensalt(rounds=12)).decode()


def verify_password(password: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode()[:72], hashed.encode())
    except ValueError:
        return False


def validate_password_strength(password: str) -> None:
    if len(password) < 10:
        raise ValueError("Password must be at least 10 characters")
    classes = sum(
        [
            any(c.islower() for c in password),
            any(c.isupper() for c in password),
            any(c.isdigit() for c in password),
            any(not c.isalnum() for c in password),
        ]
    )
    if classes < 3:
        raise ValueError("Password must contain at least three of: lowercase, uppercase, digits, symbols")


def create_session_token(user_id: uuid.UUID, token_version: int) -> tuple[str, str]:
    """Returns (jwt, session_id)."""
    s = get_settings()
    sid = secrets.token_urlsafe(16)
    now = datetime.now(UTC)
    payload = {
        "sub": str(user_id),
        "sid": sid,
        "ver": token_version,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=s.access_token_minutes)).timestamp()),
    }
    return jwt.encode(payload, s.secret_key, algorithm=ALGORITHM), sid


def decode_session_token(token: str) -> dict:
    return jwt.decode(token, get_settings().secret_key, algorithms=[ALGORITHM])


def csrf_for_session(sid: str) -> str:
    return hmac.new(get_settings().secret_key.encode(), f"csrf:{sid}".encode(), hashlib.sha256).hexdigest()


def sign_state(data: str) -> str:
    """Signed opaque state for OAuth flows."""
    sig = hmac.new(get_settings().secret_key.encode(), data.encode(), hashlib.sha256).hexdigest()[:32]
    return f"{data}.{sig}"


def verify_state(state: str) -> str | None:
    if "." not in state:
        return None
    data, sig = state.rsplit(".", 1)
    expected = hmac.new(get_settings().secret_key.encode(), data.encode(), hashlib.sha256).hexdigest()[:32]
    return data if hmac.compare_digest(sig, expected) else None
