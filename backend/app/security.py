"""
PRAHARI · passwords, tokens, sessions
════════════════════════════════════════════════════════════════════════════
Password hashing is scrypt from the standard library — no native build step, no
extra wheel to fail on a Render free tier, and the parameters below are the
OWASP-recommended interactive set (N=2^15, r=8, p=1).

A token is a JWT carrying a jti. The jti is a row in `sessions`. That is what
makes logout real: the signature stays valid, the session does not.
"""
from __future__ import annotations

import base64
import datetime as dt
import hashlib
import hmac
import secrets
import uuid
from typing import Any

import jwt

from .clock import real_now
from .config import get_settings

_SCRYPT_N, _SCRYPT_R, _SCRYPT_P, _DKLEN = 2 ** 15, 8, 1, 32


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    dk = hashlib.scrypt(password.encode(), salt=salt, n=_SCRYPT_N, r=_SCRYPT_R,
                        p=_SCRYPT_P, dklen=_DKLEN, maxmem=64 * 1024 * 1024)
    return f"scrypt${_SCRYPT_N}${_SCRYPT_R}${_SCRYPT_P}${base64.b64encode(salt).decode()}${base64.b64encode(dk).decode()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        scheme, n, r, p, salt_b64, dk_b64 = stored.split("$")
        if scheme != "scrypt":
            return False
        dk = hashlib.scrypt(password.encode(), salt=base64.b64decode(salt_b64),
                            n=int(n), r=int(r), p=int(p),
                            dklen=len(base64.b64decode(dk_b64)),
                            maxmem=64 * 1024 * 1024)
        return hmac.compare_digest(dk, base64.b64decode(dk_b64))
    except Exception:
        return False


def password_problems(password: str) -> list[str]:
    s = get_settings()
    out = []
    if len(password) < s.password_min_length:
        out.append(f"at least {s.password_min_length} characters")
    if password.isdigit():
        out.append("not only digits")
    if password.lower() in ("password", "12345678", "prahari1", "qwertyui"):
        out.append("not a common password")
    return out


def issue_token(user_id: str, role: str) -> tuple[str, str, dt.datetime]:
    """Returns (token, jti, expires_at). The caller records the session row."""
    s = get_settings()
    jti = uuid.uuid4().hex
    issued = real_now()
    expires = issued + dt.timedelta(hours=s.access_token_hours)
    payload = {"sub": user_id, "role": role, "jti": jti,
               "iat": int(issued.timestamp()), "exp": int(expires.timestamp()),
               "iss": "prahari"}
    token = jwt.encode(payload, s.jwt_secret, algorithm=s.jwt_algorithm)
    return token, jti, expires


def decode_token(token: str) -> dict[str, Any] | None:
    s = get_settings()
    try:
        return jwt.decode(token, s.jwt_secret, algorithms=[s.jwt_algorithm], issuer="prahari")
    except jwt.PyJWTError:
        return None


def reset_token() -> tuple[str, str]:
    """(plaintext, sha256). Only the hash is stored, so a database leak does not
    hand anyone a live reset link."""
    raw = secrets.token_urlsafe(32)
    return raw, hashlib.sha256(raw.encode()).hexdigest()


def hash_token(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


def new_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:12].upper()}"
