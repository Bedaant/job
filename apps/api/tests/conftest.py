import os

# Tests are hermetic: the developer's .env (e.g. LLM_PROVIDER=nvidia) must not
# route a test to a live model. Env vars beat .env in pydantic-settings, and this
# runs before anything imports core.config. Tests that need another provider
# patch it explicitly.
os.environ["LLM_PROVIDER"] = "anthropic"

import pytest
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
