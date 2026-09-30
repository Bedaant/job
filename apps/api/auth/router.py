import logging

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
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


@router.post("/signup", response_model=schemas.UserOut, status_code=status.HTTP_201_CREATED)
def signup(payload: schemas.UserCreate, db: Session = Depends(get_db)):
    existing = db.query(models.User).filter(models.User.email == payload.email).first()
    if existing:
        raise HTTPException(status.HTTP_409_CONFLICT, "Email already registered")

    user = models.User(email=payload.email, password_hash=hash_password(payload.password))
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@router.post("/login", response_model=schemas.Token)
def login(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.email == form_data.username).first()
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
def forgot_password(payload: schemas.ForgotPasswordIn, db: Session = Depends(get_db)):
    """Same answer whether or not the email has an account: no enumeration."""
    user = db.query(models.User).filter(models.User.email == payload.email).first()
    if user and user.password_hash and not user.deleted_at:
        token = create_reset_token(user.id, user.password_hash)
        send_reset_email(user.email, f"{get_settings().web_base_url}/reset-password?token={token}")
    return {"ok": True}


@router.post("/reset-password")
def reset_password(payload: schemas.ResetPasswordIn, db: Session = Depends(get_db)):
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
