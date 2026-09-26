"""Sub-project #2 (batch prep): applications.flagged_unsupported_claims,
plus three new ApplicationStatus values the review queue needs.

flagged_unsupported_claims was always computed by tailoring's truth-check
pass (tailoring/engine.py::tailor_application already returns it) but
main.py's /tailor endpoint never persisted it — silently dropped on every
call. ADR-006's whole point is "flagged claims are surfaced to you, not
silently kept"; this closes that gap.

New enum values: `ready_for_review` (batch-prepared, awaiting human
approval), `approved` (human clicked approve; not yet submitted —
sub-project #4's job), `dismissed` (user declined during review).
`dismissed` is deliberately distinct from the existing `rejected` value,
which means the employer rejected the candidate — a different thing.

Revision ID: 0011
Revises: 0010
Create Date: 2026-09-26
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None

_NEW_STATUS_VALUES = ["ready_for_review", "approved", "dismissed"]


def upgrade() -> None:
    for value in _NEW_STATUS_VALUES:
        op.execute(f"ALTER TYPE applicationstatus ADD VALUE IF NOT EXISTS '{value}'")
    op.add_column(
        "applications",
        sa.Column("flagged_unsupported_claims", postgresql.JSONB(), nullable=False, server_default="[]"),
    )


def downgrade() -> None:
    op.drop_column("applications", "flagged_unsupported_claims")
    # Postgres has no DROP VALUE for enums — removing ready_for_review/
    # approved/dismissed would require rebuilding the type and rewriting
    # every row, out of scope for a downgrade of this migration. Any row
    # actually using these values would need manual remediation first.
