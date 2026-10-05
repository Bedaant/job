"""applications.advisory_claims — the non-blocking half of pass 2 (GAPS 6.7).

Owner ruling 2026-10-05, on measured evidence: the truth-check's MODEL half is
framing, not fabrication, and must not block a send. The deterministic half
(an unlisted tool or number) stays the hard gate in
`flagged_unsupported_claims`; the model checker's audit moves here.

What forced it: on the 30-row ADR-014 golden set the bullets were 107/107
correctly grounded and pass 2 still flagged 29 of 30 rows — every flag from the
model checker, none deterministic. `main.py` drops any application with
`flagged_unsupported_claims` from the ready queue, so ~97% could never be sent.

Nullable with a server default so existing rows are valid immediately; no
backfill, because nothing has ever computed this list before.

Revision ID: 0024
Revises: 0023
Create Date: 2026-10-05
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0024"
down_revision = "0023"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "applications",
        sa.Column("advisory_claims", postgresql.JSONB(), nullable=False, server_default="[]"),
    )


def downgrade() -> None:
    op.drop_column("applications", "advisory_claims")
