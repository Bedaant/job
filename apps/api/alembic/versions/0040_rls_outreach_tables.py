"""RLS for the four tenant tables 0025/0026/0030 created without it: contacts,
outreach, gmail_credentials, fill_snapshots.

Same treatment 0010 gave the first seven: ENABLE + FORCE + a `tenant_isolation`
policy on `NULLIF(current_setting('app.current_user_id', true), '')::uuid` (the NULLIF
fails closed on the empty string a fresh connection returns). Owners:

* contacts, outreach — profile_id -> profiles.user_id
* gmail_credentials — user_id directly
* fill_snapshots — application_id -> applications.profile_id -> profiles.user_id

No grants: 0010's ALTER DEFAULT PRIVILEGES already gave job_copilot_app DML on tables
created after it, which these are.

Workers (outreach send/draft, Gmail sender, supervisor, apply-by-email) use
`session_scope()` on the owner role, which bypasses RLS, as the events relay does. The
two unauthenticated HTTP paths are handled in code: the Gmail OAuth callback sets the
tenant from its signed state; the unsubscribe link reads on the owner role
(`get_owner_db`), gated by its HMAC token.

Revision ID: 0040
Revises: 0039
Create Date: 2026-10-12
"""
from alembic import op

revision = "0040"
down_revision = "0039"
branch_labels = None
depends_on = None

_USER = "NULLIF(current_setting('app.current_user_id', true), '')::uuid"
_PROFILES = f"SELECT id FROM profiles WHERE user_id = {_USER}"

_CONDITIONS = {
    "contacts": f"profile_id IN ({_PROFILES})",
    "outreach": f"profile_id IN ({_PROFILES})",
    "gmail_credentials": f"user_id = {_USER}",
    "fill_snapshots": f"application_id IN (SELECT id FROM applications WHERE profile_id IN ({_PROFILES}))",
}


def upgrade() -> None:
    for table, condition in _CONDITIONS.items():
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(f"CREATE POLICY tenant_isolation ON {table} USING ({condition}) WITH CHECK ({condition})")


def downgrade() -> None:
    for table in _CONDITIONS:
        op.execute(f"DROP POLICY IF EXISTS tenant_isolation ON {table}")
        op.execute(f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")
