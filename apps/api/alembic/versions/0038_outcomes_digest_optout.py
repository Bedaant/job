"""applications.outcome/outcome_at ("Heard back?" answer) and users.digest_opted_out_at.

Revision ID: 0038
Revises: 0035
Create Date: 2026-10-12
"""
import sqlalchemy as sa
from alembic import op

revision = "0038"
down_revision = "0035"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("applications", sa.Column("outcome", sa.String(), nullable=True))
    op.add_column("applications", sa.Column("outcome_at", sa.DateTime(), nullable=True))
    op.add_column("users", sa.Column("digest_opted_out_at", sa.DateTime(), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "digest_opted_out_at")
    op.drop_column("applications", "outcome_at")
    op.drop_column("applications", "outcome")
