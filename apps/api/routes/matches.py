"""Matches: keyword gap, similar jobs, list, update, prepare."""

import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from core.deps import get_current_user, get_owned_profile
from database import get_db
import models
import schemas
from workers.jobs import get_queue, prepare_applications_task
import campaigns as campaigns_service
from matching.keyword_gap import compute_keyword_gap
from matching.service import build_matches
from routes._shared import _commit_new_application

router = APIRouter()

# ---------- Matching (Phase 3, SPEC.md §3.2) ----------

@router.get("/matches/{match_id}/keyword-gap", response_model=schemas.KeywordGapOut)
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


@router.get("/similar-jobs", response_model=list[schemas.SimilarJobOut])
def list_similar_jobs(profile: models.Profile = Depends(get_owned_profile), db: Session = Depends(get_db)):
    """Near misses the role judge kept instead of dropping: more options, never auto-applied."""
    return [schemas.SimilarJobOut(job=job, role=role)
            for job, role in campaigns_service.similar_jobs(db, profile)]


@router.get("/matches", response_model=list[schemas.MatchListOut])
def list_matches(profile: models.Profile = Depends(get_owned_profile), db: Session = Depends(get_db)):
    apps = {
        a.job_id: a
        for a in db.query(models.Application).filter(models.Application.profile_id == profile.id)
    }
    result = []
    for m in build_matches(db, profile):  # already within the active campaigns' bounds
        if m.state == "dismissed":
            continue
        a = apps.get(m.job_id)
        result.append(schemas.MatchListOut(
            id=m.id, job=m.job, score=float(m.score), breakdown=m.breakdown, state=m.state,
            application_id=a.id if a else None,
            application_status=a.status.value if a else None,
        ))
    return result


def _owned_match(db: Session, user: models.User, match_id: str) -> models.Match:
    match = (
        db.query(models.Match)
        .join(models.Profile)
        .filter(models.Match.id == match_id, models.Profile.user_id == user.id)
        .first()
    )
    if not match:
        raise HTTPException(404, "Match not found")
    return match


@router.patch("/matches/{match_id}", response_model=schemas.MatchOut)
def update_match(
    match_id: str,
    payload: schemas.MatchUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    match = _owned_match(db, current_user, match_id)
    match.state = payload.state
    db.commit()
    db.refresh(match)
    return match


@router.post("/matches/{match_id}/prepare", response_model=schemas.PrepareOut)
def prepare_match(
    match_id: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """"Prepare this one": get-or-create the Application, then the same RQ batch-prep
    task /applications/batch-prepare uses (tailor + truth-check -> ready_for_review).
    Only a `saved` (never prepared) application is enqueued, so a second press
    doesn't re-tailor."""
    match = _owned_match(db, current_user, match_id)
    application = (
        db.query(models.Application)
        .filter(models.Application.profile_id == match.profile_id, models.Application.job_id == match.job_id)
        .first()
    )
    if application is None:
        application = models.Application(
            profile_id=match.profile_id, job_id=match.job_id, status=models.ApplicationStatus.saved
        )
        db.add(application)
    match.state = "saved"
    _commit_new_application(db)
    db.refresh(application)
    if application.status != models.ApplicationStatus.saved:
        return schemas.PrepareOut(application_id=application.id, status=application.status.value, queued=False)
    try:
        get_queue().enqueue(prepare_applications_task, [application.id])
    except Exception:
        logging.getLogger(__name__).exception("prepare enqueue failed for %s", application.id)
        raise HTTPException(503, "Maggie couldn't start preparing this one right now. It's saved — try again in a minute.")
    return schemas.PrepareOut(application_id=application.id, status=application.status.value, queued=True)
