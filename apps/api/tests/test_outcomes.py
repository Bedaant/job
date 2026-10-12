"""P1 #10: "Heard back?" at 7 and 14 days after a send, and first-party funnel events."""
from datetime import datetime, timedelta
from unittest.mock import patch

import digest
import models
import outcomes
from events.outbox import write_event
from tests.test_activity import _client, _user


def _sent_app(SessionLocal, email, days_ago, status=models.ApplicationStatus.applied, n=0):
    db = SessionLocal()
    user = db.query(models.User).filter(models.User.email == email).one()
    profile = db.query(models.Profile).filter(models.Profile.user_id == user.id).one()
    job = models.Job(source="remotive", external_id=f"{email}-{n}", canonical_hash=f"{email}-{n}",
                     title=f"Analyst {n}", company="Acme", apply_url="https://x")
    db.add(job)
    db.flush()
    row = models.Application(profile_id=profile.id, job_id=job.id, status=status,
                             applied_at=datetime.utcnow() - timedelta(days=days_ago, hours=1))
    db.add(row)
    db.commit()
    app_id, uid = row.id, user.id
    db.close()
    return app_id, uid


def _prompts(SessionLocal, app_id):
    rows = SessionLocal().query(models.Notification).filter(
        models.Notification.trigger == outcomes.TRIGGER).all()
    return [n.payload["day"] for n in rows if n.payload["application_id"] == app_id]


def _sweep(SessionLocal, now=None):
    db = SessionLocal()
    n = outcomes.sweep_prompts(db, now or datetime.utcnow())
    db.commit()
    db.close()
    return n


def test_seven_days_after_a_send_gets_exactly_one_prompt_across_sweeps():
    client, SessionLocal = _client()
    _user(client, "a@example.com")
    app_id, _ = _sent_app(SessionLocal, "a@example.com", days_ago=7)
    fresh, _ = _sent_app(SessionLocal, "a@example.com", days_ago=3, n=1)

    assert _sweep(SessionLocal) == 1
    assert _sweep(SessionLocal) == 0
    assert _prompts(SessionLocal, app_id) == [7]
    assert _prompts(SessionLocal, fresh) == []


def test_fourteen_days_gets_its_own_single_prompt():
    client, SessionLocal = _client()
    _user(client, "a@example.com")
    app_id, _ = _sent_app(SessionLocal, "a@example.com", days_ago=7)
    _sweep(SessionLocal)
    later = datetime.utcnow() + timedelta(days=7)
    assert _sweep(SessionLocal, later) == 1
    assert _sweep(SessionLocal, later) == 0
    assert sorted(_prompts(SessionLocal, app_id)) == [7, 14]


def test_no_prompt_after_an_answer_and_none_once_status_moved_on():
    client, SessionLocal = _client()
    headers, _ = _user(client, "a@example.com")
    app_id, _ = _sent_app(SessionLocal, "a@example.com", days_ago=7)
    moved, _ = _sent_app(SessionLocal, "a@example.com", days_ago=8, status=models.ApplicationStatus.interview, n=1)
    _sweep(SessionLocal)
    assert _prompts(SessionLocal, moved) == []

    res = client.post(f"/applications/{app_id}/outcome", headers=headers, json={"outcome": "interview"})
    assert res.status_code == 200
    assert _sweep(SessionLocal, datetime.utcnow() + timedelta(days=7)) == 0
    assert _prompts(SessionLocal, app_id) == [7]


def test_no_reply_yet_still_asks_again_at_fourteen_days():
    client, SessionLocal = _client()
    headers, _ = _user(client, "a@example.com")
    app_id, _ = _sent_app(SessionLocal, "a@example.com", days_ago=7)
    _sweep(SessionLocal)
    client.post(f"/applications/{app_id}/outcome", headers=headers, json={"outcome": "no_reply"})
    assert _sweep(SessionLocal, datetime.utcnow() + timedelta(days=7)) == 1


def test_one_tap_endpoint_records_outcome_clears_prompt_and_rejects_other_users():
    client, SessionLocal = _client()
    headers_a, _ = _user(client, "a@example.com")
    headers_b, _ = _user(client, "b@example.com")
    app_id, _ = _sent_app(SessionLocal, "a@example.com", days_ago=7)
    _sweep(SessionLocal)

    listed = client.get("/outcome-prompts", headers=headers_a).json()
    assert [(p["application_id"], p["day"], p["company"]) for p in listed] == [(app_id, 7, "Acme")]
    assert client.get("/outcome-prompts", headers=headers_b).json() == []

    assert client.post(f"/applications/{app_id}/outcome", headers=headers_b,
                       json={"outcome": "rejected"}).status_code == 404
    assert client.post(f"/applications/{app_id}/outcome", headers=headers_a,
                       json={"outcome": "ghosted"}).status_code == 422
    res = client.post(f"/applications/{app_id}/outcome", headers=headers_a, json={"outcome": "rejected"})
    assert res.status_code == 200 and res.json()["outcome"] == "rejected"

    row = SessionLocal().get(models.Application, app_id)
    assert row.outcome == "rejected" and row.outcome_at is not None
    assert row.status == models.ApplicationStatus.applied  # status transitions are not ours to change
    assert client.get("/outcome-prompts", headers=headers_a).json() == []


def test_digest_carries_the_prompt_with_a_deep_link():
    client, SessionLocal = _client()
    _user(client, "a@example.com")
    app_id, uid = _sent_app(SessionLocal, "a@example.com", days_ago=7)
    _sweep(SessionLocal)
    db = SessionLocal()
    now = datetime.utcnow()
    d = digest.build_digest(db, db.get(models.User, uid), now - timedelta(days=1), now)
    assert d["had_activity"] is True
    assert [p["application_id"] for p in d["outcome_prompts"]] == [app_id]
    text = digest.render_text(d)
    assert "Heard back" in text and f"/today#outcome-{app_id}" in text


def test_daily_digest_task_sweeps_prompts_itself():
    client, SessionLocal = _client()
    _user(client, "a@example.com")
    app_id, _ = _sent_app(SessionLocal, "a@example.com", days_ago=7)
    sent = []
    with patch("digest.session_scope") as scope:
        db = SessionLocal()
        scope.return_value.__enter__.return_value = db
        scope.return_value.__exit__.return_value = False
        digest.daily_digest_task(sender=lambda to, s, body: sent.append(body) or False)
        db.commit()
    assert _prompts(SessionLocal, app_id) == [7]
    assert "Heard back" in sent[0]


def _funnel(SessionLocal, uid):
    rows = SessionLocal().query(models.Event).filter(
        models.Event.user_id == uid, models.Event.type.like("funnel.%")).all()
    return sorted(e.type for e in rows)


@patch("matching.service.embed_texts", return_value=None)
def test_funnel_events_fire_once_each(_embed):
    client, SessionLocal = _client()
    headers, pid = _user(client, "a@example.com")
    uid = SessionLocal().query(models.User).one().id

    fact = {"category": "experience", "achievement": "Cut p99 latency 40%", "tags": []}
    client.post(f"/profiles/{pid}/facts:bulk", headers=headers, json={"facts": [fact]})
    client.post(f"/profiles/{pid}/facts:bulk", headers=headers,
                json={"facts": [{**fact, "achievement": "Shipped billing"}]})

    cid = client.post("/campaigns", headers=headers,
                      json={"profile_id": pid, "name": "Analyst", "roles": ["Data Analyst"]}).json()["id"]
    for status in ("active", "paused", "active"):
        assert client.patch(f"/campaigns/{cid}", headers=headers, json={"status": status}).status_code == 200

    db = SessionLocal()
    for _ in range(2):  # no commit between: the second must still see the first
        write_event(db, uid, "match.new", {"job_id": "j"})
    db.commit()
    db.close()

    a1, _ = _sent_app(SessionLocal, "a@example.com", days_ago=7, status=models.ApplicationStatus.approved)
    a2, _ = _sent_app(SessionLocal, "a@example.com", days_ago=7, status=models.ApplicationStatus.approved, n=1)
    for a in (a1, a2):
        client.patch(f"/applications/{a}", headers=headers, json={"status": "applied"})
        client.post(f"/applications/{a}/outcome", headers=headers, json={"outcome": "no_reply"})

    assert _funnel(SessionLocal, uid) == [
        "funnel.campaign_active", "funnel.facts_confirmed", "funnel.first_match",
        "funnel.first_send", "funnel.outcome_answered", "funnel.signup",
    ]
