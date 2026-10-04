"""COLLECT-D — `Job.board_token`, so delisting is scoped per board instead of
per source.

The problem this closes (ADR-017 consequences, documented at the token lists in
`connectors/config.py`): the sweep was source-wide because nothing on the row
identified which board a job came from. Two consequences, both bad:

1. **Removing a token from config tombstoned that board's entire live
   inventory** on the next run. Editing config was a destructive data operation.
2. **One flaky board blocked delisting for the whole source.** `_fetch_ats_source`
   marked the source untrustworthy if *any* token returned empty, because an
   empty token's rows would otherwise look absent from the combined id set.

`Job.company` cannot do this job — Phase 1 made it a curated display name whose
formatting legitimately varies ("Rubrik Job Board", a trailing space), and a
mismatch there silently sweeps nothing.

Sources with no per-board concept (jobicy) keep `board_token = NULL` and are
swept by source, scoped to the NULL rows.
"""
from datetime import datetime

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import models
from connectors.normalize import canonical_hash
from database import Base
from workers.jobs import _fetch_ats_source, _sweep_delisted


def _db():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False},
                           poolclass=StaticPool)
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def _job(db, source, external_id, board_token, company="Acme", delisted_at=None):
    title = f"Job {external_id}"
    db.add(models.Job(
        source=source, external_id=external_id, board_token=board_token,
        company=company, title=title, canonical_hash=canonical_hash(company, title, None),
        apply_url=f"https://x/{external_id}", delisted_at=delisted_at,
    ))
    db.commit()


def _payload(external_id):
    return {"external_id": external_id, "title": "t", "company": "Acme"}


def _listed(db, external_id):
    row = db.query(models.Job).filter(models.Job.external_id == external_id).one()
    return row.delisted_at is None


# --- the two consequences this stage closes ----------------------------------

def test_removing_a_token_from_config_no_longer_tombstones_its_board():
    """The whole point. `okta` is no longer configured, so this run has no okta
    payload at all — its jobs must survive, because "we stopped asking" is not
    "the employer closed the role"."""
    db = _db()
    _job(db, "greenhouse", "gh-okta-1", "okta")
    _job(db, "greenhouse", "gh-druva-1", "druva")

    # Only druva is still configured, so only druva is swept.
    _sweep_delisted(db, "greenhouse", "druva", [_payload("gh-druva-1")])
    db.commit()

    assert _listed(db, "gh-okta-1"), "a removed token's jobs must not be tombstoned"
    assert _listed(db, "gh-druva-1")


def test_a_flaky_board_no_longer_blocks_delisting_for_the_whole_source():
    """druva answered and dropped a job; okta returned nothing this run. The
    druva delisting must still happen, and okta must be left alone."""
    db = _db()
    _job(db, "greenhouse", "gh-okta-1", "okta")
    _job(db, "greenhouse", "gh-druva-gone", "druva")
    _job(db, "greenhouse", "gh-druva-live", "druva")

    _sweep_delisted(db, "greenhouse", "druva", [_payload("gh-druva-live")])
    db.commit()

    assert not _listed(db, "gh-druva-gone"), "druva answered, so its absence is real"
    assert _listed(db, "gh-druva-live")
    assert _listed(db, "gh-okta-1"), "okta returned nothing; its rows are no signal"


def test_fetch_ats_source_reports_one_batch_per_token_that_answered():
    """Trust is per token now, not all-or-nothing for the source. An empty token
    contributes no batch at all, so nothing of its can be swept."""
    boards = {"okta": [], "druva": [{"title": "Product Manager", "external_id": "d1"}]}
    jobs, batches = _fetch_ats_source(lambda t: boards[t], ["okta", "druva"], ["product manager"])

    assert [t for t, _ in batches] == ["druva"]
    assert [j["external_id"] for j in jobs] == ["d1"]


def test_trust_is_still_judged_before_keyword_filtering():
    """A board that answered but has no matching title is a working fetch, not a
    dead one — otherwise every board needs an open PM role in the same run or
    nothing is ever delisted (the latest+57 bug)."""
    boards = {"druva": [{"title": "Software Engineer", "external_id": "d9"}]}
    jobs, batches = _fetch_ats_source(lambda t: boards[t], ["druva"], ["product manager"])

    assert jobs == []
    assert [t for t, _ in batches] == ["druva"], "answered-but-filtered-out is still trustworthy"


# --- safety rails -------------------------------------------------------------

def test_rows_with_no_board_token_are_never_swept_by_a_token_sweep():
    """Rows stored before this migration have board_token NULL. A token-scoped
    sweep must not touch them: it cannot tell whether they came from the board
    it is sweeping. They become sweepable once upsert_jobs refreshes them."""
    db = _db()
    _job(db, "greenhouse", "gh-legacy", None)

    _sweep_delisted(db, "greenhouse", "druva", [_payload("gh-druva-1")])
    db.commit()

    assert _listed(db, "gh-legacy")


def test_a_tokenless_source_is_swept_by_source_over_its_null_rows():
    """jobicy has no per-board concept; it is a single complete listing."""
    db = _db()
    _job(db, "jobicy", "j-gone", None)
    _job(db, "jobicy", "j-live", None)

    _sweep_delisted(db, "jobicy", None, [_payload("j-live")])
    db.commit()

    assert not _listed(db, "j-gone")
    assert _listed(db, "j-live")


def test_an_empty_payload_still_delists_nothing():
    """ADR-017 §3 — an empty fetch is no signal, never "the board is empty"."""
    db = _db()
    _job(db, "greenhouse", "gh-1", "druva")

    _sweep_delisted(db, "greenhouse", "druva", [])
    db.commit()

    assert _listed(db, "gh-1")


def test_a_non_sweepable_source_is_still_a_no_op():
    db = _db()
    _job(db, "remotive", "r-1", None)

    _sweep_delisted(db, "remotive", None, [_payload("r-other")])
    db.commit()

    assert _listed(db, "r-1")


def test_one_boards_sweep_cannot_reach_another_sources_rows():
    db = _db()
    _job(db, "lever", "lv-1", "druva")   # same token name, different source
    _job(db, "greenhouse", "gh-1", "druva")

    _sweep_delisted(db, "greenhouse", "druva", [_payload("gh-other")])
    db.commit()

    assert _listed(db, "lv-1"), "the sweep is scoped to its own source"
    assert not _listed(db, "gh-1")


# --- the column gets written ---------------------------------------------------

def test_the_ats_connectors_stamp_the_board_token():
    """Without this the column is always NULL and nothing above works."""
    from unittest.mock import MagicMock, patch

    import httpx

    def resp(payload):
        r = MagicMock(spec=httpx.Response)
        r.status_code = 200
        r.json.return_value = payload
        return r

    from connectors import ashby, greenhouse, lever

    with patch("connectors.greenhouse.httpx.get",
               return_value=resp({"jobs": [{"id": 1, "title": "PM", "absolute_url": "u"}]})):
        assert greenhouse.fetch_greenhouse_jobs("druva")[0]["board_token"] == "druva"

    with patch("connectors.lever.httpx.get",
               return_value=resp([{"id": "a", "text": "PM", "hostedUrl": "u"}])):
        assert lever.fetch_lever_jobs("meesho")[0]["board_token"] == "meesho"

    with patch("connectors.ashby.httpx.get",
               return_value=resp({"jobs": [{"id": "b", "title": "PM", "jobUrl": "u"}]})):
        assert ashby.fetch_ashby_jobs("sarvam")[0]["board_token"] == "sarvam"


def test_upsert_backfills_the_board_token_on_a_re_seen_row():
    """Pre-migration rows carry NULL. They must pick the token up the next time
    the board lists them, otherwise they stay permanently unsweepable."""
    from connectors.pipeline import upsert_jobs

    db = _db()
    _job(db, "greenhouse", "gh-legacy", None)

    with_token = {
        "source": "greenhouse", "external_id": "gh-legacy", "board_token": "druva",
        "title": "Job gh-legacy", "company": "Acme", "apply_url": "https://x/1",
        "canonical_hash": canonical_hash("Acme", "Job gh-legacy", None),
    }
    upsert_jobs(db, [with_token])

    db.expire_all()
    row = db.query(models.Job).filter(models.Job.external_id == "gh-legacy").one()
    assert row.board_token == "druva"
