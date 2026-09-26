"""Add applicant identity (JSON Resume `basics`) to profiles.

Before this, Profile held persona/headline/location/prefs and nothing an
application form asks for — no name, no phone, no structured address, no
LinkedIn/GitHub. formfill could resolve email (from User) and nothing else,
which made deterministic form-filling structurally impossible. See WORKLOG.

Deviation from SPEC.md §1, noted deliberately: work_auth is specified there as
`text[]`, implemented here as JSONB to match this project's existing ORM
convention (Job.tags, Job.skills, Profile.prefs are all JSON, never ARRAY) and
migrations 0006/0007's JSONB usage. Same data, one consistent column type.

Revision ID: 0009
Revises: 0008
Create Date: 2026-09-26
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None

_STRING_COLUMNS = [
    "full_name",
    "phone",
    "website_url",
    "street_address",
    "city",
    "region",
    "postal_code",
]


def upgrade() -> None:
    for name in _STRING_COLUMNS:
        op.add_column("profiles", sa.Column(name, sa.String(), nullable=True))
    op.add_column("profiles", sa.Column("country_code", sa.String(length=2), nullable=True))
    op.add_column(
        "profiles",
        sa.Column("network_profiles", postgresql.JSONB(), nullable=False, server_default="[]"),
    )
    op.add_column(
        "profiles",
        sa.Column("work_auth", postgresql.JSONB(), nullable=False, server_default="[]"),
    )


def downgrade() -> None:
    op.drop_column("profiles", "work_auth")
    op.drop_column("profiles", "network_profiles")
    op.drop_column("profiles", "country_code")
    for name in reversed(_STRING_COLUMNS):
        op.drop_column("profiles", name)
