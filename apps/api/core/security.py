import hashlib
from datetime import datetime, timedelta, timezone

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from jose import JWTError, jwt

from core.config import get_settings

_hasher = PasswordHasher()


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password: str, hashed: str) -> bool:
    try:
        return _hasher.verify(hashed, password)
    except VerifyMismatchError:
        return False


def create_access_token(subject: str) -> str:
    settings = get_settings()
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=settings.jwt_expires_minutes)
    payload = {"sub": subject, "exp": expires_at}
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


RESET_TOKEN_MINUTES = 60


def _password_fingerprint(password_hash: str) -> str:
    # Argon2 salts every hash, so any password change (the reset itself included) kills the token.
    return hashlib.sha256(password_hash.encode()).hexdigest()[:16]


def create_reset_token(user_id: str, password_hash: str) -> str:
    settings = get_settings()
    payload = {
        "sub": user_id, "purpose": "password_reset", "pwf": _password_fingerprint(password_hash),
        "exp": datetime.now(timezone.utc) + timedelta(minutes=RESET_TOKEN_MINUTES),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def reset_token_user_id(token: str, current_password_hash_for) -> str:
    """The user id a still-valid reset token names. `current_password_hash_for(user_id)`
    returns that user's password hash now, or None. Raises ValueError otherwise."""
    payload = decode_access_token(token)
    if payload.get("purpose") != "password_reset":
        raise ValueError("not a reset token")  # a login token must not reset a password
    current = current_password_hash_for(payload.get("sub"))
    if not current or payload.get("pwf") != _password_fingerprint(current):
        raise ValueError("used or superseded")
    return payload["sub"]


def decode_access_token(token: str) -> dict:
    settings = get_settings()
    try:
        return jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    except JWTError as exc:
        raise ValueError("invalid or expired token") from exc
