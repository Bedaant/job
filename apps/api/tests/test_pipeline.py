from unittest.mock import patch

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import models
from connectors.normalize import canonical_hash
from connectors.pipeline import upsert_jobs
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
    inserted, skipped = upsert_jobs(db, [_job("remotive", "1"), _job("remotive", "2", title="Frontend Engineer")])
    assert inserted == 2
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
    inserted, skipped = upsert_jobs(db, jobs)
    assert inserted == 1
    assert skipped == 1
    assert db.query(models.Job).count() == 1


@patch("connectors.pipeline.embed_texts", return_value=None)
def test_upsert_skips_jobs_already_in_db_across_runs(_mock_embed):
    db = _db()
    upsert_jobs(db, [_job("remotive", "1")])
    inserted, skipped = upsert_jobs(db, [_job("remotive", "1"), _job("remotive", "2", title="Frontend Engineer")])
    assert inserted == 1
    assert skipped == 1
    assert db.query(models.Job).count() == 2


@patch("connectors.pipeline.embed_texts", return_value=None)
def test_upsert_uses_at_most_two_queries_regardless_of_batch_size(_mock_embed):
    """Fixes H1: was 1 SELECT + 1 INSERT per job (N+1). Must not scale with batch size."""
    db = _db()
    query_count = 0
    original_execute = db.execute

    def counting_execute(*args, **kwargs):
        nonlocal query_count
        query_count += 1
        return original_execute(*args, **kwargs)

    db.execute = counting_execute
    jobs = [_job("remotive", str(i), title=f"Role {i}") for i in range(50)]
    upsert_jobs(db, jobs)
    # generous ceiling — the point is O(1), not O(n); 50 jobs must not mean ~100 queries
    assert query_count <= 5


@patch("matching.embeddings.get_settings")
def test_upsert_leaves_embedding_null_without_voyage_key(mock_settings):
    """embed_texts no-ops without VOYAGE_API_KEY — must not crash the pipeline."""
    mock_settings.return_value.voyage_api_key = None
    db = _db()
    upsert_jobs(db, [_job("remotive", "1")])
    assert db.query(models.Job).first().embedding is None


@patch("connectors.pipeline.embed_texts")
def test_upsert_sets_embedding_from_voyage(mock_embed):
    vec_a, vec_b = [0.1] * 512, [0.3] * 512
    mock_embed.return_value = [vec_a, vec_b]
    db = _db()
    upsert_jobs(db, [_job("remotive", "1"), _job("remotive", "2", title="Frontend Engineer")])
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
    inserted, skipped = upsert_jobs(db, jobs)
    assert inserted == 1
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
    inserted, _ = upsert_jobs(db, [_job("remotive", "1"), _job("remotive", "2", title="Frontend Engineer")])
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
    for i in range(3):
        j = _job("remotive", str(i), title=f"Engineer {i}")
        j["description"] = "word " * 6000  # ~30K chars: one job alone is at the cap
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
        assert backfill_job_embeddings(db) == 1
    assert len(calls) == 2  # stopped at the 429, didn't spend a request on the third
    assert all(sum(len(t) for t in texts) <= 24_000 for texts in calls)  # ~<10K tokens/request
    assert sum(j.embedding is not None for j in db.query(models.Job).all()) == 1


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
