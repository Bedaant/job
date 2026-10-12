"""Profiles, resume intake, confirmed facts, basics, resume.docx, answer bank."""

import logging

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from fastapi.responses import Response
from sqlalchemy.orm import Session

import answer_bank as answer_bank_service
from core.deps import get_current_user, get_owned_profile
from database import get_db
import models
import schemas
from events.outbox import record_funnel
from parsing.extract import extract_text_from_docx, extract_text_from_pdf
from parsing.linkedin_export import ExportRejected, read_linkedin_export
from parsing.llm_extract import extract_basics, extract_facts_from_text
from matching.service import refresh_fact_vectors
from routes._shared import _verified_resume_response

MAX_RESUME_UPLOAD_BYTES = 5 * 1024 * 1024  # SPEC.md §2.1: pdf/docx, ≤5MB

router = APIRouter()

# ---------- Profiles ----------

@router.post("/profiles", response_model=schemas.ProfileOut)
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


@router.get("/profiles", response_model=list[schemas.ProfileOut])
def list_profiles(db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    return db.query(models.Profile).filter(models.Profile.user_id == current_user.id).all()


# ---------- Resume intake (Phase 1, PRD.md §11 / SPEC.md §2.1) ----------
# Synchronous for now — RQ/Redis is Phase 2 scope (ADR-008). The API shape
# (upload_id, pollable status) stays stable for the later async migration.

RESUME_PARSE_FAILED = (
    "We couldn't read this resume right now. You can add your facts by hand instead, "
    "or try again in a few minutes."
)


@router.post("/profiles/{profile_id}/resume", response_model=schemas.ResumeUploadOut)
async def upload_resume(
    profile: models.Profile = Depends(get_owned_profile),
    db: Session = Depends(get_db),
    file: UploadFile = File(...),
):
    try:
        raw = await file.read()
    finally:
        await file.close()  # a >1MB upload is spooled to a temp file; don't keep it
    if len(raw) > MAX_RESUME_UPLOAD_BYTES:
        raise HTTPException(413, "Resume file exceeds 5MB limit")

    filename = (file.filename or "").lower()
    if filename.endswith(".zip"):
        # LinkedIn data export: deterministic, no model call. Drafts only, like a resume.
        try:
            facts, basics_draft = read_linkedin_export(raw)
        except ExportRejected as exc:
            raise HTTPException(422, str(exc))
        del raw
        upload = models.ResumeUpload(profile_id=profile.id, status="ready", draft_facts=facts)
        db.add(upload)
        db.commit()
        db.refresh(upload)
        return schemas.ResumeUploadOut(upload_id=upload.id, status=upload.status,
                                       facts=upload.draft_facts, basics=basics_draft)

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


@router.get("/profiles/{profile_id}/resume/{upload_id}", response_model=schemas.ResumeUploadOut)
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


def _fact_key(category, achievement, metric, proof) -> tuple:
    """Two facts are the same fact when they read the same, ignoring case and spacing."""
    norm = lambda v: " ".join((v or "").split()).casefold()
    return norm(category), norm(achievement), norm(metric), norm(proof)


@router.post("/profiles/{profile_id}/facts:bulk", response_model=list[schemas.ResumeFactOut])
def confirm_facts_bulk(
    payload: schemas.FactsBulkIn,
    response: Response,
    profile: models.Profile = Depends(get_owned_profile),
    db: Session = Depends(get_db),
):
    """Facts are NOT persisted from parsing alone — only here, once the user has
    reviewed and confirmed them (SPEC.md §2.1). Parsed output is never silently
    trusted.

    Idempotent: a fact identical (after normalisation) to one the profile already
    has — or to an earlier one in the same payload — is skipped, so onboarding's
    Back → Continue can't duplicate facts. Returns only the newly created facts;
    `X-Skipped-Facts` lists the payload indices that were skipped.
    """
    seen = {
        _fact_key(f.category, f.achievement, f.metric, f.proof)
        for f in db.query(models.ResumeFact).filter(models.ResumeFact.profile_id == profile.id).all()
    }
    created, skipped = [], []
    for i, fact_in in enumerate(payload.facts):
        key = _fact_key(fact_in.category, fact_in.achievement, fact_in.metric, fact_in.proof)
        if key in seen:
            skipped.append(str(i))
            continue
        seen.add(key)
        fact = models.ResumeFact(profile_id=profile.id, **fact_in.model_dump())
        db.add(fact)
        created.append(fact)
    response.headers["X-Skipped-Facts"] = ",".join(skipped)
    if not created:
        return []
    record_funnel(db, profile.user_id, "facts_confirmed")
    db.commit()

    # A Voyage failure (the free tier's 429) must not fail the confirm: the facts are
    # saved, and stay unembedded until the next edit re-embeds them.
    refresh_fact_vectors(db, profile)
    db.commit()

    for fact in created:
        db.refresh(fact)
    return created


# ---------- Applicant identity (JSON Resume `basics`) ----------

@router.get("/profiles/{profile_id}/basics", response_model=schemas.ApplicantBasics)
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


@router.put("/profiles/{profile_id}/basics", response_model=schemas.ApplicantBasics)
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


@router.get("/profiles/{profile_id}/resume.docx")
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


# ---------- Answer bank (ADR-015): answer once, reuse on every later form ----

@router.get("/profiles/{profile_id}/answers", response_model=list[schemas.AnswerOut])
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


@router.put("/profiles/{profile_id}/answers", response_model=schemas.AnswerOut)
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


@router.delete("/profiles/{profile_id}/answers/{answer_id}", status_code=204)
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
