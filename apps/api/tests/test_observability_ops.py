from datetime import datetime, timedelta

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import models
import observability
from core.config import get_settings
from core.deps import get_current_user
from database import get_db


class FakeRedis:
    def __init__(self):
        self.keys = {}

    def set(self, key, value, nx=False, ex=None):
        if nx and key in self.keys:
            return None
        self.keys[key] = (value, ex)
        return True


@pytest.fixture
def owner(monkeypatch):
    monkeypatch.setattr(get_settings(), "alert_email", "owner@example.com")
    monkeypatch.setenv("OWNER_EMAILS", "owner@example.com")
    monkeypatch.setattr(get_settings(), "smtp_host", "smtp.example.com")
    return "owner@example.com"


def _run(db, source, minutes_ago, error=None, duration_ms=1000):
    db.add(models.ConnectorRun(source=source, fetched=5, inserted=1, error=error,
                               duration_ms=duration_ms,
                               ran_at=datetime.utcnow() - timedelta(minutes=minutes_ago)))
    db.commit()


def _stats(queued=0, failed_discovery_at=None):
    return ({q: {"queued": queued, "failed": 0} for q in observability.QUEUES}, failed_discovery_at)


def test_health_reports_latest_run_per_source_and_queue_depths(db_session, monkeypatch):
    _run(db_session, "greenhouse", 120, error="Timeout")
    _run(db_session, "greenhouse", 10)
    _run(db_session, "lever", 30, error="HTTPError")
    monkeypatch.setattr(observability, "_queue_stats", lambda redis: _stats(queued=3))

    snap = observability.health(db_session, redis=None)

    assert snap["queues"]["background"]["queued"] == 3
    assert set(snap["queues"]) == {"default", "background", "effects"}
    assert snap["sources"]["greenhouse"]["error"] is None
    assert snap["sources"]["lever"]["error"] == "HTTPError"
    assert 9 <= snap["sources"]["greenhouse"]["age_minutes"] <= 11
    assert snap["discovery_failed"] is False


def test_health_flags_a_discovery_failure_newer_than_the_last_save(db_session, monkeypatch):
    _run(db_session, "greenhouse", 90)
    monkeypatch.setattr(observability, "_queue_stats",
                        lambda redis: _stats(failed_discovery_at=datetime.utcnow() - timedelta(minutes=5)))
    assert observability.health(db_session, redis=None)["discovery_failed"] is True

    _run(db_session, "greenhouse", 1)
    assert observability.health(db_session, redis=None)["discovery_failed"] is False


def _client(db_session, email):
    app = FastAPI()
    app.include_router(observability.router)
    app.dependency_overrides[get_db] = lambda: db_session
    app.dependency_overrides[get_current_user] = lambda: models.User(id="u1", email=email)
    return TestClient(app)


def test_ops_health_is_owner_only(db_session, owner, monkeypatch):
    monkeypatch.setattr(observability, "_queue_stats", lambda redis: _stats())
    monkeypatch.setattr(observability, "_redis", lambda: None)
    assert _client(db_session, "friend@example.com").get("/ops/health").status_code == 403
    # Called directly: TestClient's thread would get a different in-memory SQLite database.
    snap = observability.ops_health(db=db_session, user=models.User(id="u1", email="Owner@Example.com"))
    assert "queues" in snap


def test_ops_health_refuses_everyone_when_no_owner_is_configured(db_session, monkeypatch):
    monkeypatch.delenv("OWNER_EMAILS", raising=False)
    assert _client(db_session, "anyone@example.com").get("/ops/health").status_code == 403


def test_send_alert_is_deduplicated_per_kind(owner):
    redis, sent = FakeRedis(), []
    sender = lambda to, subject, body, attachments=None: sent.append((to, subject)) or True

    assert observability.send_alert(redis, "discovery_failed", "x", sender=sender) is True
    assert observability.send_alert(redis, "discovery_failed", "x", sender=sender) is False
    assert observability.send_alert(redis, "backlog", "y", sender=sender) is True
    assert [s[0] for s in sent] == [owner, owner]
    assert redis.keys["alert:discovery_failed"][1] == observability.ALERT_TTL_SECONDS


def test_send_alert_without_an_owner_address_sends_nothing(monkeypatch):
    monkeypatch.setattr(get_settings(), "alert_email", None)
    sent = []
    assert observability.send_alert(FakeRedis(), "backlog", "y", sender=lambda *a, **k: sent.append(a)) is False
    assert sent == []


def test_check_and_alert_raises_each_kind(db_session, owner, monkeypatch):
    _run(db_session, "workday", 2, duration_ms=observability.STAGE_BUDGET_MS + 1)
    monkeypatch.setattr(observability, "_queue_stats", lambda redis: _stats(
        queued=observability.BACKLOG_THRESHOLD + 1, failed_discovery_at=datetime.utcnow()))
    sent = []
    kinds = observability.check_and_alert(
        db_session, FakeRedis(), sender=lambda to, subject, body, attachments=None: sent.append(subject) or True)
    assert set(kinds) == {"discovery_failed", "backlog", "stage_budget"}
    assert len(sent) == 3


def test_check_and_alert_is_quiet_when_healthy(db_session, owner, monkeypatch):
    _run(db_session, "greenhouse", 2)
    monkeypatch.setattr(observability, "_queue_stats", lambda redis: _stats())
    assert observability.check_and_alert(db_session, FakeRedis(), sender=lambda *a, **k: True) == []


def test_ops_health_uses_the_same_owner_list_as_the_ats_controls(db_session, monkeypatch):
    from core.deps import require_owner

    monkeypatch.setattr(get_settings(), "alert_email", None)
    monkeypatch.setenv("OWNER_EMAILS", "boss@example.com")
    boss = models.User(id="u9", email="Boss@Example.com")
    assert require_owner(user=boss) is boss
    route = next(r for r in observability.router.routes if r.path == "/ops/health")
    assert require_owner in [d.call for d in route.dependant.dependencies]
