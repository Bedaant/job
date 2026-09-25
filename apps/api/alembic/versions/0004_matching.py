"""F6 matching: embeddings, fact_centroid, skills, matches table (Phase 3)

Revision ID: 0004
Revises: 0003
Create Date: 2026-08-16
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from pgvector.sqlalchemy import Vector

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None

EMBEDDING_DIM = 512  # voyage-3-lite


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.add_column("profiles", sa.Column("fact_centroid", Vector(EMBEDDING_DIM), nullable=True))

    op.add_column("jobs", sa.Column("skills", postgresql.JSON(), nullable=True))
    op.add_column("jobs", sa.Column("embedding", Vector(EMBEDDING_DIM), nullable=True))
    op.create_index(
        "ix_jobs_embedding", "jobs", ["embedding"],
        postgresql_using="ivfflat", postgresql_with={"lists": 100},
        postgresql_ops={"embedding": "vector_cosine_ops"},
    )

    op.add_column("resume_facts", sa.Column("embedding", Vector(EMBEDDING_DIM), nullable=True))

    op.create_table(
        "matches",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("profile_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("profiles.id", ondelete="CASCADE"), nullable=False),
        sa.Column("job_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("score", sa.Numeric(5, 2), nullable=False),
        sa.Column("breakdown", postgresql.JSON(), nullable=False),
        sa.Column("state", sa.String(), nullable=False, server_default="new"),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.UniqueConstraint("profile_id", "job_id", name="uq_match_profile_job"),
    )
    op.create_index("ix_matches_profile_score", "matches", ["profile_id", "score"])


def downgrade() -> None:
    op.drop_table("matches")
    op.drop_column("resume_facts", "embedding")
    op.drop_index("ix_jobs_embedding", table_name="jobs")
    op.drop_column("jobs", "embedding")
    op.drop_column("jobs", "skills")
    op.drop_column("profiles", "fact_centroid")
