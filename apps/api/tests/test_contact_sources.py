"""REACH-B — the `ContactSource` interface and its two credential-free adapters.

Measured 2026-10-09 before writing this, because the adapter is only worth having
if the yield is real (`docs/PLAN-OUTREACH.md`):

| org      | public org members | member has a public email | bio names product/head |
|----------|--------------------|---------------------------|------------------------|
| razorpay | 25                 | 12                        | 1                      |
| zerodha  | 14                 | 7                         | 0                      |
| meesho   | 2                  | -                         | -                      |
| Swiggy   | 0                  | -                         | -                      |

So GitHub is a genuinely good source for ENGINEERS — roughly half of the people it
exposes publish an address themselves, no vendor and no guessing — and a bad one for
product roles: one product-adjacent person across 39. `GitHubContactSource` is therefore
tried first and expected to return nothing for a PM search, which is not a failure and
must not be treated as one.
"""
import json
from unittest.mock import patch

import pytest


@pytest.fixture(autouse=True)
def _github_token(monkeypatch):
    """A token for every test here, because `GitHubContactSource` now refuses to spend a
    request without one — GitHub omits the email field on anonymous requests, so a
    tokenless lookup can only ever return nobody. The test that asserts THAT behaviour
    clears it again."""
    monkeypatch.setenv("GITHUB_TOKEN", "ghp-test-token")
    yield


# ---------- the interface ----------

def test_contact_candidate_requires_a_name_and_company():
    from outreach.contacts import ContactCandidate
    c = ContactCandidate(full_name="Asha Rao", company="Acme", title="Product Manager")
    assert c.email is None, "a candidate is useful before an address is known"
    assert c.source == "unknown", "every candidate records where it came from"


def test_sources_all_satisfy_the_same_interface():
    """A new adapter must be droppable in without the engine changing."""
    from outreach.contacts import GitHubContactSource, ManualContactSource
    for src in (ManualContactSource(), GitHubContactSource()):
        assert callable(getattr(src, "find", None))
        assert isinstance(src.name, str) and src.name


# ---------- ManualContactSource ----------

def test_manual_source_returns_what_it_was_given():
    from outreach.contacts import ContactCandidate, ManualContactSource
    given = [ContactCandidate(full_name="Asha Rao", company="Acme", email="a@acme.com")]
    got = ManualContactSource(given).find(company="Acme", titles=["Product Manager"], limit=5)
    assert [c.full_name for c in got] == ["Asha Rao"]
    assert got[0].source == "manual"


def test_manual_source_filters_by_company():
    """The engine asks per application, so a candidate for another company must not leak."""
    from outreach.contacts import ContactCandidate, ManualContactSource
    given = [
        ContactCandidate(full_name="Asha Rao", company="Acme"),
        ContactCandidate(full_name="Ben Shah", company="Globex"),
    ]
    got = ManualContactSource(given).find(company="acme", titles=[], limit=5)
    assert [c.full_name for c in got] == ["Asha Rao"], "company match is case-insensitive"


def test_manual_source_respects_limit():
    from outreach.contacts import ContactCandidate, ManualContactSource
    given = [ContactCandidate(full_name=f"P{i}", company="Acme") for i in range(5)]
    assert len(ManualContactSource(given).find(company="Acme", titles=[], limit=2)) == 2


# ---------- GitHubContactSource ----------

def _gh(payloads, status=200):
    """Fake `api.github.com`, one queued JSON body per call.

    DEPLOY-A.2: this used to fake `subprocess.run` because the adapter shelled out to the
    `gh` CLI. It now speaks HTTP, which removed a runtime dependency a container does not
    have — see `GitHubContactSource._gh_json`. Bodies stay JSON strings so the test
    expectations below did not have to change.
    """
    calls = iter(payloads)

    def get(url, *a, **kw):
        body = next(calls)

        class R:
            status_code = status

            def json(self):
                return json.loads(body)
        return R()
    return get


def test_github_source_returns_members_with_a_public_email():
    from outreach.contacts import GitHubContactSource
    members = '[{"login": "asha"}, {"login": "ben"}]'
    asha = '{"login": "asha", "name": "Asha Rao", "email": "asha@acme.com", "bio": "Staff Engineer"}'
    ben = '{"login": "ben", "name": "Ben Shah", "email": null, "bio": "Engineer"}'
    with patch("outreach.contacts.httpx.get", _gh([members, asha, ben])):
        got = GitHubContactSource().find(company="acme", titles=[], limit=5)
    assert [c.email for c in got] == ["asha@acme.com"], "a null email yields no candidate"
    assert got[0].source == "github"
    assert got[0].full_name == "Asha Rao"


def test_github_source_returns_empty_when_org_has_no_public_members():
    """Measured: Swiggy exposes 0. Empty is a normal answer, not an error."""
    from outreach.contacts import GitHubContactSource
    with patch("outreach.contacts.httpx.get", _gh(["[]"])):
        assert GitHubContactSource().find(company="swiggy", titles=[], limit=5) == []


def test_github_source_survives_a_missing_org():
    """GitHub answers 404 for an org that does not exist. Expected and quiet: the slug is
    guessed from a company name, so misses are the common case, not an error."""
    from outreach.contacts import GitHubContactSource

    with patch("outreach.contacts.httpx.get", _gh(["{}"], status=404)):
        assert GitHubContactSource().find(company="nosuchco", titles=[], limit=5) == []


def test_a_rate_limited_lookup_is_logged_and_not_an_empty_result(caplog):
    """DEPLOY-A.2's whole point. A 403 from the rate limiter is NOT "nobody there", and
    conflating the two is what would have made a tokenless container look like every
    company having no public members — the measured normal case for a product role."""
    from outreach.contacts import GitHubContactSource

    with caplog.at_level("WARNING"),          patch("outreach.contacts.httpx.get", _gh(["{}"], status=403)):
        assert GitHubContactSource().find(company="acme", titles=[], limit=5) == []
    assert any("not an empty result" in r.getMessage() for r in caplog.records), caplog.text


def test_a_token_is_sent_when_configured(monkeypatch):
    """Anonymous works at 60 req/hour; a token raises it to 5,000."""
    from outreach.contacts import GitHubContactSource

    monkeypatch.setenv("GITHUB_TOKEN", "ghp-test")
    seen = {}

    def get(url, *a, **kw):
        seen.update(kw.get("headers") or {})

        class R:
            status_code = 200

            def json(self):
                return []
        return R()
    with patch("outreach.contacts.httpx.get", get):
        GitHubContactSource().find(company="acme", titles=[], limit=2)
    assert seen.get("Authorization") == "Bearer ghp-test"


def test_github_source_survives_unparseable_output():
    from outreach.contacts import GitHubContactSource
    with patch("outreach.contacts.httpx.get", _gh(["not json"])):
        assert GitHubContactSource().find(company="acme", titles=[], limit=5) == []


def test_github_source_prefers_a_title_match_but_does_not_require_one():
    """GitHub has no title field, only a freeform bio. A bio hit ranks first; a miss is
    still returned, because discarding a reachable engineer over a blank bio would throw
    away most of the measured yield."""
    from outreach.contacts import GitHubContactSource
    members = '[{"login": "eng"}, {"login": "pm"}]'
    eng = '{"login": "eng", "name": "E Eng", "email": "e@acme.com", "bio": "Backend engineer"}'
    pm = '{"login": "pm", "name": "P Prod", "email": "p@acme.com", "bio": "Head of Product"}'
    with patch("outreach.contacts.httpx.get", _gh([members, eng, pm])):
        got = GitHubContactSource().find(company="acme", titles=["Product Manager"], limit=5)
    assert [c.full_name for c in got] == ["P Prod", "E Eng"], "bio match ranks first"
    assert len(got) == 2, "a non-matching bio is still a usable contact"


def test_github_source_ordering_is_deterministic():
    """GAPS 6.6 was a real nondeterminism bug from ranking with no tiebreaker. With
    auto-send on, the tiebreaker decides who receives mail."""
    from outreach.contacts import GitHubContactSource
    members = '[{"login": "b"}, {"login": "a"}]'
    b = '{"login": "b", "name": "B", "email": "b@acme.com", "bio": ""}'
    a = '{"login": "a", "name": "A", "email": "a@acme.com", "bio": ""}'
    with patch("outreach.contacts.httpx.get", _gh([members, b, a])):
        first = GitHubContactSource().find(company="acme", titles=[], limit=5)
    with patch("outreach.contacts.httpx.get", _gh([members, b, a])):
        second = GitHubContactSource().find(company="acme", titles=[], limit=5)
    assert [c.full_name for c in first] == [c.full_name for c in second]
    assert [c.full_name for c in first] == ["A", "B"], "equal bios fall back to a stable key"


def test_github_source_never_returns_a_noreply_address():
    """`@users.noreply.github.com` is deliverable to nobody. Measured as 3 of 11 distinct
    committer domains for razorpay and 4 of 9 for meesho, so this is the common case."""
    from outreach.contacts import GitHubContactSource
    members = '[{"login": "x"}]'
    x = '{"login": "x", "name": "X", "email": "1+x@users.noreply.github.com", "bio": ""}'
    with patch("outreach.contacts.httpx.get", _gh([members, x])):
        assert GitHubContactSource().find(company="acme", titles=[], limit=5) == []


def test_github_source_falls_back_to_login_when_name_is_null():
    from outreach.contacts import GitHubContactSource
    members = '[{"login": "asha"}]'
    asha = '{"login": "asha", "name": null, "email": "a@acme.com", "bio": ""}'
    with patch("outreach.contacts.httpx.get", _gh([members, asha])):
        got = GitHubContactSource().find(company="acme", titles=[], limit=5)
    assert got[0].full_name == "asha"


def test_github_source_stops_at_limit_without_fetching_more_profiles():
    """One `gh api users/{login}` call per member is the cost here, so the limit must cut
    the profile fetches, not just the returned list."""
    from outreach.contacts import GitHubContactSource
    members = '[{"login": "a"}, {"login": "b"}, {"login": "c"}]'
    prof = '{"login": "a", "name": "A", "email": "a@acme.com", "bio": ""}'
    calls = []

    def counting(url, *a, **kw):
        calls.append(url)

        class R:
            status_code = 200

            def json(self):
                return json.loads(members if len(calls) == 1 else prof)
        return R()
    with patch("outreach.contacts.httpx.get", counting):
        GitHubContactSource(max_profile_lookups=2).find(company="acme", titles=[], limit=1)
    assert len(calls) <= 3, "1 member list + at most max_profile_lookups profile calls"


def test_no_github_token_is_reported_not_silently_empty(monkeypatch, caplog):
    """MEASURED 2026-10-09: anonymously `GET /users/{login}` returns `email: None` for
    EVERY user, including those who publish one — the field is only populated on
    authenticated requests. So without a token this adapter finds nobody, every time.

    The engine reads an empty list as "nobody found", which is indistinguishable from a
    company genuinely having no public members — the measured normal case for a product
    role. Third time today that shape of bug appeared (the Apify token, JobSpy's 403s,
    this), hence a test rather than a comment.

    The 12-of-25 razorpay figure quoted elsewhere was taken through an AUTHENTICATED
    `gh`, not anonymously.
    """
    from core.config import get_settings
    from outreach.contacts import GitHubContactSource

    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.delenv("GH_TOKEN", raising=False)
    get_settings.cache_clear()
    monkeypatch.setattr(get_settings(), "github_token", None, raising=False)

    with caplog.at_level("WARNING"), patch("outreach.contacts.httpx.get") as get:
        assert GitHubContactSource().find(company="razorpay", titles=["PM"], limit=2) == []
    get.assert_not_called(), "no point spending a request that cannot return an address"
    assert any("not an empty company" in r.getMessage() for r in caplog.records), caplog.text
    get_settings.cache_clear()
