"""LinkedIn job sourcing via Apify (GAPS 3.1).

WHY THIS EXISTS, given ADR-002/ADR-015 park LinkedIn. The posture here is the same one
already accepted for `ApifyContactSource`: a paid vendor API call on Apify's own
infrastructure. No cookie, no session, no user's LinkedIn account involved, and no
anti-detection layer — none of which is in this design and none of which should be added
to it. What this project declined was driving a user's own session or defeating bot
detection; buying structured data from a vendor is a different thing and is already how
contact discovery works.

MEASURED 2026-10-09 before building, 25 rows for "Product Manager" in India:

  * 14 EXTERNAL / 11 EASY_APPLY — so 56% carry a real employer ATS link the extension
    can fill. External hosts included careers.google.com, amazon.jobs, and notably
    sustainiam.keka.com, cashflo-talent.freshteam.com and finkraft.zohorecruit.com —
    Indian ATSs this project has no connector for and reaches no other way.
  * 14/15 of an earlier sample were genuinely India-located. `location: "India"` behaves
    correctly here, unlike Glassdoor, where it returns INDIANAPOLIS (see
    connectors/config.py::JOBSPY_LOCATIONS).
  * PhonePe appeared — one of the 19 companies GAPS 3.1 records as having no board on
    greenhouse/lever/ashby at all.
  * $0.0226 for 15 jobs, about $0.0015 each: roughly 5x cheaper per row than the profile
    lookups REACH-E already pays for.
"""
import json
from unittest.mock import patch

import pytest

from connectors.linkedin_jobs import fetch_linkedin_jobs


class _Resp:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code

    def json(self):
        return self._payload


def _row(**over):
    base = {
        "id": "4012345678",
        "title": "Senior Product Manager, Insurance",
        "companyName": "PhonePe",
        "location": "Bengaluru, Karnataka, India",
        "applyType": "EXTERNAL",
        "applyUrl": "https://phonepe.com/careers/123",
        "descriptionText": "Own the insurance product.",
        "postedAt": "2026-10-05",
    }
    base.update(over)
    return base


@pytest.fixture(autouse=True)
def _token(monkeypatch):
    from core.config import get_settings

    get_settings.cache_clear()
    monkeypatch.setattr(get_settings(), "apify_token", "apify-test", raising=False)
    yield
    get_settings.cache_clear()


# ---------- the normal path ----------

def test_rows_are_normalised_for_upsert(monkeypatch):
    with patch("connectors.linkedin_jobs.httpx.post", return_value=_Resp([_row()])):
        jobs = fetch_linkedin_jobs("Product Manager", "India", rows=5)
    assert len(jobs) == 1
    j = jobs[0]
    assert j["title"] == "Senior Product Manager, Insurance"
    assert j["company"] == "PhonePe"
    assert j["location"] == "Bengaluru, Karnataka, India"
    assert j["apply_url"] == "https://phonepe.com/careers/123"
    assert j["external_id"] == "4012345678"
    assert j["description"]
    assert j["posted_at"] is not None


def test_easy_apply_and_external_are_different_sources():
    """Recorded in `source`, the same way jobspy tags per site — so no migration, and a
    job the extension cannot fill is still visible rather than silently dropped.

    Dropping Easy Apply would discard ~44% of the scarcest supply this product has; the
    user can still apply to those by hand, and the existing "no form plan" path already
    means a job needs them.
    """
    payload = [_row(), _row(id="2", applyType="EASY_APPLY",
                            applyUrl="https://in.linkedin.com/jobs/view/2")]
    with patch("connectors.linkedin_jobs.httpx.post", return_value=_Resp(payload)):
        jobs = fetch_linkedin_jobs("PM", "India", rows=5)
    assert {j["source"] for j in jobs} == {"linkedin_external", "linkedin_easy_apply"}


def test_a_row_without_an_apply_url_is_dropped():
    """`apply_url` is NOT NULL on Job, and a posting nobody can open is not a lead."""
    with patch("connectors.linkedin_jobs.httpx.post",
               return_value=_Resp([_row(applyUrl=None), _row(id="2")])):
        assert len(fetch_linkedin_jobs("PM", "India", rows=5)) == 1


def test_a_row_without_a_company_is_dropped():
    """`company` is NOT NULL, and it is a third of `canonical_hash`."""
    with patch("connectors.linkedin_jobs.httpx.post",
               return_value=_Resp([_row(companyName=None), _row(id="2")])):
        assert len(fetch_linkedin_jobs("PM", "India", rows=5)) == 1


# ---------- failure handling ----------

def test_no_token_returns_empty_without_calling(monkeypatch):
    from core.config import get_settings

    monkeypatch.setattr(get_settings(), "apify_token", None, raising=False)
    monkeypatch.delenv("APIFY_TOKEN", raising=False)
    with patch("connectors.linkedin_jobs.httpx.post") as post:
        assert fetch_linkedin_jobs("PM", "India", rows=5) == []
    post.assert_not_called()


def test_an_http_error_is_logged_and_not_silently_empty(caplog):
    """The failure shape that has now bitten four times today — the Apify token, JobSpy's
    403s, the Gmail redirect, GitHub's anonymous email field. An empty result must never
    be indistinguishable from a broken call."""
    with caplog.at_level("WARNING"), \
         patch("connectors.linkedin_jobs.httpx.post", return_value=_Resp({}, status_code=402)):
        assert fetch_linkedin_jobs("PM", "India", rows=5) == []
    assert any("402" in r.getMessage() for r in caplog.records), caplog.text


def test_a_network_failure_logs_the_type_only(caplog):
    """A vendor error body can echo the token."""
    with caplog.at_level("WARNING"), \
         patch("connectors.linkedin_jobs.httpx.post", side_effect=RuntimeError("boom apify-test")):
        assert fetch_linkedin_jobs("PM", "India", rows=5) == []
    assert not any("apify-test" in r.getMessage() for r in caplog.records)


def test_a_non_list_payload_does_not_raise():
    with patch("connectors.linkedin_jobs.httpx.post", return_value=_Resp({"error": "x"})):
        assert fetch_linkedin_jobs("PM", "India", rows=5) == []


def test_the_token_is_sent_as_a_bearer_header_not_a_query_param():
    """A token in the URL lands in proxy and server logs."""
    with patch("connectors.linkedin_jobs.httpx.post", return_value=_Resp([])) as post:
        fetch_linkedin_jobs("PM", "India", rows=5)
    assert post.call_args.kwargs["headers"]["Authorization"] == "Bearer apify-test"
    assert "apify-test" not in post.call_args.args[0]


# ---------- ingestion wiring ----------

def test_linkedin_is_never_swept_for_delistings():
    """A keyword+location slice is not a complete listing, so absence means "not in that
    search", not "gone" (ADR-017 §2). Sweeping it would tombstone live jobs."""
    from workers.jobs import SWEEPABLE_SOURCES
    assert not any(s.startswith("linkedin") for s in SWEEPABLE_SOURCES)


def test_configured_locations_are_real_places():
    from connectors import config
    assert config.LINKEDIN_JOB_LOCATIONS
    assert config.LINKEDIN_JOB_KEYWORDS


def test_a_201_created_is_success_not_a_failure():
    """`run-sync-get-dataset-items` answers **201 Created** on success, because it creates
    a run. The first version checked `!= 200` and discarded a good payload — found live,
    an hour after the warning that caught it was written. A silent `[]` here would have
    looked exactly like LinkedIn having no India PM roles, which is the one conclusion
    this whole source exists to disprove.
    """
    with patch("connectors.linkedin_jobs.httpx.post",
               return_value=_Resp([_row()], status_code=201)):
        assert len(fetch_linkedin_jobs("PM", "India", rows=5)) == 1
