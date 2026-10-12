"""applications.prep_attempts: failed tailoring passes, so a stuck prep stops retrying.

Revision ID: 0039
Revises: 0038
Create Date: 2026-10-12
"""
import sqlalchemy as sa
from alembic import op

revision = "0039"
down_revision = "0038"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("applications", sa.Column("prep_attempts", sa.Integer(), nullable=False, server_default="0"))


def downgrade() -> None:
    op.drop_column("applications", "prep_attempts")
