from unittest.mock import MagicMock, patch

import pytest

import models
from connectors import pipeline
from connectors.normalize import canonical_hash
from tests.resilience_helpers import no_network_in_transaction


def _jobs(n):
    out = []
    for i in range(n):
        j = {"source": "greenhouse", "external_id": f"r{i}", "title": f"Engineer {i}",
             "company": f"Co {i}", "location": "Remote", "apply_url": f"https://e.com/{i}",
             "description": "d"}
        j["canonical_hash"] = canonical_hash(j["company"], j["title"], j["location"])
        out.append(j)
    return out


def test_the_helper_catches_a_call_inside_an_open_transaction(db_session):
    from providers import guard

    db_session.query(models.Job).count()  # autobegins
    with pytest.raises(AssertionError, match="inside a transaction"):
        with no_network_in_transaction(db_session):
            with pytest.raises(AssertionError, match="transaction open"):
                guard.call("voyage", lambda: "x")


def test_the_helper_still_fails_when_the_caller_swallows_the_error(db_session):
    from providers import guard

    db_session.query(models.Job).count()
    with pytest.raises(AssertionError, match="inside a transaction"):
        with no_network_in_transaction(db_session):
            try:
                guard.call("voyage", lambda: "x")
            except Exception:
                pass


def test_discovery_save_makes_no_outside_call_inside_a_transaction(db_session):
    """Runs the REAL embed_texts (only the Voyage client is faked) so the call goes through the
    guard exactly as in production."""
    from matching import embeddings

    client = MagicMock()
    client.embed.side_effect = lambda texts, **k: MagicMock(
        embeddings=[[0.1] * models.EMBEDDING_DIM for _ in texts])
    with patch.object(embeddings, "get_settings", return_value=MagicMock(voyage_api_key="k")), \
         patch.object(embeddings.voyageai, "Client", return_value=client), \
         patch.object(pipeline, "embed_texts", embeddings.embed_texts), \
         no_network_in_transaction(db_session) as calls:
        inserted, _, _ = pipeline.upsert_jobs(db_session, _jobs(12))
        embedded = pipeline.backfill_job_embeddings(db_session, limit=50)  # as discover_jobs_task does
    assert inserted == 12 and embedded == 12
    assert calls and set(calls) == {"voyage"}


def test_postgres_engines_get_a_recycled_small_pool_and_sqlite_is_untouched():
    from database import engine_kwargs

    pg = engine_kwargs("postgresql://u:p@h/db")
    assert pg["pool_pre_ping"] and pg["pool_recycle"] and pg["pool_size"] <= 10
    assert "pool_size" not in engine_kwargs("sqlite:///:memory:")


def test_migration_0029_sets_role_timeouts_and_indexes_the_dedupe_lookup():
    import importlib.util
    from pathlib import Path

    versions = Path(__file__).resolve().parent.parent / "alembic" / "versions"
    [path] = list(versions.glob("0029_*.py"))
    spec = importlib.util.spec_from_file_location("m0029", path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    assert m.revision == "0029"
    assert any(p.name.startswith(f"{m.down_revision}_") for p in versions.glob("*.py"))
    src = path.read_text(encoding="utf-8")
    assert "statement_timeout" in src and "canonical_hash" in src and "RESET statement_timeout" in src
