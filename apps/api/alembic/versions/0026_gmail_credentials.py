"""REACH-A — gmail_credentials.

Storage for the Gmail OAuth grant that REACH-D's send path needs (ADR-003: outreach
sends from the user's own Gmail, token encrypted at rest). One new table, no changes to
any existing one.

`refresh_token_encrypted` is Text and holds Fernet ciphertext only — see `crypto.py`,
which raises rather than ever writing plaintext. There is no plaintext column to
accidentally populate.

LOCKING. A new table, so its unique index builds over zero rows and there is nothing to
lock out. Safe to run during ingestion. (Migration 0022's caution about non-concurrent
index builds — GAPS 6.2 — applies to indexes added over existing data, not to this.)

Revision ID: 0026
Revises: 0025
Create Date: 2026-10-09
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0026"
down_revision = "0025"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "gmail_credentials",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        # UNIQUE: one Gmail account per user, which makes "the user's credential" an
        # unambiguous lookup rather than a "pick the newest" rule.
        sa.Column(
            "user_id", postgresql.UUID(as_uuid=False),
            sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True,
        ),
        sa.Column("refresh_token_encrypted", sa.Text(), nullable=False),
        sa.Column("email_address", sa.String(), nullable=True),
        # What was GRANTED, not what was requested. Google allows partial grants, and a
        # narrowed one must be visible at connect time rather than at send time.
        sa.Column("scopes", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("connected_at", sa.DateTime(), nullable=True),
        # Soft revoke: a revocation stays auditable instead of deleting the row.
        sa.Column("revoked_at", sa.DateTime(), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("gmail_credentials")
