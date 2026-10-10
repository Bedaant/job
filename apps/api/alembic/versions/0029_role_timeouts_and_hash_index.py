"""Role-level statement timeouts, and an index for discovery's dedupe lookup.

Timeouts live on the ROLE because Neon's pooler (PgBouncer, transaction mode) rejects the
startup `options` parameter and drops session `SET`s between transactions (both verified
2026-10-10). The app role serves web requests (30 s); the owner role runs workers and
migrations (5 min). Was `0` (unlimited) for both.

`canonical_hash` had no index although every discovery chunk filters on it.
Not done, measured: switching ix_jobs_embedding to hnsw. Matching asks for LIMIT 5000 and the
planner seq-scans for that (EXPLAIN on Neon); an hnsw scan would also cap results at ef_search.

Revision ID: 0029
Revises: 0028
Create Date: 2026-10-10
"""
from alembic import op

revision = "0029"
down_revision = "0028"
branch_labels = None
depends_on = None

APP_ROLE = "job_copilot_app"  # migration 0010


def _for_app_role(sql: str) -> None:
    op.execute(f"""
        DO $$ BEGIN
            IF EXISTS (SELECT FROM pg_roles WHERE rolname = '{APP_ROLE}') THEN
                {sql};
            END IF;
        END $$
    """)


def upgrade() -> None:
    _for_app_role(f"ALTER ROLE {APP_ROLE} SET statement_timeout = '30s'")
    op.execute("ALTER ROLE CURRENT_USER SET statement_timeout = '5min'")
    op.create_index("ix_jobs_canonical_hash", "jobs", ["canonical_hash"])


def downgrade() -> None:
    op.drop_index("ix_jobs_canonical_hash", table_name="jobs")
    op.execute("ALTER ROLE CURRENT_USER RESET statement_timeout")
    _for_app_role(f"ALTER ROLE {APP_ROLE} RESET statement_timeout")
