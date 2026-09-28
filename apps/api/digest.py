"""ADR-015 rail: "daily caps + a digest of what went out". One user's day, read from
the applications table + the events outbox over a [start, end) window of naive UTC.

Delivery is behind `sender(to, subject, body) -> delivered?`. The default only logs:
there are no email credentials yet (SMTP host/user/password or a provider API key).
Plug a real one in by passing it to daily_digest_task.
"""
import logging
from collections import Counter
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

import models
from database import session_scope

logger = logging.getLogger(__name__)

TRIGGER = "daily_digest"
TEMPLATE = "daily_digest_v1"
# An employer answered: the status moved past "sent".
REPLY_STATUSES = {"oa", "recruiter", "interview", "offer", "rejected"}
SKIP_LABELS = {
    "below_score": "Below your minimum score",
    "already_applied": "Already applied",
    "daily_cap": "Daily limit reached",
}


def build_digest(db: Session, user: models.User, start: datetime, end: datetime) -> dict:
    from main import _ready_to_send  # lazy: main imports the workers that import this

    S = models.ApplicationStatus
    profiles = db.query(models.Profile).filter(models.Profile.user_id == user.id).all()
    mine = [p.id for p in profiles]
    apps = db.query(models.Application).filter(models.Application.profile_id.in_(mine))
    sent = apps.filter(models.Application.applied_at >= start, models.Application.applied_at < end)
    ready = [r for p in profiles for r in _ready_to_send(db, p)]

    events = (
        db.query(models.Event)
        .filter(
            models.Event.user_id == user.id,
            models.Event.created_at >= start,
            models.Event.created_at < end,
            models.Event.type.in_(["campaign.skipped", "application.status_changed"]),
        )
        .order_by(models.Event.id)
        .all()
    )
    # Per-job skips only; the run-level rows ("checked", "not_active") have no job.
    skips = Counter(
        e.payload["reason_code"] for e in events
        if e.type == "campaign.skipped" and e.payload.get("job_id")
    )
    replied = {  # last reply status per application wins
        e.payload["application_id"]: e.payload["status"] for e in events
        if e.type == "application.status_changed" and e.payload.get("status") in REPLY_STATUSES
    }
    replies = []
    for app_id, status in replied.items():
        row = apps.filter(models.Application.id == app_id).first()
        if row:
            job = db.get(models.Job, row.job_id)
            replies.append({"application_id": app_id, "status": status,
                            "job_title": job.title, "company": job.company})

    d = {
        "day_start": start.isoformat(),
        "day_end": end.isoformat(),
        "sent": sent.count(),
        "unconfirmed": sent.filter(models.Application.status == S.submitted_unconfirmed).count(),
        "ready_to_send": len(ready),
        # Same arithmetic as GET /today: a prepared one counts once, as ready_to_send.
        "needs_you": apps.filter(models.Application.status == S.ready_for_review).count()
        - sum(r.status == S.ready_for_review.value for r in ready),
        "skipped": sum(skips.values()),
        "top_skip_reasons": [
            {"reason_code": code, "label": SKIP_LABELS.get(code, code.replace("_", " ").capitalize()), "count": n}
            for code, n in skips.most_common(3)
        ],
        "replies": replies,
    }
    d["had_activity"] = bool(d["sent"] or d["skipped"] or replies)
    return d


def render_text(d: dict) -> str:
    lines = ["Maggie's daily digest", ""]
    if d["sent"]:
        line = f"Sent {d['sent']} application{'s' * (d['sent'] != 1)}."
        if d["unconfirmed"]:
            line += f" {d['unconfirmed']} couldn't be confirmed - check your email for a receipt."
        lines.append(line)
    else:
        lines.append("Nothing went out today.")
    if d["ready_to_send"]:
        lines.append(f"{d['ready_to_send']} ready to send - open ApplyScout and press Send.")
    if d["needs_you"]:
        lines.append(f"{d['needs_you']} need you - a question only you can answer.")
    if d["skipped"]:
        reasons = ", ".join(f"{r['label']} ({r['count']})" for r in d["top_skip_reasons"])
        lines.append(f"Skipped {d['skipped']}: {reasons}.")
    if d["replies"]:
        lines.append("Replies:")
        lines += [f"  {r['job_title']} at {r['company']}: {r['status']}" for r in d["replies"]]
    return "\n".join(lines)


def log_only_sender(to: str, subject: str, body: str) -> bool:
    logger.info("digest (not emailed, no sender configured) to=%s subject=%s\n%s", to, subject, body)
    return False


def daily_digest_task(sender=log_only_sender) -> dict:
    """Yesterday's UTC day for every user who had activity. Runs on the owner role
    (cross-tenant by design, like the campaign sweep); every query is by user id.
    Re-running the same day writes nothing new."""
    # ponytail: users have no stored timezone, so the scheduled digest is the UTC
    # day; add users.timezone (web already knows it) to send at local midnight.
    end = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    start = end - timedelta(days=1)
    notified = 0
    with session_scope() as db:
        # ponytail: one pass over every user, fine until users number in the thousands.
        for user in db.query(models.User).all():
            done = db.query(models.Notification).filter(
                models.Notification.user_id == user.id,
                models.Notification.trigger == TRIGGER,
                models.Notification.created_at >= end,
            ).first()
            if done:
                continue
            d = build_digest(db, user, start, end)
            if not d["had_activity"]:
                continue
            d["text"] = render_text(d)
            n = models.Notification(user_id=user.id, trigger=TRIGGER, channel="email",
                                    template=TEMPLATE, payload=d)
            if sender(user.email, "Your ApplyScout daily digest", d["text"]):
                n.status, n.sent_at = "sent", datetime.utcnow()
            else:
                n.status, n.error = "skipped", "no email sender configured"
            db.add(n)
            db.flush()
            notified += 1
    return {"notified": notified}
