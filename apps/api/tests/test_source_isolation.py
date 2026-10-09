"""Phase 2, items 1-3 (WORKLOG latest+67 "Next"): one failing source must not
abort the discovery run, every source's outcome is written to `connector_runs`,
and requests inside one source's loop are paced.

Before this, `fetch_remotive_jobs`/`fetch_reed_jobs` called `raise_for_status()`
with nothing catching it in `discover_jobs_task`: a Remotive 500 threw away every
other source's jobs, the delisting sweep and the embedding backfill for the whole
run. `connector_runs` had no ingestion rows at all, so `/sources` had to infer
health from job counts, which cannot tell "fetched nothing" from "never ran".
"""
from contextlib import contextmanager
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import main
import models
import workers.jobs as wj
from connectors.normalize import canonical_hash
from database import Base, get_db

PM = "Senior Product Manager"


def _board(*titles, company="acme"):
    return [{"company": company, "title": t, "location": "Bengaluru"} for t in titles]


@pytest.fixture()
def db():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False},
                           poolclass=StaticPool)
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


@contextmanager
def _offline(db=None, **overrides):
    """Every connector stubbed to return nothing, one source at a time
    overridden by keyword. Without this the test hits the real network.
    """
    stubs = {
        "fetch_remotive_jobs": MagicMock(return_value=[]),
        "fetch_reed_jobs": MagicMock(return_value=[]),
        "fetch_greenhouse_jobs": MagicMock(return_value=[]),
        "fetch_lever_jobs": MagicMock(return_value=[]),
        "fetch_ashby_jobs": MagicMock(return_value=[]),
        "fetch_workday_jobs": MagicMock(return_value=[]),
        # Added when jobspy was wired in (GAPS 3.2). Missing it is the exact failure
        # `conftest.no_real_subprocess_scrapes` exists to catch: without a stub here,
        # discovery shells out to the real Glassdoor scraper once per keyword per city.
        "fetch_jobspy_jobs": MagicMock(return_value=[]),
        "fetch_enabled_feeds": MagicMock(return_value=([], {})),
        **overrides,
    }
    patches = [patch(f"workers.jobs.{name}", stub) for name, stub in stubs.items()]
    patches.append(patch("workers.jobs.backfill_job_embeddings", MagicMock()))
    if db is not None:
        scope = MagicMock()
        scope.return_value.__enter__.return_value = db
        scope.return_value.__exit__.return_value = False
        patches.append(patch("workers.jobs.session_scope", scope))
    for p in patches:
        p.start()
    try:
        yield
    finally:
        for p in patches:
            p.stop()
        if db is not None:
            db.commit()


def _runs(db) -> dict[str, models.ConnectorRun]:
    return {r.source: r for r in db.query(models.ConnectorRun).all()}


# --- item 1: per-source error isolation --------------------------------------

@patch("workers.jobs.upsert_jobs", return_value=(1, 0, 0))
def test_a_raising_source_does_not_throw_away_the_other_sources(mock_upsert):
    """Remotive's raise_for_status() used to abort the whole run."""
    with _offline(
        db=MagicMock(),
        fetch_remotive_jobs=MagicMock(side_effect=RuntimeError("remotive 503")),
        fetch_greenhouse_jobs=MagicMock(return_value=_board(PM)),
    ), patch("workers.jobs.conn_config.GREENHOUSE_BOARD_TOKENS", ["acme"]), \
         patch("workers.jobs.conn_config.FEED_KEYWORDS", ["product manager"]), \
         patch("workers.jobs.conn_config.REMOTIVE_KEYWORDS", ["product manager"]):
        result = wj.discover_jobs_task()

    assert [j["title"] for j in mock_upsert.call_args.args[1]] == [PM]
    assert result["inserted"] == 1


@patch("workers.jobs.upsert_jobs", return_value=(0, 0, 0))
def test_a_raising_ats_source_is_never_swept(_upsert, db):
    """A source that failed produces no payload, so absence from it is not
    evidence of delisting (ADR-017 §3). Its live rows must survive.
    """
    job = models.Job(source="greenhouse", external_id="still-open", company="Acme", title=PM,
                     canonical_hash=canonical_hash("Acme", PM, None), apply_url="https://x/1")
    db.add(job)
    db.commit()

    with _offline(db=db, fetch_greenhouse_jobs=MagicMock(side_effect=RuntimeError("boom"))), \
         patch("workers.jobs.conn_config.GREENHOUSE_BOARD_TOKENS", ["acme"]):
        wj.discover_jobs_task()

    db.expire_all()
    assert db.query(models.Job).one().delisted_at is None


# --- item 2: ConnectorRun health rows ----------------------------------------

@patch("workers.jobs.upsert_jobs", return_value=(1, 0, 0))
def test_every_source_writes_a_connector_run_row(_upsert, db):
    with _offline(
        db=db,
        fetch_greenhouse_jobs=MagicMock(return_value=_board(PM)),
        fetch_remotive_jobs=MagicMock(side_effect=RuntimeError("remotive 503")),
    ), patch("workers.jobs.conn_config.GREENHOUSE_BOARD_TOKENS", ["acme"]), \
         patch("workers.jobs.conn_config.FEED_KEYWORDS", ["product manager"]), \
         patch("workers.jobs.conn_config.REMOTIVE_KEYWORDS", ["product manager"]), \
         patch("workers.jobs.conn_config.REED_KEYWORDS", []):
        wj.discover_jobs_task()

    runs = _runs(db)
    assert runs["greenhouse"].fetched == 1
    assert runs["greenhouse"].failed == 0 and runs["greenhouse"].error is None
    assert runs["greenhouse"].duration_ms is not None
    assert runs["remotive"].failed == 1
    assert "remotive 503" in runs["remotive"].error
    assert runs["remotive"].fetched == 0


@patch("workers.jobs.upsert_jobs", return_value=(0, 0, 0))
def test_the_feed_report_becomes_connector_run_rows(_upsert, db):
    """`fetch_enabled_feeds` already isolates per feed and reports a count or an
    error string per source — that report is the row, not a second mechanism.
    """
    report = {"remoteok": 3, "jobicy": "HTTPStatusError: 502", "nosuchfeed": "unknown feed name"}
    with _offline(db=db, fetch_enabled_feeds=MagicMock(return_value=([], report))):
        wj.discover_jobs_task()

    runs = _runs(db)
    assert runs["remoteok"].fetched == 3 and runs["remoteok"].failed == 0
    assert runs["jobicy"].failed == 1 and "502" in runs["jobicy"].error
    assert runs["nosuchfeed"].failed == 1


# --- item 3: per-host pacing --------------------------------------------------

def test_requests_inside_one_source_are_paced(db):
    """Nine Greenhouse tokens are nine back-to-back requests to one host."""
    with _offline(db=db, fetch_greenhouse_jobs=MagicMock(return_value=[])), \
         patch("workers.jobs.conn_config.GREENHOUSE_BOARD_TOKENS", ["a", "b", "c"]), \
         patch("workers.jobs.conn_config.LEVER_COMPANY_TOKENS", []), \
         patch("workers.jobs.conn_config.ASHBY_ORG_TOKENS", []), \
         patch("workers.jobs.conn_config.REMOTIVE_KEYWORDS", []), \
         patch("workers.jobs.conn_config.REED_KEYWORDS", []), \
         patch("workers.jobs.conn_config.WORKDAY_BOARDS", {}), \
         patch("workers.jobs.conn_config.JOBSPY_KEYWORDS", []), \
         patch("workers.jobs.upsert_jobs", MagicMock(return_value=(0, 0, 0))), \
         patch("workers.jobs.HOST_PACING_SECONDS", 0.25), \
         patch("workers.jobs.time.sleep") as sleep:
        wj.discover_jobs_task()

    # Three tokens, one host: paced between them, never before the first.
    # Every other source is zeroed above so this counts Greenhouse alone — jobspy is in
    # that list because it paces once per keyword PER CITY, so three keywords across six
    # cities would otherwise add 17 sleeps to this assertion.
    assert sleep.call_args_list == [((0.25,),), ((0.25,),)]


def test_pacing_is_configurable_and_skipped_for_a_single_request(db):
    with _offline(db=db), \
         patch("workers.jobs.conn_config.GREENHOUSE_BOARD_TOKENS", ["only"]), \
         patch("workers.jobs.conn_config.LEVER_COMPANY_TOKENS", []), \
         patch("workers.jobs.conn_config.ASHBY_ORG_TOKENS", []), \
         patch("workers.jobs.conn_config.REMOTIVE_KEYWORDS", []), \
         patch("workers.jobs.conn_config.REED_KEYWORDS", []), \
         patch("workers.jobs.conn_config.WORKDAY_BOARDS", {}), \
         patch("workers.jobs.conn_config.JOBSPY_KEYWORDS", []), \
         patch("workers.jobs.upsert_jobs", MagicMock(return_value=(0, 0, 0))), \
         patch("workers.jobs.time.sleep") as sleep:
        wj.discover_jobs_task()

    sleep.assert_not_called()


# --- item 2, read side: /sources health comes from the rows -------------------

@pytest.fixture()
def client():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False},
                           poolclass=StaticPool)
    Base.metadata.create_all(engine)
    TestSessionLocal = sessionmaker(bind=engine)

    def override_get_db():
        session = TestSessionLocal()
        try:
            yield session
        finally:
            session.close()

    main.app.dependency_overrides[get_db] = override_get_db
    yield TestClient(main.app), TestSessionLocal
    main.app.dependency_overrides.clear()
    engine.dispose()


def _login(c, email="iso@example.com"):
    c.post("/auth/signup", json={"email": email, "password": "correct horse battery staple"})
    token = c.post("/auth/login", data={"username": email,
                                        "password": "correct horse battery staple"}).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_sources_reports_a_source_whose_last_run_failed(client):
    c, SessionLocal = client
    headers = _login(c)
    db = SessionLocal()
    db.add(models.ConnectorRun(source="remoteok", fetched=0, failed=1, error="HTTPStatusError: 502"))
    db.add(models.ConnectorRun(source="jobicy", fetched=12, failed=0))
    db.commit()
    db.close()

    by_id = {s["id"]: s for s in c.get("/sources", headers=headers).json()}
    assert by_id["remoteok"]["enabled"] is False
    assert by_id["remoteok"]["reason"]
    assert by_id["jobicy"]["enabled"] is True and by_id["jobicy"]["reason"] is None


def test_sources_only_advertises_sources_discovery_actually_fetches():
    """COLLECT-F: `/sources` listed `jobspy_google` with the note "Currently
    returns no results" — JobSpy is built but has never been wired into
    `discover_jobs_task`, so the UI was offering users a source that cannot
    contribute anything. Showing a dead source is worse than not having it.

    This pins the invariant both ways, so the next source added to discovery has
    to be given a label, and a label can't outlive its fetcher.
    """
    from connectors import config as conn_config
    from main import _SOURCE_LABELS

    fetched = (
        {"remotive", "reed", "greenhouse", "lever", "ashby", "workday"}
        | set(conn_config.ENABLED_FEEDS)
    )
    assert set(_SOURCE_LABELS) == fetched, (
        "every advertised source must be fetched by discover_jobs_task, and "
        "every fetched source must be advertised"
    )


def test_sources_uses_only_the_most_recent_run_of_a_source(client):
    """A source that failed an hour ago and succeeded since is healthy."""
    from datetime import datetime, timedelta

    c, SessionLocal = client
    headers = _login(c, "iso2@example.com")
    db = SessionLocal()
    now = datetime.utcnow()
    db.add(models.ConnectorRun(source="remoteok", failed=1, error="HTTPStatusError: 502",
                               ran_at=now - timedelta(hours=1)))
    db.add(models.ConnectorRun(source="remoteok", fetched=5, failed=0, ran_at=now))
    db.commit()
    db.close()

    by_id = {s["id"]: s for s in c.get("/sources", headers=headers).json()}
    assert by_id["remoteok"]["enabled"] is True and by_id["remoteok"]["reason"] is None
