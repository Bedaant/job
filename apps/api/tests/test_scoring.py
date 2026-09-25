from datetime import datetime, timedelta

from matching.scoring import compute_match_score


def test_score_perfect_match():
    result = compute_match_score(
        semantic=1.0,
        job_skills=["python", "postgres"],
        profile_skills=["python", "postgres", "fastapi"],
        posted_at=datetime.utcnow(),
    )
    assert result["score"] == 100.0
    assert result["skill_coverage"] == 1.0
    assert result["matched_skills"] == ["postgres", "python"]  # sorted
    assert result["missing_skills"] == []


def test_score_weights_sum_correctly():
    """0.55*semantic + 0.30*skill_coverage + 0.15*recency, exactly."""
    result = compute_match_score(
        semantic=0.8,
        job_skills=["python", "postgres", "kubernetes", "terraform"],
        profile_skills=["python", "postgres"],
        posted_at=datetime.utcnow(),  # recency ~1.0
    )
    expected_skill_coverage = 2 / 4  # 0.5
    expected = 100 * (0.55 * 0.8 + 0.30 * 0.5 + 0.15 * 1.0)
    assert abs(result["score"] - expected) < 0.5  # small tolerance for recency clock drift


def test_score_missing_skills_listed():
    result = compute_match_score(
        semantic=0.7,
        job_skills=["python", "kubernetes", "terraform"],
        profile_skills=["python"],
        posted_at=datetime.utcnow(),
    )
    assert set(result["missing_skills"]) == {"kubernetes", "terraform"}
    assert result["matched_skills"] == ["python"]


def test_score_no_required_skills_gives_full_skill_coverage():
    """max(1, |job.skills|) guard — a job with no listed skills shouldn't
    zero out the whole score."""
    result = compute_match_score(semantic=0.9, job_skills=[], profile_skills=["python"], posted_at=datetime.utcnow())
    assert result["skill_coverage"] == 1.0


def test_score_recency_decays_over_30_days():
    old = compute_match_score(
        semantic=1.0, job_skills=[], profile_skills=[], posted_at=datetime.utcnow() - timedelta(days=30)
    )
    fresh = compute_match_score(semantic=1.0, job_skills=[], profile_skills=[], posted_at=datetime.utcnow())
    assert old["recency"] < fresh["recency"]
    assert old["recency"] == 0.0  # clamped at the 30-day boundary


def test_score_recency_clamps_at_zero_for_old_postings():
    result = compute_match_score(
        semantic=1.0, job_skills=[], profile_skills=[], posted_at=datetime.utcnow() - timedelta(days=90)
    )
    assert result["recency"] == 0.0  # not negative


def test_score_handles_missing_posted_at():
    result = compute_match_score(semantic=1.0, job_skills=[], profile_skills=[], posted_at=None)
    assert result["recency"] == 0.0


def test_score_is_rounded_to_two_decimals():
    result = compute_match_score(semantic=0.8123456, job_skills=[], profile_skills=[], posted_at=datetime.utcnow())
    assert result["score"] == round(result["score"], 2)
