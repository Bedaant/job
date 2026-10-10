"""Content fingerprint on jobs: re-seen rows that did not change are only marked seen, and
derived fields (skills, seniority) are recomputed only for new or changed rows."""
import os
import time
from unittest.mock import patch

import pytest
from sqlalchemy import event

import models
from connectors import pipeline
from connectors.normalize import canonical_hash


def _job(i, **over):
    j = {"source": "greenhouse", "external_id": f"x{i}", "title": f"Engineer {i}",
         "company": f"Co {i}", "location": "Remote", "apply_url": f"https://example.com/{i}",
         "description": "Plain role.", **over}
    j["canonical_hash"] = canonical_hash(j["company"], j["title"], j["location"])
    return j


def test_inserted_rows_carry_a_content_hash(db_session):
    pipeline.upsert_jobs(db_session, [_job(1)])
    assert db_session.query(models.Job).one().content_hash


def test_unchanged_rows_skip_skill_extraction_and_changed_rows_redo_it(db_session):
    pipeline.upsert_jobs(db_session, [_job(1), _job(2)])
    with patch.object(pipeline, "extract_skills", wraps=pipeline.extract_skills) as skills:
        pipeline.upsert_jobs(db_session, [_job(1), _job(2, description="We use Python daily.")])
    assert skills.call_count == 1
    rows = {r.external_id: r for r in db_session.query(models.Job)}
    assert rows["x2"].skills == ["Python"]
    assert rows["x2"].description == "We use Python daily."


def test_a_title_change_recomputes_seniority(db_session):
    pipeline.upsert_jobs(db_session, [_job(1, title="Engineer")])
    pipeline.upsert_jobs(db_session, [_job(1, title="Senior Engineer")])
    assert db_session.query(models.Job).one().seniority == "senior"


def test_a_row_stored_before_fingerprints_is_touched_not_rewritten_when_equal(db_session):
    pipeline.upsert_jobs(db_session, [_job(1)])
    db_session.query(models.Job).update({"content_hash": None})
    db_session.commit()
    params = []

    def count(conn, cursor, statement, p, context, executemany):
        if statement.lstrip().upper().startswith("UPDATE JOBS"):
            params.append(len(p) if executemany else 1)

    engine = db_session.get_bind()
    event.listen(engine, "before_cursor_execute", count)
    try:
        _, updated, _ = pipeline.upsert_jobs(db_session, [_job(1)])
    finally:
        event.remove(engine, "before_cursor_execute", count)
    assert updated == 1 and sum(params) == 1


def test_saving_jobs_makes_no_embedding_call(db_session, monkeypatch):
    """Discovery never waits on embeddings: embed_backlog_task owns them."""
    called = []
    monkeypatch.setattr(pipeline, "embed_texts", lambda *a, **k: called.append(1))
    pipeline.upsert_jobs(db_session, [_job(i) for i in range(5)])
    assert called == []


@pytest.mark.skipif(not os.getenv("RUN_LOAD_TESTS"), reason="~1 min; set RUN_LOAD_TESTS=1")
def test_a_100k_job_save_fits_its_time_budget(db_session):
    # Skipped by default: it alone would add about half again to the normal suite's runtime.
    jobs = [_job(i) for i in range(100_000)]
    start = time.perf_counter()
    assert pipeline.upsert_jobs(db_session, jobs)[0] == 100_000
    first = time.perf_counter() - start
    start = time.perf_counter()
    assert pipeline.upsert_jobs(db_session, jobs)[1] == 100_000
    again = time.perf_counter() - start
    assert first < 180 and again < 60, (first, again)
