"""P0 #7: delete my account. Hard delete of every row the user owns (DPDP: erasure on request).

Global tables (jobs, title_verdicts, form plans, connector runs, ATS controls) hold no
personal data and stay. Global suppressions (profile_id NULL) are recipients' opt-outs,
not the user's data, and stay. tests/test_account_deletion.py fails if a new table that
points at users/profiles/applications is added without being listed here.
"""
from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session

import models
from core.deps import get_current_user
from database import get_db
from outreach import gmail

router = APIRouter(tags=["account"])

M = models
# Children before parents, so this works with or without database-level cascades.
_BY_APPLICATION = [M.FillSnapshot]
_BY_PROFILE = [M.Outreach, M.Contact, M.Suppression, M.Application, M.Match, M.Campaign,
               M.ResumeFact, M.ResumeUpload, M.AnswerBank]
_BY_USER = [M.Profile, M.Event, M.Notification, M.GmailCredential]
COVERED_TABLES = [m.__tablename__ for m in _BY_APPLICATION + _BY_PROFILE + _BY_USER] + ["users"]


def delete_account(db: Session, user: models.User) -> None:
    gmail.revoke(db, user.id)  # best effort at Google; the row is deleted below either way
    profiles = db.query(M.Profile.id).filter(M.Profile.user_id == user.id).scalar_subquery()
    apps = db.query(M.Application.id).filter(M.Application.profile_id.in_(profiles)).scalar_subquery()
    for model in _BY_APPLICATION:
        db.query(model).filter(model.application_id.in_(apps)).delete(synchronize_session=False)
    for model in _BY_PROFILE:
        db.query(model).filter(model.profile_id.in_(profiles)).delete(synchronize_session=False)
    for model in _BY_USER:
        db.query(model).filter(model.user_id == user.id).delete(synchronize_session=False)
    db.query(M.User).filter(M.User.id == user.id).delete(synchronize_session=False)
    db.commit()


@router.delete("/account", status_code=204)
def delete_my_account(user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    delete_account(db, user)
    return Response(status_code=204)
