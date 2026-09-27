"""Applicant basics: `profiles.given_name` / `profiles.family_name`.

Greenhouse (and most ATSes) require First Name / Last Name; the profile only
had full_name, and splitting it is a guess (WORKLOG latest+21). These are
user-entered in onboarding and filled deterministically. Nullable, additive
only; `profiles` RLS policy is row-level and unchanged by new columns.

Revision ID: 0018
Revises: 0017
Create Date: 2026-09-27
"""
from alembic import op
import sqlalchemy as sa

revision = "0018"
down_revision = "0017"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("profiles", sa.Column("given_name", sa.String(), nullable=True))
    op.add_column("profiles", sa.Column("family_name", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column("profiles", "family_name")
    op.drop_column("profiles", "given_name")
