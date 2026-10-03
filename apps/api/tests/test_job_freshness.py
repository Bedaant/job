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
