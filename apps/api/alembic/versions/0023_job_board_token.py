"""jobs.board_token — which board within a source a job came from (COLLECT-D).

NULL means "no per-board concept" (the keyless feeds, remotive, reed) or "stored
before this migration". The delisting sweep (workers/jobs.py::_sweep_delisted)
scopes on this column, which fixes two things ADR-017 listed as consequences:

- Removing a token from `connectors/config.py` used to tombstone that board's
  entire live inventory on the next run, because the sweep was source-wide and
  the board's jobs simply stopped appearing in the payload. Editing config was a
  destructive data operation.
- One flaky board blocked delisting for the whole source: `_fetch_ats_source`
  marked the source untrustworthy whenever ANY token returned empty, since an
  empty token's rows would otherwise look absent from the combined id set.

No backfill. Deriving the token from `company` would mean reversing the curated
token->name map, and Phase 1 established that `company` is not a safe key — its
formatting varies per board ("Rubrik Job Board", a trailing space). Existing rows
pick the token up the first time their board lists them again (`upsert_jobs`
refreshes it like any other field), and until then a token-scoped sweep leaves
them alone, which is the safe direction.

Accepted residue: an ATS job that closed BEFORE this migration is never re-seen,
so it keeps NULL and is never tombstoned. Stale beats tombstoning live jobs
(ADR-017 §3). A one-off script can clear those if the count ever matters.

Revision ID: 0023
Revises: 0022
Create Date: 2026-10-04
"""
from alembic import op
import sqlalchemy as sa

revision = "0023"
down_revision = "0022"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("jobs", sa.Column("board_token", sa.String(), nullable=True))
    # Non-concurrent, like 0022's: it takes a SHARE lock while building, which is
    # negligible at current row counts but should still run outside an ingestion
    # window.
    op.create_index("ix_jobs_board_token", "jobs", ["board_token"])


def downgrade() -> None:
    op.drop_index("ix_jobs_board_token", table_name="jobs")
    op.drop_column("jobs", "board_token")
