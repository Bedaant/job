"""Correctness of irreversible actions: one application per role, never a second send,
one shared daily ceiling, and sends on their own queue.

GAPS 4.3: the same role from two sources is two Job rows with one canonical_hash, and the
per-job lock cannot see the second Application. The guard is now a UNIQUE index on
(profile_id, role_key), role_key frozen from the job's hash when the application is made.
"""
from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy.exc import IntegrityError

import apply_email
import models
from outreach import send as outreach_send


def _user_profile(db, email="c@example.com"):
    user = models.User(email=email, password_hash="x")
    db.add(user)
    db.flush()
    profile = models.Profile(user_id=user.id, full_name="Asha Rao")
    db.add(profile)
    db.flush()
    fact = models.ResumeFact(profile_id=profile.id, category="experience",
                             achievement="Built a payments ledger in Python")
    db.add(fact)
    db.flush()
    return user, profile, fact


def _job(db, n, *, hash_=None, apply_url="mailto:hr@acme.com", source="linkedin_posts"):
    job = models.Job(source=source, external_id=f"e{n}", canonical_hash=hash_ or f"h{n}",
                     title="Backend Engineer", company="Acme", apply_url=apply_url)
    db.add(job)
    db.flush()
    return job


def _application(db, profile, fact, job, status=models.ApplicationStatus.approved):
    a = models.Application(
        profile_id=profile.id, job_id=job.id, status=status,
        tailored_resume_json={"bullets": [
            {"text": "Built a payments ledger in Python", "source_fact_ids": [fact.id]}]},
        tailored_cover_letter="Dear team, I built a ledger.",
    )
    db.add(a)
    db.commit()
    return a


def _send(db, application_id, sender):
    with patch("apply_email._sender_for", return_value=sender), patch("workers.jobs.get_queue"):
        return apply_email.send_application_email(db, application_id)


# --- 1. one application per role, enforced by the database -------------------------

def test_same_role_from_two_sources_cannot_get_two_applications(db_session):
    _, profile, fact = _user_profile(db_session)
    a = _job(db_session, 1, hash_="H", source="greenhouse")
    b = _job(db_session, 2, hash_="H", source="linkedin")
    _application(db_session, profile, fact, a)
    with pytest.raises(IntegrityError):
        _application(db_session, profile, fact, b)


def test_role_key_is_frozen_from_the_job_hash_at_creation(db_session):
    _, profile, fact = _user_profile(db_session)
    job = _job(db_session, 1, hash_="H")
    app = _application(db_session, profile, fact, job)
    job.canonical_hash = "H2"
    db_session.commit()
    db_session.refresh(app)
    assert app.role_key == "H"


def test_two_profiles_may_each_apply_to_the_same_role(db_session):
    _, p1, f1 = _user_profile(db_session, "one@example.com")
    _, p2, f2 = _user_profile(db_session, "two@example.com")
    job = _job(db_session, 1, hash_="H")
    _application(db_session, p1, f1, job)
    _application(db_session, p2, f2, job)


def test_campaign_never_picks_a_role_already_applied_through_another_source(db_session):
    import campaigns

    _, profile, fact = _user_profile(db_session)
    applied = _job(db_session, 1, hash_="H", source="greenhouse")
    other_source = _job(db_session, 2, hash_="H", source="linkedin")
    twin_a = _job(db_session, 3, hash_="T", source="greenhouse")
    twin_b = _job(db_session, 4, hash_="T", source="linkedin")
    _application(db_session, profile, fact, applied)
    for j in (other_source, twin_a, twin_b):
        db_session.add(models.Match(profile_id=profile.id, job_id=j.id, score=90, breakdown={}))
    campaign = models.Campaign(profile_id=profile.id, name="c", daily_cap=10, min_match_score=0.1,
                               remote_only=False, status=models.CampaignStatus.active)
    db_session.add(campaign)
    db_session.commit()

    picked = [m.job_id for m in campaigns.select_candidates(db_session, campaign, 10)]
    assert other_source.id not in picked
    assert len([j for j in picked if j in (twin_a.id, twin_b.id)]) == 1


def test_api_returns_409_for_a_second_application_to_the_same_role():
    from tests.test_submission_loop import _auth, _bind, _client

    client, SessionLocal = _client()
    _bind(client, SessionLocal)
    headers = _auth(client, "dup-role@example.com")
    profile = client.post("/profiles", headers=headers, json={"persona": "developer"}).json()
    db = SessionLocal()
    a = _job(db, 1, hash_="H", source="greenhouse")
    b = _job(db, 2, hash_="H", source="linkedin")
    db.commit()
    ids = (a.id, b.id)
    db.close()

    first = client.post("/applications", headers=headers, json={"profile_id": profile["id"], "job_id": ids[0]})
    assert first.status_code == 200
    second = client.post("/applications", headers=headers, json={"profile_id": profile["id"], "job_id": ids[1]})
    assert second.status_code == 409
    again = client.post("/applications", headers=headers, json={"profile_id": profile["id"], "job_id": ids[0]})
    assert again.status_code == 409


# --- 2. an ambiguous send is never re-approvable -----------------------------------

def test_raising_sender_lands_unconfirmed_so_a_reapproval_cannot_send_twice(db_session):
    """An exception after the provider accepted the mail is indistinguishable from one
    before it. `ready_for_review` let the user approve, and send, a second time."""
    _, profile, fact = _user_profile(db_session)
    app = _application(db_session, profile, fact, _job(db_session, 1))

    def boom(*args, **kw):
        raise TimeoutError("read timed out")

    assert _send(db_session, app.id, boom) == "unconfirmed"
    db_session.refresh(app)
    assert app.status == models.ApplicationStatus.submitted_unconfirmed
    assert "Sent folder" in app.notes


def test_falsy_sender_delivered_nothing_so_it_goes_back_to_review(db_session):
    _, profile, fact = _user_profile(db_session)
    app = _application(db_session, profile, fact, _job(db_session, 1))
    assert _send(db_session, app.id, lambda *a, **k: None) == "failed"
    db_session.refresh(app)
    assert app.status == models.ApplicationStatus.ready_for_review


class _Crash(BaseException):
    pass


def test_a_crash_mid_send_never_sends_on_retry(db_session):
    _, profile, fact = _user_profile(db_session)
    app = _application(db_session, profile, fact, _job(db_session, 1))
    calls = []

    def crash(*args, **kw):
        calls.append(1)
        raise _Crash()

    with pytest.raises(_Crash):
        _send(db_session, app.id, crash)
    db_session.rollback()
    assert _send(db_session, app.id, crash) == "not_approved"
    assert len(calls) == 1


# --- 3. one ceiling across channels, per user ---------------------------------------

def _sent_outreach(db, profile, application, n):
    for i in range(n):
        contact = models.Contact(profile_id=profile.id, company="Acme", full_name=f"P{i}",
                                 email=f"p{i}-{application.id[:6]}@acme.com")
        db.add(contact)
        db.flush()
        db.add(models.Outreach(profile_id=profile.id, application_id=application.id,
                               contact_id=contact.id, status=models.OutreachStatus.sent,
                               sent_at=datetime.utcnow()))
    db.commit()


def test_outreach_sends_count_against_email_applications(db_session):
    user, profile, fact = _user_profile(db_session)
    # A second persona of the same user: the ceiling is per Gmail account, not per profile.
    other = models.Profile(user_id=user.id, full_name="Asha Rao",
                           persona=models.Persona.product_manager)
    db_session.add(other)
    db_session.flush()
    host = _application(db_session, other, fact, _job(db_session, 100, apply_url="https://x.com/j"),
                        status=models.ApplicationStatus.applied)
    _sent_outreach(db_session, other, host, outreach_send.DAILY_CAP)
    emailed = outreach_send.ACCOUNT_DAILY_CAP - outreach_send.DAILY_CAP
    for i in range(emailed):
        done = _application(db_session, profile, fact, _job(db_session, i),
                            status=models.ApplicationStatus.applied)
        done.applied_at = datetime.utcnow()
    db_session.commit()
    assert emailed < apply_email.DAILY_CAP  # the per-channel cap alone would allow it

    app = _application(db_session, profile, fact, _job(db_session, 99))
    calls = []
    assert _send(db_session, app.id, lambda *a, **k: calls.append(1) or "id") == "daily_cap"
    assert calls == []


def test_email_applications_count_against_outreach(db_session):
    _, profile, fact = _user_profile(db_session)
    for i in range(apply_email.DAILY_CAP):
        done = _application(db_session, profile, fact, _job(db_session, i),
                            status=models.ApplicationStatus.applied)
        done.applied_at = datetime.utcnow()
    host = _application(db_session, profile, fact, _job(db_session, 50, apply_url="https://x.com/j"),
                        status=models.ApplicationStatus.applied)
    _sent_outreach(db_session, profile, host, outreach_send.ACCOUNT_DAILY_CAP - apply_email.DAILY_CAP)
    contact = models.Contact(profile_id=profile.id, company="Acme", full_name="Q", email="q@acme.com")
    db_session.add(contact)
    db_session.flush()
    row = models.Outreach(profile_id=profile.id, application_id=host.id, contact_id=contact.id,
                          status=models.OutreachStatus.approved, subject="s", body="b")
    db_session.add(row)
    db_session.commit()

    with patch("outreach.send._unsubscribe_is_reachable", return_value=True):
        assert outreach_send.claim_outreach(db_session, row.id, profile.id) == "daily_cap"
    assert row.status == models.OutreachStatus.approved


# --- 4. sends run on their own queue ------------------------------------------------

def test_outreach_approve_enqueues_on_the_effects_queue():
    from outreach import api

    with patch("workers.jobs.get_queue") as get_queue:
        api._enqueue_send("o-1")
    get_queue.assert_called_once_with(outreach_send.EFFECTS_QUEUE)


def test_batch_approve_enqueues_the_email_on_the_effects_queue():
    from tests.test_submission_loop import _auth, _bind, _client, _seed

    client, SessionLocal = _client()
    _bind(client, SessionLocal)
    headers = _auth(client, "effects@example.com")
    _, (app_id,) = _seed(client, headers, [models.ApplicationStatus.ready_for_review],
                         apply_url="mailto:hr@acme.com?x=")
    queue = MagicMock()
    with patch("workers.jobs.get_queue", return_value=queue) as get_queue:
        r = client.post("/applications/batch-approve", headers=headers, json={"application_ids": [app_id]})
    assert r.status_code == 200
    get_queue.assert_called_with(outreach_send.EFFECTS_QUEUE)
    queue.enqueue.assert_called_once()
