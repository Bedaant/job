"""ADR-015 Phase 1 — `submitting`: the window between claiming a submission and
knowing whether the form actually went through.

POST /applications/{id}/claim-submission used to flip straight to `applied`,
before the extension's native form submit fired. Any form that then failed left
the row saying `applied`, with an `applied_at` timestamp for an event that never
happened — the user is told they applied to a job they did not apply to. That is
the worst failure mode this product has: it silently drops real applications
while reporting success.

`submitting` names that window. POST /applications/{id}/submission-result is the
only thing that closes it: submitted -> applied, failed -> approved (genuinely
retryable, the form never went through), needs_human -> ready_for_review (captcha,
account wall, free-text essay — handing over is a correct outcome, not an error).

No data backfill: `submitting` is a transient state no existing row can be in,
since nothing could write it before this migration existed. Existing `applied`
rows keep whatever truth they already had; this migration does not retroactively
reinterpret them, and it could not, because whether those forms really went
through was never recorded.

ALTER TYPE ... ADD VALUE, placed BEFORE 'applied' so the enum's declaration order
matches the lifecycle. Postgres supports ADD VALUE ... BEFORE; there is no
DROP VALUE, which is why downgrade() cannot fully reverse this.

Revision ID: 0013
Revises: 0012
Create Date: 2026-09-27
"""
from alembic import op

revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # IF NOT EXISTS so a re-run, or a database where the value was added by hand
    # during development, is not a hard failure.
    op.execute("ALTER TYPE applicationstatus ADD VALUE IF NOT EXISTS 'submitting' BEFORE 'applied'")


def downgrade() -> None:
    """Postgres has no ALTER TYPE ... DROP VALUE. Removing an enum value means
    recreating the type and rewriting every dependent column — destructive, and
    it would have to decide what to do with any row currently `submitting`
    (an in-flight submission whose outcome is genuinely unknown).

    Rather than guess, this is a deliberate no-op: the extra enum value is inert
    if nothing writes it. The application-level revert is to stop writing
    `submitting`, which is a code change, not a schema change.
    """
    pass
