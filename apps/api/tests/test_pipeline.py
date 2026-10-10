from datetime import datetime
from unittest.mock import patch

from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import models
from connectors.normalize import canonical_hash
from connectors.pipeline import backfill_job_embeddings, upsert_jobs
from database import Base


def _db():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def _job(source, external_id, company="Acme", title="Backend Engineer", location="Remote"):
    return {
        "source": source,
        "external_id": external_id,
        "canonical_hash": canonical_hash(company, title, location),
        "title": title,
        "company": company,
        "location": location,
        "remote": True,
        "apply_url": f"https://example.com/{source}/{external_id}",
    }


@patch("connectors.pipeline.embed_texts", return_value=None)
def test_upsert_inserts_new_jobs(_mock_embed):
    db = _db()
    inserted, updated, skipped = upsert_jobs(db, [_job("remotive", "1"), _job("remotive", "2", title="Frontend Engineer")])
    assert inserted == 2
    assert updated == 0
    assert skipped == 0
    assert db.query(models.Job).count() == 2


@patch("connectors.pipeline.embed_texts", return_value=None)
def test_upsert_dedupes_same_job_from_different_sources_in_one_batch(_mock_embed):
    """The exact bug H3 fixes: same role from Remotive AND the company's own
    Greenhouse board must collapse to one row, not two."""
    db = _db()
    jobs = [
        _job("remotive", "r1", company="Acme Corp Inc"),
        _job("greenhouse", "acme-42", company="Acme Corp, Inc."),  # same job, different source
    ]
    inserted, updated, skipped = upsert_jobs(db, jobs)
    assert inserted == 1
    assert updated == 0
    assert skipped == 1
    assert db.query(models.Job).count() == 1


@patch("connectors.pipeline.embed_texts", return_value=None)
def test_upsert_updates_reseen_job_and_inserts_new_one_across_runs(_mock_embed):
    """A job already in the DB (matched by source+external_id) is refreshed,
    not silently ignored — it must surface as `updated`, not `skipped`."""
    db = _db()
    upsert_jobs(db, [_job("remotive", "1")])
    inserted, updated, skipped = upsert_jobs(db, [_job("remotive", "1"), _job("remotive", "2", title="Frontend Engineer")])
    assert inserted == 1
    assert updated == 1
    assert skipped == 0
    assert db.query(models.Job).count() == 2


@patch("connectors.pipeline.embed_texts", return_value=None)
def test_upsert_reseeing_same_job_moves_last_seen_at_forward_without_duplicating(_mock_embed):
    db = _db()
    job = _job("remotive", "1")
    with patch("connectors.pipeline.datetime") as mock_dt:
        mock_dt.utcnow.return_value = datetime(2024, 1, 1)
        upsert_jobs(db, [job])
        first_seen = db.query(models.Job).one().last_seen_at

        mock_dt.utcnow.return_value = datetime(2024, 1, 2)
        inserted, updated, skipped = upsert_jobs(db, [job])

    assert db.query(models.Job).count() == 1
    assert inserted == 0
    assert updated == 1
    assert skipped == 0
    assert db.query(models.Job).one().last_seen_at > first_seen


@patch("connectors.pipeline.embed_texts", return_value=None)
def test_upsert_clears_delisted_at_on_resee(_mock_embed):
    db = _db()
    job = _job("remotive", "1")
    upsert_jobs(db, [job])
    row = db.query(models.Job).one()
    row.delisted_at = datetime.utcnow()
    db.commit()

    upsert_jobs(db, [job])

    assert db.query(models.Job).one().delisted_at is None


@patch("connectors.pipeline.embed_texts", return_value=None)
def test_upsert_updates_company_and_canonical_hash_in_place_not_duplicated(_mock_embed):
    """Task 4: a row stored under the old token-as-company value, re-ingested
    with the real company name, ends as one row with the new company and new
    canonical_hash -- not two rows. upsert_jobs matches on (source,
    external_id), so this must update rather than insert a duplicate."""
    db = _db()
    old = _job("greenhouse", "42", company="grafanalabs", title="Engineer", location="Remote")
    upsert_jobs(db, [old])

    new = _job("greenhouse", "42", company="Grafana Labs", title="Engineer", location="Remote")
    inserted, updated, skipped = upsert_jobs(db, [new])

    assert inserted == 0
    assert updated == 1
    assert skipped == 0
    assert db.query(models.Job).count() == 1
    row = db.query(models.Job).one()
    assert row.company == "Grafana Labs"
    assert row.canonical_hash == canonical_hash("Grafana Labs", "Engineer", "Remote")


@patch("connectors.pipeline.embed_texts", return_value=None)
def test_upsert_rewrites_a_hash_that_already_belongs_to_another_sources_row(_mock_embed):
    """Final review C1: `canonical_hash` must NOT be unique. Task 4 rewrites
    `company` (and therefore the hash) in place on a re-seen row, and the new
    hash can legitimately equal a row another source already stored for the
    same role -- the exact case canonical_hash exists to recognise. Under a
    UNIQUE constraint the bulk UPDATE raised IntegrityError, which escaped
    upsert_jobs and session_scope and rolled back the whole discovery run,
    every run, because the colliding pair stays stored.
    """
    db = _db()
    upsert_jobs(db, [_job("remoteok", "r1", company="Fam", title="Product Manager")])
    upsert_jobs(db, [_job("lever", "42", company="fampay", title="Product Manager")])

    # lever/42 re-seen, now resolving to the real company name -> same hash as remoteok/r1.
    inserted, updated, skipped = upsert_jobs(db, [_job("lever", "42", company="Fam", title="Product Manager")])

    assert (inserted, updated, skipped) == (0, 1, 0)
    assert db.query(models.Job).count() == 2
    hashes = {j.canonical_hash for j in db.query(models.Job).all()}
    assert len(hashes) == 1  # both rows now carry the same hash, and that is allowed


@patch("connectors.pipeline.embed_texts", return_value=None)
def test_upsert_hash_collision_inside_one_batch_does_not_raise(_mock_embed):
    """Same C1 collision, but the UPDATE and the INSERT are in the same batch
    (the bulk UPDATE runs first, so the constraint fired here too)."""
    db = _db()
    upsert_jobs(db, [_job("lever", "42", company="fampay", title="Product Manager")])

    inserted, updated, skipped = upsert_jobs(db, [
        _job("lever", "42", company="Fam", title="Product Manager"),      # update, hash -> Fam's
        _job("remoteok", "r1", company="Fam", title="Product Manager"),   # insert, same hash
    ])

    assert updated == 1
    assert inserted + skipped == 1  # the new row dedupes against the rewritten hash
    assert db.query(models.Job).count() in (1, 2)


@patch("connectors.pipeline.embed_texts", return_value=None)
def test_upsert_inserts_a_live_duplicate_when_the_only_matching_row_is_delisted(_mock_embed):
    """Final review I1: a tombstone must not suppress a live posting. The
    greenhouse row is delisted; the same role arriving live from a feed has to
    be stored, or zero live rows are served for that role forever."""
    db = _db()
    upsert_jobs(db, [_job("greenhouse", "42", company="Acme", title="Product Manager")])
    db.query(models.Job).one().delisted_at = datetime(2026, 1, 1)
    db.commit()

    inserted, updated, skipped = upsert_jobs(db, [_job("remoteok", "r1", company="Acme", title="Product Manager")])

    assert (inserted, updated, skipped) == (1, 0, 0)
    live = db.query(models.Job).filter(models.Job.delisted_at.is_(None)).all()
    assert [j.source for j in live] == ["remoteok"]


@patch("connectors.pipeline.embed_texts", return_value=None)
def test_upsert_reingests_a_repost_under_a_new_external_id_after_delisting(_mock_embed):
    """Final review I1, second half: a board that closes a req and re-opens it
    under a new external_id must be re-ingestable. With delisted rows counted
    in existing_hashes the re-post was skipped forever."""
    db = _db()
    upsert_jobs(db, [_job("greenhouse", "req-1", company="Acme", title="Product Manager")])
    db.query(models.Job).one().delisted_at = datetime(2026, 1, 1)
    db.commit()

    inserted, updated, skipped = upsert_jobs(db, [_job("greenhouse", "req-2", company="Acme", title="Product Manager")])

    assert (inserted, updated, skipped) == (1, 0, 0)
    assert db.query(models.Job).filter(models.Job.delisted_at.is_(None)).one().external_id == "req-2"


@patch("connectors.pipeline.embed_texts", return_value=None)
def test_upsert_still_skips_a_duplicate_of_a_still_listed_row(_mock_embed):
    """The other side of I1: excluding delisted rows must not weaken dedupe
    against rows that are still listed."""
    db = _db()
    upsert_jobs(db, [_job("greenhouse", "42", company="Acme", title="Product Manager")])

    inserted, updated, skipped = upsert_jobs(db, [_job("remoteok", "r1", company="Acme", title="Product Manager")])

    assert (inserted, updated, skipped) == (0, 0, 1)
    assert db.query(models.Job).count() == 1


@patch("connectors.pipeline.embed_texts", return_value=None)
def test_upsert_does_not_erase_stored_salary_when_incoming_is_none(_mock_embed):
    db = _db()
    job = _job("remotive", "1")
    job["salary"] = "$100k"
    upsert_jobs(db, [job])

    reseen = _job("remotive", "1")
    reseen["salary"] = None
    upsert_jobs(db, [reseen])

    assert db.query(models.Job).one().salary == "$100k"


@patch("connectors.pipeline.embed_texts", return_value=None)
def test_upsert_updates_row_when_company_change_alters_canonical_hash(_mock_embed):
    """Task 4 changes `company` for three connectors, which changes canonical_hash.
    Matching must stay on (source, external_id) or this duplicates the row."""
    db = _db()
    upsert_jobs(db, [_job("remotive", "1", company="Acme")])

    inserted, updated, skipped = upsert_jobs(db, [_job("remotive", "1", company="Acme Renamed")])

    assert inserted == 0
    assert updated == 1
    assert skipped == 0
    assert db.query(models.Job).count() == 1
    assert db.query(models.Job).one().company == "Acme Renamed"


def _counting(db):
    """Count statements actually sent to the DBAPI cursor, at the
    Engine/Connection level — NOT by wrapping Session.execute. ORM bulk
    operations (bulk_insert_mappings/bulk_update_mappings) call
    connection.execute(...) directly inside orm/persistence.py, bypassing
    Session.execute entirely; a counter on the latter only ever sees the
    legacy Query SELECT and silently misses both bulk statements (found in
    review round 2 — the round-1 counter was vacuously true on every test).
    before_cursor_execute fires once per statement sent to the cursor,
    including once per bulk executemany, so this is what the <=3 budget
    actually has to bound.
    """
    count = [0]
    engine = db.get_bind()

    def _count(*args, **kwargs):
        count[0] += 1

    event.listen(engine, "before_cursor_execute", _count)
    return lambda: count[0]


@patch("connectors.pipeline.embed_texts", return_value=None)
def test_upsert_uses_at_most_three_queries_regardless_of_batch_size(_mock_embed):
    """Fixes H1: was 1 SELECT + 1 INSERT per job (N+1). Must not scale with batch size.
    Raised from 2 to 3 (Task 2, freshness): one SELECT, one bulk INSERT, one bulk UPDATE."""
    db = _db()
    query_count = _counting(db)
    jobs = [_job("remotive", str(i), title=f"Role {i}") for i in range(50)]
    upsert_jobs(db, jobs)
    assert query_count() <= 3


@patch("connectors.pipeline.embed_texts", return_value=None)
def test_upsert_uses_at_most_three_queries_for_an_update_only_batch(_mock_embed):
    """The bulk UPDATE path, isolated: no new rows at all, every job in the
    batch is already stored. Must still be one SELECT + one bulk UPDATE (no
    insert query at all), and still bounded at <=3.

    The fixtures are deliberately HETEROGENEOUS — one job carries a salary and
    a posted_at the other 49 lack. bulk_update_mappings only collapses to a
    single executemany when every mapping has the same key set; with uniform
    fixtures the <=3 bound held by construction (the loop fills all
    _UPDATE_FIELDS unconditionally) rather than by this test, so a future
    data-dependent conditional in that loop would regress to N+1 and still
    ship green. Measured: 6 uniform mappings -> 1 statement, 6 heterogeneous
    mappings -> 6 statements.
    """
    db = _db()
    jobs = [_job("remotive", str(i), title=f"Role {i}") for i in range(50)]
    jobs[7]["salary"] = "$180k"
    jobs[7]["posted_at"] = datetime(2026, 9, 1)
    upsert_jobs(db, jobs)  # seed: all 50 already exist

    query_count = _counting(db)
    inserted, updated, skipped = upsert_jobs(db, jobs)  # re-seen batch: update-only
    assert inserted == 0
    assert updated == 50
    assert skipped == 0
    assert query_count() <= 3


@patch("connectors.pipeline.embed_texts", return_value=None)
def test_upsert_uses_at_most_three_queries_for_a_mixed_new_and_reseen_batch(_mock_embed):
    """The path the ceiling is actually meant to bound: a batch with both new
    rows (bulk INSERT) and already-stored rows (bulk UPDATE) in the same
    call, still at most one SELECT + one bulk INSERT + one bulk UPDATE."""
    db = _db()
    existing_jobs = [_job("remotive", str(i), title=f"Role {i}") for i in range(25)]
    upsert_jobs(db, existing_jobs)  # seed half the batch as already-stored

    query_count = _counting(db)
    mixed = existing_jobs + [_job("remotive", f"new-{i}", title=f"New Role {i}") for i in range(25)]
    inserted, updated, skipped = upsert_jobs(db, mixed)
    assert inserted == 25
    assert updated == 25
    assert skipped == 0
    assert query_count() <= 3


@patch("matching.embeddings.get_settings")
def test_upsert_leaves_embedding_null_without_voyage_key(mock_settings):
    """embed_texts no-ops without VOYAGE_API_KEY — must not crash the pipeline."""
    mock_settings.return_value.voyage_api_key = None
    db = _db()
    upsert_jobs(db, [_job("remotive", "1")])
    assert db.query(models.Job).first().embedding is None


@patch("connectors.pipeline.embed_texts")
def test_the_backlog_pass_sets_embedding_from_voyage(mock_embed):
    """Saving never embeds (discovery must not wait on Voyage); the backlog pass does."""
    vec_a, vec_b = [0.1] * 512, [0.3] * 512
    mock_embed.side_effect = lambda texts, input_type: [vec_a if "Backend" in t else vec_b for t in texts]
    db = _db()
    upsert_jobs(db, [_job("remotive", "1"), _job("remotive", "2", title="Frontend Engineer")])
    mock_embed.assert_not_called()
    assert backfill_job_embeddings(db) == 2
    embeddings = {j.title: list(j.embedding) for j in db.query(models.Job).all()}
    assert embeddings["Backend Engineer"] == vec_a
    assert embeddings["Frontend Engineer"] == vec_b


@patch("connectors.pipeline.embed_texts", return_value=None)
def test_upsert_skips_near_duplicate_reworded_title_same_company(_mock_embed):
    """F4 gap simhash-py closes: exact canonical_hash dedupe misses a
    reworded title from the same company; near-dup detection should not."""
    db = _db()
    jobs = [
        _job("remotive", "1", company="Acme", title="Senior Backend Engineer - Python/FastAPI - Remote"),
        _job("greenhouse", "2", company="Acme", title="Backend Engineer (Senior) - Python & FastAPI - Remote"),
    ]
    inserted, updated, skipped = upsert_jobs(db, jobs)
    assert inserted == 1
    assert updated == 0
    assert skipped == 1
    assert db.query(models.Job).count() == 1


@patch("connectors.pipeline.embed_texts", return_value=None)
def test_upsert_infers_seniority_from_title(_mock_embed):
    db = _db()
    upsert_jobs(db, [_job("remotive", "1", title="Senior Backend Engineer")])
    assert db.query(models.Job).first().seniority == "senior"


@patch("connectors.pipeline.embed_texts", return_value=None)
def test_upsert_extracts_skills_from_title_and_description(_mock_embed):
    db = _db()
    job = _job("remotive", "1")
    job["description"] = "Must know Python and PostgreSQL. Docker a plus."
    upsert_jobs(db, [job])
    assert db.query(models.Job).first().skills == ["Docker", "PostgreSQL", "Python"]


@patch("connectors.pipeline.embed_texts", side_effect=RuntimeError("Voyage 429: reduced rate limits"))
def test_an_embedding_outage_never_loses_discovered_jobs(_mock_embed):
    """Found live: Voyage's free-tier rate limit raised inside upsert_jobs before
    the insert, so the whole discovery run was lost. Jobs are saved without an
    embedding instead (matching skips un-embedded jobs until they're backfilled)."""
    db = _db()
    inserted, _, _ = upsert_jobs(db, [_job("remotive", "1"), _job("remotive", "2", title="Frontend Engineer")])
    assert inserted == 2
    assert db.query(models.Job).count() == 2
    assert all(j.embedding is None for j in db.query(models.Job).all())


def test_backfill_embeds_jobs_saved_during_an_outage_and_tolerates_another():
    from connectors.pipeline import backfill_job_embeddings

    db = _db()
    with patch("connectors.pipeline.embed_texts", side_effect=RuntimeError("429")):
        upsert_jobs(db, [_job("remotive", "1"), _job("remotive", "2", title="Frontend Engineer")])
        assert backfill_job_embeddings(db) == 0  # still down: no crash, nothing lost

    with patch("connectors.pipeline.embed_texts", return_value=[[0.1] * 512, [0.2] * 512]):
        assert backfill_job_embeddings(db) == 2
    assert all(j.embedding is not None for j in db.query(models.Job).all())


def test_backfill_under_a_rate_limit_keeps_what_it_embedded_and_stops():
    """Found live: Voyage's no-payment tier is 3 RPM / 10K TPM. The backfill sent
    all 50 pending jobs (full descriptions) in one request, over 10K tokens, so
    every run was rejected and embeddings never caught up. Batches must fit under
    the token cap, and a 429 mid-pass keeps the earlier batches and stops."""
    from voyageai.error import RateLimitError
    from connectors.pipeline import backfill_job_embeddings

    db = _db()
    jobs = []
    for i in range(12):  # each capped at EMBED_CHARS: 6 per request, so 2 requests
        j = _job("remotive", str(i), title=f"Engineer {i}")
        j["description"] = "word " * 6000
        jobs.append(j)
    with patch("connectors.pipeline.embed_texts", return_value=None):
        upsert_jobs(db, jobs)

    calls = []

    def fake_embed(texts, input_type):
        calls.append(texts)
        if len(calls) == 2:
            raise RateLimitError("reduced rate limits of 3 RPM and 10K TPM")
        return [[0.1] * 512 for _ in texts]

    with patch("connectors.pipeline.embed_texts", side_effect=fake_embed):
        assert backfill_job_embeddings(db) == 6
    assert len(calls) == 2  # stopped at the 429 on the second request
    assert all(sum(len(t) for t in texts) <= 24_000 for texts in calls)  # ~<10K tokens/request
    assert sum(j.embedding is not None for j in db.query(models.Job).all()) == 6


def test_backfill_skips_delisted_jobs():
    """Voyage's free tier is 3 RPM — a dead job must never take a live job's
    slot in the queue."""
    from connectors.pipeline import backfill_job_embeddings

    db = _db()
    with patch("connectors.pipeline.embed_texts", return_value=None):
        upsert_jobs(db, [_job("remotive", "gone", title="Gone Role"),
                         _job("remotive", "live", title="Live Role")])
    db.query(models.Job).filter(models.Job.external_id == "gone").one().delisted_at = datetime(2026, 1, 1)
    db.commit()

    with patch("connectors.pipeline.embed_texts", side_effect=lambda texts, input_type: [[0.1] * 512 for _ in texts]):
        assert backfill_job_embeddings(db) == 1
    assert db.query(models.Job).filter(models.Job.embedding.isnot(None)).one().title == "Live Role"


def test_backfill_embeds_the_newest_jobs_first():
    """Found live: 1,743 jobs waited for a vector on the 3 RPM free tier, picked in no
    order, so the fresh India PM postings from today's boards never got one."""
    from datetime import datetime, timedelta
    from connectors.pipeline import backfill_job_embeddings

    db = _db()
    with patch("connectors.pipeline.embed_texts", return_value=None):
        upsert_jobs(db, [_job("remotive", "old", title="Old Role"), _job("greenhouse", "new", title="Product Manager")])
    old = db.query(models.Job).filter(models.Job.external_id == "old").one()
    old.fetched_at = datetime.utcnow() - timedelta(days=30)
    db.commit()

    with patch("connectors.pipeline.embed_texts", side_effect=lambda texts, input_type: [[0.1] * 512 for _ in texts]):
        assert backfill_job_embeddings(db, limit=1) == 1
    assert db.query(models.Job).filter(models.Job.embedding.isnot(None)).one().title == "Product Manager"


def test_backfill_packs_several_long_jobs_into_one_request():
    """A job's head (title, company, role summary) is what matching needs. Embedding the
    first EMBED_CHARS instead of a whole 30K-char description packs ~6 jobs a request
    on the free tier instead of one (live: 2-4 jobs a minute, 184 waiting)."""
    from connectors.pipeline import EMBED_CHARS, backfill_job_embeddings

    db = _db()
    jobs = []
    for i in range(3):
        j = _job("remotive", str(i), title=f"Engineer {i}")
        j["description"] = "word " * 6000
        jobs.append(j)
    with patch("connectors.pipeline.embed_texts", return_value=None):
        upsert_jobs(db, jobs)
    calls = []

    def fake_embed(texts, input_type):
        calls.append(texts)
        return [[0.1] * 512 for _ in texts]

    with patch("connectors.pipeline.embed_texts", side_effect=fake_embed):
        assert backfill_job_embeddings(db) == 3
    assert len(calls) == 1 and all(len(t) <= EMBED_CHARS for t in calls[0])
