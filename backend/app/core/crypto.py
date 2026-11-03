"""Symmetric encryption for integration credentials and secret settings (Fernet / AES-128-CBC + HMAC)."""
from __future__ import annotations

import base64
import hashlib
from functools import lru_cache

from cryptography.fernet import Fernet, InvalidToken

from app.core.config import get_settings


@lru_cache
def _fernet() -> Fernet:
    s = get_settings()
    key = s.encryption_key
    if not key:
        # Development fallback: derive a stable key from SECRET_KEY. Production refuses to start
        # without ENCRYPTION_KEY (see config.get_settings).
        key = base64.urlsafe_b64encode(hashlib.sha256(("enc:" + s.secret_key).encode()).digest()).decode()
    return Fernet(key.encode() if isinstance(key, str) else key)


def encrypt(plaintext: str) -> str:
    return _fernet().encrypt(plaintext.encode()).decode()


def decrypt(token: str) -> str:
    try:
        return _fernet().decrypt(token.encode()).decode()
    except InvalidToken as exc:  # pragma: no cover - indicates key rotation/misconfig
        raise ValueError("Unable to decrypt secret: ENCRYPTION_KEY changed or data corrupted") from exc


def mask(secret: str | None) -> str | None:
    if not secret:
        return None
    return "•" * 8 + secret[-4:] if len(secret) > 8 else "•" * 8
