"""Add connector_runs (SPEC.md §1) — first writer is F5's unknown-ATS
classification review surface (connectors/discovery.py).

Revision ID: 0007
Revises: 0006
Create Date: 2026-09-26
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "connector_runs",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("source", sa.String(), nullable=False),
        sa.Column("token", sa.String(), nullable=True),
        sa.Column("fetched", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("inserted", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("failed", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("notes", postgresql.JSONB(), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("ran_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_connector_runs_source_ran_at", "connector_runs", ["source", sa.text("ran_at DESC")])


def downgrade() -> None:
    op.drop_table("connector_runs")
