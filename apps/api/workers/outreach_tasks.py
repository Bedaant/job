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


def _smtp_configured() -> bool:
    from core.config import get_settings

    return bool(get_settings().smtp_host)


def smtp_outreach_sender():
    """`digest.smtp_sender`, adapted to the outreach sender contract.

    Two reasons this wrapper exists rather than passing `digest.smtp_sender` directly:

    1. It returns `True`/`False`, while `send_outreach` stores the return value as
       `gmail_message_id` — passing the bool through would persist the literal string
       `"True"` as a message id.
    2. `False` must become `None`, because `send_outreach` treats a falsy return as a
       failed delivery. Returning a truthy id on a failed send would mark the row `sent`
       with nothing delivered, which is the one outcome worse than failing.

    SMTP gives no provider message id, so the id is synthetic and marked `smtp:` so a row
    sent this way is distinguishable from a Gmail-API one forever after.
    """
    import uuid

    import digest

    def sender(to: str, subject: str, body: str, attachments=None):
        delivered = digest.smtp_sender(to, subject, body, attachments)
        return f"smtp:{uuid.uuid4()}" if delivered else None

    return sender


def _sender_for(db, row: models.Outreach):
    """How this email actually leaves. Gmail first, SMTP as the fallback.

    ADR-003 chose per-user Gmail OAuth and it stays preferred — it is the only path that
    satisfies `PRD.md` §3 ("the user's identity, the user's reputation"), and it is tried
    whenever a grant exists.

    **The deviation the fallback introduces, stated rather than buried:** an SMTP send
    goes out from the ONE configured account, not from the identity of whichever user the
    row belongs to. So §3 holds for the Gmail path and does NOT hold here. That is
    acceptable while this is the owner plus a handful of friends, and it is why Gmail is
    preferred the moment a grant appears rather than being a configurable choice. Revisit
    before any user who is not a friend of the owner's is onboarded.

    Raises when neither is available, which the caller records as `failed`. A missing
    credential is not a transient fault, so retrying it only burns the queue — and
    returning a no-op sender instead would mark rows `sent` with nothing delivered.
    """
    from outreach.gmail import (
        GmailNotConfigured,
        GmailNotConnected,
        GmailReauthRequired,
        gmail_sender,
    )

    try:
        return gmail_sender(db, row.profile.user_id)
    except (GmailNotConnected, GmailNotConfigured, GmailReauthRequired):
        if not _smtp_configured():
            raise
        logger.info("outreach %s falling back to SMTP: no usable Gmail grant", row.id)
        return smtp_outreach_sender()


def default_sources() -> list:
    """Free sources first, paid last — `orchestrate._gather` stops as soon as the quota
    is filled, so Apify's per-profile charge is only spent on companies GitHub cannot
    reach.

    Measured 2026-10-09: GitHub exposes a public, self-published address for about half
    the people it lists, which is better provenance than any constructed or enriched
    address — but it is engineers only (one product-adjacent person across 39 across
    razorpay and zerodha, and Swiggy exposes nobody). So for an engineering-role user
    this list often never reaches Apify at all, and for a product-role user it almost
    always does.
    """
    from outreach.contacts import GitHubContactSource
    from outreach.sources_apify import ApifyContactSource

    # Apify is included unconditionally: with no token configured its `find` returns []
    # rather than raising, so an unconfigured install degrades to GitHub-only on its own.
    return [GitHubContactSource(), ApifyContactSource()]


def draft_outreach_task(application_id: str) -> dict:
    """Scheduled off the back of a submitted application (REACH-D).

    Idempotent: `draft_outreach_for_application` pre-checks for existing rows and the
    schema's UNIQUE(application_id, contact_id) backs it up. ADR-008 documents RQ
    retrying on worker crash, so this will run twice for some applications.
    """
    from outreach.orchestrate import draft_outreach_for_application

    with session_scope() as db:
        return draft_outreach_for_application(db, application_id, sources=default_sources())
