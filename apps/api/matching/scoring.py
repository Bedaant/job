"""F6 match scoring (SPEC.md §3.2). score = 0.55*semantic + 0.30*skill_coverage
+ 0.15*recency. Explainability matters as much as the number — the UI must
always be able to show matched_skills/missing_skills, never just a bare score.
"""
from datetime import datetime

SEMANTIC_WEIGHT = 0.55
SKILL_COVERAGE_WEIGHT = 0.30
RECENCY_WEIGHT = 0.15
RECENCY_WINDOW_DAYS = 30


def _clamp(value: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, value))


def compute_match_score(
    semantic: float,
    job_skills: list[str],
    profile_skills: list[str],
    posted_at: datetime | None,
) -> dict:
    job_skills_set = {s.lower() for s in job_skills}
    profile_skills_set = {s.lower() for s in profile_skills}

    matched = sorted(job_skills_set & profile_skills_set)
    missing = sorted(job_skills_set - profile_skills_set)
    # A job listing no required skills has nothing to be short on — full
    # coverage, not zero. max(1, ...) alone gets this wrong (0/1 = 0.0).
    skill_coverage = 1.0 if not job_skills_set else len(matched) / len(job_skills_set)

    if posted_at is None:
        recency = 0.0
    else:
        days_since_posted = (datetime.utcnow() - posted_at).total_seconds() / 86400
        recency = _clamp(1 - days_since_posted / RECENCY_WINDOW_DAYS)

    score = 100 * (
        SEMANTIC_WEIGHT * _clamp(semantic)
        + SKILL_COVERAGE_WEIGHT * skill_coverage
        + RECENCY_WEIGHT * recency
    )

    return {
        "score": round(score, 2),
        "semantic": round(_clamp(semantic), 4),
        "skill_coverage": round(skill_coverage, 4),
        "recency": round(recency, 4),
        "matched_skills": matched,
        "missing_skills": missing,
    }
