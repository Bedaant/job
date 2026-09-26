"""Row-Level Security for tenant-scoped tables, plus the restricted role
that makes it real.

Real finding, not assumed: `neondb_owner` (the only role this project has
ever connected as) has `rolbypassrls = True` — confirmed by querying
pg_roles directly. RLS policies are silently a no-op for any role with that
attribute or for a superuser, regardless of ENABLE/FORCE ROW LEVEL SECURITY.
So this migration does two things together, because doing only the policy
half would ship decorative security:

1. Create `job_copilot_app` — NOSUPERUSER, no BYPASSRLS attribute (the
   default when unspecified), granted ordinary DML on every table. This
   role is what the FastAPI app connects as for real user requests
   (APP_DATABASE_URL). Migrations and background workers (the events relay,
   which must see every user's unpublished events by design, and job
   discovery, which only touches the non-tenant `jobs` table) keep using
   the existing owner role (DATABASE_URL) — RLS is meant to bind the
   "acting on behalf of one specific authenticated user" code path, which
   is exactly and only the HTTP-request-serving app.
2. Enable + FORCE + policy on the 7 real tenant tables: profiles,
   resume_facts, applications, matches, resume_uploads (all via
   profile_id -> profiles.user_id), events, notifications (both via a
   direct user_id column). NOT applied to `users` (the JWT->user lookup
   happens before any tenant context exists — protecting it here is a
   chicken-and-egg problem, and there is no "list other users" endpoint to
   defend against), `jobs`/`connector_runs` (legitimately global/system
   data, not owned by any one user).

Policies check `NULLIF(current_setting('app.current_user_id', true), '')::uuid`.
Real behavior found by testing live against Neon, not assumed: `current_setting`
with `missing_ok=true` on a genuinely fresh connection returned an empty string
(`''`), not `NULL` — a direct `::uuid` cast on that crashes with
`InvalidTextRepresentation` instead of failing closed. `NULLIF(..., '')` turns
the empty string into a real NULL first, so `user_id = NULL` correctly
evaluates to false (never true) and the fail-safe direction is "see nothing"
when the variable was never set, not "see everything" and not a crash either.
core/deps.py::get_current_user sets the real value via SET LOCAL on every
authenticated request, scoped to that request's own transaction.

This is a database-level backstop, not a replacement for the existing
application-level tenancy filters (get_owned_profile / resolve_profile_
ownership) — those stay exactly as they are. If a future endpoint ever
forgets one, this is what stops the leak instead of nothing.

Revision ID: 0010
Revises: 0009
Create Date: 2026-09-26
"""
from alembic import op
import sqlalchemy as sa

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None

APP_ROLE = "job_copilot_app"

_DIRECT_USER_ID_TABLES = ["events", "notifications"]
_VIA_PROFILE_TABLES = ["profiles", "resume_facts", "applications", "matches", "resume_uploads"]


def upgrade() -> None:
    op.execute(
        f"""
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = '{APP_ROLE}') THEN
                CREATE ROLE {APP_ROLE} LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS;
            END IF;
        END
        $$;
        """
    )
    op.execute(f"GRANT USAGE ON SCHEMA public TO {APP_ROLE}")
    op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO {APP_ROLE}")
    op.execute(f"GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO {APP_ROLE}")
    op.execute(f"ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO {APP_ROLE}")
    op.execute(f"ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT USAGE, SELECT ON SEQUENCES TO {APP_ROLE}")

    for table in _DIRECT_USER_ID_TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"""
            CREATE POLICY tenant_isolation ON {table}
            USING (user_id = NULLIF(current_setting('app.current_user_id', true), '')::uuid)
            WITH CHECK (user_id = NULLIF(current_setting('app.current_user_id', true), '')::uuid)
            """
        )

    profiles_subquery = (
        "profile_id IN (SELECT id FROM profiles "
        "WHERE user_id = NULLIF(current_setting('app.current_user_id', true), '')::uuid)"
    )
    for table in _VIA_PROFILE_TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        if table == "profiles":
            condition = "user_id = NULLIF(current_setting('app.current_user_id', true), '')::uuid"
        else:
            condition = profiles_subquery
        op.execute(
            f"""
            CREATE POLICY tenant_isolation ON {table}
            USING ({condition})
            WITH CHECK ({condition})
            """
        )


def downgrade() -> None:
    for table in _VIA_PROFILE_TABLES + _DIRECT_USER_ID_TABLES:
        op.execute(f"DROP POLICY IF EXISTS tenant_isolation ON {table}")
        op.execute(f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")

    op.execute(f"ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE SELECT, INSERT, UPDATE, DELETE ON TABLES FROM {APP_ROLE}")
    op.execute(f"ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE USAGE, SELECT ON SEQUENCES FROM {APP_ROLE}")
    op.execute(f"REVOKE ALL ON ALL TABLES IN SCHEMA public FROM {APP_ROLE}")
    op.execute(f"REVOKE ALL ON ALL SEQUENCES IN SCHEMA public FROM {APP_ROLE}")
    op.execute(f"REVOKE USAGE ON SCHEMA public FROM {APP_ROLE}")
    op.execute(f"DROP ROLE IF EXISTS {APP_ROLE}")
