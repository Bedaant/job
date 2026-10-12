"""P0 #1: one `can_send()` gate on every path that reaches an employer, and an
allowed-transition table for Application.status.

Unmocked: real endpoints and services on a SQLite test DB. Only the LLM (tailoring)
and Redis (the queue) are faked.
"""
from unittest.mock import MagicMock, patch

import pytest

import apply_email
import campaigns
import models
import send_gate
from tests.test_submission_loop import _auth, _bind, _client, grounded

S = models.ApplicationStatus


def _seed(SessionLocal, email_or_profile_id, *, status=S.approved, flags=None, grounded=True,
          pending=None, with_fact=True, apply_url="https://acme.example/apply", n=0):
    """One application owned by `profile_id`; sendable unless told otherwise."""
    db = SessionLocal()
    profile_id = email_or_profile_id
    fact_id = "missing"
    if with_fact:
        fact = models.ResumeFact(profile_id=profile_id, category="experience",
                                 achievement="Built a payments ledger in Python")
        db.add(fact)
        db.flush()
        fact_id = fact.id
    job = models.Job(source="remoteok", external_id=f"g{n}", canonical_hash=f"gh{n}",
                     title="Backend Engineer", company="Acme", apply_url=apply_url)
    db.add(job)
    db.flush()
    app = models.Application(
        profile_id=profile_id, job_id=job.id, status=status,
        tailored_resume_json={"bullets": [{"text": "Built a payments ledger in Python",
                                           "source_fact_ids": [fact_id] if grounded else []}]},
        tailored_cover_letter="Dear team, I built a ledger.",
        flagged_unsupported_claims=flags or [],
        pending_questions=pending or [],
    )
    db.add(app)
    db.commit()
    app_id = app.id
    db.close()
    return app_id


def _setup(email):
    client, SessionLocal = _client()
    _bind(client, SessionLocal)
    headers = _auth(client, email)
    profile = client.post("/profiles", headers=headers, json={"persona": "developer"}).json()
    return client, SessionLocal, headers, profile["id"]


def _status(SessionLocal, app_id):
    db = SessionLocal()
    status = db.get(models.Application, app_id).status
    db.close()
    return status


# --- the predicate ----------------------------------------------------------------

@pytest.mark.parametrize("kwargs,reason", [
    ({"flags": ["Led a team of 50"]}, "flag"),
    ({"grounded": False}, "grounded"),
    ({"pending": [{"question": "Notice period?", "options": []}]}, "question"),
    ({"with_fact": False}, "facts"),
])
def test_can_send_refuses_each_blocker(kwargs, reason):
    _, SessionLocal, _, profile_id = _setup(f"gate-{reason}@example.com")
    app_id = _seed(SessionLocal, profile_id, **kwargs)
    db = SessionLocal()
    app = db.get(models.Application, app_id)
    ok, reasons = send_gate.can_send(db, app.profile.user, app)
    assert not ok
    assert any(reason in r.lower() for r in reasons), reasons


def test_can_send_passes_a_clean_application():
    _, SessionLocal, _, profile_id = _setup("gate-ok@example.com")
    app_id = _seed(SessionLocal, profile_id)
    db = SessionLocal()
    app = db.get(models.Application, app_id)
    assert send_gate.can_send(db, app.profile.user, app) == (True, [])


# --- auto mode: the plan's "done when" ----------------------------------------------

def test_auto_submit_with_one_hard_flag_leaves_ready_for_review_and_sends_nothing(db_session):
    user = models.User(email="auto@example.com", password_hash="x")
    db_session.add(user)
    db_session.flush()
    profile = models.Profile(user_id=user.id, full_name="Asha Rao")
    db_session.add(profile)
    db_session.flush()
    db_session.add(models.ResumeFact(profile_id=profile.id, category="experience",
                                     achievement="Built a payments ledger in Python"))
    job = models.Job(source="linkedin_posts", external_id="a1", canonical_hash="ah1", remote=True,
                     title="Backend Engineer", company="Acme", apply_url="mailto:hr@acme.com")
    db_session.add(job)
    db_session.flush()
    db_session.add(models.Match(profile_id=profile.id, job_id=job.id, score=95, breakdown={}, state="new"))
    campaign = models.Campaign(profile_id=profile.id, name="c", status=models.CampaignStatus.active,
                               daily_cap=3, auto_submit=True)
    db_session.add(campaign)
    db_session.commit()

    def tailor(job_dict, facts):  # the LLM, faked: one grounded bullet, one hard flag
        return {"summary": "s", "cover_letter": "Dear team",
                "bullets": [{"text": "Built a ledger", "source_fact_ids": [facts[0]["id"]]}],
                "flagged_unsupported_claims": ["Led a team of 50"]}

    queue = MagicMock()
    with patch("batch_prep.tailor_application", side_effect=tailor), \
         patch("workers.jobs.get_queue", return_value=queue):
        result = campaigns.run_campaign(db_session, campaign)

    row = db_session.query(models.Application).one()
    assert result["prepared"] == 1
    assert row.status == S.ready_for_review
    queue.enqueue.assert_not_called()


# --- every path refuses a blocked application ---------------------------------------

def test_batch_approve_refuses_a_flagged_application_and_changes_nothing():
    client, SessionLocal, headers, profile_id = _setup("ba-flag@example.com")
    clean = _seed(SessionLocal, profile_id, status=S.ready_for_review, n=1)
    flagged = _seed(SessionLocal, profile_id, status=S.ready_for_review, flags=["Led 50"], n=2)
    resp = client.post("/applications/batch-approve", headers=headers,
                       json={"application_ids": [clean, flagged]})
    assert resp.status_code == 409
    assert _status(SessionLocal, clean) == S.ready_for_review
    assert _status(SessionLocal, flagged) == S.ready_for_review


def test_claim_submission_refuses_when_the_gate_fails():
    client, SessionLocal, headers, profile_id = _setup("claim-flag@example.com")
    app_id = _seed(SessionLocal, profile_id, flags=["Led 50"])
    resp = client.post(f"/applications/{app_id}/claim-submission", headers=headers)
    assert resp.status_code == 409
    assert _status(SessionLocal, app_id) == S.approved


def test_patch_to_approved_refuses_a_flagged_application():
    client, SessionLocal, headers, profile_id = _setup("patch-flag@example.com")
    app_id = _seed(SessionLocal, profile_id, status=S.ready_for_review, flags=["Led 50"])
    resp = client.patch(f"/applications/{app_id}", headers=headers, json={"status": "approved"})
    assert resp.status_code == 409
    assert _status(SessionLocal, app_id) == S.ready_for_review


def test_email_send_refuses_a_flagged_application(db_session):
    user = models.User(email="mail-flag@example.com", password_hash="x")
    db_session.add(user)
    db_session.flush()
    profile = models.Profile(user_id=user.id, full_name="Asha Rao")
    db_session.add(profile)
    db_session.commit()
    app_id = _seed(lambda: db_session, profile.id, flags=["Led 50"], apply_url="mailto:hr@acme.com")
    sender = MagicMock(return_value="msg-1")
    with patch("apply_email._sender_for", return_value=sender):
        assert apply_email.send_application_email(db_session, app_id) == "blocked"
    sender.assert_not_called()
    assert db_session.get(models.Application, app_id).status == S.ready_for_review


def test_ready_to_send_list_excludes_an_ungrounded_application():
    client, SessionLocal, headers, profile_id = _setup("list-ground@example.com")
    good = _seed(SessionLocal, profile_id, status=S.ready_for_review, n=1)
    _seed(SessionLocal, profile_id, status=S.ready_for_review, grounded=False, n=2)
    rows = client.get(f"/applications/ready-to-send?profile_id={profile_id}", headers=headers).json()
    assert [r["id"] for r in rows] == [good]


# --- the transition table ------------------------------------------------------------

def test_submitting_to_approved_is_rejected():
    client, SessionLocal, headers, profile_id = _setup("trans@example.com")
    app_id = _seed(SessionLocal, profile_id, status=S.submitting)
    resp = client.patch(f"/applications/{app_id}", headers=headers, json={"status": "approved"})
    assert resp.status_code == 409
    assert _status(SessionLocal, app_id) == S.submitting


def test_transition_table_refuses_a_jump_into_submitting():
    app = models.Application(status=S.ready_for_review)
    with pytest.raises(send_gate.InvalidTransition):
        send_gate.transition(app, S.submitting)
    assert app.status == S.ready_for_review
    send_gate.transition(app, S.approved)
    send_gate.transition(app, S.submitting)
    assert app.status == S.submitting
