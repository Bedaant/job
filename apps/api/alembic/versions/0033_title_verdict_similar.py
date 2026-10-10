"""title_verdicts.similar: a near-miss role, shown to the user separately instead of dropped.

Existing "no" verdicts are deleted so those titles are re-judged with the three-way question;
verdicts are a cache, nothing else references them.

Revision ID: 0033
Revises: 0032
Create Date: 2026-10-10
"""
import sqlalchemy as sa
from alembic import op

revision = "0033"
down_revision = "0032"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("title_verdicts", sa.Column("similar", sa.Boolean(), nullable=False,
                                              server_default=sa.false()))
    op.execute("DELETE FROM title_verdicts WHERE match = false")


def downgrade() -> None:
    op.drop_column("title_verdicts", "similar")
