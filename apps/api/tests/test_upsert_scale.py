"""`upsert_jobs` at real discovery size.

Found in the user-zero end-to-end run (2026-10-10): discovery fetched the whole pool (ADR-021
stores whole boards, plus 69 new tokens and the LinkedIn sources) and died on Postgres at the
very end with `StatementTooComplex: stack depth limit exceeded`. The existing-row lookup put
EVERY fetched job into one `canonical_hash IN (...) OR (source, external_id) IN (...)`. SQLite
accepts that, so all 1218 tests passed while the real database refused every full run — and
because the upsert is the last step, a run saved nothing at all.

The large test is the one that matters on the Postgres lane (TEST_DATABASE_URL); the chunk
test proves the mechanism on either engine.
"""
from sqlalchemy import event

from connectors import pipeline
from connectors.normalize import canonical_hash


def _jobs(n, source="greenhouse"):
    out = []
    for i in range(n):
        j = {"source": source, "external_id": f"x{i}", "title": f"Engineer {i}",
             # One company per job: same-company titles like "Engineer 12" / "Engineer 412"
             # are correctly merged by the near-duplicate check, which isn't under test here.
             "company": f"Co {i}", "location": "Remote",
             "apply_url": f"https://example.com/{i}", "description": "d"}
        j["canonical_hash"] = canonical_hash(j["company"], j["title"], j["location"])
        out.append(j)
    return out


def test_the_existing_row_lookup_is_chunked(db_session):
    n = 2 * pipeline.UPSERT_LOOKUP_CHUNK + 5
    lookups = []

    def count(conn, cursor, statement, params, context, executemany):
        if statement.lstrip().upper().startswith("SELECT") and "FROM jobs" in statement:
            lookups.append(statement)

    engine = db_session.get_bind()
    event.listen(engine, "before_cursor_execute", count)
    try:
        inserted, _, _ = pipeline.upsert_jobs(db_session, _jobs(n))
    finally:
        event.remove(engine, "before_cursor_execute", count)
    assert inserted == n
    assert len([s for s in lookups if "canonical_hash IN" in s]) == 3


def test_a_full_discovery_sized_batch_upserts(db_session):
    """Live pool measured 2026-10-10: ~5,100 listed jobs before the new sources."""
    first, _, _ = pipeline.upsert_jobs(db_session, _jobs(6000))
    assert first == 6000
    # The steady-state run: the same pool again, now all re-seen.
    again = pipeline.upsert_jobs(db_session, _jobs(6000))
    assert again[0] == 0 and again[1] == 6000


def test_embedding_never_runs_inside_an_open_transaction(db_session, monkeypatch):
    """The real full run sat ~6 min in `embed_texts` (~1,100 Voyage requests for 6.7k new jobs)
    with the lookup transaction still open. Neon's idle_in_transaction_session_timeout is 5 min,
    so it killed the connection and the whole save was lost. Saving now never embeds, and the
    backlog pass holds no transaction across a network call. SQLite has no such timeout; the
    observable proxy is that the session holds no transaction when the call happens."""
    from sqlalchemy import select

    import models

    seen = []

    def fake_embed(texts, input_type):
        seen.append(db_session.in_transaction())
        return [[0.1] * models.EMBEDDING_DIM for _ in texts]

    monkeypatch.setattr(pipeline, "embed_texts", fake_embed)
    inserted, _, _ = pipeline.upsert_jobs(db_session, _jobs(30))
    assert inserted == 30 and seen == []
    assert pipeline.backfill_job_embeddings(db_session, limit=30) == 30
    assert seen and not any(seen)
    embedded = db_session.execute(select(models.Job).where(models.Job.embedding.is_not(None))).scalars().all()
    assert len(embedded) == 30


def test_reseeing_unchanged_jobs_is_not_one_round_trip_per_row(db_session):
    """psycopg2 runs an UPDATE executemany as one network round trip PER PARAMETER SET. At Neon's
    ~266 ms from this machine, 2,727 re-seen rows was ~12 minutes of a single save (ADR-021
    re-fetches whole boards hourly, so nearly every row is re-seen unchanged). Rows that did not
    change only need last_seen_at: that is one statement per chunk, not one per row."""
    pipeline.upsert_jobs(db_session, _jobs(300))
    round_trips = []

    def count(conn, cursor, statement, params, context, executemany):
        if statement.lstrip().upper().startswith("UPDATE JOBS"):
            round_trips.append(len(params) if executemany else 1)

    engine = db_session.get_bind()
    event.listen(engine, "before_cursor_execute", count)
    try:
        _, updated, _ = pipeline.upsert_jobs(db_session, _jobs(300))
    finally:
        event.remove(engine, "before_cursor_execute", count)
    assert updated == 300
    assert sum(round_trips) <= 3


def test_a_changed_job_is_still_updated_and_an_unchanged_one_still_marked_seen(db_session):
    import models

    first = _jobs(3)
    pipeline.upsert_jobs(db_session, first)
    before = {j.external_id: j.last_seen_at for j in db_session.query(models.Job)}
    again = _jobs(3)
    again[1]["description"] = "a new description"
    pipeline.upsert_jobs(db_session, again)
    rows = {j.external_id: j for j in db_session.query(models.Job)}
    assert rows["x1"].description == "a new description"
    assert all(rows[k].last_seen_at > before[k] for k in rows)
