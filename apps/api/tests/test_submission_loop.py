"""Phase 1 of ADR-015's execution loop: approved -> submitting -> applied.

The gap this closes: `run_campaign_task` produced `approved` applications and
nothing ever collected them, so a campaign ended in a queue rather than a sent
application. Three connections were missing — a work queue for the extension to
pull, a driver, and outcome reporting.

The correctness fix that had to come first: claim-submission used to flip
straight to `applied` *before* the native form submit fired. A form that then
failed left the user believing they had applied when they had not. `submitting`
names that window; `POST /submission-result` closes it exactly one of three ways:
  submitted   -> applied          (terminal, the real send happened)
  failed      -> approved         (retryable: the form never went through)
  needs_human -> ready_for_review (lands in the existing review queue)
"""
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import main
import models
from database import Base, get_db


def _client():
    engine = create_engine(
        "sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    TestSessionLocal = sessionmaker(bind=engine)

    def override_get_db():
        db = TestSessionLocal()
        try:
            yield db
        finally:
            db.close()

    main.app.dependency_overrides[get_db] = override_get_db
    return TestClient(main.app), TestSessionLocal


def _auth(client, email):
    client.post("/auth/signup", json={"email": email, "password": "correct horse battery staple"})
    token = client.post(
        "/auth/login", data={"username": email, "password": "correct horse battery staple"}
    ).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def _seed(client, headers, statuses, apply_url="https://acme.example/apply"):
    """Returns (profile_id, [application_id...]) with one job per application."""
    profile = client.post("/profiles", headers=headers, json={"persona": "developer"}).json()
    _, SessionLocal = client._jc_session
    db = SessionLocal()
    ids = []
    for i, status in enumerate(statuses):
        job = models.Job(
            source="remoteok", external_id=f"e{i}", canonical_hash=f"h{i}",
            title=f"Backend Engineer {i}", company="Acme", apply_url=f"{apply_url}/{i}",
        )
        db.add(job)
        db.commit()
        application = models.Application(profile_id=profile["id"], job_id=job.id, status=status)
        db.add(application)
        db.commit()
        ids.append(application.id)
    db.close()
    return profile["id"], ids


def _bind(client, SessionLocal):
    client._jc_session = (client, SessionLocal)
    return client


def _status(SessionLocal, application_id):
    db = SessionLocal()
    row = db.query(models.Application).filter(models.Application.id == application_id).first()
    status, applied_at, notes = row.status, row.applied_at, row.notes
    db.close()
    return status, applied_at, notes


# --- the work queue -----------------------------------------------------------

def test_work_queue_returns_only_approved_applications_with_their_apply_url():
    client, SessionLocal = _client()
    _bind(client, SessionLocal)
    headers = _auth(client, "wq@example.com")
    _seed(client, headers, [
        models.ApplicationStatus.approved,
        models.ApplicationStatus.ready_for_review,
        models.ApplicationStatus.applied,
        models.ApplicationStatus.saved,
    ])

    resp = client.get("/extension/work-queue", headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 1, "only `approved` applications are work; everything else is not"
    item = body[0]
    # The extension cannot do anything without somewhere to navigate to.
    assert item["apply_url"].startswith("https://acme.example/apply")
    assert item["company"] == "Acme"
    assert item["title"].startswith("Backend Engineer")
    assert item["application_id"]


def test_work_queue_never_leaks_another_users_applications():
    client, SessionLocal = _client()
    _bind(client, SessionLocal)
    theirs = _auth(client, "them@example.com")
    _seed(client, theirs, [models.ApplicationStatus.approved])

    mine = _auth(client, "me@example.com")
    resp = client.get("/extension/work-queue", headers=mine)
    assert resp.status_code == 200
    assert resp.json() == []


def test_work_queue_skips_an_application_whose_job_has_no_apply_url():
    """A job with no apply_url is unactionable — handing it to the driver would
    produce a guaranteed failure report and burn a retry."""
    client, SessionLocal = _client()
    _bind(client, SessionLocal)
    headers = _auth(client, "nourl@example.com")
    profile = client.post("/profiles", headers=headers, json={"persona": "developer"}).json()

    db = SessionLocal()
    job = models.Job(source="remoteok", external_id="e", canonical_hash="h",
                     title="Backend Engineer", company="Acme", apply_url="")
    db.add(job); db.commit()
    db.add(models.Application(profile_id=profile["id"], job_id=job.id,
                              status=models.ApplicationStatus.approved))
    db.commit(); db.close()

    assert client.get("/extension/work-queue", headers=headers).json() == []


def test_work_queue_respects_its_limit():
    client, SessionLocal = _client()
    _bind(client, SessionLocal)
    headers = _auth(client, "wqlimit@example.com")
    _seed(client, headers, [models.ApplicationStatus.approved] * 5)

    assert len(client.get("/extension/work-queue?limit=2", headers=headers).json()) == 2


# --- claim now opens the `submitting` window, it does not declare victory -----

def test_claim_submission_moves_to_submitting_not_applied():
    client, SessionLocal = _client()
    _bind(client, SessionLocal)
    headers = _auth(client, "claim2@example.com")
    _, (app_id,) = _seed(client, headers, [models.ApplicationStatus.approved])

    assert client.post(f"/applications/{app_id}/claim-submission", headers=headers).status_code == 200

    status, applied_at, _ = _status(SessionLocal, app_id)
    assert status == models.ApplicationStatus.submitting
    assert applied_at is None, "nothing has actually been sent yet — applied_at would be a lie"


def test_claim_submission_still_cannot_fire_twice():
    """Unchanged property, different mechanism: after the first claim the row is
    `submitting`, so it is no longer `approved` and a second claim is refused."""
    client, SessionLocal = _client()
    _bind(client, SessionLocal)
    headers = _auth(client, "claimtwice2@example.com")
    _, (app_id,) = _seed(client, headers, [models.ApplicationStatus.approved])

    assert client.post(f"/applications/{app_id}/claim-submission", headers=headers).status_code == 200
    assert client.post(f"/applications/{app_id}/claim-submission", headers=headers).status_code == 409


def test_a_claimed_application_leaves_the_work_queue_immediately():
    """Otherwise a second driver pass picks up the same item and double-applies."""
    client, SessionLocal = _client()
    _bind(client, SessionLocal)
    headers = _auth(client, "wqclaim@example.com")
    _, (app_id,) = _seed(client, headers, [models.ApplicationStatus.approved])

    assert len(client.get("/extension/work-queue", headers=headers).json()) == 1
    client.post(f"/applications/{app_id}/claim-submission", headers=headers)
    assert client.get("/extension/work-queue", headers=headers).json() == []


# --- outcome reporting --------------------------------------------------------

def test_reporting_submitted_finalises_as_applied_and_stamps_applied_at():
    client, SessionLocal = _client()
    _bind(client, SessionLocal)
    headers = _auth(client, "sub-ok@example.com")
    _, (app_id,) = _seed(client, headers, [models.ApplicationStatus.approved])
    client.post(f"/applications/{app_id}/claim-submission", headers=headers)

    resp = client.post(f"/applications/{app_id}/submission-result", headers=headers,
                       json={"outcome": "submitted"})
    assert resp.status_code == 200

    status, applied_at, _ = _status(SessionLocal, app_id)
    assert status == models.ApplicationStatus.applied
    assert applied_at is not None


def test_reporting_failed_returns_it_to_approved_so_it_can_be_retried():
    client, SessionLocal = _client()
    _bind(client, SessionLocal)
    headers = _auth(client, "sub-fail@example.com")
    _, (app_id,) = _seed(client, headers, [models.ApplicationStatus.approved])
    client.post(f"/applications/{app_id}/claim-submission", headers=headers)

    resp = client.post(f"/applications/{app_id}/submission-result", headers=headers,
                       json={"outcome": "failed", "reason": "no form found on page"})
    assert resp.status_code == 200

    status, applied_at, notes = _status(SessionLocal, app_id)
    assert status == models.ApplicationStatus.approved, "the form never went through; it is work again"
    assert applied_at is None
    assert "no form found on page" in (notes or ""), "a silent failure is the thing we are fixing"
    # and it is genuinely picked up again
    assert len(client.get("/extension/work-queue", headers=headers).json()) == 1


def test_reporting_needs_human_lands_in_the_existing_review_queue():
    client, SessionLocal = _client()
    _bind(client, SessionLocal)
    headers = _auth(client, "sub-human@example.com")
    profile_id, (app_id,) = _seed(client, headers, [models.ApplicationStatus.approved])
    client.post(f"/applications/{app_id}/claim-submission", headers=headers)

    resp = client.post(f"/applications/{app_id}/submission-result", headers=headers,
                       json={"outcome": "needs_human", "reason": "captcha"})
    assert resp.status_code == 200

    status, _, notes = _status(SessionLocal, app_id)
    assert status == models.ApplicationStatus.ready_for_review
    assert "captcha" in (notes or "")
    queue = client.get(f"/applications/review-queue?profile_id={profile_id}", headers=headers).json()
    assert [q["id"] for q in queue] == [app_id]


def test_reporting_an_outcome_for_an_unclaimed_application_is_refused():
    """Only a `submitting` row has an open window to close. Accepting a result
    for anything else would let a caller mark an arbitrary application applied."""
    client, SessionLocal = _client()
    _bind(client, SessionLocal)
    headers = _auth(client, "sub-unclaimed@example.com")
    _, (app_id,) = _seed(client, headers, [models.ApplicationStatus.approved])

    resp = client.post(f"/applications/{app_id}/submission-result", headers=headers,
                       json={"outcome": "submitted"})
    assert resp.status_code == 409


def test_reporting_twice_is_refused():
    client, SessionLocal = _client()
    _bind(client, SessionLocal)
    headers = _auth(client, "sub-twice@example.com")
    _, (app_id,) = _seed(client, headers, [models.ApplicationStatus.approved])
    client.post(f"/applications/{app_id}/claim-submission", headers=headers)

    first = client.post(f"/applications/{app_id}/submission-result", headers=headers,
                        json={"outcome": "submitted"})
    second = client.post(f"/applications/{app_id}/submission-result", headers=headers,
                         json={"outcome": "submitted"})
    assert first.status_code == 200
    assert second.status_code == 409


def test_reporting_an_unknown_outcome_is_rejected():
    client, SessionLocal = _client()
    _bind(client, SessionLocal)
    headers = _auth(client, "sub-bogus@example.com")
    _, (app_id,) = _seed(client, headers, [models.ApplicationStatus.approved])
    client.post(f"/applications/{app_id}/claim-submission", headers=headers)

    resp = client.post(f"/applications/{app_id}/submission-result", headers=headers,
                       json={"outcome": "definitely_applied_trust_me"})
    assert resp.status_code == 422


def test_cannot_report_an_outcome_for_someone_elses_application():
    client, SessionLocal = _client()
    _bind(client, SessionLocal)
    theirs = _auth(client, "victim@example.com")
    _, (app_id,) = _seed(client, theirs, [models.ApplicationStatus.approved])
    client.post(f"/applications/{app_id}/claim-submission", headers=theirs)

    mine = _auth(client, "attacker@example.com")
    resp = client.post(f"/applications/{app_id}/submission-result", headers=mine,
                       json={"outcome": "submitted"})
    assert resp.status_code == 404


def test_every_outcome_writes_an_event():
    """The digest (Phase 3) and any "what went out today" answer reads events."""
    client, SessionLocal = _client()
    _bind(client, SessionLocal)
    headers = _auth(client, "sub-events@example.com")
    _, (app_id,) = _seed(client, headers, [models.ApplicationStatus.approved])
    client.post(f"/applications/{app_id}/claim-submission", headers=headers)
    client.post(f"/applications/{app_id}/submission-result", headers=headers,
                json={"outcome": "submitted"})

    db = SessionLocal()
    types = [e.type for e in db.query(models.Event).all()]
    db.close()
    assert "application.submitted" in types


# ---------- stage 8 trigger (REACH-D) ----------

def test_a_successful_submission_queues_outreach():
    """README: "After you apply, the app finds a suitable person at the company."
    Nothing else in the system starts stage 8, so if this enqueue is lost the whole
    feature silently never runs."""
    from unittest.mock import patch

    client, SessionLocal = _client()
    _bind(client, SessionLocal)
    headers = _auth(client, "outreachtrigger@example.com")
    _, (app_id,) = _seed(client, headers, [models.ApplicationStatus.approved])
    client.post(f"/applications/{app_id}/claim-submission", headers=headers)

    with patch("main.get_queue") as queue:
        r = client.post(
            f"/applications/{app_id}/submission-result",
            headers=headers, json={"outcome": "submitted"},
        )
    assert r.status_code == 200
    enqueued = [c.args[0].__name__ for c in queue.return_value.enqueue.call_args_list]
    assert "draft_outreach_task" in enqueued


def test_an_outcome_that_never_sent_does_not_queue_outreach():
    """`failed` means nothing reached the employer, so there is nothing to ask about —
    and an email claiming an application that does not exist is the exact kind of
    unsupported claim this product exists not to make."""
    from unittest.mock import patch

    client, SessionLocal = _client()
    _bind(client, SessionLocal)
    headers = _auth(client, "outreachnotrigger@example.com")
    _, (app_id,) = _seed(client, headers, [models.ApplicationStatus.approved])

    with patch("main.get_queue") as queue:
        r = client.post(
            f"/applications/{app_id}/submission-result",
            headers=headers, json={"outcome": "failed", "reason": "no form"},
        )
    assert r.status_code == 200
    enqueued = [c.args[0].__name__ for c in queue.return_value.enqueue.call_args_list]
    assert "draft_outreach_task" not in enqueued


def test_a_broken_queue_does_not_lose_the_submission_result():
    """The submission result is the thing that must never be lost: it is the only record
    that an application actually went out. Outreach is an addition to it, so a Redis
    outage must not turn a successful submit into a 500."""
    from unittest.mock import patch

    client, SessionLocal = _client()
    _bind(client, SessionLocal)
    headers = _auth(client, "outreachbroken@example.com")
    _, (app_id,) = _seed(client, headers, [models.ApplicationStatus.approved])
    client.post(f"/applications/{app_id}/claim-submission", headers=headers)

    with patch("main.get_queue", side_effect=RuntimeError("redis down")):
        r = client.post(
            f"/applications/{app_id}/submission-result",
            headers=headers, json={"outcome": "submitted"},
        )
    assert r.status_code == 200
    assert r.json()["status"] == "applied"
