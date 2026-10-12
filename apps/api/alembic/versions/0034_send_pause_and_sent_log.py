"""Send safety (P0 #2): the pause switches and the per-user sent log.

* `users.sends_paused` — the user's own "pause all sends".
* `app_flags` — runtime switches; the owner's global `pause_all_sends` row. Not
  tenant data, so no RLS.
* `sent_log` — one row per outbound email and per submission. RLS exactly as 0010 gave
  `events` (direct `user_id`, the NULLIF guard against the empty-string setting).

Revision ID: 0034
Revises: 0033
Create Date: 2026-10-12
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0034"
down_revision = "0033"
branch_labels = None
depends_on = None

_TENANT = "user_id = NULLIF(current_setting('app.current_user_id', true), '')::uuid"


def upgrade() -> None:
    op.add_column("users", sa.Column("sends_paused", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.create_table(
        "app_flags",
        sa.Column("name", sa.String(), primary_key=True),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
    )
    op.create_table(
        "sent_log",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=False),
                  sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("kind", sa.String(), nullable=False),
        sa.Column("recipient", sa.String(), nullable=False),
        sa.Column("application_id", postgresql.UUID(as_uuid=False),
                  sa.ForeignKey("applications.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_sent_log_user_id", "sent_log", ["user_id"])
    op.execute("ALTER TABLE sent_log ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE sent_log FORCE ROW LEVEL SECURITY")
    op.execute(f"CREATE POLICY tenant_isolation ON sent_log USING ({_TENANT}) WITH CHECK ({_TENANT})")


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS tenant_isolation ON sent_log")
    op.drop_index("ix_sent_log_user_id", table_name="sent_log")
    op.drop_table("sent_log")
    op.drop_table("app_flags")
    op.drop_column("users", "sends_paused")
