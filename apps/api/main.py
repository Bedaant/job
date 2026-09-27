import logging
import time
from datetime import datetime, timedelta, timezone

from fastapi import FastAPI, Depends, HTTPException, Query, Request, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from sqlalchemy.orm import Session
from sse_starlette.sse import EventSourceResponse

from rq.exceptions import DuplicateJobError
from rq.job import Job as RQJob

import answer_bank as answer_bank_service
from needs_input import last_attempt, needs_input
from core.config import get_settings
from core.deps import get_current_user, get_owned_profile, resolve_profile_ownership
from database import get_db
import models
import schemas
from tailoring.engine import tailor_application
from auth.router import router as auth_router
from connectors.apply_target import resolve_apply_target
from documents.ats_safety import lint_docx
from documents.generate_docx import generate_resume_docx
from documents.parse_back import parse_back_check
from events.outbox import write_event
from events.sse import event_stream
from formfill.map_fields import build_profile_summary, map_form_fields
from parsing.extract import extract_text_from_docx, extract_text_from_pdf
from parsing.llm_extract import extract_basics, extract_facts_from_text
from workers.jobs import (
    discover_jobs_task, get_queue, get_redis_connection, prepare_applications_task, run_campaign_task,
)
import campaigns as campaigns_service
from matching.embeddings import embed_texts, compute_centroid
from matching.keyword_gap import compute_keyword_gap
from matching.service import build_matches
from parsing.jsonresume_export import facts_to_jsonresume

MAX_RESUME_UPLOAD_BYTES = 5 * 1024 * 1024  # SPEC.md §2.1: pdf/docx, ≤5MB

settings = get_settings()

# Schema is owned by Alembic now (alembic/versions/0001_baseline.py) — run
# `alembic upgrade head` before starting the app. No create_all() here; that
# was CODE-REVIEW.md B2 (silently ignores schema changes in production).

app = FastAPI(title="Job Copilot API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)


# ---------- Job discovery ----------

@app.post("/discover/run")
def run_discovery(_user: models.User = Depends(get_current_user)):
    """Enqueues onto RQ instead of running inline — fixes CODE-REVIEW.md B6.
    Requires a worker process running `rq worker` to actually process it.

    SPEC.md §3.6 idempotency, layer 1 — enqueue dedupe: job_id is derived
    from a 1-minute time bucket, enqueued with unique=True (raises
    DuplicateJobError, verified against the installed rq's own source, if a
    job with that ID is already queued/running) — a second call within the
    same minute returns the existing task_id instead of double-enqueuing.
    Layer 2 (the execution claim) lives in discover_jobs_task itself.
    """
    job_id = f"discover-{int(time.time() // 60)}"  # rq: [A-Za-z0-9_-] only
    try:
        job = get_queue().enqueue(discover_jobs_task, job_id=job_id, unique=True, kwargs={"job_id": job_id})
    except DuplicateJobError:
        job = RQJob.fetch(job_id, connection=get_redis_connection())
    return {"task_id": job.id, "status": job.get_status()}


@app.get("/discover/run/{task_id}")
def get_discovery_status(task_id: str, _user: models.User = Depends(get_current_user)):
    job = RQJob.fetch(task_id, connection=get_redis_connection())
    return {
        "task_id": job.id,
        "status": job.get_status(),
        "result": job.result,
    }


@app.get("/jobs", response_model=list[schemas.JobOut])
def list_jobs(db: Session = Depends(get_db), limit: int = 100, _user: models.User = Depends(get_current_user)):
    return db.query(models.Job).order_by(models.Job.fetched_at.desc()).limit(limit).all()


# ---------- Applications / tracker ----------

@app.post("/applications", response_model=schemas.ApplicationOut)
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
    db.commit()
    db.refresh(application)
    return application


@app.get("/applications", response_model=list[schemas.ApplicationOut])
def list_applications(profile: models.Profile = Depends(get_owned_profile), db: Session = Depends(get_db)):
    return (
        db.query(models.Application)
        .filter(models.Application.profile_id == profile.id)
        .order_by(models.Application.created_at.desc())
        .all()
    )


# ---------- Review queue (sub-projects #2/#3, ADR-001's approval checkpoint) ----------

@app.get("/applications/review-queue", response_model=list[schemas.ApplicationReviewOut])
def list_review_queue(profile: models.Profile = Depends(get_owned_profile), db: Session = Depends(get_db)):
    return _review_rows(db, profile, [models.ApplicationStatus.ready_for_review])


@app.get("/applications/ready-to-send", response_model=list[schemas.ApplicationReviewOut])
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
    return [
        r for r in rows
        if r.tailored_bullets and not r.flagged_unsupported_claims and not r.pending_questions
    ]


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
        # Derived, not stored twice: a question drops off the moment the bank
        # can answer it, however the answer got there.
        pending, prepared = [], []
        for q in row.pending_questions or []:
            hit = answer_bank_service.find_answer(db, profile.id, q)
            if hit is None:
                pending.append(q)
            else:
                prepared.append(schemas.PreparedAnswerOut(question=q, answer=hit.answer_text))
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
            prepared_answers=prepared,
            keyword_gap=tailored.get("keyword_gap"),
            needs_input=needs_input(row.notes, pending),
            last_attempt=last_attempt(row.notes),
            created_at=row.created_at,
        ))
    return result


@app.post("/applications/batch-prepare")
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


@app.post("/applications/batch-approve", response_model=schemas.BatchApproveResponse)
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

    approved_ids = []
    for row in rows:
        row.status = models.ApplicationStatus.approved
        write_event(
            db, current_user.id, "application.approved",
            {"application_id": row.id},
        )
        approved_ids.append(row.id)
    db.commit()
    return schemas.BatchApproveResponse(approved=approved_ids)


@app.post("/applications/{application_id}/claim-submission")
def claim_submission(
    application_id: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Sub-project #4 — the ONLY gate that lets the extension's bounded
    submit path (apps/extension/src/content/submitApprovedApplication.ts,
    the single reviewed exception in the ADR-001 static guard's ALLOWLIST)
    proceed. Real authority lives here, server-side — the extension-side
    code is just the mechanical trigger; it always calls this first and
    only touches the native submit API if this returns 200.

    `with_for_update()` locks the row for the transaction so two concurrent
    claims on the same application can't both succeed — a real correctness
    requirement, not decorative, since this is a one-time, irreversible
    action (ADR-001: the human already approved once; this must fire at
    most once per application, not be retriable into a duplicate send).
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

    # `submitting`, NOT `applied`: at this point nothing has been sent. The
    # native form submit fires after this call returns. Marking `applied` here
    # (as this endpoint originally did) told the user they had applied whenever
    # the form then failed, and `applied_at` would timestamp an event that never
    # happened. POST /applications/{id}/submission-result closes the window.
    # The at-most-once guarantee is unchanged: the row is no longer `approved`,
    # so a second claim still 409s.
    application.status = models.ApplicationStatus.submitting
    write_event(
        db, current_user.id, "application.status_changed",
        {"application_id": application.id, "status": "submitting"},
    )
    db.commit()
    return {"claimed": True, "application_id": application.id}


# "Connected" = the extension called in this recently. The driver only calls in
# when the popup opens or a queue run happens, so this is "recently used", not a
# live socket; 10 minutes covers a user moving between the web app and the popup.
EXTENSION_CONNECTED_WINDOW = timedelta(minutes=10)


def extension_connected(last_seen_at: datetime | None, now: datetime) -> bool:
    return last_seen_at is not None and now - last_seen_at <= EXTENSION_CONNECTED_WINDOW


def _mark_extension_seen(db: Session, user: models.User) -> None:
    user.extension_last_seen_at = datetime.utcnow()
    db.commit()


def _work_queue_query(db: Session, user: models.User):
    """What the extension driver would pick up: `approved`, owned, actionable."""
    return (
        db.query(models.Application)
        .join(models.Profile, models.Application.profile_id == models.Profile.id)
        .join(models.Job, models.Application.job_id == models.Job.id)
        .filter(
            models.Profile.user_id == user.id,
            models.Application.status == models.ApplicationStatus.approved,
            # An empty apply_url is unactionable: handing it to the driver buys a
            # guaranteed failure report and burns a retry for nothing.
            models.Job.apply_url != "",
            models.Job.apply_url.isnot(None),
        )
    )


@app.get("/extension/status", response_model=schemas.ExtensionStatusOut)
def extension_status(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Read by the web app, so it never stamps last-seen itself."""
    return schemas.ExtensionStatusOut(
        connected=extension_connected(current_user.extension_last_seen_at, datetime.utcnow()),
        last_seen_at=current_user.extension_last_seen_at,
        approved_waiting=_work_queue_query(db, current_user).count(),
    )


@app.get("/extension/work-queue", response_model=list[schemas.WorkQueueItemOut])
def extension_work_queue(
    limit: int = 20,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """ADR-015 Phase 1: the missing link between a campaign run and a sent
    application. `run_campaign_task` produced `approved` rows and nothing ever
    collected them, so a campaign ended in a queue. This is what the extension
    driver pulls.

    Only `approved` is work. A `submitting` row has already been claimed by a
    driver pass, so re-serving it is exactly how the same job gets applied to
    twice — the claim moving the row out of `approved` is what makes this queue
    self-draining.
    """
    _mark_extension_seen(db, current_user)
    rows = (
        _work_queue_query(db, current_user)
        .order_by(models.Application.created_at.asc())
        .limit(limit)
        .all()
    )
    items = []
    for row in rows:
        original = row.job.apply_url
        # ADR-015 Phase 2: a feed's apply_url is usually an aggregator redirector,
        # not the form. Resolving it is an optimisation, so a resolver failure
        # degrades to the original URL rather than emptying the queue.
        try:
            target = resolve_apply_target(original)
        except Exception:
            target = {"final_url": original, "ats_type": None, "board_token": None, "resolved": False}
        items.append(schemas.WorkQueueItemOut(
            application_id=row.id,
            profile_id=row.profile_id,
            apply_url=target["final_url"] if target["resolved"] else original,
            company=row.job.company,
            title=row.job.title,
            original_apply_url=original,
            ats_type=target["ats_type"],
            board_token=target["board_token"],
        ))
    return items


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


@app.post("/applications/{application_id}/submission-result", response_model=schemas.SubmissionResultOut)
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
    application.status = new_status
    if stamps_applied_at:
        application.applied_at = datetime.utcnow()
    if payload.reason:
        stamp = f"[{payload.outcome}] {payload.reason}"
        application.notes = f"{application.notes}\n{stamp}" if application.notes else stamp
    # Only needs_human leaves questions for the user; any other outcome means the
    # form went through or will be retried, so stale questions must not linger.
    # dict.fromkeys: dedupe, order kept. Demographic questions are dropped here —
    # they are never answerable, so asking the user for one is a trap.
    application.pending_questions = (
        list(dict.fromkeys(
            q.strip() for q in payload.unanswered_questions
            if q.strip() and not answer_bank_service.is_demographic_label(q)
        ))
        if payload.outcome == "needs_human" else []
    )

    write_event(
        db, current_user.id, f"application.{payload.outcome}",
        {"application_id": application.id, "status": new_status.value, "reason": payload.reason},
    )
    db.commit()
    return schemas.SubmissionResultOut(application_id=application.id, status=new_status.value)


@app.patch("/applications/{application_id}", response_model=schemas.ApplicationOut)
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
        app_row.status = payload.status
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


# ---------- Campaigns (ADR-015 §2 — the unit of approval) ----------

@app.post("/campaigns", response_model=schemas.CampaignOut)
def create_campaign(
    payload: schemas.CampaignCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    profile = resolve_profile_ownership(db, current_user, payload.profile_id)
    campaign = models.Campaign(
        profile_id=profile.id, **payload.model_dump(exclude={"profile_id"})
    )
    db.add(campaign)
    db.commit()
    db.refresh(campaign)
    return campaign


@app.get("/campaigns", response_model=list[schemas.CampaignOut])
def list_campaigns(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Every campaign across the caller's profiles. Scoped by the join, not by
    a client-supplied profile_id — there is nothing here to trust from the
    request at all.
    """
    return (
        db.query(models.Campaign)
        .join(models.Profile, models.Campaign.profile_id == models.Profile.id)
        .filter(models.Profile.user_id == current_user.id)
        .order_by(models.Campaign.created_at.desc())
        .all()
    )


@app.get("/campaigns/{campaign_id}", response_model=schemas.CampaignOut)
def get_campaign(
    campaign_id: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    return campaigns_service.resolve_campaign_ownership(db, current_user, campaign_id)


@app.patch("/campaigns/{campaign_id}", response_model=schemas.CampaignOut)
def update_campaign(
    campaign_id: str,
    payload: schemas.CampaignUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Edit / pause / resume. Status moves only along
    campaigns.ALLOWED_TRANSITIONS — archived is terminal.
    """
    campaign = campaigns_service.resolve_campaign_ownership(db, current_user, campaign_id)
    fields = payload.model_dump(exclude_unset=True, exclude_none=True)

    new_status = fields.pop("status", None)
    if new_status is not None:
        try:
            target = models.CampaignStatus(new_status)
        except ValueError:
            raise HTTPException(422, f"Unknown campaign status {new_status!r}")
        if target != campaign.status and target not in campaigns_service.ALLOWED_TRANSITIONS[campaign.status]:
            raise HTTPException(422, f"Cannot move a {campaign.status.value} campaign to {target.value}")
        campaign.status = target

    for key, value in fields.items():
        setattr(campaign, key, value)

    db.commit()
    db.refresh(campaign)
    return campaign


@app.delete("/campaigns/{campaign_id}", response_model=schemas.CampaignOut)
def archive_campaign(
    campaign_id: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Archive, never a hard delete — the campaign is the record of what the
    user authorized, and its applications point back at it.
    """
    campaign = campaigns_service.resolve_campaign_ownership(db, current_user, campaign_id)
    campaign.status = models.CampaignStatus.archived
    db.commit()
    db.refresh(campaign)
    return campaign


@app.post("/campaigns/{campaign_id}/run")
def run_campaign_endpoint(
    campaign_id: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Enqueues the autonomous run onto RQ — same two-layer idempotency as
    /discover/run: a per-minute job_id with unique=True here (layer 1), a
    Redis claim inside the task (layer 2).
    """
    campaign = campaigns_service.resolve_campaign_ownership(db, current_user, campaign_id)
    # rq 2.x only accepts [A-Za-z0-9_-] in job ids (a ":" 500s the enqueue).
    run_id = f"campaign-{campaign.id}-{int(time.time() // 60)}"
    try:
        job = get_queue().enqueue(
            run_campaign_task, job_id=run_id, unique=True,
            kwargs={"campaign_id": campaign.id, "run_id": run_id},
        )
    except DuplicateJobError:
        job = RQJob.fetch(run_id, connection=get_redis_connection())
    return {"task_id": job.id, "status": job.get_status()}


@app.get("/campaigns/{campaign_id}/stats", response_model=schemas.CampaignStatsOut)
def get_campaign_stats(
    campaign_id: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    campaign = campaigns_service.resolve_campaign_ownership(db, current_user, campaign_id)
    today = campaigns_service.applied_today(db, campaign)
    return schemas.CampaignStatsOut(
        applied_today=today,
        daily_cap=campaign.daily_cap,
        # Same function the worker enforces with — never recomputed here.
        remaining_today=campaigns_service.remaining_quota(db, campaign),
        total_applied=db.query(models.Application).filter(
            models.Application.campaign_id == campaign.id
        ).count(),
        last_run_at=campaign.last_run_at,
    )


# ---------- Resume facts KB ----------

@app.get("/resume-facts", response_model=list[schemas.ResumeFactOut])
def list_resume_facts(profile: models.Profile = Depends(get_owned_profile), db: Session = Depends(get_db)):
    return db.query(models.ResumeFact).filter(models.ResumeFact.profile_id == profile.id).all()


@app.post("/resume-facts", response_model=schemas.ResumeFactOut)
def add_resume_fact(
    payload: schemas.ResumeFactIn,
    profile: models.Profile = Depends(get_owned_profile),
    db: Session = Depends(get_db),
):
    fact = models.ResumeFact(profile_id=profile.id, **payload.model_dump())
    db.add(fact)
    db.commit()
    db.refresh(fact)
    return fact


# ---------- Tailoring ----------

@app.post("/tailor", response_model=schemas.TailorResponse)
def tailor(
    payload: schemas.TailorRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    profile = resolve_profile_ownership(db, current_user, payload.profile_id)
    job = db.query(models.Job).filter(models.Job.id == payload.job_id).first()
    if not job:
        raise HTTPException(404, "Job not found")

    facts = db.query(models.ResumeFact).filter(models.ResumeFact.profile_id == profile.id).all()
    facts_list = [
        {
            "id": f.id,
            "category": f.category,
            "achievement": f.achievement,
            "proof": f.proof,
            "metric": f.metric,
            "tags": f.tags,
        }
        for f in facts
    ]

    job_dict = {
        "title": job.title,
        "company": job.company,
        "description": job.description or "",
    }

    result = tailor_application(job_dict, facts_list)

    application = (
        db.query(models.Application)
        .filter(models.Application.job_id == job.id, models.Application.profile_id == profile.id)
        .order_by(models.Application.created_at.desc())
        .first()
    )
    if application:
        application.tailored_resume_json = {
            "summary": result["summary"], "bullets": result["bullets"], "keyword_gap": result.get("keyword_gap"),
        }
        application.tailored_cover_letter = result["cover_letter"]
        db.commit()

    return result


# ---------- Profiles ----------

@app.post("/profiles", response_model=schemas.ProfileOut)
def create_profile(
    payload: schemas.ProfileCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    profile = models.Profile(user_id=current_user.id, **payload.model_dump())
    db.add(profile)
    db.commit()
    db.refresh(profile)
    return profile


@app.get("/profiles", response_model=list[schemas.ProfileOut])
def list_profiles(db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    return db.query(models.Profile).filter(models.Profile.user_id == current_user.id).all()


# ---------- Resume intake (Phase 1, PRD.md §11 / SPEC.md §2.1) ----------
# Synchronous for now — RQ/Redis is Phase 2 scope (ADR-008). The API shape
# (upload_id, pollable status) stays stable for the later async migration.

RESUME_PARSE_FAILED = (
    "We couldn't read this resume right now. You can add your facts by hand instead, "
    "or try again in a few minutes."
)


@app.post("/profiles/{profile_id}/resume", response_model=schemas.ResumeUploadOut)
async def upload_resume(
    profile: models.Profile = Depends(get_owned_profile),
    db: Session = Depends(get_db),
    file: UploadFile = File(...),
):
    raw = await file.read()
    if len(raw) > MAX_RESUME_UPLOAD_BYTES:
        raise HTTPException(413, "Resume file exceeds 5MB limit")

    filename = (file.filename or "").lower()
    try:
        if filename.endswith(".pdf"):
            text = extract_text_from_pdf(raw)
        elif filename.endswith(".docx"):
            text = extract_text_from_docx(raw)
        else:
            raise HTTPException(422, "Only .pdf and .docx resumes are supported")

        facts = extract_facts_from_text(text)
        upload = models.ResumeUpload(profile_id=profile.id, status="ready", draft_facts=facts)
    except HTTPException:
        raise
    except Exception:
        # The raw error (model/provider/parser internals, e.g. an auth failure) is
        # for the server log only; the user gets what they can act on.
        logging.getLogger(__name__).exception("resume parse failed for profile %s", profile.id)
        upload = models.ResumeUpload(profile_id=profile.id, status="failed", error=RESUME_PARSE_FAILED)

    # Identity extraction is a separate, non-fatal step: the facts KB is the
    # thing ADR-009 actually requires, so a failed or unvalidatable identity
    # extraction must not throw away a successful facts parse. Returned as a
    # draft for the user to review — never persisted from parsing alone.
    basics_draft = None
    if upload.status == "ready":
        try:
            basics_draft = extract_basics(text)
        except Exception:
            basics_draft = None

    db.add(upload)
    db.commit()
    db.refresh(upload)

    return schemas.ResumeUploadOut(
        upload_id=upload.id,
        status=upload.status,
        facts=upload.draft_facts or [],
        basics=basics_draft,
        error=upload.error,
    )


@app.get("/profiles/{profile_id}/resume/{upload_id}", response_model=schemas.ResumeUploadOut)
def get_resume_upload(
    upload_id: str,
    profile: models.Profile = Depends(get_owned_profile),
    db: Session = Depends(get_db),
):
    upload = (
        db.query(models.ResumeUpload)
        .filter(models.ResumeUpload.id == upload_id, models.ResumeUpload.profile_id == profile.id)
        .first()
    )
    if not upload:
        raise HTTPException(404, "Resume upload not found")

    return schemas.ResumeUploadOut(
        upload_id=upload.id,
        status=upload.status,
        facts=upload.draft_facts or [],
        error=upload.error,
    )


@app.post("/profiles/{profile_id}/facts:bulk", response_model=list[schemas.ResumeFactOut])
def confirm_facts_bulk(
    payload: schemas.FactsBulkIn,
    profile: models.Profile = Depends(get_owned_profile),
    db: Session = Depends(get_db),
):
    """Facts are NOT persisted from parsing alone — only here, once the user has
    reviewed and confirmed them (SPEC.md §2.1). Parsed output is never silently
    trusted.
    """
    created = []
    for fact_in in payload.facts:
        fact = models.ResumeFact(profile_id=profile.id, **fact_in.model_dump())
        db.add(fact)
        created.append(fact)
    db.commit()

    embeddings = embed_texts([f.achievement for f in created], input_type="document")
    if embeddings:
        for fact, embedding in zip(created, embeddings):
            fact.embedding = embedding
        all_embeddings = [
            list(f.embedding)
            for f in db.query(models.ResumeFact).filter(models.ResumeFact.profile_id == profile.id).all()
            if f.embedding is not None
        ]
        profile.fact_centroid = compute_centroid(all_embeddings)
        db.commit()

    for fact in created:
        db.refresh(fact)
    return created


# ---------- Applicant identity (JSON Resume `basics`) ----------

@app.get("/profiles/{profile_id}/basics", response_model=schemas.ApplicantBasics)
def get_profile_basics(profile: models.Profile = Depends(get_owned_profile)):
    """The identity data an application form asks for. Built explicitly rather
    than via model_validate so a null JSON column (pre-migration rows, or the
    SQLite test engine) reads as [] instead of failing validation.
    """
    return schemas.ApplicantBasics(
        full_name=profile.full_name,
        given_name=profile.given_name,
        family_name=profile.family_name,
        phone=profile.phone,
        website_url=profile.website_url,
        street_address=profile.street_address,
        city=profile.city,
        region=profile.region,
        country_code=profile.country_code,
        postal_code=profile.postal_code,
        network_profiles=profile.network_profiles or [],
        work_auth=profile.work_auth or [],
    )


@app.put("/profiles/{profile_id}/basics", response_model=schemas.ApplicantBasics)
def update_profile_basics(
    payload: schemas.ApplicantBasics,
    profile: models.Profile = Depends(get_owned_profile),
    db: Session = Depends(get_db),
):
    """Identity is persisted only here, after the user has reviewed it — parsed
    resume output is never silently trusted (same rule as facts:bulk, SPEC.md
    §2.1). Validation in schemas.ApplicantBasics rejects placeholder names,
    fictional phone numbers, non-ISO country codes and scheme-less URLs, so a
    bad extraction cannot reach a real application form through this endpoint
    either.
    """
    profile.full_name = payload.full_name
    profile.given_name = payload.given_name
    profile.family_name = payload.family_name
    profile.phone = payload.phone
    profile.website_url = payload.website_url
    profile.street_address = payload.street_address
    profile.city = payload.city
    profile.region = payload.region
    profile.country_code = payload.country_code
    profile.postal_code = payload.postal_code
    profile.network_profiles = [p.model_dump() for p in payload.network_profiles]
    profile.work_auth = payload.work_auth
    db.commit()
    return payload


# ---------- Matching (Phase 3, SPEC.md §3.2) ----------

@app.get("/matches", response_model=list[schemas.MatchOut])
def list_matches(profile: models.Profile = Depends(get_owned_profile), db: Session = Depends(get_db)):
    return build_matches(db, profile)


@app.get("/matches/{match_id}/keyword-gap", response_model=schemas.KeywordGapOut)
def get_match_keyword_gap(
    match_id: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """ATS keyword targeting for one match (matching/keyword_gap.py).

    `documents/ats_safety.py` already guarantees the DOCX is *parseable*; this
    is the other half of "more interview calls" — which of the JD's keywords
    the user's real facts actually surface. Deterministic and free (regex +
    rapidfuzz, no model call), so it can be called on every match.

    ADR-009: `missing` keywords are reported but never suggested. Every
    suggestion points at a `ResumeFact` the user already owns and only ever
    reorders, surfaces, or rewords it.
    """
    match = (
        db.query(models.Match)
        .join(models.Profile)
        .filter(models.Match.id == match_id, models.Profile.user_id == current_user.id)
        .first()
    )
    if not match:
        raise HTTPException(404, "Match not found")

    facts = db.query(models.ResumeFact).filter(models.ResumeFact.profile_id == match.profile_id).all()
    return compute_keyword_gap(
        match.job.description, facts, job_skills=match.job.skills, job_title=match.job.title
    )


@app.get("/profiles/{profile_id}/resume.docx")
def download_resume_docx(profile: models.Profile = Depends(get_owned_profile), db: Session = Depends(get_db)):
    """Phase 4 documents (SPEC.md §3.5): DOCX generated from the Facts KB only
    (ADR-009), never the raw resume blob. Both the ATS-safety linter and the
    parse-back check run before any bytes leave the server — a document that
    fails either never ships, rather than shipping a document nobody verified.
    """
    facts = db.query(models.ResumeFact).filter(models.ResumeFact.profile_id == profile.id).all()
    if not facts:
        # docs/LIVE-FORM-TEST.md #12: an empty 200 docx was attached as the
        # candidate's resume on three real forms. No facts = no resume to send.
        raise HTTPException(409, "This profile has no resume facts yet, so there is no resume to generate.")
    facts_list = [
        {
            "id": f.id, "category": f.category, "achievement": f.achievement,
            "period_from": f.period_from, "period_to": f.period_to,
        }
        for f in facts
    ]
    return _verified_resume_response(profile, facts_list, "resume.docx")


@app.get("/applications/{application_id}/resume.docx")
def download_tailored_resume_docx(
    application_id: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """The tailored resume for one application (assisted apply). Only bullets
    whose every source_fact_id resolves to this profile's facts go in (ADR-009);
    the LLM's free-text summary does not. Same linter + parse-back as the base."""
    application = _owned_application(db, current_user, application_id)
    facts = {
        f.id: f for f in
        db.query(models.ResumeFact).filter(models.ResumeFact.profile_id == application.profile_id)
    }
    facts_list = []
    for i, bullet in enumerate((application.tailored_resume_json or {}).get("bullets") or []):
        ids = bullet.get("source_fact_ids") or []
        text = (bullet.get("text") or "").strip()
        if not text or not ids or any(fid not in facts for fid in ids):
            continue
        cited = [facts[fid] for fid in ids]
        # Dates only when every cited fact agrees — a merged bullet has no one period.
        same_period = len({(f.period_from, f.period_to) for f in cited}) == 1
        facts_list.append({
            "id": f"bullet-{i}", "category": cited[0].category, "achievement": text,
            "period_from": cited[0].period_from if same_period else None,
            "period_to": cited[0].period_to if same_period else None,
        })
    if not facts_list:
        raise HTTPException(409, "This application has no tailored bullets grounded in your facts, so there is no tailored resume to generate.")
    return _verified_resume_response(application.profile, facts_list, "tailored-resume.docx")


def _contact_header(profile: models.Profile) -> tuple[str | None, list[str]]:
    """Name + one contact line from the profile's own basics; never guessed."""
    name = profile.full_name or " ".join(p for p in (profile.given_name, profile.family_name) if p) or None
    place = ", ".join(p for p in (profile.city, profile.region) if p)
    links = [profile.website_url] + [n.get("url") for n in (profile.network_profiles or []) if isinstance(n, dict)]
    contact = [profile.user.email, profile.phone, place, *links]
    return name, list(dict.fromkeys(c for c in contact if c))


def _verified_resume_response(profile: models.Profile, facts_list: list[dict], filename: str) -> Response:
    """Render, then lint and parse-back before any bytes leave the server —
    a document that fails either never ships."""
    name, contact = _contact_header(profile)
    docx_bytes = generate_resume_docx(profile.headline, facts_list, name=name, contact=contact)

    violations = lint_docx(docx_bytes)
    if violations:
        raise HTTPException(500, f"Generated resume failed ATS-safety checks: {violations}")

    failed_parse_back = [r for r in parse_back_check(docx_bytes, facts_list) if not r["passed"]]
    if failed_parse_back:
        raise HTTPException(500, f"Generated resume failed parse-back check: {failed_parse_back}")

    return Response(
        content=docx_bytes,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@app.get("/resume-facts:jsonresume")
def export_resume_facts_jsonresume(profile: models.Profile = Depends(get_owned_profile), db: Session = Depends(get_db)):
    """JSON Resume schema export (jsonresume.org, DEPENDENCIES.md §3)."""
    facts = db.query(models.ResumeFact).filter(models.ResumeFact.profile_id == profile.id).all()
    facts_dicts = [
        {"category": f.category, "achievement": f.achievement, "proof": f.proof, "metric": f.metric, "tags": f.tags}
        for f in facts
    ]
    return facts_to_jsonresume(facts_dicts)


# ---------- F11 form-fill agent (ADR-011, SPEC.md §3.7) ----------

@app.post("/extension/map-fields", response_model=list[schemas.FieldMappingOut])
def extension_map_fields(
    payload: schemas.MapFieldsRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Proxies the bounded Claude/nvidia_smoke call for the extension's
    content script — the model call happens here, server-side, never from
    extension code, so no Anthropic/NVIDIA key ever ships client-side.
    """
    profile = resolve_profile_ownership(db, current_user, payload.profile_id)
    _mark_extension_seen(db, current_user)

    profile_summary = build_profile_summary(profile, current_user.email)
    fields = [f.model_dump() for f in payload.fields]

    # The answer bank, scoped to this profile and injected as a plain callable —
    # a question the user has already answered in their own words is filled here
    # instead of interrupting them again. serve_answer refuses demographic
    # questions itself, and map_form_fields never reaches it for one anyway.
    def answer_lookup(question_text: str | None) -> str | None:
        if not question_text:
            return None
        return answer_bank_service.serve_answer(db, profile.id, question_text)

    return map_form_fields(fields, profile_summary, answer_lookup=answer_lookup, ats_type=payload.ats_type)


# ---------- Answer bank (ADR-015): answer once, reuse on every later form ----

@app.get("/profiles/{profile_id}/answers", response_model=list[schemas.AnswerOut])
def list_answers(
    profile: models.Profile = Depends(get_owned_profile),
    db: Session = Depends(get_db),
):
    return (
        db.query(models.AnswerBank)
        .filter(models.AnswerBank.profile_id == profile.id)
        .order_by(models.AnswerBank.updated_at.desc())
        .all()
    )


@app.put("/profiles/{profile_id}/answers", response_model=schemas.AnswerOut)
def upsert_answer(
    payload: schemas.AnswerIn,
    profile: models.Profile = Depends(get_owned_profile),
    db: Session = Depends(get_db),
):
    """PUT rather than POST because the unique key is the question, not an id:
    answering the same question twice must update, never add a second
    contradictory answer. save_answer 400s on a demographic/EEO question.
    """
    return answer_bank_service.save_answer(
        db, profile.id, payload.question_text, payload.answer_text
    )


@app.delete("/profiles/{profile_id}/answers/{answer_id}", status_code=204)
def delete_answer(
    answer_id: str,
    profile: models.Profile = Depends(get_owned_profile),
    db: Session = Depends(get_db),
):
    row = (
        db.query(models.AnswerBank)
        .filter(
            models.AnswerBank.id == answer_id,
            # scoped by profile, not just by user — a user with two personas
            # must not delete one profile's answer through the other's path
            models.AnswerBank.profile_id == profile.id,
        )
        .first()
    )
    if not row:
        raise HTTPException(404, "Answer not found")
    db.delete(row)
    db.commit()
    return Response(status_code=204)


# ---------- Real-time events / notifications (ADR-012, SPEC.md §2.6) ----------

@app.get("/events")
async def stream_events(
    request: Request,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    last_event_id = request.headers.get("Last-Event-ID")
    return EventSourceResponse(event_stream(db, current_user.id, last_event_id))


# Event type -> (title, detail when the payload gives none). Only types something
# actually writes; `application.status_changed` is left out on purpose — it is
# the claim/PATCH plumbing, not something Maggie did that the user needs to see.
_ACTIVITY = {
    "match.new": ("New match", None),
    "application.ready_for_review": ("Ready for your review", None),
    "application.approved": ("Approved to send", None),
    "application.submitted": ("Applied", None),
    "application.unconfirmed": ("Sent — couldn't confirm it went through",
                                "Check your email for a confirmation, or open the form."),
    "application.needs_human": ("Stopped on a question", "Needs an answer from you before it can be sent."),
    "application.failed": ("Couldn't send", "Maggie will try again."),
    "campaign.skipped": ("Skipped", None),
    "campaign.scheduled_run": ("Ran on schedule", None),
}
# campaign.skipped rows without a job are run-level notes; title by reason_code.
_RUN_SKIP_TITLES = {"checked": "Checked new jobs", "daily_cap": "Daily limit reached", "not_active": "Didn't run"}


@app.get("/activity", response_model=list[schemas.ActivityItemOut])
def list_activity(
    since: datetime | None = None,
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """What Maggie did, newest first, from the events outbox. Plain JSON, not
    SSE: a native EventSource can't send the bearer header."""
    query = db.query(models.Event).filter(
        models.Event.user_id == current_user.id, models.Event.type.in_(_ACTIVITY)
    )
    if since is not None:
        if since.tzinfo:
            since = since.astimezone(timezone.utc).replace(tzinfo=None)
        query = query.filter(models.Event.created_at >= since)
    events = query.order_by(models.Event.created_at.desc(), models.Event.id.desc()).limit(limit).all()

    # Two batched lookups, not one per row. Applications are reached only
    # through the caller's own profiles.
    app_ids = {e.payload.get("application_id") for e in events} - {None}
    apps = {
        a.id: a for a in db.query(models.Application).join(models.Profile)
        .filter(models.Application.id.in_(app_ids), models.Profile.user_id == current_user.id)
    } if app_ids else {}
    job_ids = {e.payload.get("job_id") for e in events} | {a.job_id for a in apps.values()}
    job_ids.discard(None)
    jobs = {j.id: j for j in db.query(models.Job).filter(models.Job.id.in_(job_ids))} if job_ids else {}

    items = []
    for e in events:
        p = e.payload or {}
        title, fallback = _ACTIVITY[e.type]
        application = apps.get(p.get("application_id"))
        job = jobs.get(application.job_id if application else p.get("job_id"))
        if e.type == "match.new" and p.get("score") is not None:
            detail = f"{round(float(p['score']))}% match"  # Match.score is 0..100
        else:
            detail = p.get("reason") or fallback
        if e.type == "campaign.skipped" and not job:
            title = _RUN_SKIP_TITLES.get(p.get("reason_code"), "Maggie didn't apply")
        if e.type == "application.submitted" and p.get("manual"):
            title = "You sent it"
        unconfirmed = e.type == "application.unconfirmed"
        if unconfirmed and job:
            title = f"Sent to {job.company} — couldn't confirm it went through"
        items.append(schemas.ActivityItemOut(
            id=e.id, type=e.type, at=e.created_at.replace(tzinfo=timezone.utc), title=title, detail=detail,
            application_id=application.id if application else None,
            job=schemas.ActivityJob(title=job.title, company=job.company) if job else None,
            apply_url=job.apply_url if unconfirmed and job else None,
        ))
    return items


@app.get("/today", response_model=schemas.TodayOut)
def get_today(
    tz: str | None = Query(None, max_length=64),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Home-screen counters across all the caller's profiles, over the caller's
    local day (`tz` = IANA name; invalid or missing → UTC) so they agree with the
    activity list. The daily cap stays on the UTC day. Campaign status and the
    cap come from /campaigns and /campaigns/{id}/stats, not here.
    """
    start = campaigns_service.local_day_start(tz)
    mine = db.query(models.Profile.id).filter(models.Profile.user_id == current_user.id)
    apps = db.query(models.Application).filter(models.Application.profile_id.in_(mine))
    sent = apps.filter(models.Application.applied_at >= start)
    ready = [
        r for p in db.query(models.Profile).filter(models.Profile.user_id == current_user.id)
        for r in _ready_to_send(db, p)
    ]
    return schemas.TodayOut(
        ready_to_send=len(ready),
        sent_today=sent.count(),
        unconfirmed_today=sent.filter(
            models.Application.status == models.ApplicationStatus.submitted_unconfirmed
        ).count(),
        # The review queue minus what's ready to send (needs_human lands back in ready_for_review).
        # A prepared one is counted once, as ready_to_send, not also here.
        needs_you=apps.filter(models.Application.status == models.ApplicationStatus.ready_for_review).count()
        - sum(r.status == models.ApplicationStatus.ready_for_review.value for r in ready),
        new_matches_today=db.query(models.Match).filter(
            models.Match.profile_id.in_(mine), models.Match.created_at >= start
        ).count(),
    )


@app.get("/notifications", response_model=list[schemas.NotificationOut])
def list_notifications(
    status: str | None = None,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    query = db.query(models.Notification).filter(models.Notification.user_id == current_user.id)
    if status:
        query = query.filter(models.Notification.status == status)
    return query.order_by(models.Notification.created_at.desc()).all()


@app.patch("/notifications/{notification_id}", response_model=schemas.NotificationOut)
def update_notification(
    notification_id: str,
    payload: schemas.NotificationUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    notif = (
        db.query(models.Notification)
        .filter(models.Notification.id == notification_id, models.Notification.user_id == current_user.id)
        .first()
    )
    if not notif:
        raise HTTPException(404, "Notification not found")
    notif.status = payload.status
    db.commit()
    db.refresh(notif)
    return notif


@app.get("/health")
def health():
    return {"status": "ok"}
