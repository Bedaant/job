"""GAPS 4.3 — one application per role per profile, enforced by the schema.

The same role from two sources is two Job rows sharing a canonical_hash, and the
(profile_id, job_id) constraint cannot see that. `role_key` is the job's hash frozen when
the application is made (models._stamp_role_key); UNIQUE(profile_id, role_key) refuses a
second one however the code races.

Backfill keeps the OLDEST application per (profile, hash) keyed and leaves later duplicates
NULL (NULLs never collide), so the migration cannot fail on existing data. Neon checked
read-only 2026-10-10: 6 applications, 0 duplicates.

LOCKING. The table is tiny (single digits of rows); a plain index build is instant.

Revision ID: 0028
Revises: 0027
Create Date: 2026-10-10
"""
from alembic import op
import sqlalchemy as sa

revision = "0028"
down_revision = "0027"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("applications", sa.Column("role_key", sa.String(), nullable=True))
    op.execute(
        """
        UPDATE applications a SET role_key = ranked.canonical_hash
        FROM (
            SELECT a2.id, j.canonical_hash,
                   row_number() OVER (PARTITION BY a2.profile_id, j.canonical_hash
                                      ORDER BY a2.created_at, a2.id) AS rn
            FROM applications a2 JOIN jobs j ON j.id = a2.job_id
        ) ranked
        WHERE ranked.id = a.id AND ranked.rn = 1
        """
    )
    op.create_unique_constraint("uq_application_profile_role", "applications", ["profile_id", "role_key"])


def downgrade() -> None:
    op.drop_constraint("uq_application_profile_role", "applications", type_="unique")
    op.drop_column("applications", "role_key")
