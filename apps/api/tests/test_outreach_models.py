"""REACH-B — the outreach tables (`docs/PLAN-OUTREACH.md`).

These pin the three properties that are enforced in the SCHEMA rather than in code,
because each one guards something a later code change could otherwise quietly undo:

- one email per person per application (`Outreach`),
- one contact row per address per profile, and contacts never shared across profiles
  (`Contact`),
- a suppression that applies to everyone, not just the user who caused it
  (`Suppression.profile_id IS NULL`).
"""
import pytest
from sqlalchemy.exc import IntegrityError

import models


def _profile(db, email="a@example.com"):
    user = models.User(email=email, password_hash="x")
    db.add(user)
    db.flush()
    profile = models.Profile(user_id=user.id, full_name="Asha Rao")
    db.add(profile)
    db.flush()
    return profile


def _job(db, company="Acme", title="Product Manager"):
    job = models.Job(
        source="clipped", external_id=f"e-{company}-{title}", canonical_hash=f"h-{company}-{title}",
        title=title, company=company, apply_url="https://example.com/job",
    )
    db.add(job)
    db.flush()
    return job


def _application(db, profile, job):
    app = models.Application(profile_id=profile.id, job_id=job.id)
    db.add(app)
    db.flush()
    return app


# ---------- Profile additions ----------

def test_auto_send_is_off_by_default(db_session):
    """PRD section 2 keeps a human in the loop. Auto-send is earned, never the default."""
    p = _profile(db_session)
    db_session.commit()
    assert p.outreach_auto_send is False
    assert p.outreach_contacts_per_application == 2


# ---------- Contact ----------

def test_contact_is_unique_per_profile_and_email(db_session):
    p = _profile(db_session)
    db_session.add(models.Contact(profile_id=p.id, company="Acme", full_name="B", email="b@acme.com"))
    db_session.commit()
    db_session.add(models.Contact(profile_id=p.id, company="Acme", full_name="B again", email="b@acme.com"))
    with pytest.raises(IntegrityError):
        db_session.commit()


def test_the_same_contact_may_exist_for_two_profiles(db_session):
    """Contacts are profile-scoped, so two users independently finding the same person
    is normal. A global unique constraint would make one user's lookup fail because of
    another user's data, and leak that they had it."""
    a = _profile(db_session, "a@example.com")
    b = _profile(db_session, "b@example.com")
    db_session.add(models.Contact(profile_id=a.id, company="Acme", full_name="B", email="b@acme.com"))
    db_session.add(models.Contact(profile_id=b.id, company="Acme", full_name="B", email="b@acme.com"))
    db_session.commit()
    assert db_session.query(models.Contact).count() == 2


def test_contacts_are_not_visible_across_profiles(db_session):
    """The privacy property of profile scoping — user A must not be able to infer who
    user B is contacting."""
    a = _profile(db_session, "a@example.com")
    b = _profile(db_session, "b@example.com")
    db_session.add(models.Contact(profile_id=a.id, company="Acme", full_name="Only A's", email="x@acme.com"))
    db_session.commit()
    assert db_session.query(models.Contact).filter(models.Contact.profile_id == b.id).count() == 0


def test_contact_may_exist_before_an_email_is_known(db_session):
    """An adapter can learn who someone is before how to reach them. The unique
    constraint must not collapse two unknown-email contacts into one."""
    p = _profile(db_session)
    db_session.add(models.Contact(profile_id=p.id, company="Acme", full_name="One"))
    db_session.add(models.Contact(profile_id=p.id, company="Acme", full_name="Two"))
    db_session.commit()
    assert db_session.query(models.Contact).count() == 2


# ---------- Outreach ----------

def test_outreach_is_unique_per_application_and_contact(db_session):
    """In draft-or-send terms alike: one ask per person per application. This is the
    duplicate guarantee, in the schema rather than in a code path that could be
    refactored around."""
    p = _profile(db_session)
    app = _application(db_session, p, _job(db_session))
    c = models.Contact(profile_id=p.id, company="Acme", full_name="B", email="b@acme.com")
    db_session.add(c)
    db_session.flush()
    db_session.add(models.Outreach(profile_id=p.id, application_id=app.id, contact_id=c.id))
    db_session.commit()
    db_session.add(models.Outreach(profile_id=p.id, application_id=app.id, contact_id=c.id))
    with pytest.raises(IntegrityError):
        db_session.commit()


def test_outreach_starts_ready_for_review(db_session):
    p = _profile(db_session)
    app = _application(db_session, p, _job(db_session))
    c = models.Contact(profile_id=p.id, company="Acme", full_name="B", email="b@acme.com")
    db_session.add(c)
    db_session.flush()
    o = models.Outreach(profile_id=p.id, application_id=app.id, contact_id=c.id)
    db_session.add(o)
    db_session.commit()
    assert o.status is models.OutreachStatus.ready_for_review
    assert o.flagged_unsupported_claims == []
    assert o.approved_by is None, "nothing is approved until someone or something approves it"


def test_outreach_status_covers_the_whole_send_path(db_session):
    """`sending` exists so the at-most-once lock has a state to claim into — the same
    shape as the application-side `approved -> submitting` transition."""
    names = {s.name for s in models.OutreachStatus}
    assert {"ready_for_review", "approved", "sending", "sent", "skipped", "failed"} <= names


def test_skipping_records_a_reason(db_session):
    """A skip must never be a silent no-op: no contact found, suppressed and
    unverifiable are different outcomes and the user is owed the difference."""
    p = _profile(db_session)
    app = _application(db_session, p, _job(db_session))
    o = models.Outreach(
        profile_id=p.id, application_id=app.id, contact_id=None,
        status=models.OutreachStatus.skipped, skip_reason="no_contact_found",
    )
    db_session.add(o)
    db_session.commit()
    assert o.contact_id is None, "a skip for 'nobody found' has no contact to point at"
    assert o.skip_reason == "no_contact_found"


# ---------- Suppression ----------

def test_a_global_suppression_has_no_profile(db_session):
    """Someone who asks not to be contacted should not have to ask each user
    separately, so an opt-out writes `profile_id IS NULL`."""
    s = models.Suppression(profile_id=None, email="no@acme.com", reason="opt_out")
    db_session.add(s)
    db_session.commit()
    assert s.profile_id is None


def test_suppression_can_be_scoped_to_one_profile(db_session):
    p = _profile(db_session)
    db_session.add(models.Suppression(profile_id=p.id, email="x@acme.com", reason="manual"))
    db_session.commit()
    assert db_session.query(models.Suppression).filter_by(profile_id=p.id).count() == 1


def test_suppression_can_cover_a_whole_domain(db_session):
    """A company asking to be left alone entirely is one row, not one per employee."""
    db_session.add(models.Suppression(profile_id=None, domain="acme.com", reason="opt_out"))
    db_session.commit()
    assert db_session.query(models.Suppression).filter_by(domain="acme.com").count() == 1
