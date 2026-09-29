from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import models
from database import Base
from matching.service import build_matches


def _db():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def _profile(db, fact_centroid=None):
    user = models.User(email="a@b.com", password_hash="x")
    db.add(user)
    db.commit()
    profile = models.Profile(user_id=user.id, persona="developer", fact_centroid=fact_centroid)
    db.add(profile)
    db.commit()
    return profile


def _job(db, title, embedding=None, skills=None):
    job = models.Job(
        source="remotive", external_id=title, canonical_hash=title, title=title,
        company="Acme", apply_url="https://x", embedding=embedding, skills=skills or [],
    )
    db.add(job)
    db.commit()
    return job


def test_build_matches_returns_empty_without_fact_centroid():
    db = _db()
    profile = _profile(db, fact_centroid=None)
    _job(db, "Backend Engineer", embedding=[1.0] * 512)
    assert build_matches(db, profile) == []


def test_build_matches_scores_and_orders_by_similarity():
    db = _db()
    profile = _profile(db, fact_centroid=[1.0] + [0.0] * 511)
    _job(db, "Close Match", embedding=[1.0] + [0.0] * 511)
    _job(db, "Far Match", embedding=[0.0, 1.0] + [0.0] * 510)

    matches = build_matches(db, profile)

    assert [m.job.title for m in matches] == ["Close Match", "Far Match"]
    assert matches[0].score > matches[1].score
    assert matches[0].breakdown["semantic"] == 1.0


def test_build_matches_upserts_not_duplicates():
    db = _db()
    profile = _profile(db, fact_centroid=[1.0] + [0.0] * 511)
    _job(db, "Backend Engineer", embedding=[1.0] + [0.0] * 511)

    build_matches(db, profile)
    build_matches(db, profile)

    assert db.query(models.Match).count() == 1


def test_build_matches_writes_match_new_event_once_not_on_rebuild():
    """ADR-012 outbox: a genuinely new match fires match.new; re-scoring an
    already-seen match on a later build_matches call must not re-fire it."""
    db = _db()
    profile = _profile(db, fact_centroid=[1.0] + [0.0] * 511)
    _job(db, "Backend Engineer", embedding=[1.0] + [0.0] * 511)

    build_matches(db, profile)
    build_matches(db, profile)

    events = db.query(models.Event).filter(models.Event.type == "match.new").all()
    assert len(events) == 1
    assert events[0].user_id == profile.user_id
    assert events[0].published_at is None


def test_build_matches_skips_jobs_without_embedding():
    db = _db()
    profile = _profile(db, fact_centroid=[1.0] + [0.0] * 511)
    _job(db, "No Embedding Yet", embedding=None)
    assert build_matches(db, profile) == []


def test_build_matches_excludes_jobs_failing_hard_filters():
    db = _db()
    user = models.User(email="c@d.com", password_hash="x")
    db.add(user)
    db.commit()
    profile = models.Profile(
        user_id=user.id, persona="developer",
        fact_centroid=[1.0] + [0.0] * 511,
        prefs={"locations": ["Bengaluru"]},
    )
    db.add(profile)
    db.commit()
    _job(db, "Backend Engineer, Berlin", embedding=[1.0] + [0.0] * 511)
    berlin = db.query(models.Job).filter(models.Job.title.like("%Berlin%")).first()
    berlin.location = "Berlin"
    berlin.remote = False
    db.commit()

    assert build_matches(db, profile) == []


def test_build_matches_breakdown_is_json_serializable_with_numpy_input():
    """Regression: a real Postgres connection returns numpy.float32 arrays
    from pgvector columns (unlike the SQLite test engine, which round-trips
    plain lists). A numpy scalar buried in `breakdown` fails json.dumps on
    insert — only reproducible against real Postgres, not caught by the
    other tests here, so this test fakes the numpy-array shape directly."""
    import json
    import numpy as np

    db = _db()
    profile = _profile(db, fact_centroid=np.array([1.0] + [0.0] * 511, dtype=np.float32))
    _job(db, "Backend Engineer", embedding=np.array([1.0] + [0.0] * 511, dtype=np.float32))

    matches = build_matches(db, profile)

    json.dumps(matches[0].breakdown)  # raises if any value is still numpy


def test_build_matches_takes_its_top_n_inside_the_active_campaigns_bounds():
    """Live (2026-09-29): the global top 20 was picked first, then the Matches page kept
    the India ones. US jobs scoring higher starve the India ones out entirely."""
    db = _db()
    profile = _profile(db, fact_centroid=[1.0] + [0.0] * 511)
    us = [_job(db, f"US PM {i}", embedding=[1.0] + [0.0] * 511) for i in range(3)]  # best score
    for j in us:
        j.location = "Remote - US"
    india = _job(db, "India PM", embedding=[0.6, 0.8] + [0.0] * 510)
    india.location = "Bengaluru, India"
    campaign = models.Campaign(profile_id=profile.id, name="India", roles=[], locations=["India"],
                               remote_only=False, sources=[], status=models.CampaignStatus.draft)
    db.add(campaign)
    db.commit()
    assert [m.job.title for m in build_matches(db, profile, limit=1)] == ["US PM 0"], "a draft doesn't bound"
    campaign.status = models.CampaignStatus.active
    db.commit()

    assert [m.job.title for m in build_matches(db, profile, limit=1)] == ["India PM"]
