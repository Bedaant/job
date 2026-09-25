"""Add events (transactional outbox) + notifications (SPEC.md §1, ADR-012)

Revision ID: 0006
Revises: 0005
Create Date: 2026-09-26
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "events",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("type", sa.String(), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("published_at", sa.DateTime(), nullable=True),
    )
    op.create_index(
        "ix_events_unpublished", "events", ["user_id", "id"],
        postgresql_where=sa.text("published_at IS NULL"),
    )
    op.create_index("ix_events_user_id_desc", "events", ["user_id", sa.text("id DESC")])

    op.create_table(
        "notifications",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("trigger", sa.String(), nullable=False),
        sa.Column("channel", sa.String(), nullable=False),
        sa.Column("template", sa.String(), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("status", sa.String(), nullable=False, server_default="pending"),
        sa.Column("sent_at", sa.DateTime(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        # SPEC.md §2.6 patches status to "seen" for the in-app read receipt, but
        # SPEC.md §1's own DDL CHECK only listed the four delivery states — a
        # real spec inconsistency (see WORKLOG). Extending the CHECK to include
        # "seen" satisfies both sections without a second column.
        sa.CheckConstraint(
            "channel IN ('email','in_app')", name="ck_notifications_channel"
        ),
        sa.CheckConstraint(
            "status IN ('pending','sent','failed','skipped','seen')", name="ck_notifications_status"
        ),
    )
    op.create_index("ix_notifications_user_created", "notifications", ["user_id", sa.text("created_at DESC")])
    op.create_index(
        "ix_notifications_pending", "notifications", ["status"],
        postgresql_where=sa.text("status = 'pending'"),
    )


def downgrade() -> None:
    op.drop_table("notifications")
    op.drop_table("events")
