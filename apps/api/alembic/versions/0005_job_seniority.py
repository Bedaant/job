"""Add jobs.seniority (Phase 3 hard filters, F6)

Revision ID: 0005
Revises: 0004
Create Date: 2026-08-16
"""
from alembic import op
import sqlalchemy as sa

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("jobs", sa.Column("seniority", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column("jobs", "seniority")
