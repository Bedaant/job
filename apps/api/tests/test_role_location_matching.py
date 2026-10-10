"""A campaign's role and location filters, matched the way real postings are written.

Measured 2026-10-10 on a real "Brand Head, Mumbai" campaign: on-demand search found 51 relevant
postings ("Head of Brand & Communications", "Creative Head – Brand") and the campaign kept 0 of
them, because the role filter was the literal phrase `title ILIKE '%Brand Head%'` — which also
matched 0 of 12,100 live jobs. Locations had the same shape: 304 live postings say "Bengaluru"
and 247 say "Bangalore", so a campaign set to either city missed nearly half its market.
"""
import pytest

import models
from campaigns import _in_bounds
from tests.test_campaigns import _campaign, _job, _profile


def _titles(db, campaign):
    return sorted(j.title for j in _in_bounds(db.query(models.Job), campaign))


@pytest.fixture
def pool(db_session):
    titles = ["Head of Brand & Communications", "Creative Head – Brand", "Brand Manager",
              "Headquarters Brand Coordinator", "Chief Marketing Officer", "CMO, D2C",
              "VP Marketing", "Vice President, Marketing", "Cafe Manager"]
    for n, t in enumerate(titles):
        _job(db_session, n, title=t)
    return db_session


def _c(db, **kw):
    kw.setdefault("remote_only", False)
    return _campaign(db, _profile(db, f"u{len(kw)}{kw.get('name', '')}@x.com"), **kw)


def test_role_words_match_in_any_order_as_whole_words(pool):
    c = _c(pool, roles=["Brand Head"])
    assert _titles(pool, c) == ["Creative Head – Brand", "Head of Brand & Communications"]


def test_filler_words_in_a_role_do_not_have_to_appear(pool):
    c = _c(pool, name="b", roles=["Head of Brand"])
    assert _titles(pool, c) == ["Creative Head – Brand", "Head of Brand & Communications"]


def test_an_abbreviation_matches_its_expansion_both_ways(pool):
    by_abbr = _c(pool, name="c", roles=["CMO"])
    assert _titles(pool, by_abbr) == ["CMO, D2C", "Chief Marketing Officer"]
    by_words = _c(pool, name="d", roles=["Chief Marketing Officer"])
    assert _titles(pool, by_words) == ["CMO, D2C", "Chief Marketing Officer"]
    vp = _c(pool, name="e", roles=["VP Marketing"])
    assert _titles(pool, vp) == ["VP Marketing", "Vice President, Marketing"]


def test_a_city_matches_its_other_spelling(db_session):
    for n, loc in enumerate(["Bangalore, Karnataka", "Bengaluru, India", "Gurgaon", "Pune"]):
        _job(db_session, n, title="Designer", location=loc)
    c = _c(db_session, roles=["Designer"], locations=["Bengaluru"])
    assert sorted(j.location for j in _in_bounds(db_session.query(models.Job), c)) == [
        "Bangalore, Karnataka", "Bengaluru, India"]
    g = _c(db_session, name="g", roles=["Designer"], locations=["Gurugram"])
    assert [j.location for j in _in_bounds(db_session.query(models.Job), g)] == ["Gurgaon"]


def test_a_blank_role_never_widens_the_filter_to_everything(pool):
    c = _c(pool, name="h", roles=["  ", "CMO"])
    assert _titles(pool, c) == ["CMO, D2C", "Chief Marketing Officer"]
