"""Migration 0040: RLS on contacts, outreach, gmail_credentials, fill_snapshots.

SQLite has no RLS, so the always-on tests pin the migration's shape and the two
unauthenticated routes' wiring; the isolation itself is proven only in the Postgres
lane (TEST_DATABASE_URL).
"""
import importlib.util
import os
from pathlib import Path

import pytest
from sqlalchemy import text

import models

TABLES = ["contacts", "outreach", "gmail_credentials", "fill_snapshots"]
API_DIR = Path(__file__).resolve().parent.parent
needs_pg = pytest.mark.skipif(not os.environ.get("TEST_DATABASE_URL"), reason="TEST_DATABASE_URL not set; SQLite lane")


def test_migration_0040_chains_from_0039_names_all_four_tables_and_is_the_only_head():
    from alembic.config import Config
    from alembic.script import ScriptDirectory

    [path] = list((API_DIR / "alembic" / "versions").glob("0040_*.py"))
    spec = importlib.util.spec_from_file_location("m0040", path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    assert (m.revision, m.down_revision) == ("0040", "0039")
    assert set(m._CONDITIONS) == set(TABLES)

    cfg = Config(str(API_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(API_DIR / "alembic"))
    assert ScriptDirectory.from_config(cfg).get_heads() == ["0040"]


def test_unsubscribe_reads_on_the_owner_role():
    """The recipient has no account, so there is no tenant to set; the outreach row is
    found by its signed id. On the app role RLS would hide it and the opt-out would
    silently write nothing."""
    from database import get_owner_db
    from outreach.api import router

    [route] = [r for r in router.routes if r.path == "/outreach/unsubscribe/{token}"]
    assert get_owner_db in [d.call for d in route.dependant.dependencies]


@needs_pg
def test_one_user_cannot_read_anothers_rows_in_any_of_the_four_tables(db_session):
    rows = {}
    for who in ("a", "b"):
        user = models.User(email=f"rls-{who}@example.com", password_hash="x")
        db_session.add(user)
        db_session.flush()
        profile = models.Profile(user_id=user.id, full_name=who)
        job = models.Job(source="rls", external_id=who, canonical_hash=who, title="T",
                         company="Acme", apply_url="https://example.invalid")
        db_session.add_all([profile, job])
        db_session.flush()
        app = models.Application(profile_id=profile.id, job_id=job.id)
        contact = models.Contact(profile_id=profile.id, company="Acme", full_name=who)
        db_session.add_all([app, contact])
        db_session.flush()
        db_session.add_all([
            models.Outreach(profile_id=profile.id, application_id=app.id, contact_id=contact.id),
            models.GmailCredential(user_id=user.id, refresh_token_encrypted="x"),
            models.FillSnapshot(application_id=app.id, record={}),
        ])
        db_session.flush()
        rows[who] = user.id

    db_session.execute(text("SET LOCAL ROLE job_copilot_app"))
    for table in TABLES:  # no tenant set: fail closed
        assert db_session.execute(text(f"SELECT count(*) FROM {table}")).scalar() == 0, table

    db_session.execute(text("SELECT set_config('app.current_user_id', :uid, true)"), {"uid": rows["a"]})
    for table in TABLES:
        assert db_session.execute(text(f"SELECT count(*) FROM {table}")).scalar() == 1, table
    assert db_session.execute(text("SELECT user_id FROM gmail_credentials")).scalar() == rows["a"]
