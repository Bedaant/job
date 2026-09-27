"""`unconfirmed`: the form was submitted but the employer's page never confirmed it.

The extension used to report `submitted` the instant the native submit fired, so a
validation error, a post-submit captcha or a silently rejected form all became
`applied`. Now `submitted` means the page confirmed it; `unconfirmed` means the
submit was sent and nothing confirmed or rejected it. That row must not read as
plain `applied`, and must never go back to `approved` (a retry could apply twice).
"""
from datetime import datetime, timedelta

import models
from tests.test_activity import _world
from tests.test_submission_loop import _auth, _bind, _client, _seed, _status


def _claimed(email):
    client, SessionLocal = _client()
    _bind(client, SessionLocal)
    headers = _auth(client, email)
    profile_id, (app_id,) = _seed(client, headers, [models.ApplicationStatus.approved])
    client.post(f"/applications/{app_id}/claim-submission", headers=headers)
    return client, SessionLocal, headers, profile_id, app_id


def test_unconfirmed_is_its_own_status_not_applied_and_not_retried():
    client, SessionLocal, headers, profile_id, app_id = _claimed("unconf@example.com")

    resp = client.post(f"/applications/{app_id}/submission-result", headers=headers,
                       json={"outcome": "unconfirmed", "reason": "No confirmation page appeared within 20 seconds."})
    assert resp.status_code == 200
    assert resp.json()["status"] == "submitted_unconfirmed"

    status, applied_at, notes = _status(SessionLocal, app_id)
    assert status == models.ApplicationStatus.submitted_unconfirmed
    # applied_at = when the submit was sent; the status says it is unconfirmed.
    assert applied_at is not None
    assert "[unconfirmed] No confirmation page" in notes
    # Never handed back to the driver: a second submit could apply twice.
    assert client.get("/extension/work-queue", headers=headers).json() == []
    # Not a review item either: the user's action is "check your email", not "approve".
    queue = client.get(f"/applications/review-queue?profile_id={profile_id}", headers=headers).json()
    assert queue == []


def test_unconfirmed_writes_its_own_event_and_closes_the_window():
    client, SessionLocal, headers, _, app_id = _claimed("unconf-ev@example.com")
    client.post(f"/applications/{app_id}/submission-result", headers=headers, json={"outcome": "unconfirmed"})
    again = client.post(f"/applications/{app_id}/submission-result", headers=headers, json={"outcome": "submitted"})
    assert again.status_code == 409, "reported once; a late confirmation cannot re-open it"

    db = SessionLocal()
    types = [e.type for e in db.query(models.Event).all()]
    db.close()
    assert "application.unconfirmed" in types


def test_user_can_mark_an_unconfirmed_application_applied_once_they_see_the_email():
    client, SessionLocal, headers, _, app_id = _claimed("unconf-fix@example.com")
    client.post(f"/applications/{app_id}/submission-result", headers=headers, json={"outcome": "unconfirmed"})
    sent_at = _status(SessionLocal, app_id)[1]

    resp = client.patch(f"/applications/{app_id}", headers=headers, json={"status": "applied"})
    assert resp.status_code == 200
    status, applied_at, _ = _status(SessionLocal, app_id)
    assert status == models.ApplicationStatus.applied
    assert applied_at == sent_at, "keeps the time the form was actually sent"


def test_stopping_before_the_claim_can_still_be_reported():
    """The extension reports needs_human (blocking field, no form, captcha on load)
    and failed BEFORE it claims — nothing was sent, so the row is still `approved`.
    Those reports used to 409 and were lost; the card never reached the review queue."""
    client, SessionLocal = _client()
    _bind(client, SessionLocal)
    headers = _auth(client, "preclaim@example.com")
    _, (a, b, c) = _seed(client, headers, [models.ApplicationStatus.approved] * 3)

    r = client.post(f"/applications/{a}/submission-result", headers=headers,
                    json={"outcome": "needs_human", "reason": "captcha", "unanswered_questions": ["Portfolio URL?"]})
    assert r.status_code == 200
    assert _status(SessionLocal, a)[0] == models.ApplicationStatus.ready_for_review
    assert client.post(f"/applications/{b}/submission-result", headers=headers,
                       json={"outcome": "failed", "reason": "fill error"}).status_code == 200
    assert _status(SessionLocal, b)[0] == models.ApplicationStatus.approved
    # Anything that says a send happened still requires the claim.
    for outcome in ("submitted", "unconfirmed"):
        assert client.post(f"/applications/{c}/submission-result", headers=headers,
                           json={"outcome": outcome}).status_code == 409


def test_activity_titles_an_unconfirmed_send_plainly_with_the_company_and_form_link():
    client, SessionLocal, headers_a, _, ids, _ = _world()
    db = SessionLocal()
    user_a = db.query(models.User).filter(models.User.email == "a@example.com").one()
    db.add(models.Event(user_id=user_a.id, type="application.unconfirmed",
                        payload={"application_id": ids["application"], "status": "submitted_unconfirmed",
                                 "reason": None}, created_at=datetime.utcnow()))
    db.commit()
    db.close()

    items = client.get("/activity", headers=headers_a).json()
    row = next(i for i in items if i["type"] == "application.unconfirmed")
    assert row["title"] == "Sent to Acme — couldn't confirm it went through"
    assert row["detail"]
    assert row["apply_url"] == "https://x", "so the user can open the form and check"
    # Other rows don't carry a form link.
    assert all(i.get("apply_url") is None for i in items if i["type"] != "application.unconfirmed")


def test_today_counts_unconfirmed_as_sent_and_says_how_many():
    client, SessionLocal, headers_a, _, ids, _ = _world()
    db = SessionLocal()
    now = datetime.utcnow()
    jobs = [models.Job(source="remotive", external_id=f"u{n}", canonical_hash=f"u{n}", title="SRE",
                       company="Beta", apply_url="https://y") for n in range(3)]
    db.add_all(jobs)
    db.flush()
    db.add_all([
        models.Application(profile_id=ids["profile_a"], job_id=jobs[0].id,
                           status=models.ApplicationStatus.applied, applied_at=now),
        models.Application(profile_id=ids["profile_a"], job_id=jobs[1].id,
                           status=models.ApplicationStatus.submitted_unconfirmed, applied_at=now),
        models.Application(profile_id=ids["profile_a"], job_id=jobs[2].id,
                           status=models.ApplicationStatus.submitted_unconfirmed,
                           applied_at=now - timedelta(days=2)),
    ])
    db.commit()
    db.close()

    today = client.get("/today", headers=headers_a).json()
    assert today["sent_today"] == 2
    assert today["unconfirmed_today"] == 1
