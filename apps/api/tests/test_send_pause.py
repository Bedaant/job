"""P0 #2: a global (owner) and a per-user "pause all sends" switch, folded into
send_gate.can_send, and a per-user sent log.

Unmocked: real endpoints and services on a SQLite test DB; only the LLM, Redis and the
mail sender are faked. Every send path gets one test per switch.
"""
from unittest.mock import MagicMock, patch

import pytest

import apply_email
import campaigns
import models
import send_gate
from outreach.send import claim_outreach, send_outreach
from tests.test_outreach_send import _outreach
from tests.test_send_gate import _seed, _setup, _status

S = models.ApplicationStatus
MODES = ["user", "global"]


def _pause_in(db, user_id, mode):
    if mode == "global":
        db.add(models.AppFlag(name=send_gate.GLOBAL_PAUSE, enabled=True))
    else:
        db.get(models.User, user_id).sends_paused = True
    db.commit()


def _pause(SessionLocal, profile_id, mode):
    db = SessionLocal()
    _pause_in(db, db.get(models.Profile, profile_id).user_id, mode)
    db.close()


@pytest.fixture(autouse=True)
def _public_base_url(monkeypatch):
    from core.config import get_settings

    get_settings.cache_clear()
    monkeypatch.setattr(get_settings(), "api_base_url", "https://api.applyscout.in", raising=False)
    yield
    get_settings.cache_clear()


# --- switch on = zero sends, per path ---------------------------------------------

@pytest.mark.parametrize("mode", MODES)
def test_paused_batch_approve_approves_nothing(mode):
    client, SessionLocal, headers, profile_id = _setup(f"p-ba-{mode}@example.com")
    app_id = _seed(SessionLocal, profile_id, status=S.ready_for_review, apply_url="mailto:hr@acme.com")
    _pause(SessionLocal, profile_id, mode)
    queue = MagicMock()
    with patch("workers.jobs.get_queue", return_value=queue):
        resp = client.post("/applications/batch-approve", headers=headers, json={"application_ids": [app_id]})
    assert resp.status_code == 409
    assert _status(SessionLocal, app_id) == S.ready_for_review
    queue.enqueue.assert_not_called()


@pytest.mark.parametrize("mode", MODES)
def test_paused_claim_submission_is_refused(mode):
    client, SessionLocal, headers, profile_id = _setup(f"p-claim-{mode}@example.com")
    app_id = _seed(SessionLocal, profile_id)
    _pause(SessionLocal, profile_id, mode)
    assert client.post(f"/applications/{app_id}/claim-submission", headers=headers).status_code == 409
    assert _status(SessionLocal, app_id) == S.approved


@pytest.mark.parametrize("mode", MODES)
def test_paused_patch_to_approved_is_refused(mode):
    client, SessionLocal, headers, profile_id = _setup(f"p-patch-{mode}@example.com")
    app_id = _seed(SessionLocal, profile_id, status=S.ready_for_review)
    _pause(SessionLocal, profile_id, mode)
    resp = client.patch(f"/applications/{app_id}", headers=headers, json={"status": "approved"})
    assert resp.status_code == 409
    assert _status(SessionLocal, app_id) == S.ready_for_review


@pytest.mark.parametrize("mode", MODES)
def test_paused_extension_work_queue_hands_out_nothing(mode):
    client, SessionLocal, headers, profile_id = _setup(f"p-wq-{mode}@example.com")
    _seed(SessionLocal, profile_id)
    _pause(SessionLocal, profile_id, mode)
    assert client.get("/extension/work-queue", headers=headers).json() == []


@pytest.mark.parametrize("mode", MODES)
def test_paused_campaign_auto_mode_approves_nothing(mode, db_session):
    user = models.User(email=f"p-auto-{mode}@example.com", password_hash="x")
    db_session.add(user)
    db_session.flush()
    profile = models.Profile(user_id=user.id, full_name="Asha Rao")
    db_session.add(profile)
    db_session.flush()
    db_session.add(models.ResumeFact(profile_id=profile.id, category="experience", achievement="Built a ledger"))
    job = models.Job(source="linkedin_posts", external_id="a1", canonical_hash="ah1", remote=True,
                     title="Backend Engineer", company="Acme", apply_url="mailto:hr@acme.com")
    db_session.add(job)
    db_session.flush()
    db_session.add(models.Match(profile_id=profile.id, job_id=job.id, score=95, breakdown={}, state="new"))
    campaign = models.Campaign(profile_id=profile.id, name="c", status=models.CampaignStatus.active,
                               daily_cap=3, auto_submit=True)
    db_session.add(campaign)
    db_session.commit()
    _pause_in(db_session, user.id, mode)

    def tailor(job_dict, facts):  # the LLM, faked: clean and grounded
        return {"summary": "s", "cover_letter": "Dear team", "flagged_unsupported_claims": [],
                "bullets": [{"text": "Built a ledger", "source_fact_ids": [facts[0]["id"]]}]}

    queue = MagicMock()
    with patch("batch_prep.tailor_application", side_effect=tailor), \
         patch("workers.jobs.get_queue", return_value=queue):
        campaigns.run_campaign(db_session, campaign)
    assert db_session.query(models.Application).one().status == S.ready_for_review
    queue.enqueue.assert_not_called()


@pytest.mark.parametrize("mode", MODES)
def test_paused_email_application_sends_nothing(mode, db_session):
    user = models.User(email=f"p-mail-{mode}@example.com", password_hash="x")
    db_session.add(user)
    db_session.flush()
    profile = models.Profile(user_id=user.id, full_name="Asha Rao")
    db_session.add(profile)
    db_session.commit()
    profile_id, user_id = profile.id, user.id
    app_id = _seed(lambda: db_session, profile_id, apply_url="mailto:hr@acme.com")
    _pause_in(db_session, user_id, mode)
    sender = MagicMock(return_value="msg-1")
    with patch("apply_email._sender_for", return_value=sender):
        assert apply_email.send_application_email(db_session, app_id) == "blocked"
    sender.assert_not_called()


@pytest.mark.parametrize("mode", MODES)
def test_paused_outreach_approve_is_refused(mode):
    client, SessionLocal, headers, profile_id = _setup(f"p-oa-{mode}@example.com")
    db = SessionLocal()
    row_id = _outreach(db, db.get(models.Profile, profile_id), status=models.OutreachStatus.ready_for_review).id
    db.commit()
    db.close()
    _pause(SessionLocal, profile_id, mode)
    with patch("outreach.api._enqueue_send") as enqueue:
        assert client.post(f"/outreach/{row_id}/approve", headers=headers).status_code == 409
    enqueue.assert_not_called()


@pytest.mark.parametrize("mode", MODES)
def test_paused_outreach_send_task_claims_nothing(mode, db_session):
    user = models.User(email=f"p-os-{mode}@example.com", password_hash="x")
    db_session.add(user)
    db_session.flush()
    profile = models.Profile(user_id=user.id, full_name="Asha Rao")
    db_session.add(profile)
    db_session.flush()
    row = _outreach(db_session, profile)
    db_session.commit()
    _pause_in(db_session, user.id, mode)
    assert claim_outreach(db_session, row.id, row.profile_id) == "paused"
    assert row.status is models.OutreachStatus.approved, "held, not dropped: it sends once unpaused"


# --- the switches themselves -------------------------------------------------------

def test_user_flips_their_own_pause():
    client, _, headers, _ = _setup("flip@example.com")
    assert client.get("/send-safety", headers=headers).json() == {"paused": False, "paused_globally": False}
    assert client.put("/send-safety", headers=headers, json={"paused": True}).json()["paused"] is True
    assert client.get("/send-safety", headers=headers).json()["paused"] is True


def test_only_an_owner_flips_the_global_pause(monkeypatch):
    monkeypatch.setenv("OWNER_EMAILS", "owner@example.com")
    client, _, owner, _ = _setup("owner@example.com")
    from tests.test_submission_loop import _auth
    other = _auth(client, "someone@example.com")
    assert client.put("/ops/send-pause", headers=other, json={"paused": True}).status_code == 403
    assert client.put("/ops/send-pause", headers=owner, json={"paused": True}).status_code == 200
    assert client.get("/send-safety", headers=other).json()["paused_globally"] is True
    assert client.put("/ops/send-pause", headers=owner, json={"paused": False}).status_code == 200
    assert client.get("/send-safety", headers=other).json()["paused_globally"] is False


# --- the sent log ------------------------------------------------------------------

def test_sent_log_lists_every_submission_and_email_and_only_the_callers():
    client, SessionLocal, headers, profile_id = _setup("log@example.com")
    web = _seed(SessionLocal, profile_id, n=1)
    mail = _seed(SessionLocal, profile_id, apply_url="mailto:hr@acme.com", n=2)
    assert client.post(f"/applications/{web}/claim-submission", headers=headers).status_code == 200

    db = SessionLocal()
    with patch("apply_email._sender_for", return_value=MagicMock(return_value="msg-1")), \
         patch("workers.jobs.get_queue"):
        assert apply_email.send_application_email(db, mail) == "sent"
    row = _outreach(db, db.get(models.Profile, profile_id), email="cto@acme.com")
    row.status = models.OutreachStatus.sending
    assert send_outreach(db, row, lambda to, subject, body: "msg-2")
    db.commit()
    db.close()

    log = client.get("/sent-log", headers=headers).json()
    assert sorted((e["kind"], e["recipient"]) for e in log) == [
        ("email", "hr@acme.com"),
        ("outreach_email", "cto@acme.com"),
        ("submission", "https://acme.example/apply"),
    ]
    assert {e["application_id"] for e in log if e["kind"] != "outreach_email"} == {web, mail}

    from tests.test_submission_loop import _auth
    stranger = _auth(client, "stranger@example.com")
    assert client.get("/sent-log", headers=stranger).json() == []
