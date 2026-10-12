"""Resume facts KB, tailoring, JSON Resume export."""

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy.orm import Session

from core.deps import get_current_user, get_owned_profile, resolve_profile_ownership
from database import get_db
import models
import schemas
from tailoring.engine import tailor_application
from matching.service import refresh_fact_vectors
from parsing.jsonresume_export import facts_to_jsonresume

router = APIRouter()

# ---------- Resume facts KB ----------

@router.get("/resume-facts", response_model=list[schemas.ResumeFactOut])
def list_resume_facts(profile: models.Profile = Depends(get_owned_profile), db: Session = Depends(get_db)):
    return db.query(models.ResumeFact).filter(models.ResumeFact.profile_id == profile.id).all()


@router.post("/resume-facts", response_model=schemas.ResumeFactOut)
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


def _owned_fact(db: Session, user: models.User, fact_id: str) -> models.ResumeFact:
    fact = (
        db.query(models.ResumeFact)
        .join(models.Profile, models.Profile.id == models.ResumeFact.profile_id)
        .filter(models.ResumeFact.id == fact_id, models.Profile.user_id == user.id)
        .first()
    )
    if not fact:
        raise HTTPException(404, "Fact not found")
    return fact


@router.patch("/resume-facts/{fact_id}", response_model=schemas.ResumeFactOut)
def update_resume_fact(
    fact_id: str,
    payload: schemas.ResumeFactPatch,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Future tailoring only: applications already tailored keep their own copy
    of the bullet text (tailored_resume_json)."""
    fact = _owned_fact(db, current_user, fact_id)
    changes = payload.model_dump(exclude_unset=True)
    if "achievement" in changes and changes["achievement"] != fact.achievement:
        fact.embedding = None  # never match on a vector of words that are gone
    for key, value in changes.items():
        setattr(fact, key, value)
    if fact.embedding is None:
        db.flush()
        refresh_fact_vectors(db, fact.profile)
    db.commit()
    db.refresh(fact)
    return fact


@router.delete("/resume-facts/{fact_id}", status_code=204)
def delete_resume_fact(
    fact_id: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    fact = _owned_fact(db, current_user, fact_id)
    profile = fact.profile
    db.delete(fact)
    db.flush()
    refresh_fact_vectors(db, profile)
    db.commit()
    return Response(status_code=204)


# ---------- Tailoring ----------

@router.post("/tailor", response_model=schemas.TailorResponse)
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


@router.get("/resume-facts:jsonresume")
def export_resume_facts_jsonresume(profile: models.Profile = Depends(get_owned_profile), db: Session = Depends(get_db)):
    """JSON Resume schema export (jsonresume.org, DEPENDENCIES.md §3)."""
    facts = db.query(models.ResumeFact).filter(models.ResumeFact.profile_id == profile.id).all()
    facts_dicts = [
        {"category": f.category, "achievement": f.achievement, "proof": f.proof, "metric": f.metric, "tags": f.tags}
        for f in facts
    ]
    return facts_to_jsonresume(facts_dicts)
