"""Transactional outbox writer (ADR-012, ARCHITECTURE.md §4.6). Call inside
the same DB transaction as the business-row change it announces; the caller
commits both together.

Also the first-party funnel (P1 #10): `record_funnel` writes `funnel.<step>` once per
user. No third-party analytics. first_match and first_send derive from the events every
match/send path already writes, so a new send path is counted without being touched.
"""
from sqlalchemy.orm import Session

import models

# Event type -> funnel step it implies. An unconfirmed submit still went out.
_FUNNEL_FROM_EVENT = {
    "match.new": "first_match",
    "application.submitted": "first_send",
    "application.unconfirmed": "first_send",
}


def write_event(db: Session, user_id: str, type: str, payload: dict) -> models.Event:
    event = models.Event(user_id=user_id, type=type, payload=payload)
    db.add(event)
    if type in _FUNNEL_FROM_EVENT:
        record_funnel(db, user_id, _FUNNEL_FROM_EVENT[type])
    return event


def record_funnel(db: Session, user_id: str, step: str) -> bool:
    """Write `funnel.<step>` unless this user already has one. True if written."""
    type_ = f"funnel.{step}"
    if any(isinstance(o, models.Event) and o.user_id == user_id and o.type == type_ for o in db.new):
        return False
    # ponytail: check-then-insert; two concurrent first sends can write two rows.
    # A partial unique index on (user_id, type) WHERE type LIKE 'funnel.%' closes it if it matters.
    # No autoflush: the caller may be half-way through a row, and an early flush of it fails.
    with db.no_autoflush:
        exists = db.query(models.Event.id).filter(
            models.Event.user_id == user_id, models.Event.type == type_).first()
    if exists:
        return False
    db.add(models.Event(user_id=user_id, type=type_, payload={"step": step}))
    return True
