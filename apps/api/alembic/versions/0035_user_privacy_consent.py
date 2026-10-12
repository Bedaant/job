"""users.privacy_consent_at: when the user accepted the privacy notice at signup (DPDP).

Revision ID: 0035
Revises: 0034
Create Date: 2026-10-12
"""
import sqlalchemy as sa
from alembic import op

revision = "0035"
down_revision = "0034"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("privacy_consent_at", sa.DateTime(), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "privacy_consent_at")
