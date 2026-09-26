"""Password hashing, JWT access tokens bound to server-side sessions, secret encryption."""

from __future__ import annotations

import base64
import hashlib
import secrets
from datetime import timedelta

import bcrypt
import jwt
from cryptography.fernet import Fernet, InvalidToken

from app.config import get_settings
from app.models import utcnow

JWT_ALG = "HS256"
BCRYPT_ROUNDS = 12
MIN_PASSWORD_LENGTH = 12


def hash_password(password: str, rounds: int | None = None) -> str:
    # bcrypt truncates at 72 bytes; pre-hash so long passphrases keep full entropy.
    digest = base64.b64encode(hashlib.sha256(password.encode()).digest())
    return bcrypt.hashpw(digest, bcrypt.gensalt(rounds or BCRYPT_ROUNDS)).decode()


def verify_password(password: str, hashed: str) -> bool:
    digest = base64.b64encode(hashlib.sha256(password.encode()).digest())
    try:
        return bcrypt.checkpw(digest, hashed.encode())
    except ValueError:
        return False


def validate_password_policy(password: str) -> None:
    if len(password) < MIN_PASSWORD_LENGTH:
        raise ValueError(f"password must be at least {MIN_PASSWORD_LENGTH} characters")
    classes = sum(bool(any(f(c) for c in password)) for f in (str.islower, str.isupper, str.isdigit, lambda c: not c.isalnum()))
    if classes < 3:
        raise ValueError("password must contain at least three of: lowercase, uppercase, digit, symbol")


def create_access_token(user_id: str, role: str, session_id: str) -> tuple[str, int]:
    s = get_settings()
    now = utcnow()
    exp = now + timedelta(minutes=s.access_token_minutes)
    payload = {"sub": user_id, "role": role, "sid": session_id, "iat": int(now.timestamp()), "exp": int(exp.timestamp()),
               "jti": secrets.token_hex(8), "iss": "tessera"}
    return jwt.encode(payload, s.secret_key, algorithm=JWT_ALG), s.access_token_minutes * 60


def decode_access_token(token: str) -> dict:
    s = get_settings()
    return jwt.decode(token, s.secret_key, algorithms=[JWT_ALG], issuer="tessera", options={"require": ["exp", "sub", "sid"]})


def _fernet() -> Fernet:
    return Fernet(get_settings().encryption_key.encode())


def encrypt_secret(plaintext: str) -> str:
    return _fernet().encrypt(plaintext.encode()).decode()


def decrypt_secret(token: str) -> str:
    try:
        return _fernet().decrypt(token.encode()).decode()
    except InvalidToken as exc:
        raise ValueError("secret cannot be decrypted with the configured key") from exc
