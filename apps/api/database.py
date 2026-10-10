from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

from core.config import get_settings

settings = get_settings()

# Two engines, deliberately different roles (migration 0010, docs/WORKLOG.md):
# `engine` (the owner role from database_url) is for Alembic and for
# background workers/scripts that are legitimately cross-tenant by design —
# the events relay must see every user's unpublished events; job discovery
# only touches the non-tenant `jobs` table. `app_engine` (app_database_url,
# a deliberately restricted, non-BYPASSRLS role once migration 0010's role
# exists) is what every real HTTP request runs on — Postgres Row-Level
# Security only protects anything if the connecting role can't bypass it.
# Falls back to `database_url` when `app_database_url` is unset (e.g. before
# the role/password exist yet, or on the SQLite test engine, which has no
# concept of Postgres roles at all).
def engine_kwargs(url: str) -> dict:
    # Neon's pooler is PgBouncer in transaction mode: keep the client pool small and recycle
    # before its idle limits. Statement timeouts are role-level (migration 0029): the pooler
    # rejects startup `options` and SET does not survive transaction pooling (verified 2026-10-10).
    if not url.startswith("postgresql"):
        return {"pool_pre_ping": True}
    return {"pool_pre_ping": True, "pool_size": 5, "max_overflow": 5, "pool_recycle": 300}


engine = create_engine(settings.database_url, **engine_kwargs(settings.database_url))
_app_url = settings.app_database_url or settings.database_url
app_engine = create_engine(_app_url, **engine_kwargs(_app_url))

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
AppSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=app_engine)
Base = declarative_base()


def get_db():
    """FastAPI dependency — request-scoped session on the RLS-restricted
    role. Every real user-facing endpoint goes through this.
    """
    db = AppSessionLocal()
    try:
        yield db
    finally:
        db.close()


@contextmanager
def session_scope():
    """For use outside a request (startup hooks, RQ workers, scripts).

    `next(get_db())` — the previous pattern here — pulls the generator's first
    value without ever running its `finally`, leaking the connection for the
    process lifetime. This closes and rolls back on error, always.
    """
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
