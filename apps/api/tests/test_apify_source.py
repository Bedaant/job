"""REACH-E — `ApifyContactSource` (`docs/PLAN-OUTREACH.md`).

Mostly mocked, and the distinction matters for what these tests prove. The request shape
and the failure handling are verified here; the OUTPUT field mapping was originally only
as good as the actor's published documentation.

**Confirmed live 2026-10-09** against a real token: a Razorpay / "Product Manager" query
returned 2 candidates in 16.2s with `full_name`, `title`, `email`, `location`,
`source_ref` and — importantly for `outreach/signals.py` — 8 and 9 `past_companies` plus
1 and 2 `schools` each. So `former_employer` and `same_university` ARE reachable through
this adapter, which is the whole reason it exists alongside the free GitHub one.
"""
from unittest.mock import patch

import httpx
import pytest

from outreach.sources_apify import ApifyContactSource


@pytest.fixture()
def no_apify_token(monkeypatch):
    """Isolate from a REAL configured token.

    `patch.dict("os.environ", clear=True)` is NOT sufficient: `_resolve_token` also
    consults Settings, which loads `apps/api/.env`. Without this, a test asserting
    "unconfigured" behaviour makes a live, billable Apify call on any machine where the
    token is set — which is exactly what happened the first time one was.
    """
    from core.config import get_settings

    monkeypatch.delenv("APIFY_TOKEN", raising=False)
    get_settings.cache_clear()
    monkeypatch.setattr(get_settings(), "apify_token", None, raising=False)
    yield
    get_settings.cache_clear()


class _Resp:
    def __init__(self, payload, status_code=201):
        self._payload = payload
        self.status_code = status_code

    def json(self):
        if isinstance(self._payload, Exception):
            raise self._payload
        return self._payload


def _src():
    return ApifyContactSource(token="t-test")


def _profile(**over):
    item = {
        "id": "abc123",
        "publicIdentifier": "asha-rao",
        "firstName": "Asha",
        "lastName": "Rao",
        "headline": "Product Manager at Acme",
        "location": "Bengaluru, India",
        "email": "asha@acme.com",
        "experience": [
            {"companyName": "Acme"},
            {"companyName": "Flipkart"},
        ],
        "education": [{"schoolName": "VIT Vellore"}],
    }
    item.update(over)
    return item


# ---------- not configured ----------

def test_no_token_returns_empty_and_makes_no_request(no_apify_token):
    """Not configured is not an error — the Reed connector and the embedding pipeline
    no-op the same way without their keys."""
    with patch("httpx.post") as post:
        assert ApifyContactSource().find(company="Acme", titles=["PM"], limit=2) == []
    post.assert_not_called()


def test_token_from_the_environment_is_used(no_apify_token, monkeypatch):
    """The raw-env fallback, for a deployment that injects the token instead of using a
    `.env` file. The fixture blanks the Settings source first, so this proves the
    fallback rather than accidentally reading the configured token."""
    monkeypatch.setenv("APIFY_TOKEN", "env-token")
    with patch("httpx.post", return_value=_Resp([])) as post:
        ApifyContactSource().find(company="Acme", titles=[], limit=2)
    assert post.call_args.kwargs["headers"]["Authorization"] == "Bearer env-token"


def test_token_from_dotenv_settings_is_preferred(no_apify_token, monkeypatch):
    """Where the owner actually puts it. Every other credential in this project lives in
    `apps/api/.env`, so Settings is the PRIMARY source and the env var is the fallback —
    the original implementation read only `os.environ`, so a token in `.env` was reachable
    by neither path and the adapter silently reported "no candidates"."""
    from core.config import get_settings

    monkeypatch.setenv("APIFY_TOKEN", "env-token")
    monkeypatch.setattr(get_settings(), "apify_token", "dotenv-token", raising=False)
    with patch("httpx.post", return_value=_Resp([])) as post:
        ApifyContactSource().find(company="Acme", titles=[], limit=2)
    assert post.call_args.kwargs["headers"]["Authorization"] == "Bearer dotenv-token"


def test_a_blank_company_makes_no_request():
    with patch("httpx.post") as post:
        assert _src().find(company="   ", titles=["PM"], limit=2) == []
    post.assert_not_called()


def test_a_zero_limit_makes_no_request():
    """The engine computes `limit` from `profile.outreach_contacts_per_application`, so a
    zero must not become an unbounded, billable search."""
    with patch("httpx.post") as post:
        assert _src().find(company="Acme", titles=["PM"], limit=0) == []
    post.assert_not_called()


# ---------- the request ----------

def test_the_request_is_a_narrow_lookup_not_a_harvest():
    with patch("httpx.post", return_value=_Resp([])) as post:
        _src().find(company="Acme", titles=["Product Manager"], limit=2)
    body = post.call_args.kwargs["json"]
    assert body["currentCompanies"] == ["Acme"]
    assert body["currentJobTitles"] == ["Product Manager"]
    assert body["maxItems"] == 2, "the limit is sent to the actor, not just applied after"
    assert body["profileScraperMode"] == "Full + email search"


def test_no_titles_means_the_title_filter_is_omitted_entirely():
    """Sending an empty list could be read as "match nothing" rather than "no filter"."""
    with patch("httpx.post", return_value=_Resp([])) as post:
        _src().find(company="Acme", titles=["", "  "], limit=2)
    assert "currentJobTitles" not in post.call_args.kwargs["json"]


def test_the_actor_run_is_time_capped_server_side():
    """Bounded timeout: the cap is passed to Apify so the run stops and stops billing,
    rather than relying on a local disconnect that leaves it going."""
    with patch("httpx.post", return_value=_Resp([])) as post:
        _src().find(company="Acme", titles=[], limit=2)
    kwargs = post.call_args.kwargs
    assert kwargs["params"]["timeout"] > 0
    assert kwargs["timeout"] > kwargs["params"]["timeout"], (
        "the client must outwait the server cap so the cap is what fires"
    )


def test_the_cheaper_mode_can_be_selected():
    with patch("httpx.post", return_value=_Resp([])) as post:
        ApifyContactSource(mode="Full", token="t").find(company="Acme", titles=[], limit=1)
    assert post.call_args.kwargs["json"]["profileScraperMode"] == "Full"


# ---------- mapping ----------

def test_a_profile_maps_onto_every_field_the_ranker_needs():
    with patch("httpx.post", return_value=_Resp([_profile()])):
        got = _src().find(company="Acme", titles=["Product Manager"], limit=2)
    assert len(got) == 1
    c = got[0]
    assert c.full_name == "Asha Rao", "firstName and lastName are separate in the output"
    assert c.title == "Product Manager at Acme"
    assert c.email == "asha@acme.com"
    assert c.location == "Bengaluru, India"
    assert c.source == "apify"
    assert c.source_ref == "asha-rao"
    assert c.past_companies == ["Acme", "Flipkart"], "unlocks the former_employer signal"
    assert c.schools == ["VIT Vellore"], "unlocks the same_university signal"


def test_a_nested_location_object_is_handled():
    item = _profile(location={"linkedinText": "Mumbai, Maharashtra, India"})
    with patch("httpx.post", return_value=_Resp([item])):
        got = _src().find(company="Acme", titles=[], limit=2)
    assert got[0].location == "Mumbai, Maharashtra, India"


def test_duplicate_employers_are_deduped_in_order():
    item = _profile(experience=[
        {"companyName": "Flipkart"}, {"companyName": "Acme"}, {"companyName": "Flipkart"},
    ])
    with patch("httpx.post", return_value=_Resp([item])):
        got = _src().find(company="Acme", titles=[], limit=2)
    assert got[0].past_companies == ["Flipkart", "Acme"]


def test_a_profile_with_no_name_is_dropped():
    """There is nowhere to improvise a greeting."""
    item = {"id": "x", "headline": "PM", "email": "x@acme.com"}
    with patch("httpx.post", return_value=_Resp([item])):
        assert _src().find(company="Acme", titles=[], limit=2) == []


def test_non_dict_items_are_skipped_not_fatal():
    with patch("httpx.post", return_value=_Resp(["junk", None, _profile()])):
        assert len(_src().find(company="Acme", titles=[], limit=5)) == 1


# ---------- email is never fabricated ----------

def test_a_profile_without_an_email_is_still_returned_with_email_none():
    """The actor says email search is not guaranteed. A missing address is a normal
    result — the engine's verification gate and the manual fallback handle it."""
    item = _profile()
    del item["email"]
    with patch("httpx.post", return_value=_Resp([item])):
        got = _src().find(company="Acme", titles=[], limit=2)
    assert len(got) == 1
    assert got[0].email is None, "no address must ever be constructed or guessed"
    assert got[0].full_name == "Asha Rao", "the rest of the profile is still useful"


def test_an_email_list_is_read_but_a_blank_one_is_not():
    item = _profile()
    del item["email"]
    item["emails"] = ["", "  ", "real@acme.com"]
    with patch("httpx.post", return_value=_Resp([item])):
        assert _src().find(company="Acme", titles=[], limit=2)[0].email == "real@acme.com"


def test_contactable_candidates_rank_above_unreachable_ones():
    no_mail = _profile(publicIdentifier="a-aaa", firstName="A", lastName="A")
    del no_mail["email"]
    with_mail = _profile(publicIdentifier="z-zzz", firstName="Z", lastName="Z")
    with patch("httpx.post", return_value=_Resp([no_mail, with_mail])):
        got = _src().find(company="Acme", titles=[], limit=5)
    assert [c.full_name for c in got] == ["Z Z", "A A"]


def test_ordering_is_deterministic_regardless_of_dataset_order():
    """Apify promises no dataset ordering. GAPS 6.6 was a real nondeterminism bug from
    ranking with no tiebreaker, and with auto-send on the tiebreaker decides who
    receives mail."""
    a = _profile(publicIdentifier="aaa", firstName="A", lastName="A")
    b = _profile(publicIdentifier="bbb", firstName="B", lastName="B")
    with patch("httpx.post", return_value=_Resp([a, b])):
        first = _src().find(company="Acme", titles=[], limit=5)
    with patch("httpx.post", return_value=_Resp([b, a])):
        second = _src().find(company="Acme", titles=[], limit=5)
    assert [c.source_ref for c in first] == [c.source_ref for c in second] == ["aaa", "bbb"]


def test_more_results_than_asked_for_are_truncated():
    items = [_profile(publicIdentifier=f"p{i}", firstName=f"P{i}") for i in range(5)]
    with patch("httpx.post", return_value=_Resp(items)):
        assert len(_src().find(company="Acme", titles=[], limit=2)) == 2


# ---------- failure handling: never raise, never leak ----------

@pytest.mark.parametrize("payload", [[], None, {}, "not a list"])
def test_an_empty_or_wrong_shaped_response_returns_empty(payload):
    with patch("httpx.post", return_value=_Resp(payload)):
        assert _src().find(company="Acme", titles=[], limit=2) == []


@pytest.mark.parametrize("status", [400, 401, 402, 429, 500, 503])
def test_an_http_error_returns_empty_rather_than_raising(status):
    with patch("httpx.post", return_value=_Resp([_profile()], status_code=status)):
        assert _src().find(company="Acme", titles=[], limit=2) == []


def test_a_timeout_returns_empty_rather_than_raising():
    with patch("httpx.post", side_effect=httpx.ReadTimeout("timed out")):
        assert _src().find(company="Acme", titles=[], limit=2) == []


def test_malformed_json_returns_empty_rather_than_raising():
    with patch("httpx.post", return_value=_Resp(ValueError("not json"))):
        assert _src().find(company="Acme", titles=[], limit=2) == []


def test_only_the_exception_type_is_logged_never_the_token(caplog):
    """A provider's reply can echo the request, and the request carries the bearer token.
    `digest.smtp_sender` and `outreach/send.py` set this precedent."""
    boom = RuntimeError("401 unauthorized for Bearer t-supersecret-token")
    with patch("httpx.post", side_effect=boom), caplog.at_level("WARNING"):
        assert _src().find(company="Acme", titles=[], limit=2) == []
    assert "RuntimeError" in caplog.text
    assert "supersecret" not in caplog.text


def test_one_attempt_only_no_retry_storm():
    with patch("httpx.post", side_effect=RuntimeError("down")) as post:
        _src().find(company="Acme", titles=[], limit=2)
    assert post.call_count == 1
