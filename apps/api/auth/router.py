import logging

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import func
from sqlalchemy.orm import Session

import models
import schemas
from core.deps import get_current_user
from core.config import get_settings
from core.security import (
    RESET_TOKEN_MINUTES, create_access_token, create_reset_token, hash_password, reset_token_user_id, verify_password,
)
from database import get_db
from digest import smtp_sender

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/auth", tags=["auth"])

WINDOW_SECONDS = 15 * 60
EMAIL_LIMIT = 10  # attempts per account per window: slows password guessing on one account
IP_LIMIT = 30  # attempts per client address per window: slows spraying many accounts


def _redis():
    from workers.jobs import get_redis_connection  # lazy, as in providers/guard.py
    return get_redis_connection()


def _throttle(request: Request, email: str | None = None) -> None:
    """429 once this address or account has used up its attempts for the window.

    ponytail: fails OPEN when Redis is down, like providers/guard.py: an outage must not lock
    every user out. The address is request.client.host, so behind a proxy uvicorn needs
    --proxy-headers or every user shares one bucket.
    """
    scope = request.url.path.rsplit("/", 1)[-1]
    keys = [f"authrl:{scope}:ip:{request.client.host if request.client else '?'}"]
    limits = [IP_LIMIT]
    if email:
        keys.append(f"authrl:{scope}:email:{email}")
        limits.append(EMAIL_LIMIT)
    try:
        r = _redis()
        counts = []
        for key in keys:
            r.set(key, 0, ex=WINDOW_SECONDS, nx=True)  # TTL set once; INCR keeps it
            counts.append(r.incr(key))
    except Exception as exc:
        logger.warning("auth rate limit skipped: redis unavailable (%s)", type(exc).__name__)
        return
    if any(n > limit for n, limit in zip(counts, limits)):
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "Too many attempts. Try again in a few minutes.",
                            headers={"Retry-After": str(WINDOW_SECONDS)})


def _normalise(email: str) -> str:
    return email.strip().lower()


def _user_by_email(db: Session, email: str):
    # lower() on the column too: rows written before emails were normalised may be mixed-case.
    return db.query(models.User).filter(func.lower(models.User.email) == _normalise(email)).first()


@router.post("/signup", response_model=schemas.UserOut, status_code=status.HTTP_201_CREATED)
def signup(payload: schemas.UserCreate, request: Request, db: Session = Depends(get_db)):
    _throttle(request)
    existing = _user_by_email(db, payload.email)
    if existing:
        raise HTTPException(status.HTTP_409_CONFLICT, "Email already registered")

    user = models.User(email=_normalise(payload.email), password_hash=hash_password(payload.password))
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@router.post("/login", response_model=schemas.Token)
def login(request: Request, form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    _throttle(request, _normalise(form_data.username))
    user = _user_by_email(db, form_data.username)
    if not user or not user.password_hash or not verify_password(form_data.password, user.password_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Incorrect email or password")

    token = create_access_token(subject=user.id)
    return schemas.Token(access_token=token)


def send_reset_email(to: str, link: str) -> None:
    settings = get_settings()
    body = (f"Someone asked to reset the ApplyScout password for {to}.\n\n"
            f"Set a new one here (the link works once, for {RESET_TOKEN_MINUTES} minutes):\n{link}\n\n"
            "If it wasn't you, ignore this email; your password hasn't changed.")
    if settings.smtp_host:
        smtp_sender(to, "Reset your ApplyScout password", body)
    else:
        # Local dev without SMTP (same rule as the digest): the link goes to the server log only.
        logger.warning("SMTP_HOST not set; password reset link for %s: %s", to, link)


@router.post("/forgot-password", status_code=status.HTTP_202_ACCEPTED)
def forgot_password(payload: schemas.ForgotPasswordIn, request: Request, db: Session = Depends(get_db)):
    """Same answer whether or not the email has an account: no enumeration."""
    _throttle(request, _normalise(payload.email))
    user = _user_by_email(db, payload.email)
    if user and user.password_hash and not user.deleted_at:
        token = create_reset_token(user.id, user.password_hash)
        send_reset_email(user.email, f"{get_settings().web_base_url}/reset-password?token={token}")
    return {"ok": True}


@router.post("/reset-password")
def reset_password(payload: schemas.ResetPasswordIn, request: Request, db: Session = Depends(get_db)):
    _throttle(request)
    def current_hash(user_id):
        user = db.get(models.User, user_id) if user_id else None
        return user.password_hash if user and not user.deleted_at else None

    try:
        user_id = reset_token_user_id(payload.token, current_hash)
    except ValueError:
        raise HTTPException(status.HTTP_400_BAD_REQUEST,
                            "This reset link is invalid or has expired. Ask for a new one.")
    user = db.get(models.User, user_id)
    user.password_hash = hash_password(payload.password)
    db.commit()
    return {"ok": True}


@router.get("/me", response_model=schemas.UserOut)
def me(current_user: models.User = Depends(get_current_user)):
    return current_user
