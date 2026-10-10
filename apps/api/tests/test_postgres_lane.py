"""GAPS 5.4 — the real-Postgres test lane.

The default suite is in-memory SQLite: fast, isolated, no infrastructure. That covers
ORM-level logic but **structurally cannot** cover the things that have actually needed
verifying: Alembic migration correctness, pgvector, JSONB semantics, real enum types, and
`NULLS NOT DISTINCT` on the partial-unique constraints REACH-B relies on.

Migrations 0025 and 0026 were verified by INSPECTING the live Neon schema, because no
test could do it. This lane is what replaces that.

These tests check the LANE's wiring, not Postgres. The Postgres path itself is exercised
only when `TEST_DATABASE_URL` is set, and the two tests below that need it skip cleanly
otherwise — so this file is honest on both sides of the switch rather than silently
passing because nothing ran.
"""
import os

import pytest

import models

PG = os.environ.get("TEST_DATABASE_URL")
needs_pg = pytest.mark.skipif(not PG, reason="TEST_DATABASE_URL not set; SQLite lane")


def test_the_default_lane_is_sqlite_and_needs_no_infrastructure(db_session):
    """`pytest -q` must stay runnable with nothing installed. A test lane that requires a
    running database is a lane people stop running."""
    name = db_session.get_bind().dialect.name
    expected = "postgresql" if PG else "sqlite"
    assert name == expected


@needs_pg
def test_the_schema_came_from_alembic_not_create_all(db_session):
    """The point of the lane. `Base.metadata.create_all` builds the schema the ORM
    DESCRIBES, so it can never catch a migration that is wrong, missing or out of order.
    If `alembic_version` is present and at head, the schema under test was migrated."""
    from sqlalchemy import text

    from pathlib import Path

    from alembic.config import Config
    from alembic.script import ScriptDirectory

    api_dir = Path(__file__).resolve().parent.parent
    cfg = Config(str(api_dir / "alembic.ini"))
    cfg.set_main_option("script_location", str(api_dir / "alembic"))
    head = ScriptDirectory.from_config(cfg).get_current_head()
    row = db_session.execute(text("select version_num from alembic_version")).scalar()
    assert row == head, f"expected the lane to migrate to head {head!r}, got {row!r}"


@needs_pg
def test_pgvector_is_available_in_the_lane(db_session):
    """Migration 0004 declares `Vector` columns. The plain `postgres:16-alpine` image has
    no `vector` extension — its control file is simply absent — which is why this lane
    uses `pgvector/pgvector:pg16` and could not just point at the dev `db` service."""
    from sqlalchemy import text

    ext = db_session.execute(
        text("select extname from pg_extension where extname = 'vector'")
    ).scalar()
    assert ext == "vector"


@needs_pg
def test_a_contact_may_exist_before_an_email_on_real_postgres(db_session):
    """Worth having specifically on Postgres: REACH-B relies on NULL emails NOT colliding
    under `UNIQUE(profile_id, email)`. SQLite and Postgres both allow it, but they do so
    for different reasons, and this constraint guards a privacy property — so it is
    asserted against the engine that actually runs in production."""
    user = models.User(email="pg@example.com", password_hash="x")
    db_session.add(user)
    db_session.flush()
    profile = models.Profile(user_id=user.id, full_name="PG Tester")
    db_session.add(profile)
    db_session.flush()
    db_session.add(models.Contact(profile_id=profile.id, company="Acme", full_name="One"))
    db_session.add(models.Contact(profile_id=profile.id, company="Acme", full_name="Two"))
    db_session.flush()
    assert db_session.query(models.Contact).count() == 2
