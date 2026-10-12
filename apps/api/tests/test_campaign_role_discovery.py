"""P0 #6: discovery searches what active campaigns ask for, not a fixed product-manager list.

The keyword sources (Remotive, Reed) and Workday's pre-hydration filter took their terms from
hardcoded PM lists in connectors/config.py, so a Data Analyst campaign searched a PM pool.
LinkedIn and JobSpy title searches already run per campaign (campaign_search_task and the daily
union refresh), so the global discovery pass no longer repeats them with PM keywords.
"""
from unittest.mock import MagicMock, patch

import models
import workers.jobs as wj
from connectors import config, workday
from tests.test_campaigns import _campaign, _profile
from tests.test_source_isolation import _offline


def test_no_fixed_product_manager_list_remains_in_connectors_config():
    for name in dir(config):
        value = getattr(config, name)
        if isinstance(value, (list, tuple)):
            assert not any("product" in str(v).lower() for v in value), name


def test_keyword_sources_and_workday_search_active_campaign_roles(db_session):
    profile = _profile(db_session)
    _campaign(db_session, profile, roles=["Data Analyst", "data analyst", "BI Analyst"])
    _campaign(db_session, profile, roles=["Chef"], status=models.CampaignStatus.paused)
    remotive, reed, wd = MagicMock(return_value=[]), MagicMock(return_value=[]), MagicMock(return_value=[])
    with _offline(db=db_session, fetch_remotive_jobs=remotive, fetch_reed_jobs=reed, fetch_workday_jobs=wd), \
            patch("workers.jobs.conn_config.WORKDAY_BOARDS", {"adobe": "wd5/x"}), \
            patch("workers.jobs.conn_config.WORKDAY_INTERVAL_HOURS", 1), \
            patch("workers.jobs.time.sleep"):
        wj.discover_inline()

    assert [c.args[0] for c in remotive.call_args_list] == ["Data Analyst", "BI Analyst"]
    assert [c.args[0] for c in reed.call_args_list] == ["Data Analyst", "BI Analyst"]
    assert wd.call_args.args == ("adobe", ["Data Analyst", "BI Analyst"])


def test_no_active_campaign_means_no_keyword_search(db_session):
    remotive = MagicMock(return_value=[])
    with _offline(db=db_session, fetch_remotive_jobs=remotive), patch("workers.jobs.time.sleep"):
        wj.discover_inline()
    remotive.assert_not_called()


def test_title_searches_are_left_to_campaign_search():
    sources = {source for source, _ in wj._discovery_units()}
    assert "jobspy" not in sources and "linkedin" not in sources
    assert "linkedin_posts" in sources  # role-agnostic hiring posts stay global


def test_workday_hydrates_nothing_without_keywords():
    with patch("connectors.workday.WORKDAY_BOARDS", {"acme": "wd5/ext"}), \
            patch("connectors.workday._post") as post, patch("connectors.workday._get") as get:
        assert workday.fetch_workday_jobs("acme", []) == []
    post.assert_not_called()
    get.assert_not_called()
