"""resume_uploads table (Phase 1, SPEC.md §2.1)

Revision ID: 0002
Revises: 0001
Create Date: 2026-08-15
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "resume_uploads",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("profile_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("profiles.id", ondelete="CASCADE"), nullable=False),
        sa.Column("status", sa.String(), nullable=False, server_default="parsing"),
        sa.Column("draft_facts", postgresql.JSON(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("resume_uploads")
