from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import models
from database import Base
from events.outbox import write_event


def _db():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def _user(db):
    user = models.User(email="a@b.com", password_hash="x")
    db.add(user)
    db.commit()
    return user


def test_write_event_creates_unpublished_event_row():
    db = _db()
    user = _user(db)

    event = write_event(db, user.id, "match.new", {"match_id": "m1"})
    db.commit()

    assert db.query(models.Event).count() == 1
    assert event.user_id == user.id
    assert event.type == "match.new"
    assert event.payload == {"match_id": "m1"}
    assert event.published_at is None


def test_write_event_does_not_commit_itself():
    """Caller controls the transaction — write_event must be safe to call
    alongside other same-transaction writes (ADR-012's outbox pattern)."""
    db = _db()
    user = _user(db)

    write_event(db, user.id, "match.new", {"match_id": "m1"})
    db.rollback()

    assert db.query(models.Event).count() == 0
