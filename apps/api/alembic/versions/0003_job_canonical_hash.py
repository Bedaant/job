"""jobs.canonical_hash + last_seen_at (Phase 2, fixes CODE-REVIEW.md H3)

Revision ID: 0003
Revises: 0002
Create Date: 2026-08-16
"""
from alembic import op
import sqlalchemy as sa

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("jobs", sa.Column("canonical_hash", sa.String(), nullable=True))
    op.add_column("jobs", sa.Column("last_seen_at", sa.DateTime(), nullable=True))
    # jobs table has no live data yet (discovery has never run against Postgres) —
    # safe to go straight to NOT NULL + unique without a backfill step.
    op.alter_column("jobs", "canonical_hash", nullable=False)
    op.create_unique_constraint("uq_jobs_canonical_hash", "jobs", ["canonical_hash"])


def downgrade() -> None:
    op.drop_constraint("uq_jobs_canonical_hash", "jobs", type_="unique")
    op.drop_column("jobs", "last_seen_at")
    op.drop_column("jobs", "canonical_hash")
