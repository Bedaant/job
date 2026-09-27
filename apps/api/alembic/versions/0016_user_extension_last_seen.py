"""ADR-015 — `users.extension_last_seen_at`: is the user's extension connected?

Nothing is submitted unless the browser extension runs the queue, so the web app
needs to know whether it has called in. Stamped by GET /extension/work-queue and
POST /extension/map-fields; read by GET /extension/status. Nullable, additive
only. `users` has no RLS by design (0010: the JWT->user lookup runs before any
tenant context exists); the app role's DML grant from 0010 already covers it.

Revision ID: 0016
Revises: 0015
Create Date: 2026-09-27
"""
from alembic import op
import sqlalchemy as sa

revision = "0016"
down_revision = "0015"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("extension_last_seen_at", sa.DateTime(), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "extension_last_seen_at")
