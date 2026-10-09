"""REACH-D — the RQ task that actually sends an approved note.

Separate from the endpoint on purpose. `POST /outreach/{id}/approve` only passes the
gates and marks the row `approved`; this task performs the `approved -> sending` claim
under `with_for_update()` and then calls Gmail.

Why not send inline in the request: it would hold an HTTP request open across a Gmail
call, and — more importantly — it would give the lock nothing to protect against. The
lock exists because two workers can pick up the same `approved` row; that only happens
out here.

Idempotency is the claim itself, not a separate key. ADR-008 documents that RQ retries
on worker crash or timeout, so this task WILL sometimes run twice for one row. The second
run finds the row already `sending` or `sent`, `claim_outreach` refuses it, and nothing
is sent twice — which is the whole point of `outreach/send.py`'s at-most-once guarantee.
"""
import logging

import models
from database import session_scope
from outreach.send import claim_outreach, send_outreach

logger = logging.getLogger(__name__)


def send_outreach_task(outreach_id: str) -> dict:
    """Claim, then send. Returns a small dict for the RQ result, never the message body."""
    with session_scope() as db:
        row = db.query(models.Outreach).filter(models.Outreach.id == outreach_id).first()
        if row is None:
            return {"outreach_id": outreach_id, "result": "not_found"}

        refusal = claim_outreach(db, outreach_id, row.profile_id)
        if refusal is not None:
            # Every refusal is a legitimate outcome, not an error: a retry of an
            # already-sent row, a suppression that landed after approval, or the daily
            # cap. `daily_cap` deliberately leaves the row `approved` so the next day's
            # sweep picks it up.
            logger.info("outreach %s not claimed: %s", outreach_id, refusal)
            return {"outreach_id": outreach_id, "result": refusal}

        # Committed BEFORE the network call, so a crash mid-send leaves the row
        # `sending` rather than `approved`. That is the safe direction: a stuck
        # `sending` row is visible and reconcilable against Gmail by message id,
        # whereas an `approved` row would be picked up and sent again.
        db.commit()

        try:
            sender = _sender_for(db, row)
        except Exception as exc:
            row.status = models.OutreachStatus.failed
            row.error = type(exc).__name__
            logger.warning("outreach %s has no usable sender: %s", outreach_id, type(exc).__name__)
            return {"outreach_id": outreach_id, "result": "no_sender"}

        delivered = send_outreach(db, row, sender)
        return {"outreach_id": outreach_id, "result": "sent" if delivered else "failed"}


def _sender_for(db, row: models.Outreach):
    """The user's own Gmail (ADR-003). Raises if they have no usable grant, which the
    caller records as `failed` rather than retrying — a missing credential is not a
    transient fault and retrying it just burns the queue.
    """
    from outreach.gmail import gmail_sender

    return gmail_sender(db, row.profile.user_id)
