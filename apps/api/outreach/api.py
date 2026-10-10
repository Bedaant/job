"""REACH-D/E — the outreach HTTP surface (`docs/PLAN-OUTREACH.md`).

Its own router rather than 150 more lines in `main.py`, following `outreach/gmail.py`.

The shape worth understanding before editing: **approval and sending are separate.**
`POST /approve` only checks the gates and marks the row `approved`; the actual
`approved -> sending` claim happens in the worker, under `with_for_update()`, because
that is where real concurrency lives (`outreach/send.py`). An endpoint that sent inline
would hold an HTTP request open across a Gmail call and give the lock nothing to protect
against.
"""
import logging

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

import models
from core.deps import get_current_user, resolve_profile_ownership
from database import get_db
from outreach import optout

logger = logging.getLogger(__name__)
router = APIRouter(tags=["outreach"])

# Indirection so tests can override the identity without minting a real JWT, matching
# `outreach/gmail.py::current_user_id`.
current_user = get_current_user

# These three are module-level names, not imports at call sites, so a test can replace
# them. The alternative — importing `workers.jobs` at module scope — drags Redis into
# every import of this router.


def _enqueue_send(outreach_id: str) -> None:
    from outreach.send import EFFECTS_QUEUE
    from workers.jobs import get_queue
    from workers.outreach_tasks import send_outreach_task

    get_queue(EFFECTS_QUEUE).enqueue(send_outreach_task, outreach_id)


def _recheck(subject: str, body: str, facts: list[dict]) -> list[str]:
    """Re-run ADR-006's truth-check over an edited draft. Separate function so the edit
    path cannot accidentally skip it."""
    from tailoring.engine import split_gate_findings, truth_check

    findings = truth_check(f"{subject}\n\n{body}", facts)
    hard, _advisory = split_gate_findings(findings)
    return hard


def _owned(db: Session, outreach_id: str, user: models.User) -> models.Outreach:
    """404, never 403. A 403 confirms the row exists, which is itself a disclosure
    (ADR-007's tenancy rule)."""
    row = (
        db.query(models.Outreach)
        .join(models.Profile, models.Outreach.profile_id == models.Profile.id)
        .filter(models.Outreach.id == outreach_id, models.Profile.user_id == user.id)
        .first()
    )
    if row is None:
        raise HTTPException(404, "Outreach not found")
    return row


def _serialise(row: models.Outreach) -> dict:
    """Deliberately hand-rolled rather than a response_model: the user is about to send
    this under their own name, so the queue has to carry the recipient, the signal and
    the verification status — enough to judge, not just the text."""
    contact = row.contact
    return {
        "id": row.id,
        "application_id": row.application_id,
        "status": row.status.value,
        "subject": row.subject,
        "body": row.body,
        "flagged_unsupported_claims": row.flagged_unsupported_claims or [],
        "warm_signal_used": row.warm_signal_used,
        "skip_reason": row.skip_reason,
        "sent_at": row.sent_at,
        "contact": None if contact is None else {
            "id": contact.id,
            "full_name": contact.full_name,
            "title": contact.title,
            "company": contact.company,
            "email": contact.email,
            "email_verification_status": contact.email_verification_status,
            "source": contact.source,
        },
    }


# Static paths are declared before the parameterised ones so `review-queue` can never be
# captured as an `{outreach_id}`.

@router.get("/outreach/review-queue")
def review_queue(
    profile_id: str = Query(...),
    db: Session = Depends(get_db),
    user: models.User = Depends(current_user),
):
    profile = resolve_profile_ownership(db, user, profile_id)
    rows = (
        db.query(models.Outreach)
        .filter(
            models.Outreach.profile_id == profile.id,
            models.Outreach.status == models.OutreachStatus.ready_for_review,
        )
        .order_by(models.Outreach.created_at.asc())
        .all()
    )
    return [_serialise(r) for r in rows]


@router.get("/outreach")
def list_outreach(
    profile_id: str = Query(...),
    db: Session = Depends(get_db),
    user: models.User = Depends(current_user),
):
    profile = resolve_profile_ownership(db, user, profile_id)
    rows = (
        db.query(models.Outreach)
        .filter(models.Outreach.profile_id == profile.id)
        .order_by(models.Outreach.created_at.desc())
        .all()
    )
    return [_serialise(r) for r in rows]


@router.patch("/outreach/{outreach_id}")
def edit_outreach(
    outreach_id: str,
    payload: dict = Body(...),
    db: Session = Depends(get_db),
    user: models.User = Depends(current_user),
):
    """An edit RE-RUNS the truth-check rather than clearing its findings.

    This is the gate's weakest point: without the re-check, "edit the text, then approve"
    is a one-click bypass of ADR-006 for anyone who finds the flag annoying.
    """
    row = _owned(db, outreach_id, user)
    if row.status not in (models.OutreachStatus.ready_for_review, models.OutreachStatus.approved):
        raise HTTPException(409, f"This note is {row.status.value} and can no longer be edited.")

    if "subject" in payload:
        row.subject = payload["subject"]
    if "body" in payload:
        row.body = payload["body"]

    facts = [
        {"id": f.id, "achievement": f.achievement, "proof": f.proof, "metric": f.metric}
        for f in row.profile.resume_facts
    ]
    row.flagged_unsupported_claims = _recheck(row.subject or "", row.body or "", facts)
    # Back to review whatever it was: an edited note has not been approved in its new
    # form, and the previous approval was of different text.
    row.status = models.OutreachStatus.ready_for_review
    db.commit()
    db.refresh(row)
    return _serialise(row)


@router.post("/outreach/{outreach_id}/approve")
def approve_outreach(
    outreach_id: str,
    db: Session = Depends(get_db),
    user: models.User = Depends(current_user),
):
    """Mark it approved and queue the send. NOT idempotent, deliberately: approving twice
    would queue two sends of an irreversible outward-facing action, so a second call is
    a 409 rather than a no-op.
    """
    row = _owned(db, outreach_id, user)
    if row.status is not models.OutreachStatus.ready_for_review:
        raise HTTPException(409, f"This note is already {row.status.value}.")
    if row.flagged_unsupported_claims:
        # ADR-006. The check is a gate, not a label: edit the note or skip it.
        raise HTTPException(409, "This note makes a claim your facts don't support. Edit it first.")

    row.status = models.OutreachStatus.approved
    row.approved_by = "user"
    db.commit()

    try:
        _enqueue_send(row.id)
    except Exception:
        # Same recovery as main.py's prepare path: hand the row back rather than leaving
        # it `approved` with nothing that will ever send it.
        row.status = models.OutreachStatus.ready_for_review
        row.approved_by = None
        db.commit()
        logger.exception("outreach send enqueue failed for %s", row.id)
        raise HTTPException(503, "Maggie couldn't queue that send. It's saved — try again shortly.")

    db.refresh(row)
    return _serialise(row)


@router.post("/outreach/{outreach_id}/skip")
def skip_outreach(
    outreach_id: str,
    payload: dict = Body(default={}),
    db: Session = Depends(get_db),
    user: models.User = Depends(current_user),
):
    row = _owned(db, outreach_id, user)
    if row.status in (models.OutreachStatus.sent, models.OutreachStatus.sending):
        raise HTTPException(409, f"This note is already {row.status.value}.")
    row.status = models.OutreachStatus.skipped
    row.skip_reason = (payload or {}).get("reason") or "user_skipped"
    db.commit()
    db.refresh(row)
    return _serialise(row)


# ---------- public, unauthenticated ----------

_OPT_OUT_PAGE = (
    "<!doctype html><html><head><meta charset=\"utf-8\">"
    "<title>Unsubscribed</title></head><body>"
    "<h1>You're unsubscribed</h1>"
    "<p>You won't receive any further notes from this service.</p>"
    "</body></html>"
)


@router.get("/outreach/unsubscribe/{token}", response_class=HTMLResponse)
def unsubscribe(token: str, db: Session = Depends(get_db)):
    """Unauthenticated by necessity: the recipient has no account here and must never
    need one to be left alone.

    **Answers identically whether or not it wrote a row.** A different response for a
    real id would turn this into an id oracle, letting anyone walk the id space — and
    the page never echoes the address, so a leaked token is not a disclosure either.
    """
    outreach_id = optout.verify_token(token)
    if outreach_id:
        optout.record_optout(db, outreach_id)
        db.commit()
    return HTMLResponse(_OPT_OUT_PAGE)
