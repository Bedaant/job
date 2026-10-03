"""COLLECT-C: the Workday CXS connector.

Everything asserted here was measured off live responses on 2026-10-03/04 —
see `docs/harness-reports/collect-c-platforms.md`:

- `limit` is capped at 20; 50 and above return HTTP 400.
- `searchText` filters single words but NOT phrases: "engineer" cut adobe's board
  from 527 to 343, while "product manager" returned all 527 ranked. So the
  connector fetches the whole board and filters client-side, like the other ATS
  connectors — it cannot push the keyword filter to the server.
- `locationsText` in the LIST payload is frequently a count, not a place
  ("5 Locations", "3 Locations", …). Storing it would poison `canonical_hash`
  and make the India filter meaningless, so locations come from the per-job
  detail endpoint.
- The detail endpoint carries `location`, `additionalLocations`, `country` and
  `startDate` — a real ISO date. `startDate` tracked `postedOn` with an exact,
  constant one-day offset across six jobs with six different `postedOn` values
  ("Posted Yesterday" → 2026-10-02, "Posted 12 Days Ago" → 2026-09-21), which is
  what proves it is the posting date and not a role start date. The offset is a
  timezone artifact of Workday's prose; `startDate` is used as-is.
"""
from unittest.mock import MagicMock, call, patch

import pytest

from connectors import workday


def _listing(titles, total=None):
    """One LIST page. locationsText is deliberately a count for every row — the
    connector must never use it.

    `total` defaults to the row count, but **real pages past the first report
    `total: 0`** (measured on adobe: offset 0 → total 526, offset 20 → total 0
    with 20 rows). Fixtures must mirror that, or a pagination test passes while
    the connector stops after two pages.
    """
    return {
        "total": total if total is not None else len(titles),
        "jobPostings": [
            {"title": t, "externalPath": f"/job/X/{t.replace(' ', '-')}_R{i}",
             "locationsText": "5 Locations", "postedOn": "Posted 3 Days Ago",
             "bulletFields": [f"R{i}"]}
            for i, t in enumerate(titles)
        ],
    }


def _detail(title, location="Bengaluru", extra=None, start="2026-09-18", req="R0"):
    return {"jobPostingInfo": {
        "title": title, "jobReqId": req, "location": location,
        "additionalLocations": extra or [], "startDate": start,
        "country": {"descriptor": "India"}, "timeType": "Full time",
        "jobDescription": "<p>Build things.</p>",
        "externalUrl": f"https://acme.wd5.myworkdayjobs.com/ext/job/{req}",
    }}


BOARDS = {"acme": "wd5/ext"}
NAMES = {"acme": "Acme Corp"}


def _cfg():
    return (patch("connectors.workday.WORKDAY_BOARDS", BOARDS),
            patch("connectors.workday.TOKEN_COMPANY_NAMES", NAMES),
            patch("connectors.workday.KEYWORDS", ["product manager"]),
            patch("connectors.workday.PAGE_PACING_SECONDS", 0))


def _run(post_pages, details):
    patches = list(_cfg())
    patches.append(patch("connectors.workday._post", side_effect=post_pages))
    patches.append(patch("connectors.workday._get", side_effect=details))
    for p in patches:
        p.start()
    try:
        return workday.fetch_workday_jobs("acme")
    finally:
        for p in patches:
            p.stop()


def test_only_keyword_matches_are_detail_fetched():
    """The whole point of the two-step shape: adobe's board is 527 jobs and only
    a handful are PM roles. Detail-fetching the board would be 527 extra requests.
    """
    pages = [_listing(["Product Manager", "Software Engineer", "Recruiter"])]
    details = MagicMock(side_effect=[_detail("Product Manager", req="R0")])
    jobs = _run(pages, details)

    assert len(jobs) == 1
    assert details.call_count == 1, "only the PM title should be hydrated"
    assert jobs[0]["title"] == "Product Manager"


def test_location_comes_from_the_detail_endpoint_never_from_a_count():
    """`locationsText` is "5 Locations" on every fixture row. If that string ever
    reaches `location`, canonical_hash and the India filter are both broken."""
    jobs = _run([_listing(["Product Manager"])],
                [_detail("Product Manager", location="Bengaluru",
                         extra=["Hyderabad"], req="R0")])

    assert jobs[0]["location"] == "Bengaluru; Hyderabad"
    assert "Locations" not in jobs[0]["location"]


def test_posted_at_is_the_real_iso_start_date():
    jobs = _run([_listing(["Product Manager"])],
                [_detail("Product Manager", start="2026-09-18", req="R0")])
    assert jobs[0]["posted_at"].strftime("%Y-%m-%d") == "2026-09-18"


def test_a_missing_start_date_is_null_not_a_guess():
    """Phase 1's lesson (coerce_posted_at took three rounds): a wrong-but-
    plausible date is worse than no date. `postedOn` prose like "Posted 30+ Days
    Ago" is never parsed into one."""
    jobs = _run([_listing(["Product Manager"])],
                [_detail("Product Manager", start=None, req="R0")])
    assert jobs[0]["posted_at"] is None


def test_external_id_is_tenant_scoped():
    """`uq_job_source_external_id` spans the whole source, and Workday req ids
    are only unique within a tenant — two tenants can both have R1001."""
    jobs = _run([_listing(["Product Manager"])],
                [_detail("Product Manager", req="R1001")])
    assert jobs[0]["external_id"] == "acme:R1001"


def test_company_name_comes_from_the_curated_map():
    jobs = _run([_listing(["Product Manager"])], [_detail("Product Manager", req="R0")])
    assert jobs[0]["company"] == "Acme Corp"


def test_the_board_is_paginated_to_exhaustion_at_twenty_per_page():
    """limit > 20 is HTTP 400, so 45 jobs is three requests.

    Only the FIRST page carries `total`; pages 2 and 3 report `total: 0`, as the
    live API does. Trusting the per-page value made `len(rows) >= total` true at
    `40 >= 0` and returned 40 of 526 rows — and because a short listing is still
    fed to the delisting sweep, the other 486 live jobs would have been
    tombstoned.
    """
    pages = [_listing([f"Role {i}" for i in range(20)], total=45),
             _listing([f"Role {i}" for i in range(20, 40)], total=0),
             _listing(["Product Manager"] + [f"Role {i}" for i in range(41, 45)], total=0)]
    post = MagicMock(side_effect=pages)
    patches = list(_cfg()) + [patch("connectors.workday._post", post),
                              patch("connectors.workday._get",
                                    side_effect=[_detail("Product Manager", req="R0")])]
    for p in patches:
        p.start()
    try:
        jobs = workday.fetch_workday_jobs("acme")
    finally:
        for p in patches:
            p.stop()

    assert [c.args[1] for c in post.call_args_list] == [0, 20, 40]
    assert len(jobs) == 1


def test_a_board_bigger_than_the_page_cap_raises_rather_than_truncating():
    """A truncated listing must never reach the delisting sweep: every job on the
    pages that were not fetched would look absent from the board. Failing loudly
    beats tombstoning live jobs (ADR-017 §3)."""
    page = _listing([f"Role {i}" for i in range(20)], total=10_000)
    patches = list(_cfg()) + [patch("connectors.workday.MAX_PAGES", 2),
                              patch("connectors.workday._post", return_value=page),
                              patch("connectors.workday._get", return_value={})]
    for p in patches:
        p.start()
    try:
        with pytest.raises(RuntimeError, match="page cap"):
            workday.fetch_workday_jobs("acme")
    finally:
        for p in patches:
            p.stop()


def test_a_listing_that_ends_early_raises_instead_of_being_swept():
    """An empty page before `total` is reached is indistinguishable from a
    failure, so it must not be read as "end of board" — that is ADR-017 §3's
    empty-fetch trap, and here it would hand the sweep a short listing."""
    pages = [_listing([f"Role {i}" for i in range(20)], total=500),
             _listing([], total=0)]
    patches = list(_cfg()) + [patch("connectors.workday._post", side_effect=pages),
                              patch("connectors.workday._get", return_value={})]
    for p in patches:
        p.start()
    try:
        with pytest.raises(RuntimeError, match="incomplete"):
            workday.fetch_workday_jobs("acme")
    finally:
        for p in patches:
            p.stop()


def test_a_genuinely_empty_board_is_not_an_error():
    """qualcomm's board returned total=0 with no rows — a real, empty board."""
    patches = list(_cfg()) + [patch("connectors.workday._post",
                                    return_value={"total": 0, "jobPostings": []}),
                              patch("connectors.workday._get", return_value={})]
    for p in patches:
        p.start()
    try:
        assert workday.fetch_workday_jobs("acme") == []
    finally:
        for p in patches:
            p.stop()


def test_a_failed_detail_fetch_raises_instead_of_dropping_the_job():
    """Dropping it would remove it from the payload the sweep compares against,
    and tombstone a job that is still listed."""
    patches = list(_cfg()) + [
        patch("connectors.workday._post", return_value=_listing(["Product Manager"])),
        patch("connectors.workday._get", side_effect=RuntimeError("detail 503")),
    ]
    for p in patches:
        p.start()
    try:
        with pytest.raises(RuntimeError):
            workday.fetch_workday_jobs("acme")
    finally:
        for p in patches:
            p.stop()


def test_an_unconfigured_tenant_is_a_no_op():
    patches = list(_cfg())
    for p in patches:
        p.start()
    try:
        assert workday.fetch_workday_jobs("nosuchtenant") == []
    finally:
        for p in patches:
            p.stop()


def test_workday_is_only_fetched_on_runs_where_it_is_due():
    """Two boards measured ~4.3 minutes. Discovery is hourly on a single
    SimpleWorker, so fetching every run would park the worker and queue campaign
    runs behind it."""
    from datetime import datetime

    from workers.jobs import _workday_tokens

    with patch("workers.jobs.conn_config.WORKDAY_BOARDS", {"adobe": "wd5/x"}), \
         patch("workers.jobs.conn_config.WORKDAY_INTERVAL_HOURS", 6):
        with patch("workers.jobs.datetime") as dt:
            dt.utcnow.return_value = datetime(2026, 10, 4, 12, 0)   # 12 % 6 == 0
            assert _workday_tokens() == ["adobe"]
            dt.utcnow.return_value = datetime(2026, 10, 4, 13, 0)   # 13 % 6 != 0
            assert _workday_tokens() == []


def test_an_interval_of_one_or_zero_means_every_run():
    """0 must not divide by zero, and 1 must not accidentally skip."""
    from workers.jobs import _workday_tokens

    for every in (0, 1):
        with patch("workers.jobs.conn_config.WORKDAY_BOARDS", {"adobe": "wd5/x"}), \
             patch("workers.jobs.conn_config.WORKDAY_INTERVAL_HOURS", every):
            assert _workday_tokens() == ["adobe"], every


def test_every_configured_board_has_a_wd_and_site_and_a_company_name():
    """Guards the config shape: "wd5/external_experienced", plus the same
    token->name rule the board tokens have (an unmapped token would become the
    `company` value and feed canonical_hash)."""
    from connectors import config

    for tenant, board in config.WORKDAY_BOARDS.items():
        wd, slash, site = board.partition("/")
        assert slash and site, f"{tenant}: {board!r} is not 'wd<N>/<site>'"
        assert wd.startswith("wd"), f"{tenant}: {wd!r} is not a wd host"
        assert tenant in config.TOKEN_COMPANY_NAMES, f"{tenant} has no company name"
