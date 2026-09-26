"""ADR-015 §2 — campaigns: the unit of approval, replacing ADR-001's
per-application review gate.

Two schema changes plus one security change:

1. `campaigns` — the bounds the user approves once (roles/locations/sources,
   remote_only, min_match_score, daily_cap, auto_submit, tailoring_notes).
   `status` is a new enum type `campaignstatus` (draft|active|paused|archived);
   DELETE /campaigns/{id} sets `archived`, it is never a hard delete.
2. `applications.campaign_id` — nullable, ON DELETE SET NULL. This column is
   the daily-cap source of truth: the cap is
   `count(applications WHERE campaign_id = ? AND created_at is today UTC)`,
   computed in exactly one place (campaigns.py::remaining_quota). Deliberately
   NO counter column and NO campaign_runs table — a denormalized counter drifts
   from what actually went out, the rows can't. SET NULL rather than CASCADE
   because the application history is the user's real record and must outlive a
   hard-deleted campaign row.
3. RLS, the same treatment migration 0010 gave the other 7 tenant tables.
   Without this, `campaigns` would be the one tenant table with no
   database-level backstop under its application-level scoping
   (campaigns.py::resolve_campaign_ownership) — exactly the gap 0010 exists to
   close. Scoped via profile_id -> profiles.user_id with the same
   `NULLIF(current_setting('app.current_user_id', true), '')::uuid` expression.
   The NULLIF is not decorative: 0010 found live that current_setting returns an
   empty string, not NULL, on a fresh connection, and a bare ::uuid cast on that
   crashes instead of failing closed.

Numeric(4,3) for min_match_score: it is a 0..1 fraction (the contract the
campaign UI is built against), while matches.score is stored 0..100 — the
comparison scales by 100 in campaigns.py::select_candidates.

JSON columns are `nullable=False, server_default='[]'` while the ORM declares
them `Column(JSON, default=list)`, same split migration 0011 used for
applications.flagged_unsupported_claims — the app always supplies a list, and
the server default keeps a hand-written INSERT from producing a NULL that
every reader would then have to guard.

Revision ID: 0012
Revises: 0011
Create Date: 2026-09-26
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None

_TENANT_CONDITION = (
    "profile_id IN (SELECT id FROM profiles "
    "WHERE user_id = NULLIF(current_setting('app.current_user_id', true), '')::uuid)"
)


def upgrade() -> None:
    campaign_status = postgresql.ENUM(
        "draft", "active", "paused", "archived", name="campaignstatus", create_type=False
    )
    campaign_status.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "campaigns",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column(
            "profile_id", postgresql.UUID(as_uuid=False),
            sa.ForeignKey("profiles.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("status", campaign_status, nullable=False, server_default="draft"),
        sa.Column("roles", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("locations", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("remote_only", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("sources", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("min_match_score", sa.Numeric(4, 3), nullable=False, server_default="0.7"),
        sa.Column("daily_cap", sa.Integer(), nullable=False, server_default="10"),
        sa.Column("auto_submit", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("tailoring_notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.Column("last_run_at", sa.DateTime(), nullable=True),
    )
    # Every campaign read is scoped by profile (list/get/stats) and the worker
    # selects by profile_id too — this is the one index that earns its keep.
    op.create_index("ix_campaigns_profile_id", "campaigns", ["profile_id"])

    op.add_column(
        "applications",
        sa.Column("campaign_id", postgresql.UUID(as_uuid=False), nullable=True),
    )
    op.create_foreign_key(
        "fk_applications_campaign_id", "applications", "campaigns",
        ["campaign_id"], ["id"], ondelete="SET NULL",
    )
    # The daily-cap count is exactly this pair of columns, on every run and
    # every /stats call.
    op.create_index(
        "ix_applications_campaign_id_created_at", "applications", ["campaign_id", "created_at"]
    )

    op.execute("ALTER TABLE campaigns ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE campaigns FORCE ROW LEVEL SECURITY")
    op.execute(
        f"""
        CREATE POLICY tenant_isolation ON campaigns
        USING ({_TENANT_CONDITION})
        WITH CHECK ({_TENANT_CONDITION})
        """
    )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS tenant_isolation ON campaigns")
    op.drop_index("ix_applications_campaign_id_created_at", table_name="applications")
    op.drop_constraint("fk_applications_campaign_id", "applications", type_="foreignkey")
    op.drop_column("applications", "campaign_id")
    op.drop_index("ix_campaigns_profile_id", table_name="campaigns")
    op.drop_table("campaigns")
    op.execute("DROP TYPE IF EXISTS campaignstatus")
