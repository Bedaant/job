"""`withdrawn`: the user pulled out after sending (the tracker's Closed column).

`dismissed` means "declined before sending" and clears applied_at on undo; a
withdrawal keeps the date it was sent. Same pattern as 0013/0017.

Numbered 0020 because 0019 is reserved for the concurrent profile work. If that
migration lands, set `down_revision = "0019"` here when merging so there is one head.

Revision ID: 0020
Revises: 0018
Create Date: 2026-09-28
"""
from alembic import op

revision = "0020"
down_revision = "0018"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TYPE applicationstatus ADD VALUE IF NOT EXISTS 'withdrawn'")


def downgrade() -> None:
    """No-op, same reasoning as 0013: Postgres has no ALTER TYPE ... DROP VALUE."""
    pass
