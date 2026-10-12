"""Applications: create, review queue, batch prep/approve, submission, tracker and detail."""

import logging
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

import answer_bank as answer_bank_service
import apply_email
from needs_input import attempt_history, last_attempt, needs_input
from core.deps import get_current_user, get_owned_profile, resolve_profile_ownership
from database import get_db
import models
import schemas
import send_gate
from documents.tailored_resume import tailored_facts
from events.outbox import record_funnel, write_event
import outcomes
from workers.jobs import get_queue, prepare_applications_task
from workers.outreach_tasks import draft_outreach_task
from matching.keyword_gap import compute_keyword_gap
from routes._shared import _commit_new_application, _verified_resume_response

router = APIRouter()

# ---------- Applications / tracker ----------

@router.post("/applications", response_model=schemas.ApplicationOut)
def create_application(
    payload: schemas.ApplicationCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    profile = resolve_profile_ownership(db, current_user, payload.profile_id)
    job = db.query(models.Job).filter(models.Job.id == payload.job_id).first()
    if not job:
        raise HTTPException(404, "Job not found")
    application = models.Application(
        profile_id=profile.id, job_id=payload.job_id, portal=payload.portal, notes=payload.notes
    )
    db.add(application)
    _commit_new_application(db)
    db.refresh(application)
    return application


# ---------- Review queue (sub-projects #2/#3, ADR-001's approval checkpoint) ----------

@router.get("/applications/review-queue", response_model=list[schemas.ApplicationReviewOut])
def list_review_queue(profile: models.Profile = Depends(get_owned_profile), db: Session = Depends(get_db)):
    return _review_rows(db, profile, [models.ApplicationStatus.ready_for_review])


@router.get("/applications/ready-to-send", response_model=list[schemas.ApplicationReviewOut])
def list_ready_to_send(profile: models.Profile = Depends(get_owned_profile), db: Session = Depends(get_db)):
    """Assisted apply: prepared applications the user can send themselves now."""
    return _ready_to_send(db, profile)


def _ready_to_send(db: Session, profile: models.Profile) -> list[schemas.ApplicationReviewOut]:
    """Ready = tailored with at least one bullet, nothing flagged by the truth-check
    (ADR-006), and no question only the user can answer. A captcha or account wall
    that stopped Maggie is not a blocker here: the user is the one sending."""
    rows = _review_rows(
        db, profile, [models.ApplicationStatus.ready_for_review, models.ApplicationStatus.approved]
    )
    return [r for r in rows if not send_gate.blockers(db, db.get(models.Application, r.id))]


def _review_rows(db: Session, profile: models.Profile, statuses) -> list[schemas.ApplicationReviewOut]:
    rows = (
        db.query(models.Application)
        .filter(
            models.Application.profile_id == profile.id,
            models.Application.status.in_(statuses),
        )
        .order_by(models.Application.created_at.desc())
        .all()
    )
    matches_by_job_id = {
        m.job_id: m
        for m in db.query(models.Match).filter(models.Match.profile_id == profile.id).all()
    }

    result = []
    for row in rows:
        match = matches_by_job_id.get(row.job_id)
        tailored = row.tailored_resume_json or {}
        pending, options, consent, prepared = send_gate.split_pending(db, profile.id, row.pending_questions)
        result.append(schemas.ApplicationReviewOut(
            id=row.id,
            job=row.job,
            match_score=float(match.score) if match else None,
            match_breakdown=match.breakdown if match else None,
            status=row.status.value,
            tailored_summary=tailored.get("summary"),
            tailored_bullets=tailored.get("bullets", []),
            tailored_cover_letter=row.tailored_cover_letter,
            flagged_unsupported_claims=row.flagged_unsupported_claims or [],
            pending_questions=pending,
            question_options=options,
            consent_questions=consent,
            prepared_answers=prepared,
            keyword_gap=tailored.get("keyword_gap"),
            needs_input=needs_input(row.notes, pending, consent),
            last_attempt=last_attempt(row.notes),
            created_at=row.created_at,
        ))
    return result


@router.post("/applications/batch-prepare")
def batch_prepare_applications(
    payload: schemas.BatchApproveRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Enqueues sub-project #2's async prep job — real LLM calls per
    application, must not block the request thread (same reasoning as
    /discover/run). Validates ownership up front so a malicious id can't be
    smuggled into the RQ job payload.
    """
    owned_count = (
        db.query(models.Application)
        .join(models.Profile)
        .filter(
            models.Application.id.in_(payload.application_ids),
            models.Profile.user_id == current_user.id,
        )
        .count()
    )
    if owned_count != len(payload.application_ids):
        raise HTTPException(404, "One or more applications not found")

    job = get_queue().enqueue(prepare_applications_task, payload.application_ids)
    return {"task_id": job.id, "status": job.get_status()}


@router.post("/applications/batch-approve", response_model=schemas.BatchApproveResponse)
def batch_approve_applications(
    payload: schemas.BatchApproveRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """All-or-nothing (SPEC.md's own '"no partial sends" discipline, already
    used for outreach): every id must belong to the caller and be
    ready_for_review, or nothing transitions at all.
    """
    rows = (
        db.query(models.Application)
        .join(models.Profile)
        .filter(
            models.Application.id.in_(payload.application_ids),
            models.Profile.user_id == current_user.id,
        )
        .all()
    )
    if len(rows) != len(payload.application_ids):
        raise HTTPException(404, "One or more applications not found")
    if any(row.status != models.ApplicationStatus.ready_for_review for row in rows):
        raise HTTPException(422, "One or more applications are not ready for review")
    blocked = [r for row in rows for r in send_gate.can_send(db, current_user, row)[1]]
    if blocked:
        raise HTTPException(409, "Nothing was approved: " + " ".join(dict.fromkeys(blocked)))

    approved_ids = []
    for row in rows:
        send_gate.transition(row, models.ApplicationStatus.approved)
        write_event(
            db, current_user.id, "application.approved",
            {"application_id": row.id},
        )
        approved_ids.append(row.id)
    db.commit()
    # mailto: jobs never reach the extension queue; the email task is their submit path.
    for row in rows:
        if (row.job.apply_url or "").startswith("mailto:"):
            apply_email.enqueue_send(db, row)
    return schemas.BatchApproveResponse(approved=approved_ids)


@router.post("/applications/{application_id}/claim-submission")
def claim_submission(
    application_id: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """The ONLY gate that lets the extension's bounded submit path
    (apps/extension/src/content/submitApprovedApplication.ts, the single
    reviewed entry in the static guard's ALLOWLIST) proceed. Real authority
    lives here, server-side — the extension-side code is just the mechanical
    trigger; it always calls this first and only touches the native submit API
    if this returns 200.

    `with_for_update()` locks the row for the transaction so two concurrent
    claims on the same application can't both succeed — a real correctness
    requirement, not decorative, because sending an application to an employer
    is one-time and irreversible. **This must fire at most once per
    application and never be retriable into a duplicate send.**

    Note what `approved` means now (ADR-015, amended 2026-10-04): it no longer
    implies a human clicked Approve on this item — `campaigns.run_campaign`
    sets it directly when `campaign.auto_submit` is true, which is exactly
    ADR-015 §2's campaign-level approval. So this endpoint is NOT the per-item
    human gate the pivot removed, and must not be deleted as part of it: it is
    the at-most-once guarantee (pinned by
    test_claim_submission_still_cannot_fire_twice) and the per-submission
    accounting the daily-caps rail depends on.
    """
    application = (
        db.query(models.Application)
        .join(models.Profile)
        .filter(models.Application.id == application_id, models.Profile.user_id == current_user.id)
        .with_for_update()
        .first()
    )
    if not application:
        raise HTTPException(404, "Application not found")
    if application.status != models.ApplicationStatus.approved:
        raise HTTPException(409, "Application is not in an approved, claimable state")
    ok, reasons = send_gate.can_send(db, current_user, application)
    if not ok:
        raise HTTPException(409, "Not sent: " + " ".join(reasons))

    # `submitting`, NOT `applied`: at this point nothing has been sent. The
    # native form submit fires after this call returns. Marking `applied` here
    # (as this endpoint originally did) told the user they had applied whenever
    # the form then failed, and `applied_at` would timestamp an event that never
    # happened. POST /applications/{id}/submission-result closes the window.
    # The at-most-once guarantee is unchanged: the row is no longer `approved`,
    # so a second claim still 409s.
    send_gate.transition(application, models.ApplicationStatus.submitting)
    # Logged at the claim: from here the form may reach the employer.
    send_gate.log_sent(db, current_user.id, "submission", application.job.apply_url, application.id)
    write_event(
        db, current_user.id, "application.status_changed",
        {"application_id": application.id, "status": "submitting"},
    )
    db.commit()
    return {"claimed": True, "application_id": application.id}


_SUBMISSION_OUTCOMES = {
    # outcome -> (resulting status, stamps applied_at)
    "submitted": (models.ApplicationStatus.applied, True),
    # Sent, but the employer's page neither confirmed nor rejected it. Its own
    # status: not `applied` (unverified), never `approved` (a retry could apply
    # twice). applied_at still stamps when the submit was sent.
    "unconfirmed": (models.ApplicationStatus.submitted_unconfirmed, True),
    # The form never went through, so this is work again rather than a lie. The
    # reason is recorded because a silent failure is the whole thing being fixed.
    "failed": (models.ApplicationStatus.approved, False),
    # Captcha, an account wall, a free-text essay question — the driver stopping
    # and handing over is a correct outcome, not an error.
    "needs_human": (models.ApplicationStatus.ready_for_review, False),
}

# Outcomes that mean the form reached the employer, and therefore that stage 8 has
# something to ask about. Mirrors `outreach.orchestrate._SENT_STATES` — kept as its own
# name here so the trigger is visible at the call site rather than implied.
_OUTREACH_TRIGGER_STATES = {
    models.ApplicationStatus.applied,
    models.ApplicationStatus.submitted_unconfirmed,
}


@router.post("/applications/{application_id}/submission-result", response_model=schemas.SubmissionResultOut)
def report_submission_result(
    application_id: str,
    payload: schemas.SubmissionResultIn,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Close the `submitting` window opened by claim-submission.

    Only a `submitting` row may be closed. Accepting a result for any other
    status would let a caller mark an arbitrary application `applied` without
    ever having claimed it — the claim is what proves one driver owns this
    submission, and it is also what makes reporting twice a 409.
    """
    application = (
        db.query(models.Application)
        .join(models.Profile)
        .filter(
            models.Application.id == application_id,
            models.Profile.user_id == current_user.id,
        )
        .with_for_update()
        .first()
    )
    if not application:
        raise HTTPException(404, "Application not found")
    # `failed`/`needs_human` also close from `approved`: the extension stops
    # BEFORE claiming (blocking field, no form, captcha on load), so nothing was
    # sent and there is no claim. Anything that says a send happened
    # (submitted/unconfirmed) still requires the claim.
    allowed = {models.ApplicationStatus.submitting}
    if payload.outcome in ("failed", "needs_human"):
        allowed.add(models.ApplicationStatus.approved)
    if application.status not in allowed:
        raise HTTPException(
            409,
            f"Application is {application.status.value}, not submitting — there is no open "
            "submission to report on (claim it first, and report exactly once).",
        )

    new_status, stamps_applied_at = _SUBMISSION_OUTCOMES[payload.outcome]
    if new_status == models.ApplicationStatus.approved and application.status == models.ApplicationStatus.submitting:
        # A claimed form that "failed" may still have gone through: the user re-approves,
        # never an automatic retry (send_gate.ALLOWED_TRANSITIONS).
        new_status = models.ApplicationStatus.ready_for_review
    send_gate.transition(application, new_status)
    if stamps_applied_at:
        application.applied_at = datetime.utcnow()
    if payload.reason:
        stamp = f"[{payload.outcome}] {payload.reason}"
        application.notes = f"{application.notes}\n{stamp}" if application.notes else stamp
    # Only needs_human leaves questions for the user; any other outcome means the
    # form went through or will be retried, so stale questions must not linger.
    # Deduped by question, order kept. Demographic questions (label or options) are
    # dropped here — never answerable, so asking the user for one is a trap.
    # Consent is kept: send_gate.split_pending shows it as the user's own step.
    questions: dict[str, dict] = {}
    for item in payload.unanswered_questions if payload.outcome == "needs_human" else []:
        q, opts = (item, []) if isinstance(item, str) else (item.question, item.options)
        q, opts = q.strip(), [o.strip() for o in opts if o.strip()]
        if q and q not in questions and not answer_bank_service.is_demographic_field(q, opts):
            questions[q] = {"question": q, "options": opts}
    application.pending_questions = list(questions.values())

    write_event(
        db, current_user.id, f"application.{payload.outcome}",
        {"application_id": application.id, "status": new_status.value, "reason": payload.reason},
    )
    db.commit()

    # Stage 8 (REACH-D): the application reached the employer, so now look for someone
    # there to tell. README: "After you apply, the app finds a suitable person at the
    # company". Enqueued AFTER the commit and deliberately never fatal — the submission
    # result is the thing that must not be lost, and outreach is an addition to it.
    # `draft_outreach_for_application` re-checks the status itself, so an outcome that
    # did not send simply returns `not_sent`.
    if new_status in _OUTREACH_TRIGGER_STATES:
        try:
            get_queue().enqueue(draft_outreach_task, application.id)
        except Exception:
            logging.getLogger(__name__).exception(
                "outreach enqueue failed for application %s", application.id
            )

    return schemas.SubmissionResultOut(application_id=application.id, status=new_status.value)


@router.patch("/applications/{application_id}", response_model=schemas.ApplicationOut)
def update_application(
    application_id: str,
    payload: schemas.ApplicationUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    app_row = _owned_application(db, current_user, application_id)

    if payload.status:
        S = models.ApplicationStatus
        was = app_row.status
        if payload.status == S.approved and was != S.approved:
            ok, reasons = send_gate.can_send(db, current_user, app_row)
            if not ok:
                raise HTTPException(409, "Not approved: " + " ".join(reasons))
        send_gate.transition(app_row, payload.status)
        if payload.status == S.applied and not app_row.applied_at:
            app_row.applied_at = datetime.utcnow()
        # Undo of "I've sent it": back to a not-yet-sent status means it wasn't sent.
        if was == S.applied and payload.status in (S.saved, S.ready_for_review, S.approved, S.dismissed):
            app_row.applied_at = None
        write_event(
            db, current_user.id, "application.status_changed",
            {"application_id": app_row.id, "status": payload.status.value},
        )
        if payload.status == S.applied and was != S.applied:
            # The user pressed the employer's Submit themselves (assisted apply).
            write_event(
                db, current_user.id, "application.submitted",
                {"application_id": app_row.id, "status": S.applied.value, "manual": True},
            )
    if payload.portal is not None:
        app_row.portal = payload.portal
    if payload.notes is not None:
        app_row.notes = payload.notes
    if payload.next_follow_up_at is not None:
        app_row.next_follow_up_at = payload.next_follow_up_at

    db.commit()
    db.refresh(app_row)
    return app_row


def _owned_application(db: Session, user: models.User, application_id: str) -> models.Application:
    row = (
        db.query(models.Application)
        .join(models.Profile)
        .filter(models.Application.id == application_id, models.Profile.user_id == user.id)
        .first()
    )
    if not row:
        raise HTTPException(404, "Application not found")
    return row


@router.get("/applications/{application_id}/resume.docx")
def download_tailored_resume_docx(
    application_id: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """The tailored resume for one application (assisted apply). Only bullets
    whose every source_fact_id resolves to this profile's facts go in (ADR-009);
    the LLM's free-text summary does not. Same linter + parse-back as the base."""
    application = _owned_application(db, current_user, application_id)
    facts_list = tailored_facts(db, application)
    if not facts_list:
        raise HTTPException(409, "This application has no tailored bullets grounded in your facts, so there is no tailored resume to generate.")
    return _verified_resume_response(application.profile, facts_list, "tailored-resume.docx")


@router.post("/applications/{application_id}/outcome")
def record_application_outcome(
    application_id: str,
    payload: schemas.OutcomeIn,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    app_row = _owned_application(db, current_user, application_id)
    outcomes.record_outcome(db, app_row, current_user.id, payload.outcome)
    record_funnel(db, current_user.id, "outcome_answered")
    db.commit()
    return {"application_id": app_row.id, "outcome": app_row.outcome}


# ---------- Applications tracker + detail, match actions (WORKLOG latest+46) ----------
# Registered after /applications/review-queue and /ready-to-send on purpose: a
# `/applications/{application_id}` route declared first would swallow those paths.

@router.get("/applications", response_model=list[schemas.ApplicationListOut])
def list_applications(profile: models.Profile = Depends(get_owned_profile), db: Session = Depends(get_db)):
    return (
        db.query(models.Application)
        .filter(models.Application.profile_id == profile.id)
        .order_by(models.Application.created_at.desc())
        .all()
    )


@router.get("/applications/{application_id}", response_model=schemas.ApplicationDetailOut)
def get_application_detail(
    application_id: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    row = _owned_application(db, current_user, application_id)
    job = row.job
    facts = db.query(models.ResumeFact).filter(models.ResumeFact.profile_id == row.profile_id).all()
    facts_by_id = {f.id: f for f in facts}
    tailored = row.tailored_resume_json or {}
    bullets = [
        {
            **b,
            "sources": [
                {"id": fid, "achievement": facts_by_id[fid].achievement}
                for fid in b.get("source_fact_ids") or [] if fid in facts_by_id
            ],
        }
        for b in tailored.get("bullets") or [] if b.get("text")
    ]
    # Deterministic and free (no model call), so it runs on every view.
    gap = compute_keyword_gap(job.description or "", facts, job_skills=job.skills, job_title=job.title)
    reworded = sorted({s["keyword"] for s in gap["suggestions"] if s["action"] == "reword"})
    match = (
        db.query(models.Match)
        .filter(models.Match.profile_id == row.profile_id, models.Match.job_id == row.job_id)
        .first()
    )
    pending, options, consent, _ = send_gate.split_pending(db, row.profile_id, row.pending_questions)
    return schemas.ApplicationDetailOut(
        id=row.id, status=row.status.value, job=job, portal=row.portal,
        match_score=float(match.score) if match else None,
        created_at=row.created_at, updated_at=row.updated_at,
        applied_at=row.applied_at, next_follow_up_at=row.next_follow_up_at,
        tailored_summary=tailored.get("summary"), tailored_bullets=bullets,
        tailored_cover_letter=row.tailored_cover_letter,
        flagged_unsupported_claims=row.flagged_unsupported_claims or [],
        pending_questions=pending,
        question_options=options,
        consent_questions=consent,
        keyword_gap=tailored.get("keyword_gap"),
        keywords=schemas.KeywordsOut(
            matched=[m["keyword"] for m in gap["matched"] if m["keyword"] not in reworded],
            reworded=reworded,
            missing=[m["keyword"] for m in gap["missing"]],
        ),
        needs_input=needs_input(row.notes, pending, consent),
        last_attempt=last_attempt(row.notes),
        history=attempt_history(row.notes),
    )
