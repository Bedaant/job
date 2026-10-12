"""The one gate in front of everything that reaches an employer or a recruiter.

`can_send()` is called by every send path (batch approve, PATCH to approved, claim-submission,
campaign auto mode, the apply-by-email task). `transition()` is the only way
Application.status changes, so a status jump no path should make (submitting -> approved,
which could apply twice) is refused in one place.
"""
from sqlalchemy.orm import Session

import answer_bank
import models
import schemas
from documents.tailored_resume import tailored_facts
from formfill.deterministic import bind_to_options

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


def can_send(db: Session, user: models.User, application: models.Application | None = None) -> tuple[bool, list[str]]:
    reasons = blockers(db, application) if application is not None else []
    return not reasons, reasons
