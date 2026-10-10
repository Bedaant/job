"""title_verdicts: the LLM's per (role, job title) decision for campaign role matching.

Revision ID: 0032
Revises: 0031
Create Date: 2026-10-10
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0032"
down_revision = "0031"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "title_verdicts",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("role_key", sa.String(), nullable=False),
        sa.Column("title_key", sa.String(), nullable=False),
        sa.Column("match", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.UniqueConstraint("role_key", "title_key", name="uq_title_verdict_pair"),
    )


def downgrade() -> None:
    op.drop_table("title_verdicts")
