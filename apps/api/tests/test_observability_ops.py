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
    def __init__(self, clients=3):
        self.keys, self.lists, self.clients = {}, {}, clients

    def set(self, key, value, nx=False, ex=None):
        if nx and key in self.keys:
            return None
        self.keys[key] = (value, ex)
        return True

    def get(self, key):
        return self.keys.get(key, (None,))[0]

    def incr(self, key):
        self.keys[key] = (int(self.get(key) or 0) + 1, None)
        return self.keys[key][0]

    def incrbyfloat(self, key, amount):
        self.keys[key] = (float(self.get(key) or 0) + amount, None)

    def expire(self, key, seconds):
        pass

    def exists(self, key):
        return int(key in self.keys)

    def delete(self, key):
        self.keys.pop(key, None)

    def lpush(self, key, value):
        self.lists.setdefault(key, []).insert(0, value)

    def ltrim(self, key, start, end):
        self.lists[key] = self.lists.get(key, [])[start:end + 1]

    def lrange(self, key, start, end):
        return self.lists.get(key, [])[start:None if end == -1 else end + 1]

    def info(self, section):
        assert section == "clients"
        return {"connected_clients": self.clients}


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

    snap = observability.health(db_session, redis=FakeRedis())

    assert snap["queues"]["background"]["queued"] == 3
    assert set(snap["queues"]) == {"default", "background", "effects"}
    assert snap["sources"]["greenhouse"]["error"] is None
    assert snap["sources"]["lever"]["error"] == "HTTPError"
    assert 9 <= snap["sources"]["greenhouse"]["age_minutes"] <= 11
    assert snap["discovery_failed"] is False


def test_queue_stats_report_the_oldest_queued_job_age(monkeypatch):
    """P1 #16 / plan §6: depth alone hides a stuck queue; the head job's age shows it."""
    import rq
    from rq.job import Job

    now = datetime.utcnow()
    heads = {"default": ["j1"], "background": [], "effects": ["j3"]}
    enqueued = {"j1": now - timedelta(seconds=600), "j3": None}

    class FakeQueue:
        def __init__(self, name, connection):
            self.name, self.count = name, len(heads[name])
            self.failed_job_registry = type("R", (), {"count": 0, "get_job_ids": lambda *a, **k: []})()

        def get_job_ids(self, offset=0, length=-1):
            assert (offset, length) == (0, 1)  # the head of the list is the oldest job
            return heads[self.name]

    monkeypatch.setattr(rq, "Queue", FakeQueue)
    monkeypatch.setattr(Job, "fetch_many", classmethod(
        lambda cls, ids, connection: [type("J", (), {"enqueued_at": enqueued[i]})() for i in ids]))

    stats, _ = observability._queue_stats(redis=None)

    assert 595 <= stats["default"]["oldest_queued_age_seconds"] <= 610
    assert stats["background"]["oldest_queued_age_seconds"] is None
    assert stats["effects"]["oldest_queued_age_seconds"] is None


def test_health_flags_a_discovery_failure_newer_than_the_last_save(db_session, monkeypatch):
    _run(db_session, "greenhouse", 90)
    monkeypatch.setattr(observability, "_queue_stats",
                        lambda redis: _stats(failed_discovery_at=datetime.utcnow() - timedelta(minutes=5)))
    assert observability.health(db_session, redis=FakeRedis())["discovery_failed"] is True

    _run(db_session, "greenhouse", 1)
    assert observability.health(db_session, redis=FakeRedis())["discovery_failed"] is False


def _client(db_session, email):
    app = FastAPI()
    app.include_router(observability.router)
    app.dependency_overrides[get_db] = lambda: db_session
    app.dependency_overrides[get_current_user] = lambda: models.User(id="u1", email=email)
    return TestClient(app)


def test_ops_health_is_owner_only(db_session, owner, monkeypatch):
    monkeypatch.setattr(observability, "_queue_stats", lambda redis: _stats())
    monkeypatch.setattr(observability, "_redis", FakeRedis)
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


# --- NEXT-WORK-PLAN section 6 metrics ---------------------------------------------------------

def test_health_counts_submitting_rows_older_than_the_threshold(db_session, monkeypatch):
    monkeypatch.setattr(observability, "_queue_stats", lambda redis: _stats())
    user = models.User(email="m@x.com", password_hash="x")
    db_session.add(user)
    db_session.flush()
    profile = models.Profile(user_id=user.id, persona=models.Persona.developer)
    db_session.add(profile)
    db_session.flush()
    old = datetime.utcnow() - timedelta(minutes=observability.SUBMITTING_STALE_MINUTES + 5)
    for n, (status, updated) in enumerate([
        (models.ApplicationStatus.submitting, old),                 # stuck: counted
        (models.ApplicationStatus.submitting, datetime.utcnow()),   # in flight
        (models.ApplicationStatus.approved, old),                   # not submitting
    ]):
        job = models.Job(source="greenhouse", external_id=str(n), canonical_hash=f"m{n}", title="T",
                         company="C", apply_url=f"https://x/{n}")
        db_session.add(job)
        db_session.flush()
        db_session.add(models.Application(profile_id=profile.id, job_id=job.id, status=status, updated_at=updated))
    db_session.commit()

    assert observability.health(db_session, FakeRedis())["submitting_stale"] == 1


def test_guard_counts_llm_calls_per_minute_and_429s(db_session, monkeypatch):
    import httpx

    from providers import guard

    redis, now = FakeRedis(), 1_000_000 * 60.0
    monkeypatch.setattr(guard, "_redis", lambda: redis)
    monkeypatch.setattr(guard, "_daily_cap", lambda provider: None)
    monkeypatch.setattr(observability, "_queue_stats", lambda redis: _stats())
    guard._reset_local_state()
    monkeypatch.setattr(guard.time, "time", lambda: now + 5)
    for _ in range(3):
        guard.call("llm", lambda: "ok", retries=0)
    too_many = httpx.HTTPStatusError("429", request=httpx.Request("POST", "https://llm.example"),
                                     response=httpx.Response(429))
    with pytest.raises(httpx.HTTPStatusError):
        guard.call("llm", lambda: (_ for _ in ()).throw(too_many), retries=0)

    monkeypatch.setattr(guard.time, "time", lambda: now + 65)  # the next minute reads the last full one
    llm = observability.health(db_session, redis)["llm"]
    guard._reset_local_state()
    assert llm == {"calls_last_minute": 4, "rate_limited_today": 1}


def test_tailoring_time_and_cost_percentiles(db_session, monkeypatch):
    monkeypatch.setattr(observability, "_queue_stats", lambda redis: _stats())
    redis = FakeRedis()
    for n in range(1, 21):
        observability.record_tailoring(redis, seconds=float(n), cost_usd=0.06)
    tailoring = observability.health(db_session, redis)["tailoring"]
    assert tailoring["samples"] == 20
    assert 10 <= tailoring["p50_seconds"] <= 11 and tailoring["p95_seconds"] >= 19
    assert tailoring["avg_cost_usd"] == pytest.approx(0.06)
    assert observability.health(db_session, FakeRedis())["tailoring"] == {"samples": 0}


def test_prepare_records_one_tailoring_sample(monkeypatch):
    from types import SimpleNamespace

    import batch_prep

    samples = []
    monkeypatch.setattr(observability, "record_tailoring", lambda redis, seconds, cost_usd: samples.append(seconds))
    monkeypatch.setattr(observability, "_redis", lambda: None)
    monkeypatch.setattr(batch_prep, "tailor_application", lambda job, facts: {
        "summary": "", "bullets": [], "cover_letter": "", "flagged_unsupported_claims": []})
    monkeypatch.setattr(batch_prep, "write_event", lambda *a, **k: None)
    query = SimpleNamespace(filter=lambda *a: SimpleNamespace(all=lambda: []))
    db = SimpleNamespace(query=lambda model: query, commit=lambda: None, refresh=lambda a: None)
    app = SimpleNamespace(id="a1", status=models.ApplicationStatus.saved, profile=SimpleNamespace(id="p1", user_id="u1"),
                          job=SimpleNamespace(title="T", company="C", description=""))
    batch_prep.prepare_application_for_review(db, app)
    assert len(samples) == 1 and samples[0] >= 0


def test_redis_client_count_is_reported_and_alerts_above_25(db_session, owner, monkeypatch):
    monkeypatch.setattr(observability, "_queue_stats", lambda redis: _stats())
    assert observability.health(db_session, FakeRedis(clients=12))["redis_clients"] == 12
    sent = lambda *a, **k: True  # noqa: E731
    assert observability.check_and_alert(db_session, FakeRedis(clients=25), sender=sent) == []
    assert observability.check_and_alert(db_session, FakeRedis(clients=26), sender=sent) == ["redis_clients"]
