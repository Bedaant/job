"""REACH-B — contacts, outreach, suppressions, and two profile columns.

Stage 8 of the nine in README.md (`docs/PLAN-OUTREACH.md`): after an application goes
out, find someone at the company, write a grounded note, and send it from the user's own
Gmail. This migration is the storage only — no endpoint reads or writes these tables yet.

LOCKING. GAPS 6.2 records that migration 0022's `create_index` calls were non-concurrent
and took a SHARE lock while building, which is why its advice was to run the first
`alembic upgrade` outside an ingestion window. That does not apply here and the reason is
worth stating so nobody copies 0022's caution without thinking:

- The three tables are NEW. Their indexes build over zero rows, so there is nothing to
  lock out and `CONCURRENTLY` would buy nothing (it also cannot run inside Alembic's
  transaction).
- The two `profiles` columns are added WITH a non-volatile `server_default`, which on
  Postgres 11+ is a catalogue-only change — no table rewrite, no long ACCESS EXCLUSIVE
  hold. The defaults are not optional for that reason: adding them later as a separate
  `ALTER ... SET DEFAULT` plus backfill would be the slow path.

So this one is safe to run during ingestion.

JSONB, not JSON, matching migration 0024 — the ORM declares `JSON`, which maps to JSONB
here and to TEXT under the SQLite test engine. Nothing in this migration depends on
JSONB operators; the type is for consistency with what is already in the database.

Revision ID: 0025
Revises: 0024
Create Date: 2026-10-09
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0025"
down_revision = "0024"
branch_labels = None
depends_on = None

OUTREACH_STATUS = (
    "ready_for_review", "approved", "sending", "sent", "skipped", "failed",
)


def upgrade() -> None:
    # Off by default, and not merely a config toggle: REACH-E unlocks it only after ten
    # emails have been approved by hand, so the user has seen what the system writes
    # before delegating it.
    op.add_column(
        "profiles",
        sa.Column("outreach_auto_send", sa.Boolean(), nullable=False, server_default="false"),
    )
    op.add_column(
        "profiles",
        sa.Column(
            "outreach_contacts_per_application", sa.Integer(), nullable=False, server_default="2"
        ),
    )

    op.create_table(
        "contacts",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column(
            "profile_id", postgresql.UUID(as_uuid=False),
            sa.ForeignKey("profiles.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column("company", sa.String(), nullable=False),
        sa.Column("full_name", sa.String(), nullable=False),
        sa.Column("title", sa.String(), nullable=True),
        # Nullable: an adapter can learn WHO someone is before how to reach them.
        sa.Column("email", sa.String(), nullable=True),
        sa.Column("email_verification_status", sa.String(), nullable=True),
        sa.Column("email_verified_at", sa.DateTime(), nullable=True),
        sa.Column("source", sa.String(), nullable=False, server_default="manual"),
        sa.Column("source_ref", sa.String(), nullable=True),
        sa.Column("warm_signal", postgresql.JSONB(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        # Scoped to the profile, never global: a global constraint would make one user's
        # lookup fail because another user already stored that person, which leaks that
        # they had them. In Postgres NULLs do not collide here, which is what allows a
        # contact to exist before an address is known.
        sa.UniqueConstraint("profile_id", "email", name="uq_contact_profile_email"),
    )
    op.create_index("ix_contacts_profile_company", "contacts", ["profile_id", "company"])

    op.create_table(
        "outreach",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column(
            "profile_id", postgresql.UUID(as_uuid=False),
            sa.ForeignKey("profiles.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column(
            "application_id", postgresql.UUID(as_uuid=False),
            sa.ForeignKey("applications.id", ondelete="CASCADE"), nullable=False,
        ),
        # SET NULL, not CASCADE: a "nobody found" skip has no contact to point at, and
        # deleting a contact must not erase the record that we once tried.
        sa.Column(
            "contact_id", postgresql.UUID(as_uuid=False),
            sa.ForeignKey("contacts.id", ondelete="SET NULL"), nullable=True,
        ),
        sa.Column(
            "status",
            sa.Enum(*OUTREACH_STATUS, name="outreachstatus"),
            nullable=False, server_default="ready_for_review",
        ),
        sa.Column("skip_reason", sa.String(), nullable=True),
        sa.Column("subject", sa.String(), nullable=True),
        sa.Column("body", sa.Text(), nullable=True),
        sa.Column(
            "flagged_unsupported_claims", postgresql.JSONB(),
            nullable=False, server_default="[]",
        ),
        sa.Column("warm_signal_used", postgresql.JSONB(), nullable=True),
        sa.Column("approved_by", sa.String(), nullable=True),
        sa.Column("gmail_message_id", sa.String(), nullable=True),
        sa.Column("gmail_thread_id", sa.String(), nullable=True),
        sa.Column("sent_at", sa.DateTime(), nullable=True),
        sa.Column("error", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        # The duplicate guarantee lives here rather than in a code path someone can
        # refactor around: one ask per person per application.
        sa.UniqueConstraint(
            "application_id", "contact_id", name="uq_outreach_application_contact"
        ),
    )
    # ADR-003's 10/day cap counts today's sent rows for one profile, inside the send
    # lock. This is the index that query needs.
    op.create_index("ix_outreach_profile_sent_at", "outreach", ["profile_id", "sent_at"])

    op.create_table(
        "suppressions",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        # NULL = GLOBAL, applying to every user. Someone who asks not to be contacted
        # should not have to ask each user of this product separately.
        sa.Column(
            "profile_id", postgresql.UUID(as_uuid=False),
            sa.ForeignKey("profiles.id", ondelete="CASCADE"), nullable=True,
        ),
        sa.Column("email", sa.String(), nullable=True),
        sa.Column("domain", sa.String(), nullable=True),
        sa.Column("reason", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=True),
    )
    # Checked before every draft and again immediately before send, so both lookups are
    # indexed. No unique constraint: the same address being suppressed globally and by
    # one profile is legitimate, and a duplicate opt-out must never raise.
    op.create_index("ix_suppressions_email", "suppressions", ["email"])
    op.create_index("ix_suppressions_domain", "suppressions", ["domain"])


def downgrade() -> None:
    op.drop_index("ix_suppressions_domain", table_name="suppressions")
    op.drop_index("ix_suppressions_email", table_name="suppressions")
    op.drop_table("suppressions")
    op.drop_index("ix_outreach_profile_sent_at", table_name="outreach")
    op.drop_table("outreach")
    op.drop_index("ix_contacts_profile_company", table_name="contacts")
    op.drop_table("contacts")
    op.drop_column("profiles", "outreach_contacts_per_application")
    op.drop_column("profiles", "outreach_auto_send")
    # The Enum type is created implicitly by create_table on Postgres but is NOT dropped
    # implicitly, so a downgrade-then-upgrade would fail on "type already exists".
    sa.Enum(name="outreachstatus").drop(op.get_bind(), checkfirst=True)
