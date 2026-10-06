"""GAPS 2.6 — stop dragging every embedded job's vector into Python.

`build_matches` scored by fetching every live embedded job and computing cosine
in a Python loop. Measured against the real database: 1,859 live embedded jobs
x 512 float32, so the dominant cost is the *transfer*, not the arithmetic. The
ivfflat index from migration 0004 has sat unused since Phase 3.

What this change is NOT. Vector order is not score order: `scoring.py` weights
semantic at 0.55, so skill coverage (0.30) and recency (0.15) can move a job by
up to 45 points, and a job much further away in cosine can still outrank a
nearer one. So the SQL `ORDER BY embedding <=> centroid` is a *prefilter* that
hands a wide candidate pool to the unchanged Python scorer — replacing the
composite sort with distance would silently change which jobs users see.

That makes it approximate by construction: a job outside the nearest
CANDIDATE_POOL can no longer reach the top `limit` on coverage alone. The pool
is deliberately wide (500 against a 1,859-job live pool) so that only binds on
jobs whose semantic score is already far down.
"""
from sqlalchemy.dialects import postgresql

import models
from matching.service import CANDIDATE_POOL, _narrow, build_matches
from tests.test_matching_service import _db, _job, _profile


def _compiled(query) -> str:
    """The LIMIT and the vector are bound parameters, so they only become
    readable with literal_binds."""
    sql = query.statement.compile(
        dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}
    )
    return str(sql).replace("\n", " ")


def _embedded_fact(db, profile, tags):
    """A fact with no embedding makes build_matches early-return (it re-embeds
    first), so a profile-skills fixture has to carry a vector."""
    profile.resume_facts.append(
        models.ResumeFact(
            profile_id=profile.id, category="experience", achievement="shipped it", tags=tags,
            embedding=[1.0] + [0.0] * 511,
        )
    )
    db.commit()


def test_the_pool_is_wider_than_the_match_limit():
    """A pool at or near `limit` would make the prefilter the ranking."""
    assert CANDIDATE_POOL >= 20 * 10


def test_postgres_orders_by_the_cosine_operator_and_limits():
    """The whole point: the distance and the LIMIT must reach SQL, or the
    planner cannot use ix_jobs_embedding and nothing was saved."""
    db = _db()

    sql = _compiled(_narrow(db.query(models.Job), [0.5] * 512, 20, "postgresql"))

    assert "<=>" in sql, sql
    assert f"LIMIT {CANDIDATE_POOL}" in sql, sql


def test_sqlite_still_scans_everything():
    """The unit-test engine has no pgvector, so the fallback must return every
    row rather than raise — every other matching test rides this path."""
    db = _db()
    _profile(db, fact_centroid=[1.0] + [0.0] * 511)
    _job(db, "A", embedding=[1.0] + [0.0] * 511)
    _job(db, "B", embedding=[0.0, 1.0] + [0.0] * 510)

    rows = _narrow(db.query(models.Job), [1.0] + [0.0] * 511, 20, "sqlite").all()

    assert {j.title for j in rows} == {"A", "B"}


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


def test_the_pool_is_not_narrowed_to_the_match_limit():
    """`limit` caps the MATCHES, and the Python scorer picks which ones.
    Narrowing to `limit` rows in SQL would leave it nothing to choose from."""
    db = _db()
    profile = _profile(db, fact_centroid=[1.0] + [0.0] * 511)
    for i in range(5):
        _job(db, f"Job {i}", embedding=[1.0 - i / 10, i / 10] + [0.0] * 510)

    sql = _compiled(_narrow(db.query(models.Job), [1.0] + [0.0] * 511, 2, "postgresql"))
    assert f"LIMIT {CANDIDATE_POOL}" in sql, sql
    assert "LIMIT 2" not in sql, sql

    matches = build_matches(db, profile, limit=2)
    assert [m.job.title for m in matches] == ["Job 0", "Job 1"]
