"""The one gate in front of everything that reaches an employer or a recruiter.

`can_send()` is called by every send path (batch approve, PATCH to approved, claim-submission,
the extension work queue, campaign auto mode, the apply-by-email task, outreach approve and
claim). It also holds the two pause switches: the owner's global one (models.AppFlag) and the
user's own (users.sends_paused). `log_sent()` writes the per-user sent log. `transition()` is the only way
Application.status changes, so a status jump no path should make (submitting -> approved,
which could apply twice) is refused in one place.
"""
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

import answer_bank
import models
import schemas
from core.deps import get_current_user, require_owner
from database import get_db
from documents.tailored_resume import tailored_facts
from formfill.deterministic import bind_to_options

# The owner's runtime switch (models.AppFlag); flipped by PUT /ops/send-pause.
GLOBAL_PAUSE = "pause_all_sends"

S = models.ApplicationStatus
_TRACKER = {S.applied, S.recruiter, S.oa, S.interview, S.offer, S.rejected, S.withdrawn}
# Undo of "I've sent it" (PATCH back from applied) lands on one of these.
_UNDO = {S.saved, S.ready_for_review, S.approved, S.dismissed}

ALLOWED_TRANSITIONS: dict[S, set[S]] = {
    S.saved: {S.ready_for_review, S.dismissed} | _TRACKER,
    S.ready_for_review: {S.approved, S.dismissed} | _TRACKER,
    S.approved: {S.submitting, S.ready_for_review, S.dismissed} | _TRACKER,
    S.dismissed: {S.saved, S.ready_for_review} | _TRACKER,
    # Out of the in-flight window only by a result: never back to approved (a retry could
    # apply twice).
    S.submitting: {S.submitted_unconfirmed, S.ready_for_review} | _TRACKER,
    S.submitted_unconfirmed: _TRACKER,
    S.applied: _TRACKER | _UNDO,
    **{s: set(_TRACKER) for s in _TRACKER - {S.applied}},
}


class InvalidTransition(ValueError):
    """main.py maps this to a 409."""


def transition(application: models.Application, new: S) -> None:
    old = application.status or S.saved
    if new != old and new not in ALLOWED_TRANSITIONS[old]:
        raise InvalidTransition(f"An application can't move from {old.value} to {new.value}.")
    application.status = new


def split_pending(db: Session, profile_id: str, stored: list | None):
    """What a needs_human run left for the user, derived on every read (never
    stored twice): a question drops off the moment the bank can answer it,
    however the answer got there. Returns (pending, options, consent, prepared).

    Consent is its own list: never answerable here (answer_bank rail), the user
    ticks it on the form. A dropdown stays pending until its bank answer picks
    one of its options — the same bind map_fields fills with, so "prepared"
    means the next run really fills it.
    """
    pending, options, consent, prepared = [], {}, [], []
    for entry in stored or []:
        # A bare string is a row stored before options were reported.
        q, opts = (entry, []) if isinstance(entry, str) else (entry["question"], entry.get("options") or [])
        if answer_bank.is_consent_field(q, opts):
            consent.append(q)
            continue
        hit = answer_bank.find_answer(db, profile_id, q)
        answer = bind_to_options(hit.answer_text, opts) if hit else None
        if answer is None:
            pending.append(q)
            if opts:
                options[q] = opts
        else:
            prepared.append(schemas.PreparedAnswerOut(question=q, answer=answer))
    return pending, options, consent, prepared


def blockers(db: Session, application: models.Application) -> list[str]:
    """Why this application's content may not go out; empty when it may."""
    reasons = []
    if application.flagged_unsupported_claims:
        reasons.append("The truth check flagged a claim your facts don't support.")
    if not tailored_facts(db, application):
        reasons.append("No tailored bullet is grounded in your facts.")
    if split_pending(db, application.profile_id, application.pending_questions)[0]:
        reasons.append("A question only you can answer is still open.")
    if not db.query(models.ResumeFact).filter(models.ResumeFact.profile_id == application.profile_id).first():
        reasons.append("Your profile has no facts yet.")
    return reasons


def _paused_globally(db: Session) -> bool:
    flag = db.get(models.AppFlag, GLOBAL_PAUSE)
    return bool(flag and flag.enabled)


def can_send(db: Session, user: models.User, application: models.Application | None = None) -> tuple[bool, list[str]]:
    """Without an application (outreach, the extension queue) only the pause switches apply."""
    reasons = []
    if _paused_globally(db):
        reasons.append("All sending is paused by ApplyScout.")
    if user.sends_paused:
        reasons.append("You paused all sending.")
    if application is not None:
        reasons += blockers(db, application)
    return not reasons, reasons


def log_sent(db: Session, user_id: str, kind: str, recipient: str, application_id: str | None = None) -> None:
    """Added to the caller's transaction, so it commits with the status change it records."""
    db.add(models.SentLog(user_id=user_id, kind=kind, recipient=recipient or "", application_id=application_id))


# ---------- the switches and the log ----------

router = APIRouter()


class PauseIn(BaseModel):
    paused: bool


def _safety(db: Session, user: models.User) -> dict:
    return {"paused": bool(user.sends_paused), "paused_globally": _paused_globally(db)}


@router.get("/send-safety")
def get_send_safety(db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    return _safety(db, user)


@router.put("/send-safety")
def set_my_pause(payload: PauseIn, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    user.sends_paused = payload.paused
    db.commit()
    return _safety(db, user)


@router.put("/ops/send-pause")
def set_global_pause(payload: PauseIn, db: Session = Depends(get_db), _owner: models.User = Depends(require_owner)):
    flag = db.get(models.AppFlag, GLOBAL_PAUSE) or models.AppFlag(name=GLOBAL_PAUSE)
    flag.enabled = payload.paused
    db.add(flag)
    db.commit()
    return {"paused_globally": flag.enabled}


@router.get("/sent-log")
def list_sent_log(limit: int = Query(100, ge=1, le=500), db: Session = Depends(get_db),
                  user: models.User = Depends(get_current_user)):
    rows = (db.query(models.SentLog).filter(models.SentLog.user_id == user.id)
            .order_by(models.SentLog.created_at.desc()).limit(limit).all())
    return [{"kind": r.kind, "recipient": r.recipient, "application_id": r.application_id,
             "created_at": r.created_at} for r in rows]
