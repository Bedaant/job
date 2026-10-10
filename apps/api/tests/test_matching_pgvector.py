"""GAPS 2.6 — let pgvector compute similarity; stop shipping vectors to Python.

`build_matches` fetched every live embedded job as a full ORM row and computed
cosine in a Python loop. Each row carried a 512-float embedding and a full job
description, and measured against the real database that transfer — not the
arithmetic — was the whole cost. Postgres now returns the similarity (7.7ms of
server time) and both large columns stay on the server.

Two things this must not become, each pinned by a test below.

1. **The SQL ordering is not the ranking.** `scoring.py` weights semantic at
   0.55, so coverage (0.30) and recency (0.15) can move a job 45 points and a
   more distant job can outrank a nearer one. The ORDER BY only bounds the
   candidate set.

2. **The bound must stay far above the live pool.** Measured with a pool of
   500 against 1,925 live embedded jobs, the top-20 lost 1-3 jobs per profile
   (overlap 17-19/20); the misses scored 58-69 and sat at vector ranks
   513-1025, winning on recency and coverage despite mediocre similarity.
   CANDIDATE_POOL is a worst-case ceiling, not a target.
"""
from sqlalchemy.dialects import postgresql

import models
from matching.service import CANDIDATE_POOL, _candidates, _pgvector_query, build_matches
from tests.test_matching_service import _db, _job, _profile


def _embedded_fact(db, profile, tags):
    """A fact with no embedding makes build_matches early-return (it re-embeds
    first), so a profile-skills fixture has to carry a vector."""
    profile.resume_facts.append(
        models.ResumeFact(
            profile_id=profile.id, category="experience", achievement="shipped it",
            tags=tags, embedding=[1.0] + [0.0] * 511,
        )
    )
    db.commit()


def test_the_pool_ceiling_stays_above_the_live_job_pool():
    """At 500 this measurably dropped real top-20 matches (see module docstring).
    The live embedded pool was 1,925 when that was measured."""
    assert CANDIDATE_POOL >= 5000


def test_postgres_computes_the_similarity_and_leaves_the_vector_behind():
    """The point of the change. If `embedding` is still selected, the dominant
    cost is still being paid and nothing was gained."""
    db = _db()

    sql = _postgres_sql(db)

    assert "<=>" in sql, sql
    assert "jobs.embedding AS" not in sql, "the embedding column must stay on the server"
    assert "jobs.description" not in sql, "description is only needed for the visa filter"
    assert f"LIMIT {CANDIDATE_POOL}" in sql, sql


def test_the_visa_filter_still_gets_the_description():
    """`_passes_visa` reads job.description. Deferring it unconditionally would
    make that filter lazy-load per row — an N+1 worse than the problem."""
    db = _db()

    sql = _postgres_sql(db, need_description=True)

    assert "jobs.description" in sql, sql


def _postgres_sql(db, need_description=False) -> str:
    """Compile the query rather than run it — SQLite cannot answer `<=>`."""
    query = _pgvector_query(db.query(models.Job), [0.5] * 512, need_description)
    return str(
        query.statement.compile(
            dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}
        )
    ).replace("\n", " ")


def test_sqlite_defers_the_similarity_to_python():
    """The unit-test engine has no pgvector, so `semantic` comes back None and
    the caller falls back to the Python cosine — the path every other matching
    test rides."""
    db = _db()
    _profile(db, fact_centroid=[1.0] + [0.0] * 511)
    _job(db, "A", embedding=[1.0] + [0.0] * 511)
    _job(db, "B", embedding=[0.0, 1.0] + [0.0] * 510)

    rows = _candidates(db.query(models.Job), [1.0] + [0.0] * 511, "sqlite", False)

    assert {job.title for job, _ in rows} == {"A", "B"}
    assert all(semantic is None for _, semantic in rows)


def test_coverage_still_beats_distance():
    """The regression this change could plausibly cause. "Far" is the more
    distant vector but matches every listed skill; "Near" is nearer and matches
    none. If the SQL order ever became the answer, Near would come first.

    Near: 0.55*0.951 + 0.30*0.0 + 0 = 52.3.  Far: 0.55*0.6 + 0.30*1.0 = 63.0.
    """
    db = _db()
    profile = _profile(db, fact_centroid=[1.0] + [0.0] * 511)
    _embedded_fact(db, profile, ["python", "sql"])
    _job(db, "Near", embedding=[0.95, 0.31] + [0.0] * 510, skills=["rust", "go"])
    _job(db, "Far", embedding=[0.6, 0.8] + [0.0] * 510, skills=["python", "sql"])

    matches = build_matches(db, profile)

    assert [m.job.title for m in matches] == ["Far", "Near"]
    assert matches[0].breakdown["semantic"] < matches[1].breakdown["semantic"]
    assert matches[0].breakdown["skill_coverage"] == 1.0


def test_limit_caps_matches_not_the_candidate_pool():
    """`limit` caps the MATCHES and the Python scorer picks which ones; it must
    not shrink what the scorer gets to choose from."""
    db = _db()
    profile = _profile(db, fact_centroid=[1.0] + [0.0] * 511)
    for i in range(5):
        _job(db, f"Job {i}", embedding=[1.0 - i / 10, i / 10] + [0.0] * 510)

    matches = build_matches(db, profile, limit=2)

    assert [m.job.title for m in matches] == ["Job 0", "Job 1"]
    assert f"LIMIT {CANDIDATE_POOL}" in _postgres_sql(db)
