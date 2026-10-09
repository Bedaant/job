import os

# Tests are hermetic: the developer's .env (e.g. LLM_PROVIDER=nvidia) must not
# route a test to a live model. Env vars beat .env in pydantic-settings, and this
# runs before anything imports core.config. Tests that need another provider
# patch it explicitly.
os.environ["LLM_PROVIDER"] = "anthropic"

import pytest
from unittest.mock import patch
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import models
from database import Base


@pytest.fixture()
def db_session():
    """In-memory SQLite per test — fast, isolated, no Postgres/Docker required.

    Not a substitute for the real Postgres integration suite (Alembic migration
    correctness, pgvector, JSONB semantics) — those need a real Postgres and are
    blocked on Docker approval (DEPENDENCIES.md §5). This covers ORM-level logic:
    tenancy, relationships, constraints that behave the same on both engines.
    """
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


@pytest.fixture(autouse=True)
def no_live_apply_target_resolution():
    """`GET /extension/work-queue` resolves each aggregator `apply_url` to its
    real ATS (ADR-015 Phase 2), which costs an HTTP round trip. The whole suite
    must stay offline, so the default here is a no-op pass-through. Tests that
    care about resolution patch `main.resolve_apply_target` themselves and that
    inner patch wins.
    """
    from unittest.mock import patch

    def passthrough(url: str) -> dict:
        return {"final_url": url, "ats_type": None, "board_token": None, "resolved": False}

    with patch("main.resolve_apply_target", side_effect=passthrough):
        yield


@pytest.fixture(autouse=True)
def no_host_pacing():
    """Discovery paces requests inside one source's loop (workers/jobs.py,
    HOST_PACING_SECONDS). Real sleeps would add ~15s per discovery test for the
    20 configured tokens/keywords. Tests about pacing patch it back themselves.
    """
    from unittest.mock import patch

    with patch("workers.jobs.HOST_PACING_SECONDS", 0):
        yield


@pytest.fixture(autouse=True)
def no_real_network():
    """Fail any test that reaches the real network, instead of hanging on it.

    This has now bitten twice: a connector gets wired into `discover_jobs_task`
    and a test helper's stub list isn't updated, so the suite quietly fetches
    live job boards. The Workday connector made it worse than slow — two boards
    are ~160 paced requests, which pushed the suite past a 10-minute timeout.

    Only the real-socket transport is blocked. FastAPI's `TestClient` talks to
    the app through `ASGITransport`, so every API test is unaffected; a test
    that genuinely wants an HTTP fixture patches its own connector function.
    """
    import httpx

    def blocked(self, request, *args, **kwargs):
        raise RuntimeError(
            f"the test suite tried to reach {request.url} for real. Stub the "
            "connector (see tests/test_source_isolation.py::_offline) rather "
            "than letting the suite depend on a live job board."
        )

    with patch.object(httpx.HTTPTransport, "handle_request", blocked), \
         patch.object(httpx.AsyncHTTPTransport, "handle_async_request", blocked):
        yield


@pytest.fixture(autouse=True)
def no_real_subprocess_scrapes():
    """`no_real_network` cannot see into a subprocess, and that gap has now cost a
    second slow suite.

    `connectors/jobspy_connector.py` shells out to `tools/.venv-jobspy/` because JobSpy
    pins numpy 1.26.3 against this app's 2.x. The httpx transport patch above therefore
    does nothing for it: when jobspy was wired into `discover_jobs_task` (GAPS 3.2), the
    suite went from ~90s to over 600s doing 18 real Glassdoor scrapes per discovery
    test, with no failure to point at the cause.

    So fail fast instead, exactly as `no_real_network` does.

    Blocked at the DISCOVERY boundary (`workers.jobs.fetch_jobspy_jobs`), deliberately,
    not inside the connector. The first attempt patched
    `connectors.jobspy_connector.subprocess.run` — which patches `subprocess.run`
    **globally**, because that attribute is the one shared module object every importer
    sees. It duly broke `test_answer_bank.py`'s import-graph probe, which legitimately
    shells out to a fresh interpreter.

    This target leaves `tests/test_jobspy_connector.py` free to exercise the real
    function against a mocked `subprocess.run`, and a discovery test that wants rows
    patches the same name itself (its patch is applied inside this one and wins).
    """
    def blocked(*args, **kwargs):
        raise RuntimeError(
            "the test suite tried to run a real JobSpy scrape in a subprocess. Stub "
            "workers.jobs.fetch_jobspy_jobs (see tests/test_source_isolation.py"
            "::_offline) rather than letting the suite depend on a live job board."
        )

    with patch("workers.jobs.fetch_jobspy_jobs", blocked):
        yield
