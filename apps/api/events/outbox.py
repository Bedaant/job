"""Transactional outbox writer (ADR-012, ARCHITECTURE.md §4.6). Call inside
the same DB transaction as the business-row change it announces; the caller
commits both together.
"""
from sqlalchemy.orm import Session

import models


def write_event(db: Session, user_id: str, type: str, payload: dict) -> models.Event:
    event = models.Event(user_id=user_id, type=type, payload=payload)
    db.add(event)
    return event
