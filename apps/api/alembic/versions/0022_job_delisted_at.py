"""jobs.delisted_at + indexes on posted_at/last_seen_at for freshness tracking (Phase 1).

NULL `delisted_at` means the job is still listed; later tasks set it from a
sweep when a source stops listing a job. The two indexes support sorting and
filtering jobs by recency (Tasks 2 and 5) — no logic added here.

Revision ID: 0022
Revises: 0021
Create Date: 2026-10-03
"""
from alembic import op
import sqlalchemy as sa

revision = "0022"
down_revision = "0021"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("jobs", sa.Column("delisted_at", sa.DateTime(), nullable=True))
    op.create_index("ix_jobs_posted_at", "jobs", ["posted_at"])
    op.create_index("ix_jobs_last_seen_at", "jobs", ["last_seen_at"])


def downgrade() -> None:
    op.drop_index("ix_jobs_last_seen_at", table_name="jobs")
    op.drop_index("ix_jobs_posted_at", table_name="jobs")
    op.drop_column("jobs", "delisted_at")
