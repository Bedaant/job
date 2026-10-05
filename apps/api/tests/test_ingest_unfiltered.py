"""Discovery stores whole boards; `FEED_KEYWORDS` stops being a global ingest gate.

**Why (owner decision 2026-10-05).** `FEED_KEYWORDS` lived in `connectors/config.py`
and gated what *entered* the pool for every ATS board and every feed. A user's
own description (campaign roles/locations, résumé-fact centroid, prefs) only
ever *filtered* what that global config had already collected — so for a product
the PRD calls multi-tenant, discovery was single-tenant.

Measured before the change: 1,758 live jobs, 309 product roles, **6 SRE roles —
while four campaigns asked for SRE.** Those campaigns were searching a pool
never collected for them, and no amount of matching quality could fix it.

**This is deliberately NOT uniform, because the sources are not uniform:**

| source | fetch shape | stores everything? |
|---|---|---|
| greenhouse / lever / ashby | one request returns every opening | **yes** — filter dropped |
| the keyless feeds | whole board per fetch | **yes** — filter dropped |
| workday | cheap list + one EXPENSIVE detail call per job | **no** — must filter before hydration, or Adobe alone is 526 detail requests per run |
| remotive / reed | the keyword IS the query parameter | **no** — there is no unfiltered fetch to make |

So `FEED_KEYWORDS` still gates Workday (a cost necessity, documented in its
connector) and `REMOTIVE_KEYWORDS`/`REED_KEYWORDS` remain query parameters. The
bulk of the pool becomes user-agnostic, which is the point.

**Freshness gets strictly better, not worse.** ADR-017 recorded a hazard:
narrowing `FEED_KEYWORDS` tombstoned stored jobs whose titles stopped matching,
because they dropped out of the keyword-filtered payload the sweep compares
against. With whole boards stored and compared, that hazard disappears for these
sources.

**The cost is embedding, not storage.** An unembedded job cannot be matched, and
Voyage's free tier is 3 RPM. `embed_backlog_task` embeds jobs an active campaign
asks for FIRST (`_in_bounds`), so a larger pool stays latent rather than
harmful — but broad multi-user coverage is gated on paid embeddings. See
ADR-021.
"""
from unittest.mock import MagicMock, patch

from workers.jobs import _fetch_ats_source


def test_ats_boards_keep_every_posting_not_just_keyword_matches():
    """The core change: a board returns every opening and we store all of it."""
    board = [
        {"title": "Senior Product Manager", "external_id": "1"},
        {"title": "Site Reliability Engineer", "external_id": "2"},
        {"title": "Staff Accountant", "external_id": "3"},
    ]
    jobs, batches = _fetch_ats_source(lambda token: board, ["acme"], ["product manager"])

    assert [j["external_id"] for j in jobs] == ["1", "2", "3"], (
        "FEED_KEYWORDS must no longer gate what enters the pool"
    )
    assert [t for t, _ in batches] == ["acme"]


def test_the_sweep_batch_now_carries_the_whole_board():
    """ADR-017's hazard — editing FEED_KEYWORDS tombstoning stored jobs — only
    existed because the sweep compared against a keyword-filtered payload. With
    the whole board in the batch, the comparison is complete."""
    board = [{"title": "Site Reliability Engineer", "external_id": "sre-1"}]
    _, batches = _fetch_ats_source(lambda token: board, ["acme"], ["product manager"])

    (_token, batch_jobs), = batches
    assert [j["external_id"] for j in batch_jobs] == ["sre-1"]


def test_an_empty_board_still_contributes_no_batch():
    """Unchanged safety property: an empty fetch is no signal, never "the board
    is empty" (ADR-017 §3), so nothing of that board's can be delisted."""
    jobs, batches = _fetch_ats_source(lambda token: [], ["acme"], [])
    assert jobs == [] and batches == []


def test_feeds_are_asked_for_everything():
    """`filter_by_keywords` treats "no keywords" as "no filter"; discovery now
    relies on that instead of passing the global list."""
    from workers import jobs as wj

    captured = {}

    def fake_feeds(enabled, keywords):
        captured["keywords"] = keywords
        return [], {}

    patches = [
        patch("workers.jobs.fetch_remotive_jobs", MagicMock(return_value=[])),
        patch("workers.jobs.fetch_reed_jobs", MagicMock(return_value=[])),
        patch("workers.jobs.fetch_greenhouse_jobs", MagicMock(return_value=[])),
        patch("workers.jobs.fetch_lever_jobs", MagicMock(return_value=[])),
        patch("workers.jobs.fetch_ashby_jobs", MagicMock(return_value=[])),
        patch("workers.jobs.fetch_workday_jobs", MagicMock(return_value=[])),
        patch("workers.jobs.fetch_enabled_feeds", fake_feeds),
        patch("workers.jobs.upsert_jobs", MagicMock(return_value=(0, 0, 0))),
        patch("workers.jobs.backfill_job_embeddings", MagicMock()),
        patch("workers.jobs.session_scope", MagicMock()),
    ]
    for p in patches:
        p.start()
    try:
        wj.discover_jobs_task()
    finally:
        for p in patches:
            p.stop()

    assert captured["keywords"] == [], (
        "feeds must be asked for their whole board; filtering is now per-user at match time"
    )


def test_workday_still_filters_before_hydrating():
    """NOT a inconsistency to tidy away: Workday's list endpoint is cheap but
    every job needs its own detail request, so hydrating a whole board would be
    526 extra requests for Adobe alone. The filter there is a cost control."""
    from connectors import workday

    assert workday.KEYWORDS, (
        "workday must keep a keyword filter; see its module docstring for why"
    )
