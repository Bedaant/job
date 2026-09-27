"""ADR-015 — `applications.pending_questions`: what a needs_human run stopped on.

Nullable JSON list of question strings, verbatim from the form. The answer bank
fills itself from these: the review queue shows the ones it can't answer yet.
Additive only; `applications` already has RLS from 0010, which covers new columns.

Revision ID: 0015
Revises: 0014
Create Date: 2026-09-27
"""
from alembic import op
import sqlalchemy as sa

revision = "0015"
down_revision = "0014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("applications", sa.Column("pending_questions", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("applications", "pending_questions")
