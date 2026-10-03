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

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import models
from connectors.normalize import canonical_hash
from database import Base
from workers.jobs import _fetch_ats_source, _sweep_delisted


def _db():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def _job(db, source, external_id, company="Acme", title=None, delisted_at=None):
    title = title or f"Job {external_id}"
    job = models.Job(
        source=source, external_id=external_id, company=company, title=title,
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
    _job(db, "remoteok", "1")
    _job(db, "remoteok", "2")
    _job(db, "remoteok", "3")

    # This run's fetch only returned 1 and 2 — 3 fell off the board.
    _sweep_delisted(db, "remoteok", [_payload("remoteok", "1"), _payload("remoteok", "2")])
    db.commit()

    by_id = {j.external_id: j for j in db.query(models.Job).filter(models.Job.source == "remoteok")}
    assert by_id["1"].delisted_at is None
    assert by_id["2"].delisted_at is None
    assert by_id["3"].delisted_at is not None


def test_sweep_does_not_redelist_an_already_delisted_row():
    """Bulk UPDATE scoped to currently-listed (NULL) rows only — a tombstone's
    delisted_at must not be overwritten with a later timestamp on every sweep."""
    db = _db()
    from datetime import datetime
    _job(db, "remoteok", "1")
    stale = _job(db, "remoteok", "2", delisted_at=datetime(2020, 1, 1))

    _sweep_delisted(db, "remoteok", [_payload("remoteok", "1")])
    db.commit()

    assert db.query(models.Job).filter_by(external_id="2").one().delisted_at == datetime(2020, 1, 1)


def test_sweep_on_empty_payload_delists_nothing():
    """A failed fetch (greenhouse/lever/ashby return [] on non-200) must look
    identical, here, to a genuinely empty board — either way, no signal."""
    db = _db()
    _job(db, "remoteok", "1")

    _sweep_delisted(db, "remoteok", [])
    db.commit()

    assert db.query(models.Job).filter_by(external_id="1").one().delisted_at is None


def test_sweep_tolerates_a_payload_entry_missing_external_id():
    """A malformed/partial payload entry (no external_id) must never raise,
    and must never be the reason something gets delisted — it can't be
    matched to any stored row, so it's dropped from the comparison rather
    than landing a bare None in the NOT IN set (which would make every row's
    comparison NULL instead of a real id check)."""
    db = _db()
    _job(db, "remoteok", "1")
    _job(db, "remoteok", "2")

    # "1" is genuinely still present; the malformed entry carries no id at all.
    _sweep_delisted(db, "remoteok", [{"source": "remoteok", "title": "no id here"},
                                      _payload("remoteok", "1")])
    db.commit()

    assert db.query(models.Job).filter_by(external_id="1").one().delisted_at is None
    assert db.query(models.Job).filter_by(external_id="2").one().delisted_at is not None


def test_sweep_all_entries_missing_external_id_delists_nothing():
    """If nothing in this run's payload carries an external_id at all, there is
    no id to compare against — treat it exactly like an empty payload."""
    db = _db()
    _job(db, "remoteok", "1")

    _sweep_delisted(db, "remoteok", [{"source": "remoteok", "title": "no id here"}])
    db.commit()

    assert db.query(models.Job).filter_by(external_id="1").one().delisted_at is None


def test_sweep_ignores_non_qualifying_source():
    """remotive/reed only ever return a keyword slice (config.py) — absence
    there means "not in that search", not "gone". Never sweep them, even if
    called by mistake."""
    db = _db()
    _job(db, "remotive", "1")

    _sweep_delisted(db, "remotive", [])  # would look like "empty payload" too, but source itself disqualifies
    db.commit()
    assert db.query(models.Job).filter_by(external_id="1").one().delisted_at is None

    _sweep_delisted(db, "remotive", [_payload("remotive", "999")])  # job "1" absent from this payload
    db.commit()
    assert db.query(models.Job).filter_by(external_id="1").one().delisted_at is None


def test_sweep_delists_a_job_stored_under_its_real_company_name():
    """Pins the Task 4 integration: `company` holds a real display name, not
    the board token, and the sweep must not care — it never filters on
    company at all."""
    db = _db()
    _job(db, "greenhouse", "1", company="Okta")   # absent this run
    _job(db, "greenhouse", "2", company="Okta")   # re-seen this run

    _sweep_delisted(db, "greenhouse", [_payload("greenhouse", "2", company="Okta")])
    db.commit()

    assert db.query(models.Job).filter_by(external_id="1").one().delisted_at is not None
    assert db.query(models.Job).filter_by(external_id="2").one().delisted_at is None


# ---------- _fetch_ats_source: combining per-token fetches safely ----------

def test_fetch_ats_source_combines_every_tokens_jobs():
    def fetcher(token):
        return [{"source": "greenhouse", "external_id": f"{token}-1", "title": "Product Manager",
                  "company": token, "location": None}]

    jobs, trustworthy = _fetch_ats_source(fetcher, ["okta", "druva"], ["product manager"])

    assert trustworthy is True
    assert {j["external_id"] for j in jobs} == {"okta-1", "druva-1"}


def test_fetch_ats_source_is_untrustworthy_if_any_token_returns_empty():
    """One dead/404 token must not make the whole source's sweep unsafe to
    skip — it makes it unsafe to RUN: without a stable per-token identity on
    the stored row (Task 4 removed it), a source-wide sweep using only the
    tokens that did respond would wrongly delist the failed token's jobs
    too. So the whole source is marked untrustworthy and the caller must not
    sweep with these jobs this run."""
    def fetcher(token):
        return [] if token == "druva" else [
            {"source": "greenhouse", "external_id": f"{token}-1", "title": "Product Manager",
             "company": token, "location": None}
        ]

    jobs, trustworthy = _fetch_ats_source(fetcher, ["okta", "druva"], ["product manager"])

    assert trustworthy is False
    assert {j["external_id"] for j in jobs} == {"okta-1"}  # still collected, just not safe to sweep with


# ---------- wiring: discover_jobs_task actually calls the sweep ----------

@patch("workers.jobs.get_redis_connection")
@patch("workers.jobs.session_scope")
def test_discover_jobs_task_sweeps_delisted_jobs_end_to_end(mock_session_scope, mock_get_redis):
    """Both okta and druva succeed this run (trustworthy), so the combined,
    source-wide sweep runs: okta's missing job gets delisted, okta's re-seen
    job and druva's job (different company, real display names, not tokens)
    both survive untouched."""
    from workers import jobs as worker_jobs

    db = _db()
    _job(db, "greenhouse", "1", company="Okta")       # will be absent this run -> delisted
    _job(db, "greenhouse", "5", company="Okta")        # re-seen this run -> stays listed
    _job(db, "greenhouse", "2", company="Druva")       # different company, must survive untouched
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
def test_discover_jobs_task_skips_the_whole_sources_sweep_when_one_token_fetch_is_empty(
    mock_session_scope, mock_get_redis
):
    """druva's board returns nothing this run (a dead board, or a config.py
    token with no real signal either way — the two are indistinguishable).
    Without a stable per-token key, the whole greenhouse source must be
    skipped for delisting this run: okta's genuinely-absent job must NOT be
    delisted, because sweeping with only okta's+druva's(empty) combined ids
    would be sweeping on an untrustworthy fetch."""
    from workers import jobs as worker_jobs

    db = _db()
    _job(db, "greenhouse", "1", company="Okta")   # genuinely absent this run, but must NOT be delisted
    mock_session_scope.return_value.__enter__.return_value = db
    mock_session_scope.return_value.__exit__.return_value = False
    mock_get_redis.return_value = MagicMock()

    def _fetch_greenhouse(token):
        # okta succeeds (and no longer lists job "1" -- it looks gone); druva fails outright.
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
        patch("workers.jobs.fetch_enabled_feeds", return_value=([], {})),
        patch("connectors.pipeline.embed_texts", return_value=None),
    ]
    for p in patches:
        p.start()
    try:
        worker_jobs.discover_jobs_task()
    finally:
        for p in patches:
            p.stop()

    assert db.query(models.Job).filter_by(external_id="1").one().delisted_at is None
