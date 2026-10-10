"""Intake: jobs.content_hash, connector_runs.fetch_ms / save_ms.

Three nullable columns, no defaults, no index: a metadata-only change on Postgres, so it
takes a brief lock and rewrites nothing. Safe to run during ingestion.

Revision ID: 0027
Revises: 0026
Create Date: 2026-10-10
"""
from alembic import op
import sqlalchemy as sa

revision = "0027"
down_revision = "0026"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("jobs", sa.Column("content_hash", sa.String(), nullable=True))
    op.add_column("connector_runs", sa.Column("fetch_ms", sa.Integer(), nullable=True))
    op.add_column("connector_runs", sa.Column("save_ms", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("connector_runs", "save_ms")
    op.drop_column("connector_runs", "fetch_ms")
    op.drop_column("jobs", "content_hash")
