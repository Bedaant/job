import pytest
from fastapi import HTTPException

import models
from core.deps import get_owned_profile


def _make_user_and_profile(db, email):
    user = models.User(email=email, password_hash="x")
    db.add(user)
    db.flush()
    profile = models.Profile(user_id=user.id, persona=models.Persona.developer)
    db.add(profile)
    db.commit()
    return user, profile


def test_owner_can_access_own_profile(db_session):
    user, profile = _make_user_and_profile(db_session, "owner@example.com")
    result = get_owned_profile(profile.id, current_user=user, db=db_session)
    assert result.id == profile.id


def test_other_user_gets_404_not_someone_elses_profile(db_session):
    owner, profile = _make_user_and_profile(db_session, "owner@example.com")
    intruder, _ = _make_user_and_profile(db_session, "intruder@example.com")

    with pytest.raises(HTTPException) as exc_info:
        get_owned_profile(profile.id, current_user=intruder, db=db_session)

    assert exc_info.value.status_code == 404


def test_nonexistent_profile_gets_404(db_session):
    user, _ = _make_user_and_profile(db_session, "owner@example.com")
    with pytest.raises(HTTPException) as exc_info:
        get_owned_profile("00000000-0000-0000-0000-000000000000", current_user=user, db=db_session)
    assert exc_info.value.status_code == 404
