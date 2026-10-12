"""Helpers used by more than one route module."""

from fastapi import HTTPException
from fastapi.responses import Response
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

import models
from documents.tailored_resume import DOCX_MIME, ResumeNotRenderable, render_verified_resume


_DUPLICATE_ROLE = "You already have an application for this role (possibly listed by another source)."


def _commit_new_application(db: Session) -> None:
    """uq_application_profile_job / uq_application_profile_role: a duplicate is a 409, not a 500."""
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, _DUPLICATE_ROLE)


def _verified_resume_response(profile: models.Profile, facts_list: list[dict], filename: str) -> Response:
    try:
        docx_bytes = render_verified_resume(profile, facts_list)
    except ResumeNotRenderable as exc:
        raise HTTPException(500, str(exc)) from None

    return Response(
        content=docx_bytes,
        media_type=DOCX_MIME,
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )
