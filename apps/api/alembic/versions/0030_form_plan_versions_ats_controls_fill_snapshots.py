"""Architecture plan section 10: versioned form plans, per-ATS kill switch, fill snapshots.

* `form_plans.version` is the active version; `form_plan_versions` keeps every good plan, so a
  bad re-plan can be rolled back (and a failed one no longer overwrites a good one: formplans.py).
  Existing ok plans are backfilled as version 1.
* `ats_controls`: no row = filling enabled. Global, no RLS (like jobs/form_plans).
* `fill_snapshots`: labels, sources and statuses only, never a value. No RLS, same as the
  outreach tables; ownership is checked in ats_controls.post_snapshot.

Revision ID: 0030
Revises: 0029
Create Date: 2026-10-10
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0030"
down_revision = "0029"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("form_plans", sa.Column("version", sa.Integer(), nullable=False, server_default="0"))
    op.create_table(
        "form_plan_versions",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("form_plan_id", postgresql.UUID(as_uuid=False),
                  sa.ForeignKey("form_plans.id", ondelete="CASCADE"), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("plan", sa.JSON(), nullable=False),
        sa.Column("fingerprint", sa.String(16), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.UniqueConstraint("form_plan_id", "version", name="uq_form_plan_versions_plan_version"),
    )
    op.execute("UPDATE form_plans SET version = 1 WHERE status = 'ok' AND plan IS NOT NULL")
    op.execute(
        "INSERT INTO form_plan_versions (id, form_plan_id, version, plan, fingerprint, created_at) "
        "SELECT gen_random_uuid(), id, 1, plan, fingerprint, created_at FROM form_plans WHERE version = 1"
    )
    op.create_table(
        "ats_controls",
        sa.Column("ats", sa.String(32), primary_key=True),
        sa.Column("fill_enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
    )
    op.create_table(
        "fill_snapshots",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("application_id", postgresql.UUID(as_uuid=False),
                  sa.ForeignKey("applications.id", ondelete="CASCADE"), nullable=False),
        sa.Column("plan_version", sa.Integer(), nullable=True),
        sa.Column("record", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_fill_snapshots_application_id", "fill_snapshots", ["application_id"])


def downgrade() -> None:
    op.drop_index("ix_fill_snapshots_application_id", table_name="fill_snapshots")
    op.drop_table("fill_snapshots")
    op.drop_table("ats_controls")
    op.drop_table("form_plan_versions")
    op.drop_column("form_plans", "version")
