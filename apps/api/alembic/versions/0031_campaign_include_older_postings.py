"""campaigns.include_older_postings: opt back in to postings older than the 60-day limit.

Revision ID: 0031
Revises: 0030
Create Date: 2026-10-10
"""
import sqlalchemy as sa
from alembic import op

revision = "0031"
down_revision = "0030"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("campaigns", sa.Column("include_older_postings", sa.Boolean(), nullable=False,
                                         server_default=sa.false()))


def downgrade() -> None:
    op.drop_column("campaigns", "include_older_postings")
