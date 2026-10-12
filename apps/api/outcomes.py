"""P1 #10 outcome capture: one-tap "Heard back?" at 7 and 14 days after a send.

A prompt is an in-app `notifications` row (trigger outcome_prompt, payload
{application_id, day}); the daily digest lists the new ones with a deep link. The
answer lives on `applications.outcome`, never on `status` (send transitions are not
this module's). "No reply yet" is not final, so the 14-day prompt still comes.
"""
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

import models

TRIGGER = "outcome_prompt"
TEMPLATE = "outcome_prompt_v1"
OUTCOMES = ("interview", "rejected", "no_reply")
PROMPT_DAYS = (7, 14)
# Older sends are not prompted at all: a first sweep must not ask about months-old history.
MAX_AGE_DAYS = 21
_SENT = (models.ApplicationStatus.applied, models.ApplicationStatus.submitted_unconfirmed)


def sweep_prompts(db: Session, now: datetime) -> int:
    """Create the due prompts for every user. Cross-tenant (owner role, like the digest).
    Idempotent: at most one prompt per (application, day). Returns how many it created."""
    A = models.Application
    rows = (
        db.query(A, models.Profile.user_id).join(models.Profile)
        .filter(A.status.in_(_SENT), A.applied_at.isnot(None),
                A.applied_at <= now - timedelta(days=PROMPT_DAYS[0]),
                A.applied_at > now - timedelta(days=MAX_AGE_DAYS))
        .all()
    )
    existing = {
        (n.payload.get("application_id"), n.payload.get("day"))
        for n in db.query(models.Notification).filter(models.Notification.trigger == TRIGGER)
    }
    created = 0
    for app, user_id in rows:
        day = max(d for d in PROMPT_DAYS if app.applied_at <= now - timedelta(days=d))
        if (app.id, day) in existing:
            continue
        if app.outcome and (app.outcome != "no_reply" or app.outcome_at >= app.applied_at + timedelta(days=day)):
            continue
        db.add(models.Notification(user_id=user_id, trigger=TRIGGER, channel="in_app", template=TEMPLATE,
                                   payload={"application_id": app.id, "day": day}))
        existing.add((app.id, day))
        created += 1
    return created


def pending_prompts(db: Session, user_id: str, since: datetime | None = None) -> list[dict]:
    """Unanswered prompts for one user, newest first, with the job they ask about."""
    q = db.query(models.Notification).filter(
        models.Notification.user_id == user_id, models.Notification.trigger == TRIGGER,
        models.Notification.status == "pending")
    if since is not None:
        q = q.filter(models.Notification.created_at >= since)
    out = []
    for n in q.order_by(models.Notification.created_at.desc()):
        app = db.get(models.Application, n.payload.get("application_id"))
        if app is None:
            continue
        out.append({"application_id": app.id, "day": n.payload.get("day"),
                    "job_title": app.job.title, "company": app.job.company})
    return out


def record_outcome(db: Session, app: models.Application, user_id: str, outcome: str) -> None:
    """Caller has already checked ownership. Clears that application's open prompts."""
    app.outcome, app.outcome_at = outcome, datetime.utcnow()
    for n in db.query(models.Notification).filter(
            models.Notification.user_id == user_id, models.Notification.trigger == TRIGGER,
            models.Notification.status == "pending"):
        if n.payload.get("application_id") == app.id:
            n.status = "seen"
