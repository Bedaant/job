import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import models
from database import Base


@pytest.fixture()
def db_session():
    """In-memory SQLite per test — fast, isolated, no Postgres/Docker required.

    Not a substitute for the real Postgres integration suite (Alembic migration
    correctness, pgvector, JSONB semantics) — those need a real Postgres and are
    blocked on Docker approval (DEPENDENCIES.md §5). This covers ORM-level logic:
    tenancy, relationships, constraints that behave the same on both engines.
    """
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()
