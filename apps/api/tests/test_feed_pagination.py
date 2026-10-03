"""Phase 2 item 4a — pagination to exhaustion, and which feeds that makes
sweepable for delisting.

ADR-017 §2: only a source that returns a COMPLETE listing may be swept, because
absence from a truncated "newest N" window is age, not delisting. Phase 1 left
all six keyless feeds out of `SWEEPABLE_SOURCES` and recorded "paginate those
fetchers to exhaustion" as Phase 2 work.

Measured live 2026-10-03, with 1s pacing — only one of the six is exhaustible:

  jobicy         7 requests, 633 jobs, cursor + hasMore. EXHAUSTIBLE -> sweepable
  himalayas      totalCount 115,729 at a server-forced limit of 20/page
                 (limit=100 ignored) = 5,786 requests. Not exhaustible.
  arbeitnow      325/page then 100/page, links.last is null; HTTP 429 at page 21
                 (>2,450 jobs) and its own terms say "please do not abuse".
  remoteok       fixed 100-row payload, limit/offset ignored. Structural.
  weworkremotely RSS, latest ~90 items. Structural.
  workingnomads  no page/cursor/count knob, rolling ~30-day window. Structural.

So five of six stay non-sweepable and keep accumulating stale rows, by decision
rather than omission. The numbers are here so the next session doesn't re-probe.
"""
from unittest.mock import MagicMock, call, patch

import pytest

from connectors import feeds
from workers.jobs import SWEEPABLE_SOURCES

JOBICY_URL = "https://jobicy.com/api/v2/remote-jobs"


def _page(ids, cursor=None, more=False):
    resp = MagicMock()
    resp.json.return_value = {
        "jobs": [{"id": i, "jobTitle": f"PM {i}", "companyName": "Acme",
                  "url": f"https://jobicy.com/jobs/{i}"} for i in ids],
        "nextCursor": cursor,
        "hasMore": more,
    }
    return resp


def test_jobicy_follows_the_cursor_until_there_is_no_more():
    pages = [
        _page([1, 2], cursor="c1", more=True),
        _page([3, 4], cursor="c2", more=True),
        _page([5], cursor=None, more=False),
    ]
    with patch("connectors.feeds._get", side_effect=pages) as get, \
         patch("connectors.feeds.time.sleep") as sleep:
        jobs = feeds.fetch_jobicy_jobs(count=100)

    assert [j["external_id"] for j in jobs] == ["1", "2", "3", "4", "5"]
    assert get.call_args_list == [
        call(JOBICY_URL, {"count": 100}),
        call(JOBICY_URL, {"count": 100, "cursor": "c1"}),
        call(JOBICY_URL, {"count": 100, "cursor": "c2"}),
    ]
    # Same host, back-to-back pages: paced between them, not before the first.
    assert sleep.call_count == 2


def test_jobicy_stops_when_hasmore_is_true_but_the_cursor_is_missing():
    """Trusting `hasMore` alone would re-request page 1 forever."""
    with patch("connectors.feeds._get", side_effect=[_page([1], cursor=None, more=True)]) as get:
        jobs = feeds.fetch_jobicy_jobs()
    assert len(jobs) == 1 and get.call_count == 1


def test_jobicy_pagination_is_capped():
    """A feed that always claims hasMore must not spin the worker forever."""
    endless = [_page([i], cursor=f"c{i}", more=True) for i in range(feeds.MAX_PAGES + 5)]
    with patch("connectors.feeds._get", side_effect=endless) as get, \
         patch("connectors.feeds.time.sleep"):
        feeds.fetch_jobicy_jobs()
    assert get.call_count == feeds.MAX_PAGES


def test_a_failure_part_way_through_pagination_discards_the_partial_listing():
    """A partial listing must never reach the delisting sweep: the pages that
    did not arrive would look like jobs absent from the board. Raising is what
    makes `fetch_enabled_feeds` record an error and hand the sweep nothing.
    """
    pages = [_page([1], cursor="c1", more=True), RuntimeError("502 on page 2")]
    with patch("connectors.feeds._get", side_effect=pages), \
         patch("connectors.feeds.time.sleep"):
        with pytest.raises(RuntimeError):
            feeds.fetch_jobicy_jobs()

    # End to end: the error is reported, and the source contributes no jobs.
    # Patched at `_get`, not at `fetch_jobicy_jobs` — FEED_FETCHERS holds a
    # direct reference to the function object, so patching the module attribute
    # would not be seen by fetch_enabled_feeds (and would hit the real network).
    with patch("connectors.feeds._get", side_effect=[_page([1], cursor="c1", more=True),
                                                     RuntimeError("502 on page 2")]), \
         patch("connectors.feeds.time.sleep"):
        jobs, report = feeds.fetch_enabled_feeds(["jobicy"], [])
    assert jobs == []
    assert "502 on page 2" in report["jobicy"]


def test_only_exhaustible_sources_are_sweepable():
    """Pins the measured outcome (see this module's docstring). Adding a source
    here has to be a deliberate edit with a measurement behind it.
    """
    assert SWEEPABLE_SOURCES == {"greenhouse", "lever", "ashby", "jobicy"}
    for truncated in ("remoteok", "himalayas", "arbeitnow", "weworkremotely", "workingnomads"):
        assert truncated not in SWEEPABLE_SOURCES, truncated
