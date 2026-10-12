"""Self-healing for the unattended loop (P1 #15): close what a crash left open, and tell the owner.

A `submitting` row is an irreversible send in flight. If nothing closed it (the user shut the browser
mid-fill, a worker died mid-send), it may or may not have reached the employer, so it moves to
`submitted_unconfirmed`, never back to `approved`: a retry could apply twice.
"""
import logging
from datetime import datetime, timedelta

import models
import observability
import send_gate
from events.outbox import write_event

logger = logging.getLogger(__name__)

# Longer than any real fill or send; observability alerts on 15 min, this acts on 30.
SUBMITTING_TIMEOUT_MINUTES = 30
SUPERVISE_INTERVAL_SECONDS = 15 * 60
S = models.ApplicationStatus


def recover_stale_submissions(db, now: datetime | None = None) -> list[str]:
    cutoff = (now or datetime.utcnow()) - timedelta(minutes=SUBMITTING_TIMEOUT_MINUTES)
    # updated_at is when the claim happened: the claim is the row's last write.
    rows = (db.query(models.Application)
            .filter(models.Application.status == S.submitting, models.Application.updated_at < cutoff)
            .with_for_update().all())
    for application in rows:
        send_gate.transition(application, S.submitted_unconfirmed)
        stamp = ("[unconfirmed] The submission never reported back, so it may or may not have gone. "
                 "Check the employer's site or your Sent folder, then mark it applied.")
        application.notes = f"{application.notes}\n{stamp}" if application.notes else stamp
        url = application.job.apply_url or ""
        if url.startswith("mailto:"):
            # The extension path logged at its claim; the email path only logs an outcome.
            import apply_email  # lazy: apply_email pulls in the outreach workers
            send_gate.log_sent(db, application.profile.user_id, "email",
                               apply_email.recipient(url) or url, application.id)
        write_event(db, application.profile.user_id, "application.status_changed",
                    {"application_id": application.id, "status": application.status.value})
    db.commit()
    return [a.id for a in rows]


def supervise(db, redis, sender=None) -> dict:
    recovered = recover_stale_submissions(db)
    if recovered:
        logger.warning("recovered %d stale submission(s): %s", len(recovered), recovered)
        observability.send_alert(redis, "submitting_recovered",
                                 f"{len(recovered)} submission(s) never reported back and were marked "
                                 f"unconfirmed: {recovered}", sender)
    return {"recovered_submissions": recovered}


def supervise_task() -> dict:
    from database import session_scope
    with session_scope() as db:
        return supervise(db, observability._redis())
