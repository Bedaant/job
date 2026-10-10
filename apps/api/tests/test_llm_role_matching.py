"""The LLM decides which titles are a campaign's role; word rules only find candidates.

Measured 2026-10-10 on 120 labelled real titles: LLM yes/no F1 0.96 (precision 1.00), JobBERT
0.88, word rules 0.85, Voyage title embeddings 0.74. Word rules missed "Chief Brand Officer",
"Director of Brand", "Applied Scientist", "Product Owner" and let in "Chief of Staff to the CMO".
"""
from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest

import models
from campaigns import _in_bounds
from matching import role_judge
from tests.test_campaigns import _campaign, _job, _profile


def _titles(db, campaign):
    return sorted(j.title for j in _in_bounds(db.query(models.Job), campaign))


def _verdict(db, role, title, match):
    db.add(models.TitleVerdict(role_key=role.strip().lower(), title_key=title.strip().lower(), match=match))
    db.commit()


@pytest.fixture
def brand(db_session):
    for n, t in enumerate(["Head of Brand Marketing", "Director of Brand", "Brand Designer",
                           "Brand Ambassador", "Software Engineer"]):
        _job(db_session, n, title=t)
    c = _campaign(db_session, _profile(db_session), roles=["Brand Head"], remote_only=False)
    return db_session, c


def test_the_llm_verdict_beats_the_word_rules_both_ways(brand):
    db, c = brand
    _verdict(db, "Brand Head", "Director of Brand", True)        # words miss it, LLM accepts
    _verdict(db, "Brand Head", "Head of Brand Marketing", False)  # words accept it, LLM says no
    assert _titles(db, c) == ["Director of Brand"]


def test_an_unjudged_title_falls_back_to_the_word_rules(brand):
    db, c = brand
    assert _titles(db, c) == ["Head of Brand Marketing"]


def test_a_verdict_for_another_role_does_not_leak(brand):
    db, c = brand
    _verdict(db, "Brand Manager", "Brand Designer", True)
    assert "Brand Designer" not in _titles(db, c)


def test_candidates_share_a_role_word_and_respect_the_other_bounds(db_session):
    _job(db_session, 1, title="Director of Brand", location="Mumbai")
    _job(db_session, 2, title="Head of Sales", location="Mumbai")
    _job(db_session, 3, title="Brand Lead", location="Berlin")
    _job(db_session, 4, title="Software Engineer", location="Mumbai")
    c = _campaign(db_session, _profile(db_session), roles=["Brand Head"], locations=["Mumbai"],
                  remote_only=False)
    assert sorted(role_judge.candidate_titles(db_session, c, "Brand Head")) == [
        "Director of Brand", "Head of Sales"]


def _offline(db):
    scope = MagicMock()
    scope.return_value.__enter__.return_value = db
    scope.return_value.__exit__.return_value = False
    return patch("matching.role_judge.session_scope", scope)


def test_the_sweep_judges_with_the_workers_session(db_session):
    import workers.jobs as wj
    c = _campaign(db_session, _profile(db_session), roles=["Brand Head"], remote_only=False)
    scope = MagicMock()
    scope.return_value.__enter__.return_value = db_session
    scope.return_value.__exit__.return_value = False
    with patch("workers.jobs.session_scope", scope), patch("workers.jobs.judge_campaign_titles") as judge,             patch("workers.jobs.build_matches"), patch("workers.jobs.get_queue"):
        wj.sweep_campaigns_task()
    judge.assert_called_once_with(c.id, limit=wj.SWEEP_JUDGE_LIMIT, scope=scope)


def test_judging_asks_only_about_unjudged_titles_and_stores_the_answers(brand, monkeypatch):
    db, c = brand
    _verdict(db, "Brand Head", "Head of Brand Marketing", True)
    asked = []

    def fake_ask(role, titles):
        asked.append((role, sorted(titles)))
        return {t: t != "Brand Ambassador" for t in titles}

    monkeypatch.setattr(role_judge, "_ask", fake_ask)
    with _offline(db):
        result = role_judge.judge_campaign_titles(c.id)
    assert asked == [("Brand Head", ["Brand Ambassador", "Brand Designer", "Director of Brand"])]
    assert result["judged"] == 3
    assert _titles(db, c) == ["Brand Designer", "Director of Brand", "Head of Brand Marketing"]
    with _offline(db):
        assert role_judge.judge_campaign_titles(c.id)["judged"] == 0  # cached


def test_titles_the_model_skipped_stay_unjudged(brand, monkeypatch):
    db, c = brand
    monkeypatch.setattr(role_judge, "_ask", lambda role, titles: {"Director of Brand": True})
    with _offline(db):
        assert role_judge.judge_campaign_titles(c.id)["judged"] == 1
    assert db.query(models.TitleVerdict).count() == 1


def test_a_failed_llm_call_keeps_the_word_rules_in_charge(brand, monkeypatch):
    db, c = brand

    def boom(role, titles):
        raise RuntimeError("nim down")

    monkeypatch.setattr(role_judge, "_ask", boom)
    with _offline(db):
        assert role_judge.judge_campaign_titles(c.id)["judged"] == 0
    assert _titles(db, c) == ["Head of Brand Marketing"]


def test_the_prompt_counts_specialisations_as_the_same_role():
    assert "Technical Product Manager" in role_judge.SYSTEM
    assert "Product Owner" in role_judge.SYSTEM
