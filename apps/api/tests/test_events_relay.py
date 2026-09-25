from unittest.mock import MagicMock

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import models
from database import Base
from events.outbox import write_event
from events.relay import relay_once


def _db():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def _user(db):
    user = models.User(email="a@b.com", password_hash="x")
    db.add(user)
    db.commit()
    return user


def test_relay_once_publishes_unpublished_events_and_marks_them():
    db = _db()
    user = _user(db)
    write_event(db, user.id, "match.new", {"x": 1})
    write_event(db, user.id, "match.new", {"x": 2})
    db.commit()

    redis = MagicMock()
    published = relay_once(db, redis)

    assert published == 2
    assert redis.publish.call_count == 2
    assert db.query(models.Event).filter(models.Event.published_at.is_(None)).count() == 0


def test_relay_once_does_not_republish_already_published_rows():
    db = _db()
    user = _user(db)
    write_event(db, user.id, "match.new", {"x": 1})
    db.commit()

    redis = MagicMock()
    relay_once(db, redis)
    published_again = relay_once(db, redis)

    assert published_again == 0
    assert redis.publish.call_count == 1


def test_relay_once_publishes_to_per_user_redis_channel():
    db = _db()
    user = _user(db)
    write_event(db, user.id, "application.status_changed", {"status": "applied"})
    db.commit()

    redis = MagicMock()
    relay_once(db, redis)

    channel_arg = redis.publish.call_args[0][0]
    assert channel_arg == f"user:{user.id}"


def test_relay_once_returns_zero_when_nothing_pending():
    db = _db()
    redis = MagicMock()
    assert relay_once(db, redis) == 0
    redis.publish.assert_not_called()
