"""COLLECT-F — `connector_runs` retention.

COLLECT-B started writing one row per source per discovery run and nothing ever
removed them: ~14 rows an hour, forever. `/sources` only reads the newest 200,
so the rest is pure growth.

The trap: `connector_runs` is not only an ingestion log. F5's ATS classifier
(`connectors/discovery.py::discover_ats_for_domain`) writes rows there with its
proposed pattern in `notes`, and `models.ConnectorRun`'s own docstring calls that
**the review surface the owner promotes proposals from** — decided as "no new
table, no admin UI, this is it". Age-pruning the table blindly would delete
un-reviewed proposals, which is destroying the only copy of a human decision
queue. Those rows are never pruned.
"""
from datetime import datetime, timedelta

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import models
from database import Base
from workers.jobs import CLASSIFIER_SOURCE, RUN_RETENTION_DAYS, _prune_connector_runs


def _db():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False},
                           poolclass=StaticPool)
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def _run(db, source, days_old, notes=None):
    db.add(models.ConnectorRun(source=source, fetched=1, notes=notes,
                               ran_at=datetime.utcnow() - timedelta(days=days_old)))
    db.commit()


def _sources(db):
    return sorted(r.source for r in db.query(models.ConnectorRun).all())


def test_ingestion_rows_older_than_the_window_are_removed():
    db = _db()
    _run(db, "greenhouse", days_old=RUN_RETENTION_DAYS + 1)
    _run(db, "jobicy", days_old=1)

    _prune_connector_runs(db)
    db.commit()

    assert _sources(db) == ["jobicy"]


def test_the_ats_classifiers_proposals_are_never_pruned():
    """They are the owner's review queue, not a log. Deleting an un-reviewed
    proposal destroys the only copy of it."""
    db = _db()
    _run(db, CLASSIFIER_SOURCE, days_old=400, notes={"pattern": "boards.acme.com"})

    _prune_connector_runs(db)
    db.commit()

    assert _sources(db) == [CLASSIFIER_SOURCE]


def test_pruning_keeps_enough_history_for_the_sources_endpoint():
    """GET /sources reads the newest rows per source to report health; a window
    that pruned today's runs would blind it."""
    db = _db()
    for hours in (1, 5, 20):
        db.add(models.ConnectorRun(source="greenhouse", fetched=1,
                                   ran_at=datetime.utcnow() - timedelta(hours=hours)))
    db.commit()

    _prune_connector_runs(db)
    db.commit()

    assert len(db.query(models.ConnectorRun).all()) == 3
    assert RUN_RETENTION_DAYS >= 7, "a week is the floor for a useful health history"


def test_pruning_an_empty_table_is_a_no_op():
    db = _db()
    _prune_connector_runs(db)
    db.commit()
    assert _sources(db) == []
