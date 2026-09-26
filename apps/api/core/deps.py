from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import text
from sqlalchemy.orm import Session

import models
from core.security import decode_access_token
from database import get_db

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")


def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> models.User:
    try:
        payload = decode_access_token(token)
    except ValueError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired token")

    user = db.query(models.User).filter(models.User.id == payload.get("sub")).first()
    if not user:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "User not found")

    # Postgres RLS backstop (migration 0010): every subsequent query on this
    # request's connection now carries the authenticated user's id, so a
    # missed application-level tenancy filter still can't leak another
    # user's row — the database itself won't return it. SET LOCAL is
    # transaction-scoped and resets automatically; guarded to Postgres only
    # since SQLite (the unit-test engine) has no such syntax at all and
    # would raise on it.
    if db.get_bind().dialect.name == "postgresql":
        db.execute(text("SET LOCAL app.current_user_id = :uid"), {"uid": user.id})

    return user


def resolve_profile_ownership(db: Session, current_user: models.User, profile_id: str) -> models.Profile:
    """The single tenancy enforcement point (ARCHITECTURE.md §5). Plain function,
    not a FastAPI dependency — safe to call directly when profile_id comes from a
    request body rather than a path/query param, where Depends() resolution
    doesn't apply.
    """
    profile = (
        db.query(models.Profile)
        .filter(models.Profile.id == profile_id, models.Profile.user_id == current_user.id)
        .first()
    )
    if not profile:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Profile not found")
    return profile


def get_owned_profile(
    profile_id: str,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> models.Profile:
    """FastAPI-dependency form of resolve_profile_ownership — for routes where
    profile_id is a path or query param (FastAPI resolves it automatically).
    """
    return resolve_profile_ownership(db, current_user, profile_id)
