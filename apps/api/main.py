import time
from datetime import datetime

from fastapi import FastAPI, Depends, HTTPException, Request, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from sqlalchemy.orm import Session
from sse_starlette.sse import EventSourceResponse

from rq.exceptions import DuplicateJobError
from rq.job import Job as RQJob

from core.config import get_settings
from core.deps import get_current_user, get_owned_profile, resolve_profile_ownership
from database import get_db
import models
import schemas
from tailoring.engine import tailor_application
from auth.router import router as auth_router
from documents.ats_safety import lint_docx
from documents.generate_docx import generate_resume_docx
from documents.parse_back import parse_back_check
from events.outbox import write_event
from events.sse import event_stream
from formfill.map_fields import build_profile_summary, map_form_fields
from parsing.extract import extract_text_from_docx, extract_text_from_pdf
from parsing.llm_extract import extract_basics, extract_facts_from_text
from workers.jobs import discover_jobs_task, get_queue, get_redis_connection
from matching.embeddings import embed_texts, compute_centroid
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
    job_id = f"discover:{int(time.time() // 60)}"
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


@app.patch("/applications/{application_id}", response_model=schemas.ApplicationOut)
def update_application(
    application_id: str,
    payload: schemas.ApplicationUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    app_row = (
        db.query(models.Application)
        .join(models.Profile)
        .filter(models.Application.id == application_id, models.Profile.user_id == current_user.id)
        .first()
    )
    if not app_row:
        raise HTTPException(404, "Application not found")

    if payload.status:
        app_row.status = payload.status
        if payload.status == "applied" and not app_row.applied_at:
            app_row.applied_at = datetime.utcnow()
        write_event(
            db, current_user.id, "application.status_changed",
            {"application_id": app_row.id, "status": payload.status},
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
        application.tailored_resume_json = {"summary": result["summary"], "bullets": result["bullets"]}
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
    except Exception as exc:
        upload = models.ResumeUpload(profile_id=profile.id, status="failed", error=str(exc))

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


@app.get("/profiles/{profile_id}/resume.docx")
def download_resume_docx(profile: models.Profile = Depends(get_owned_profile), db: Session = Depends(get_db)):
    """Phase 4 documents (SPEC.md §3.5): DOCX generated from the Facts KB only
    (ADR-009), never the raw resume blob. Both the ATS-safety linter and the
    parse-back check run before any bytes leave the server — a document that
    fails either never ships, rather than shipping a document nobody verified.
    """
    facts = db.query(models.ResumeFact).filter(models.ResumeFact.profile_id == profile.id).all()
    facts_list = [
        {
            "id": f.id, "category": f.category, "achievement": f.achievement,
            "period_from": f.period_from, "period_to": f.period_to,
        }
        for f in facts
    ]

    docx_bytes = generate_resume_docx(profile.headline, facts_list)

    violations = lint_docx(docx_bytes)
    if violations:
        raise HTTPException(500, f"Generated resume failed ATS-safety checks: {violations}")

    failed_parse_back = [r for r in parse_back_check(docx_bytes, facts_list) if not r["passed"]]
    if failed_parse_back:
        raise HTTPException(500, f"Generated resume failed parse-back check: {failed_parse_back}")

    return Response(
        content=docx_bytes,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": "attachment; filename=resume.docx"},
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

    profile_summary = build_profile_summary(profile, current_user.email)
    fields = [f.model_dump() for f in payload.fields]
    return map_form_fields(fields, profile_summary)


# ---------- Real-time events / notifications (ADR-012, SPEC.md §2.6) ----------

@app.get("/events")
async def stream_events(
    request: Request,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    last_event_id = request.headers.get("Last-Event-ID")
    return EventSourceResponse(event_stream(db, current_user.id, last_event_id))


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
