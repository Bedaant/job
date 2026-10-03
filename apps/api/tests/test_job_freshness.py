from datetime import datetime

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import models
from connectors.normalize import canonical_hash
from database import Base


def _db():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def _job(delisted_at=None):
    return models.Job(
        source="remotive",
        external_id="1",
        canonical_hash=canonical_hash("Acme", "Backend Engineer", "Remote"),
        title="Backend Engineer",
        company="Acme",
        location="Remote",
        apply_url="https://example.com/remotive/1",
        delisted_at=delisted_at,
    )


def test_model_declares_the_freshness_indexes_migration_0022_creates():
    """Final review I2: migration 0022 creates ix_jobs_posted_at and
    ix_jobs_last_seen_at, but the model didn't declare them. alembic/env.py
    autogenerates against Base.metadata, so the next --autogenerate would emit
    op.drop_index for both and silently revert Task 1 -- and the suite would
    not notice, because create_all builds from the model."""
    names = {ix.name for ix in models.Job.__table__.indexes}
    assert {"ix_jobs_posted_at", "ix_jobs_last_seen_at"} <= names


def test_model_does_not_declare_canonical_hash_unique():
    """Final review C1: the UNIQUE constraint is gone from the schema; dedupe
    is upsert_jobs' job. Autogenerate must not resurrect it either."""
    assert models.Job.__table__.c.canonical_hash.unique is not True
    assert not any(
        {c.name for c in uc.columns} == {"canonical_hash"}
        for uc in models.Job.__table__.constraints
        if hasattr(uc, "columns")
    )


def test_job_delisted_at_defaults_to_none():
    db = _db()
    job = _job()
    db.add(job)
    db.commit()

    reloaded = db.query(models.Job).filter_by(id=job.id).one()
    assert reloaded.delisted_at is None


def test_job_delisted_at_persists_a_datetime():
    db = _db()
    job = _job()
    db.add(job)
    db.commit()

    job.delisted_at = datetime(2026, 9, 30, 12, 0, 0)
    db.commit()

    reloaded = db.query(models.Job).filter_by(id=job.id).one()
    assert reloaded.delisted_at == datetime(2026, 9, 30, 12, 0, 0)
