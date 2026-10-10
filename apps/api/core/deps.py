import os

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import event, text
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

    # Postgres RLS backstop (migration 0010): every query on this request's
    # session carries the authenticated user's id, so a missed
    # application-level tenancy filter still can't leak another user's row.
    # Stored on the session and re-applied by _reapply_tenant at the start of
    # EVERY transaction — the setting is transaction-local, so without that a
    # read after db.commit() ran with no tenant and RLS hid the row just written.
    db.info["current_user_id"] = user.id
    _reapply_tenant(db, None, db.connection())

    return user


_SET_TENANT = text("SELECT set_config('app.current_user_id', :uid, true)")


@event.listens_for(Session, "after_begin")
def _reapply_tenant(session, transaction, connection):
    """Transaction-local (is_local=true, i.e. SET LOCAL) so a pooled connection
    never carries one user's id into another request. Postgres only: SQLite, the
    unit-test engine, has no set_config."""
    uid = session.info.get("current_user_id")
    if uid and connection.dialect.name == "postgresql":
        connection.execute(_SET_TENANT, {"uid": uid})


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


def require_owner(user: models.User = Depends(get_current_user)) -> models.User:
    # ponytail: env list, not a users.is_owner column; move to Settings if owners change at runtime.
    owners = {e.strip().lower() for e in os.environ.get("OWNER_EMAILS", "").split(",") if e.strip()}
    if (user.email or "").lower() not in owners:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Owner only")
    return user
