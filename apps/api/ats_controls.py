"""Owner controls over the extension fill (architecture plan section 10): a per-ATS kill switch,
form-plan rollback, and the fill snapshot the extension posts after each page.

The switch is enforced at /extension/map-fields (ensure_fill_enabled), the call every fill makes
before it touches the page. So an unreachable server means no fill at all, never a stale "on".
"""
from typing import List, Literal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

import formplans
import models
from connectors.apply_target import _detect
from core.deps import get_current_user, require_owner
from database import get_db

router = APIRouter()
current_user = get_current_user


def _ats_of(ats_type: str | None, url: str | None) -> str | None:
    return (ats_type or _detect(url or "")[0] or "").lower() or None


def paused_ats(db: Session) -> set[str]:
    return {a for (a,) in db.query(models.AtsControl.ats).filter(models.AtsControl.fill_enabled.is_(False))}


def ensure_fill_enabled(db: Session, ats_type: str | None, url: str | None) -> None:
    """423 when the owner paused this ATS. The page URL decides when the client sends no type."""
    ats = _ats_of(ats_type, url)
    if ats and ats in paused_ats(db):
        raise HTTPException(423, f"Filling paused for {ats}. ApplyScout left this page untouched.")


class SwitchIn(BaseModel):
    fill_enabled: bool


@router.get("/admin/ats-controls")
def list_switches(db: Session = Depends(get_db), _: models.User = Depends(require_owner)) -> dict[str, bool]:
    return {r.ats: r.fill_enabled for r in db.query(models.AtsControl).order_by(models.AtsControl.ats)}


@router.put("/admin/ats-controls/{ats}")
def set_switch(ats: str, payload: SwitchIn, db: Session = Depends(get_db), _: models.User = Depends(require_owner)):
    ats = ats.lower()[:32]
    row = db.get(models.AtsControl, ats) or models.AtsControl(ats=ats)
    row.fill_enabled = payload.fill_enabled
    db.add(row)
    db.commit()
    return {"ats": ats, "fill_enabled": row.fill_enabled}


class RollbackIn(BaseModel):
    version: int = Field(ge=1)


@router.get("/admin/form-plans/{job_id}/versions")
def list_versions(job_id: str, db: Session = Depends(get_db), _: models.User = Depends(require_owner)):
    row = db.query(models.FormPlan).filter(models.FormPlan.job_id == job_id).first()
    if not row:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No plan for this job")
    versions = (db.query(models.FormPlanVersion).filter_by(form_plan_id=row.id)
                .order_by(models.FormPlanVersion.version.desc()).all())
    return {"active": row.version, "versions": [
        {"version": v.version, "fingerprint": v.fingerprint, "fields": len(v.plan.get("fields", [])),
         "created_at": v.created_at} for v in versions
    ]}


@router.post("/admin/form-plans/{job_id}/rollback")
def rollback_plan(job_id: str, payload: RollbackIn, db: Session = Depends(get_db), _: models.User = Depends(require_owner)):
    row = formplans.rollback(db, job_id, payload.version)
    if not row:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such plan version")
    return {"job_id": job_id, "version": row.version}


class SnapshotField(BaseModel):
    model_config = ConfigDict(extra="forbid")  # a stray `value` is refused, not silently stored

    label: str = Field(max_length=200)
    source: str = Field(max_length=64)
    status: Literal["filled", "flagged", "left_blank", "skipped"]
    required: bool = False


class SnapshotIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    application_id: str = Field(max_length=36)
    page: int = Field(ge=1, le=20)
    fields: List[SnapshotField] = Field(max_length=300)


@router.post("/extension/fill-snapshots", status_code=201)
def post_snapshot(payload: SnapshotIn, db: Session = Depends(get_db), user: models.User = Depends(current_user)):
    application = (
        db.query(models.Application)
        .join(models.Profile, models.Application.profile_id == models.Profile.id)
        .filter(models.Application.id == payload.application_id, models.Profile.user_id == user.id)
        .first()
    )
    if not application:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Application not found")
    record = payload.model_dump(exclude={"application_id"})
    db.add(models.FillSnapshot(
        application_id=application.id, plan_version=formplans.active_version(db, application.job_id), record=record,
    ))
    db.commit()
    return {"ok": True}
