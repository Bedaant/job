"""ADR-015 — `answer_bank`: the questions the user has already answered.

Every form question we could not answer used to cost the user an interruption
and then throw the answer away. This table is what makes the second employer
asking the same question free.

Shape notes:

* Unique on `(profile_id, question_normalized)`. `question_normalized` is the
  derived matching key (lowercased, punctuation collapsed —
  answer_bank.py::normalize_question), so this constraint is what makes
  re-answering an UPDATE rather than a second, contradictory row for the same
  question. There is deliberately no uniqueness on `question_text`: the same
  question arrives with different punctuation from every ATS.
* `ix_answer_bank_question_normalized` on the normalized column: the exact-match
  lookup runs on the form-fill path, per field.
* `times_used`/`last_used_at` are `NOT NULL DEFAULT 0` / nullable respectively,
  incremented only when an answer is actually served. No trigger — the ORM owns
  the increment (answer_bank.py::serve_answer) because "served" is an
  application-level fact the database cannot see.
* RLS, exactly as migration 0012 gave `campaigns`: ENABLE + FORCE + a
  `tenant_isolation` policy scoped via `profile_id -> profiles.user_id`. Same
  `NULLIF(current_setting('app.current_user_id', true), '')::uuid` expression,
  and the NULLIF is not decorative — 0010 found live that `current_setting`
  returns an empty string, not NULL, on a fresh connection, and a bare `::uuid`
  cast on that crashes instead of failing closed. This table holds free-text
  answers the user wrote about themselves, so it is the last place to leave
  without a database-level backstop under the application-level scoping.

Revision ID: 0014
Revises: 0013
Create Date: 2026-09-27
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0014"
down_revision = "0013"
branch_labels = None
depends_on = None

_TENANT_CONDITION = (
    "profile_id IN (SELECT id FROM profiles "
    "WHERE user_id = NULLIF(current_setting('app.current_user_id', true), '')::uuid)"
)


def upgrade() -> None:
    op.create_table(
        "answer_bank",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column(
            "profile_id", postgresql.UUID(as_uuid=False),
            sa.ForeignKey("profiles.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column("question_text", sa.Text(), nullable=False),
        sa.Column("question_normalized", sa.String(), nullable=False),
        sa.Column("answer_text", sa.Text(), nullable=False),
        sa.Column("times_used", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_used_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.UniqueConstraint(
            "profile_id", "question_normalized", name="uq_answer_bank_profile_question"
        ),
    )
    op.create_index(
        "ix_answer_bank_question_normalized", "answer_bank", ["question_normalized"]
    )

    op.execute("ALTER TABLE answer_bank ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE answer_bank FORCE ROW LEVEL SECURITY")
    op.execute(
        f"""
        CREATE POLICY tenant_isolation ON answer_bank
        USING ({_TENANT_CONDITION})
        WITH CHECK ({_TENANT_CONDITION})
        """
    )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS tenant_isolation ON answer_bank")
    op.drop_index("ix_answer_bank_question_normalized", table_name="answer_bank")
    op.drop_table("answer_bank")
