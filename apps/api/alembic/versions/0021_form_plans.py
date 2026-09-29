"""ADR-016 (2026-09-29 amendment) — `form_plans`: one read-only planner run per job.

The Stagehand planner reads a job's application form once on the server and the
extension's fill reuses that plan for every user (formplans.py). Shape notes:

* Unique on `job_id`, CASCADE with the job: one plan per job, a re-plan updates
  the row, and a deleted job takes its plan with it.
* No RLS. Like `jobs`, this is global data: the plan holds live-DOM keys, labels
  and fill sources only (never a value, an option or a user's answer), so there
  is no tenant to isolate.
* `fingerprint` = first 16 hex of sha256 over the sorted keys, so a form that
  changed under us can be told apart without diffing JSON.

Revision ID: 0021
Revises: 0020
Create Date: 2026-09-29
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0021"
down_revision = "0020"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "form_plans",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column(
            "job_id", postgresql.UUID(as_uuid=False),
            sa.ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column("url", sa.String(), nullable=False),
        sa.Column("ats", sa.String(), nullable=True),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("fingerprint", sa.String(16), nullable=True),
        sa.Column("plan", sa.JSON(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.UniqueConstraint("job_id", name="uq_form_plans_job_id"),
    )


def downgrade() -> None:
    op.drop_table("form_plans")
