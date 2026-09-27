"""`submitted_unconfirmed`: the submit was sent, but the employer's page never
confirmed it.

The extension used to report `submitted` the instant the native submit fired, so
a validation error, a captcha after submit or a silently rejected form all became
`applied`. It now waits for the page: a confirmation -> `submitted` -> `applied`;
visible errors -> `needs_human`; neither within the bound -> `unconfirmed` ->
this status. Not `applied` (unverified) and never back to `approved` (a retry
could apply twice). The user checks their email and PATCHes it to `applied`.

Follows 0013 exactly: ALTER TYPE ... ADD VALUE IF NOT EXISTS, placed BEFORE
'applied' so declaration order matches the lifecycle. No backfill: nothing could
write this value before this migration existed.

Revision ID: 0017
Revises: 0016
Create Date: 2026-09-27
"""
from alembic import op

revision = "0017"
down_revision = "0016"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TYPE applicationstatus ADD VALUE IF NOT EXISTS 'submitted_unconfirmed' BEFORE 'applied'"
    )


def downgrade() -> None:
    """Deliberate no-op, same reasoning as 0013: Postgres has no ALTER TYPE ...
    DROP VALUE, and rewriting the type would have to decide what an unconfirmed
    row "really" is — which nobody knows. The inert value is harmless if nothing
    writes it; the application-level revert is to stop reporting `unconfirmed`.
    """
    pass
