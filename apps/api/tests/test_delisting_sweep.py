"""Task 5 — delisting sweep (workers/jobs.py). Absence from a trustworthy,
full-listing payload is the only delisting signal (see module docstring in
workers/jobs.py for which sources qualify and why).

Greenhouse/lever/ashby no longer have a stable per-token key on the stored
row: Task 4 made `Job.company` a display name (resolved from the API
payload or a token->name map), which can vary in formatting run to run, so
it is never used to scope the sweep. Instead `_fetch_ats_source` combines
every token's fetch for one source and only hands `_sweep_delisted` a
non-empty, "trustworthy" (every token returned something) payload — see
`_fetch_ats_source`'s docstring for the full reasoning.
"""
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import main
import models
from connectors.normalize import canonical_hash
from database import Base, get_db
from workers.jobs import _fetch_ats_source, _sweep_delisted


def _db():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def _job(db, source, external_id, company="Acme", title=None, delisted_at=None,
         board_token=None):
    """COLLECT-D: `board_token` scopes the sweep. None means a source with no
    per-board concept (a feed), or a row stored before migration 0023."""
    title = title or f"Job {external_id}"
    job = models.Job(
        source=source, external_id=external_id, company=company, title=title,
        board_token=board_token,
        canonical_hash=canonical_hash(company, title, None), apply_url=f"https://x/{external_id}",
        delisted_at=delisted_at,
    )
    db.add(job)
    db.commit()
    return job


def _payload(source, external_id, company="Acme", title=None):
    title = title or f"Job {external_id}"
    return {"source": source, "external_id": external_id, "company": company, "title": title}


# ---------- core sweep behavior ----------

def test_sweep_delists_job_absent_from_this_runs_payload():
    db = _db()
    _job(db, "greenhouse", "1", board_token="acme")
    _job(db, "greenhouse", "2", board_token="acme")
    _job(db, "greenhouse", "3", board_token="acme")

    # This run's fetch only returned 1 and 2 — 3 fell off the board.
    _sweep_delisted(db, "greenhouse", "acme", [_payload("greenhouse", "1"), _payload("greenhouse", "2")])
    db.commit()

    by_id = {j.external_id: j for j in db.query(models.Job).filter(models.Job.source == "greenhouse")}
    assert by_id["1"].delisted_at is None
    assert by_id["2"].delisted_at is None
    assert by_id["3"].delisted_at is not None


def test_sweep_does_not_redelist_an_already_delisted_row():
    """Bulk UPDATE scoped to currently-listed (NULL) rows only — a tombstone's
    delisted_at must not be overwritten with a later timestamp on every sweep."""
    db = _db()
    from datetime import datetime
    _job(db, "greenhouse", "1", board_token="acme")
    stale = _job(db, "greenhouse", "2", delisted_at=datetime(2020, 1, 1))

    _sweep_delisted(db, "greenhouse", "acme", [_payload("greenhouse", "1")])
    db.commit()

    assert db.query(models.Job).filter_by(external_id="2").one().delisted_at == datetime(2020, 1, 1)


def test_sweep_on_empty_payload_delists_nothing():
    """A failed fetch (greenhouse/lever/ashby return [] on non-200) must look
    identical, here, to a genuinely empty board — either way, no signal."""
    db = _db()
    _job(db, "greenhouse", "1", board_token="acme")

    _sweep_delisted(db, "greenhouse", "acme", [])
    db.commit()

    assert db.query(models.Job).filter_by(external_id="1").one().delisted_at is None


def test_sweep_tolerates_a_payload_entry_missing_external_id():
    """A malformed/partial payload entry (no external_id) must never raise,
    and must never be the reason something gets delisted — it can't be
    matched to any stored row, so it's dropped from the comparison rather
    than landing a bare None in the NOT IN set (which would make every row's
    comparison NULL instead of a real id check)."""
    db = _db()
    _job(db, "greenhouse", "1", board_token="acme")
    _job(db, "greenhouse", "2", board_token="acme")

    # "1" is genuinely still present; the malformed entry carries no id at all.
    _sweep_delisted(db, "greenhouse", "acme", [{"source": "greenhouse", "title": "no id here"},
                                               _payload("greenhouse", "1")])
    db.commit()

    assert db.query(models.Job).filter_by(external_id="1").one().delisted_at is None
    assert db.query(models.Job).filter_by(external_id="2").one().delisted_at is not None


def test_sweep_tolerates_an_explicit_none_external_id():
    """Same as a missing key through .get(), but spelled out explicitly."""
    db = _db()
    _job(db, "greenhouse", "1", board_token="acme")

    _sweep_delisted(db, "greenhouse", "acme", [{"source": "greenhouse", "external_id": None, "title": "no id here"}])
    db.commit()

    assert db.query(models.Job).filter_by(external_id="1").one().delisted_at is None


def test_sweep_all_entries_missing_external_id_delists_nothing():
    """If nothing in this run's payload carries an external_id at all, there is
    no id to compare against — treat it exactly like an empty payload."""
    db = _db()
    _job(db, "greenhouse", "1", board_token="acme")

    _sweep_delisted(db, "greenhouse", "acme", [{"source": "greenhouse", "title": "no id here"}])
    db.commit()

    assert db.query(models.Job).filter_by(external_id="1").one().delisted_at is None


def test_sweep_ignores_non_qualifying_source():
    """remotive/reed only ever return a keyword slice (config.py) — absence
    there means "not in that search", not "gone". Never sweep them, even if
    called by mistake."""
    db = _db()
    _job(db, "remotive", "1")

    _sweep_delisted(db, "remotive", None, [])  # would look like "empty payload" too, but source itself disqualifies
    db.commit()
    assert db.query(models.Job).filter_by(external_id="1").one().delisted_at is None

    _sweep_delisted(db, "remotive", None, [_payload("remotive", "999")])  # job "1" absent from this payload
    db.commit()
    assert db.query(models.Job).filter_by(external_id="1").one().delisted_at is None


def test_sweep_delists_a_job_stored_under_its_real_company_name():
    """Pins the Task 4 integration: `company` holds a real display name, not
    the board token, and the sweep must not care — it never filters on
    company at all."""
    db = _db()
    _job(db, "greenhouse", "1", company="Okta", board_token="okta")   # absent this run
    _job(db, "greenhouse", "2", company="Okta", board_token="okta")   # re-seen this run

    _sweep_delisted(db, "greenhouse", "okta", [_payload("greenhouse", "2", company="Okta")])
    db.commit()

    assert db.query(models.Job).filter_by(external_id="1").one().delisted_at is not None
    assert db.query(models.Job).filter_by(external_id="2").one().delisted_at is None


def test_sweepable_sources_is_pinned_to_the_complete_listing_sources():
    """Final review C2: absence from a newest-N window IS age, and expiry by
    age is forbidden. All six keyless feeds are disqualified (evidence read
    off live responses on 2026-10-03):

    - remoteok: /api returns a fixed 100 rows (1 ToS notice + 99 jobs) and
      ignores limit/offset -- the same 99 ids come back either way.
    - himalayas: fetch_himalayas_jobs(limit=100) is capped server-side at 20
      per page; the response carries totalCount 115415 and a nextCursor.
    - jobicy: fetch_jobicy_jobs(count=50) is a count parameter; the response
      carries hasMore/nextCursor. REVISED IN PHASE 2 — it is now paged to
      exhaustion (7 requests, 633 jobs, measured 2026-10-03), so it returns a
      complete listing and qualifies. See tests/test_feed_pagination.py for
      the per-feed measurements; the other five were re-probed and stay out
      (himalayas needs 5,786 requests, arbeitnow 429s at page 21).
    - arbeitnow: page 1 of a paginated endpoint (meta.current_page,
      links.next -> page=2); nothing reads links/meta.
    - weworkremotely: RSS, latest 90 items observed.
    - workingnomads: no cursor/page/count knob, but its age distribution is
      [1, 1, 2, 3, ..., 28, 28, 29] days -- a rolling ~30-day window, nothing
      at or beyond 30. A job aging past 30 days would vanish from the
      payload while still live; that's age, not absence. Whether the source
      itself expires postings at 30 days is unverified -- unproven absence
      doesn't qualify.

    greenhouse/lever/ashby each hit one unpaginated board endpoint per token
    and return every open posting. A disqualified source must stay out of the
    sweep rather than be swept on partial/unproven data. This assertion exists
    so re-adding one cannot be quiet.
    """
    from workers.jobs import SWEEPABLE_SOURCES

    assert SWEEPABLE_SOURCES == {"greenhouse", "lever", "ashby", "jobicy"}  # workday removed 2026-10-06: its payload is keyword-filtered (one detail request per posting), so it is not a complete listing and narrowing FEED_KEYWORDS would have tombstoned live Adobe/Cisco roles


def test_sweep_ignores_a_truncated_feed():
    """A himalayas job that scrolled out of the newest-20 window is still
    live. It must not be tombstoned for being absent from this run's page."""
    db = _db()
    _job(db, "himalayas", "1")

    _sweep_delisted(db, "himalayas", None, [_payload("himalayas", "999")])
    db.commit()

    assert db.query(models.Job).filter_by(external_id="1").one().delisted_at is None


def test_sweep_ignores_workingnomads():
    """workingnomads is a rolling ~30-day window (observed ages 1..29 days,
    nothing at or beyond 30), not a complete listing -- disqualified. A job
    older than the window is still live and must not be tombstoned just for
    falling off this run's payload."""
    db = _db()
    _job(db, "workingnomads", "1")

    _sweep_delisted(db, "workingnomads", None, [_payload("workingnomads", "999")])
    db.commit()

    assert db.query(models.Job).filter_by(external_id="1").one().delisted_at is None


# ---------- _fetch_ats_source: combining per-token fetches safely ----------

def test_fetch_ats_source_trusts_a_board_that_matches_no_keyword():
    """Final review I3: trust is about whether the FETCH worked, not whether
    anything matched FEED_KEYWORDS. Judging it after filtering meant every one
    of nine Greenhouse boards had to have an open PM role in the same run or
    no Greenhouse job was ever delisted -- silently."""
    def fetcher(token):
        if token == "druva":
            return [{"source": "greenhouse", "external_id": "druva-1", "title": "Staff Accountant",
                     "company": token, "location": None}]
        return [{"source": "greenhouse", "external_id": f"{token}-1", "title": "Product Manager",
                 "company": token, "location": None}]

    jobs, batches = _fetch_ats_source(fetcher, ["okta", "druva"])

    # Both answered, so both get a batch. ADR-021 then removed keyword filtering
    # at ingest, so druva's non-matching posting is STORED rather than dropped —
    # the user's description filters at match time instead of deciding what was
    # ever collected. The property this test guards (trust follows the FETCH,
    # not the keyword match) is unchanged and now trivially true.
    assert [t for t, _ in batches] == ["okta", "druva"]
    assert {j["external_id"] for j in jobs} == {"okta-1", "druva-1"}


def test_fetch_ats_source_combines_every_tokens_jobs():
    def fetcher(token):
        return [{"source": "greenhouse", "external_id": f"{token}-1", "title": "Product Manager",
                  "company": token, "location": None}]

    jobs, batches = _fetch_ats_source(fetcher, ["okta", "druva"])

    assert [t for t, _ in batches] == ["okta", "druva"]
    assert {j["external_id"] for j in jobs} == {"okta-1", "druva-1"}


def test_an_empty_board_contributes_no_batch_and_the_others_still_sweep():
    """COLLECT-D REPLACED the old all-or-nothing rule here.

    This test used to be `..._is_untrustworthy_if_any_token_returns_empty` and
    asserted `trustworthy is False` -- one dead board disabled delisting for the
    WHOLE source, because without a per-token key on the row a source-wide sweep
    would have wrongly delisted the failed board's jobs too.

    `Job.board_token` (migration 0023) removes that compromise: each board is
    swept against its own payload, so an empty board simply contributes no batch
    and nothing of its is touched, while every board that answered is still
    swept. The old assertion is deliberately inverted, not accidentally broken.
    """
    def fetcher(token):
        return [] if token == "druva" else [
            {"source": "greenhouse", "external_id": f"{token}-1", "title": "Product Manager",
             "company": token, "location": None}
        ]

    jobs, batches = _fetch_ats_source(fetcher, ["okta", "druva"])

    assert [t for t, _ in batches] == ["okta"], "druva answered nothing, so it is not swept"
    assert {j["external_id"] for j in jobs} == {"okta-1"}


# ---------- wiring: discover_jobs_task actually calls the sweep ----------

@patch("workers.jobs.get_redis_connection")
@patch("workers.jobs.session_scope")
def test_discover_jobs_task_sweeps_delisted_jobs_end_to_end(mock_session_scope, mock_get_redis):
    """Both okta and druva answer this run, so each board is swept against its
    OWN payload (COLLECT-D): okta's missing job gets delisted, okta's re-seen job
    and druva's job both survive untouched."""
    from workers import jobs as worker_jobs

    db = _db()
    _job(db, "greenhouse", "1", company="Okta", board_token="okta")   # absent this run -> delisted
    _job(db, "greenhouse", "5", company="Okta", board_token="okta")   # re-seen -> stays listed
    _job(db, "greenhouse", "2", company="Druva", board_token="druva")  # other board, untouched
    mock_session_scope.return_value.__enter__.return_value = db
    mock_session_scope.return_value.__exit__.return_value = False
    mock_get_redis.return_value = MagicMock()

    def _fetch_greenhouse(token):
        by_token = {
            "okta": [{"source": "greenhouse", "external_id": "5", "title": "Product Manager",
                       "company": "Okta", "location": None, "remote": False, "salary": None,
                       "description": "", "apply_url": "https://x/5", "tags": [], "posted_at": None}],
            "druva": [{"source": "greenhouse", "external_id": "2", "title": "Product Manager",
                        "company": "Druva", "location": None, "remote": False, "salary": None,
                        "description": "", "apply_url": "https://x/2", "tags": [], "posted_at": None}],
        }
        return by_token.get(token, [])

    patches = [
        patch("workers.jobs.fetch_remotive_jobs", return_value=[]),
        patch("workers.jobs.fetch_reed_jobs", return_value=[]),
        patch("workers.jobs.conn_config.GREENHOUSE_BOARD_TOKENS", ["okta", "druva"]),
        patch("workers.jobs.fetch_greenhouse_jobs", side_effect=_fetch_greenhouse),
        patch("workers.jobs.fetch_lever_jobs", return_value=[]),
        patch("workers.jobs.fetch_ashby_jobs", return_value=[]),
        patch("workers.jobs.fetch_enabled_feeds", return_value=([], {})),
    ]
    for p in patches:
        p.start()
    try:
        worker_jobs.discover_jobs_task()
    finally:
        for p in patches:
            p.stop()

    assert db.query(models.Job).filter_by(external_id="1").one().delisted_at is not None   # okta, gone
    assert db.query(models.Job).filter_by(external_id="5").one().delisted_at is None        # okta, re-seen
    assert db.query(models.Job).filter_by(external_id="2").one().delisted_at is None        # druva, untouched


@patch("workers.jobs.get_redis_connection")
@patch("workers.jobs.session_scope")
def test_one_empty_board_no_longer_blocks_the_other_boards_sweep(
    mock_session_scope, mock_get_redis
):
    """COLLECT-D CHANGED THIS BEHAVIOUR DELIBERATELY.

    The previous version of this test was
    `..._skips_the_whole_sources_sweep_when_one_token_fetch_is_empty`, and it
    asserted that okta's genuinely-absent job must NOT be delisted when druva's
    board returned nothing. That was the only safe option while the sweep was
    source-wide: with no per-token key on the row, sweeping with the responding
    boards' combined ids would have tombstoned the silent board's live jobs.

    With `Job.board_token` (migration 0023) each board is swept on its own, so:
      - okta answered and no longer lists job "1" -> that IS real signal, delist it;
      - druva returned nothing -> no batch, so its job is left alone.
    """
    from workers import jobs as worker_jobs

    db = _db()
    _job(db, "greenhouse", "1", company="Okta", board_token="okta")    # absent from okta -> delisted now
    _job(db, "greenhouse", "7", company="Druva", board_token="druva")  # druva silent -> must survive
    mock_session_scope.return_value.__enter__.return_value = db
    mock_session_scope.return_value.__exit__.return_value = False
    mock_get_redis.return_value = MagicMock()

    def _fetch_greenhouse(token):
        if token == "okta":
            return [{"source": "greenhouse", "external_id": "999", "title": "Product Manager",
                     "company": "Okta", "location": None, "remote": False, "salary": None,
                     "description": "", "apply_url": "https://x/999", "tags": [], "posted_at": None}]
        return []

    patches = [
        patch("workers.jobs.fetch_remotive_jobs", return_value=[]),
        patch("workers.jobs.fetch_reed_jobs", return_value=[]),
        patch("workers.jobs.conn_config.GREENHOUSE_BOARD_TOKENS", ["okta", "druva"]),
        patch("workers.jobs.fetch_greenhouse_jobs", side_effect=_fetch_greenhouse),
        patch("workers.jobs.fetch_lever_jobs", return_value=[]),
        patch("workers.jobs.fetch_ashby_jobs", return_value=[]),
        patch("workers.jobs.fetch_workday_jobs", return_value=[]),
        patch("workers.jobs.fetch_enabled_feeds", return_value=([], {})),
    ]
    for p_ in patches:
        p_.start()
    try:
        worker_jobs.discover_jobs_task()
    finally:
        for p_ in patches:
            p_.stop()

    assert db.query(models.Job).filter_by(external_id="1").one().delisted_at is not None,         "okta answered without it, so its absence is real signal"
    assert db.query(models.Job).filter_by(external_id="7").one().delisted_at is None,         "druva returned nothing; a silent board delists nothing"


# ---------- GET /jobs must not serve a delisted job ----------

def _client_and_session():
    engine = create_engine(
        "sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    TestSessionLocal = sessionmaker(bind=engine)

    def override_get_db():
        db = TestSessionLocal()
        try:
            yield db
        finally:
            db.close()

    main.app.dependency_overrides[get_db] = override_get_db
    return TestClient(main.app), TestSessionLocal


def _auth(client, email):
    client.post("/auth/signup", json={"email": email, "password": "correct horse battery staple"})
    token = client.post(
        "/auth/login", data={"username": email, "password": "correct horse battery staple"}
    ).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_list_jobs_excludes_delisted_and_keeps_still_listed():
    from datetime import datetime
    client, TestSessionLocal = _client_and_session()
    headers = _auth(client, "delisting-jobs-ep@example.com")
    db = TestSessionLocal()
    _job(db, "remoteok", "1", title="Gone Role", delisted_at=datetime(2026, 1, 1))
    _job(db, "remoteok", "2", title="Still Open Role")
    db.close()

    resp = client.get("/jobs", headers=headers)

    assert resp.status_code == 200
    titles = {j["title"] for j in resp.json()}
    assert titles == {"Still Open Role"}
