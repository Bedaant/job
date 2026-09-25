"""Add resume_facts.period_from/period_to (SPEC.md §1) — needed for real date
data to feed the Phase 4 DOCX generator's date-range rendering and the
ATS-safety linter's date-format rule (SPEC.md §3.5 rule 8).

Revision ID: 0008
Revises: 0007
Create Date: 2026-09-26
"""
from alembic import op
import sqlalchemy as sa

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("resume_facts", sa.Column("period_from", sa.Date(), nullable=True))
    op.add_column("resume_facts", sa.Column("period_to", sa.Date(), nullable=True))


def downgrade() -> None:
    op.drop_column("resume_facts", "period_to")
    op.drop_column("resume_facts", "period_from")
