import os

# Tests are hermetic: the developer's .env (e.g. LLM_PROVIDER=nvidia) must not
# route a test to a live model. Env vars beat .env in pydantic-settings, and this
# runs before anything imports core.config. Tests that need another provider
# patch it explicitly.
os.environ["LLM_PROVIDER"] = "anthropic"

from pathlib import Path

import pytest
from unittest.mock import patch
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import models
from database import Base


# GAPS 5.4's real-Postgres lane. Opt-in, because the default must stay fast and need no
# infrastructure: `pytest -q` is SQLite as before, and
#
#     TEST_DATABASE_URL=postgresql://jobcopilot:jobcopilot@localhost:5433/jobcopilot_test \
#         .venv/Scripts/python.exe -m pytest -q
#
# runs the identical suite against a real Postgres. `docker compose up -d db-test` starts
# one; it uses the pgvector image because migration 0004 declares Vector columns and the
# plain postgres:16-alpine image has no `vector` extension (verified: its control file is
# simply absent).
TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL")


@pytest.fixture(scope="session")
def _pg_engine():
    """A migrated Postgres, built once per session.

    **Migrated with Alembic, not `Base.metadata.create_all`** — that difference is the
    whole point of this lane. `create_all` builds the schema the ORM *describes*, so it
    can never catch a migration that is wrong, missing, or out of order. Migrations
    0025 and 0026 were verified by INSPECTING the live Neon schema precisely because no
    test could do it; this is what replaces that.
    """
    if not TEST_DATABASE_URL:
        yield None
        return

    from alembic import command
    from alembic.config import Config

    engine = create_engine(TEST_DATABASE_URL)
    api_dir = Path(__file__).resolve().parent.parent
    cfg = Config(str(api_dir / "alembic.ini"))
    cfg.set_main_option("script_location", str(api_dir / "alembic"))
    cfg.set_main_option("sqlalchemy.url", TEST_DATABASE_URL)
    # Downgrade-then-upgrade is deliberately NOT done here: 0025's downgrade drops an
    # enum type, and proving that path belongs in its own test rather than in every run's
    # setup.
    command.upgrade(cfg, "head")
    try:
        yield engine
    finally:
        engine.dispose()


@pytest.fixture()
def db_session(_pg_engine):
    """A session per test. SQLite in-memory by default; real Postgres when opted in.

    SQLite is fast, isolated and needs no infrastructure, and it covers ORM-level logic —
    tenancy, relationships, constraints that behave identically on both engines. What it
    structurally CANNOT cover, and what the Postgres lane exists for: Alembic migration
    correctness, pgvector, JSONB semantics, real enum types, and `NULLS NOT DISTINCT`
    behaviour on the partial-unique constraints REACH-B relies on.

    The Postgres path wraps each test in a transaction and rolls back, rather than
    recreating the schema — migrating once per session and rolling back per test keeps
    the real lane usable rather than something nobody runs because it takes an hour.
    """
    if _pg_engine is None:
        engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
        Base.metadata.create_all(engine)
        session = sessionmaker(bind=engine)()
        try:
            yield session
        finally:
            session.close()
            engine.dispose()
        return

    connection = _pg_engine.connect()
    transaction = connection.begin()
    session = sessionmaker(bind=connection)()
    try:
        yield session
    finally:
        session.close()
        # Roll back whatever the test did, including DDL-free schema state. The next test
        # therefore sees the migrated schema with no rows, without paying to rebuild it.
        transaction.rollback()
        connection.close()


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
