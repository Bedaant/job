"""Hiring posts on LinkedIn as a job source ("we're hiring — apply here / email your CV").

Same posture as `linkedin_jobs.py`: a vendor API on Apify's infrastructure (`harvestapi/
linkedin-post-search`, $0.002/post). No cookie, no session, no anti-detection layer. Agent-Reach
was checked first and does NOT cover this: its LinkedIn channel wraps a logged-in-session MCP
server and has no post search.

The one rule that matters: **the apply route comes from the post text by regex, never from the
model.** The model only reads title / company / location and confirms the post is an opening.

MEASURED 2026-10-10, 60 live posts from three role-agnostic queries:
  * 58/60 carried an apply route: 39 email-only, 12 link-only, 7 both, 2 neither.
  * 30 of the links were `lnkd.in` shortlinks — LinkedIn's own redirector, opaque until
    resolved, so an email in the same post is the more reliable route.
  * Every post was 0 days old with sortBy=date.
  * Company-page authors have a follower count ("535 followers") where a person has a
    headline, so the author NAME must reach the model too; one author had no headline at all.
  * Roles were everything, not just PM: AI engineer, BA, sales, interpreter, content intern.
"""
import re
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest

from connectors import linkedin_posts
from connectors.linkedin_posts import fetch_linkedin_posts, parse_posts


class _Resp:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code

    def json(self):
        return self._payload


def _recent(days=0):
    return (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%S.000Z")


def _post(**over):
    base = {
        "type": "post",
        "id": "7330988768578920448",
        "linkedinUrl": "https://www.linkedin.com/posts/asha_hiring-activity-7330988768578920448-Je01",
        "content": "We are hiring a Product Manager at Acme in Bengaluru. Apply: https://acme.example/careers/pm-1",
        "author": {"name": "Asha Rao", "info": "Head of Product at Acme",
                   "linkedinUrl": "https://www.linkedin.com/in/asha"},
        "postedAt": {"date": _recent()},
    }
    base.update(over)
    return base


def _facts(**over):
    f = {"is_job_post": True, "title": "Product Manager", "company": "Acme", "location": "Bengaluru"}
    f.update(over)
    return f


class _LLM:
    """Stands in for `_call_claude_structured`: answers every `[n]` block in the prompt.

    `per_index` overrides the answer for one post; `calls` records each batch's prompt."""

    def __init__(self, **per_index):
        self.per_index = per_index
        self.calls = []
        self.raise_on_call = set()

    def __call__(self, system, user, response_model, **kw):
        self.calls.append(user)
        if len(self.calls) - 1 in self.raise_on_call:
            raise RuntimeError("boom secret-text")
        idx = [int(n) for n in re.findall(r"^\[(\d+)\]", user, re.M)]
        return response_model(posts=[
            {"index": i, **self.per_index.get(f"p{i}", _facts())} for i in idx
        ])


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    from core.config import get_settings

    get_settings.cache_clear()
    monkeypatch.setattr(get_settings(), "apify_token", "apify-test", raising=False)
    yield
    get_settings.cache_clear()


@pytest.fixture()
def llm():
    fake = _LLM()
    with patch("connectors.linkedin_posts._call_claude_structured", side_effect=fake):
        yield fake


# ---------- the normal path ----------

def test_a_post_with_an_apply_link_becomes_a_job(llm):
    (j,) = parse_posts([_post()])
    assert j["source"] == "linkedin_post"
    assert j["external_id"] == "7330988768578920448"
    assert j["title"] == "Product Manager" and j["company"] == "Acme"
    assert j["location"] == "Bengaluru"
    assert j["apply_url"] == "https://acme.example/careers/pm-1"
    assert j["posted_at"] is not None


def test_the_description_says_who_posted_it_and_links_the_original(llm):
    """The poster is often the hiring manager or recruiter — the person the user would
    follow up with — and the original post is the source of truth if extraction is off."""
    (j,) = parse_posts([_post()])
    assert "Asha Rao" in j["description"]
    assert "Head of Product at Acme" in j["description"]
    assert "https://www.linkedin.com/posts/asha_hiring" in j["description"]
    assert "We are hiring a Product Manager" in j["description"]


def test_an_email_only_post_gets_a_mailto_apply_url(llm):
    (j,) = parse_posts([_post(content="Hiring PM at Acme. Email your CV to jobs@acme.example.")])
    assert j["apply_url"] == "mailto:jobs@acme.example"


def test_a_real_link_beats_an_email(llm):
    """A link to the employer's form can be autofilled by the extension."""
    p = _post(content="Hiring PM at Acme. Apply https://acme.example/pm or mail jobs@acme.example")
    (j,) = parse_posts([p])
    assert j["apply_url"] == "https://acme.example/pm"


def test_an_email_beats_a_shortlink(llm):
    """lnkd.in was half the links measured, and it is opaque — it may well resolve to a
    LinkedIn page the extension cannot fill. The address in the same post is certain."""
    p = _post(content="Hiring PM at Acme. Details https://lnkd.in/abc123 or mail jobs@acme.example")
    (j,) = parse_posts([p])
    assert j["apply_url"] == "mailto:jobs@acme.example"


def test_a_shortlink_alone_is_still_a_route(llm):
    (j,) = parse_posts([_post(content="Hiring PM at Acme, apply https://lnkd.in/abc123")])
    assert j["apply_url"] == "https://lnkd.in/abc123"


def test_the_apply_route_is_never_taken_from_the_model(llm):
    llm.per_index["p0"] = _facts(title="PM")
    p = _post(content="Hiring PM at Acme. Email your CV to jobs@acme.example")
    (j,) = parse_posts([p])
    assert j["apply_url"] == "mailto:jobs@acme.example"


def test_any_role_not_just_pm(llm):
    llm.per_index["p0"] = _facts(title="Sales Associate", company="JSW One")
    (j,) = parse_posts([_post(content="HIRING ALERT | SALES ASSOCIATE. Send CV to hr@jsw.example")])
    assert j["title"] == "Sales Associate"


# ---------- the poster and their headline ----------

def test_a_company_page_author_passes_its_name_not_a_follower_count(llm):
    p = _post(author={"name": "InfyCrest Solutions", "info": "535 followers",
                      "linkedinUrl": "https://www.linkedin.com/company/infycrest"})
    parse_posts([p])
    assert "InfyCrest Solutions" in llm.calls[0]


def test_an_author_without_a_headline_does_not_crash(llm):
    assert len(parse_posts([_post(author={"name": "X", "info": None})])) == 1
    assert len(parse_posts([_post(author=None)])) == 1


# ---------- freshness ----------

def test_an_old_post_is_dropped_before_any_llm_call(llm):
    """postedLimit is asked of the vendor, but the date is checked here too: a vendor-side
    filter we cannot see is not one this project relies on."""
    old = _post(postedAt={"date": _recent(days=linkedin_posts.MAX_POST_AGE_DAYS + 1)})
    assert parse_posts([old]) == []
    assert llm.calls == []


def test_a_post_inside_the_window_is_kept(llm):
    ok = _post(postedAt={"date": _recent(days=linkedin_posts.MAX_POST_AGE_DAYS - 1)})
    assert len(parse_posts([ok])) == 1


def test_a_post_with_no_date_is_kept_with_no_posted_at(llm):
    """Unknown age is not old. The freshness UI already handles a NULL posted_at."""
    (j,) = parse_posts([_post(postedAt=None)])
    assert j["posted_at"] is None


# ---------- batching: one LLM call per chunk, not per post ----------

def test_posts_are_extracted_in_batches(llm):
    posts = [_post(id=str(i)) for i in range(linkedin_posts.LLM_BATCH_SIZE + 3)]
    jobs = parse_posts(posts)
    assert len(jobs) == len(posts)
    assert len(llm.calls) == 2


def test_each_post_in_a_batch_gets_its_own_answer(llm):
    llm.per_index["p1"] = _facts(is_job_post=False)
    llm.per_index["p2"] = _facts(title="Data Analyst")
    jobs = parse_posts([_post(id="a"), _post(id="b"), _post(id="c")])
    assert [(j["external_id"], j["title"]) for j in jobs] == [("a", "Product Manager"), ("c", "Data Analyst")]


def test_a_model_answer_for_an_unknown_index_is_ignored():
    """The model can return an index it was never given; that must not crash or misattach."""
    from connectors.linkedin_posts import _Batch

    with patch("connectors.linkedin_posts._call_claude_structured",
               return_value=_Batch(posts=[{"index": 7, **_facts()}])):
        assert parse_posts([_post()]) == []


def test_one_failed_batch_does_not_cost_the_others(llm, caplog):
    llm.raise_on_call = {0}
    posts = [_post(id=str(i)) for i in range(linkedin_posts.LLM_BATCH_SIZE + 1)]
    with caplog.at_level("WARNING"):
        jobs = parse_posts(posts)
    assert [j["external_id"] for j in jobs] == [str(linkedin_posts.LLM_BATCH_SIZE)]
    assert "secret-text" not in caplog.text, "log the exception type only"


def test_a_long_post_is_truncated_for_the_model_but_kept_whole_in_the_description(llm):
    long = "Hiring PM at Acme. Mail jobs@acme.example. " + "x" * 10_000
    (j,) = parse_posts([_post(content=long)])
    assert len(llm.calls[0]) < 4_000
    assert "x" * 10_000 in j["description"]


# ---------- what must be dropped ----------

def test_a_post_with_no_apply_route_is_dropped_without_an_llm_call(llm):
    assert parse_posts([_post(content="We are hiring a PM at Acme! Comment below.")]) == []
    assert llm.calls == []


def test_a_linkedin_only_link_is_not_an_apply_route(llm):
    assert parse_posts([_post(content="Hiring PM, see https://www.linkedin.com/jobs/view/123")]) == []
    assert llm.calls == []


def test_a_post_the_model_says_is_not_a_job_is_dropped(llm):
    llm.per_index["p0"] = _facts(is_job_post=False)
    assert parse_posts([_post()]) == []


def test_a_post_without_a_company_or_title_is_dropped(llm):
    llm.per_index["p0"] = _facts(company=None)
    assert parse_posts([_post()]) == []
    llm.per_index["p0"] = _facts(title="")
    assert parse_posts([_post()]) == []


def test_a_post_missing_id_or_content_is_dropped(llm):
    assert parse_posts([_post(id=None), _post(content=None), "junk"]) == []


def test_the_same_post_twice_in_one_payload_is_one_job(llm):
    """Several queries in one run return overlapping posts."""
    assert len(parse_posts([_post(), _post()])) == 1


# ---------- fetch: the recurring empty-vs-broken bug class ----------

def _fetch(posts, status=200):
    with patch("connectors.linkedin_posts.httpx.post", return_value=_Resp(posts, status)):
        return fetch_linkedin_posts(["#hiring India apply"], rows=5)


def test_fetch_parses_the_payload(llm):
    assert len(_fetch([_post()])) == 1


def test_no_token_returns_empty_without_calling(monkeypatch):
    from core.config import get_settings

    monkeypatch.setattr(get_settings(), "apify_token", None, raising=False)
    monkeypatch.delenv("APIFY_TOKEN", raising=False)
    with patch("connectors.linkedin_posts.httpx.post") as post:
        assert fetch_linkedin_posts(["q"], rows=5) == []
    post.assert_not_called()


def test_an_http_error_is_logged_not_silently_empty(llm, caplog):
    with caplog.at_level("WARNING"):
        assert _fetch([], status=402) == []
    assert any("402" in r.getMessage() for r in caplog.records), caplog.text


def test_201_created_is_success(llm):
    assert len(_fetch([_post()], status=201)) == 1


def test_a_non_list_payload_does_not_raise():
    assert _fetch({"error": "x"}) == []


def test_token_travels_as_a_bearer_header_only():
    with patch("connectors.linkedin_posts.httpx.post", return_value=_Resp([])) as post:
        fetch_linkedin_posts(["q"], rows=5)
    assert post.call_args.kwargs["headers"]["Authorization"] == "Bearer apify-test"
    assert "apify-test" not in post.call_args.args[0]


def test_all_queries_go_in_one_actor_run():
    """One run, one actor-start charge, instead of one per query."""
    with patch("connectors.linkedin_posts.httpx.post", return_value=_Resp([])) as post:
        fetch_linkedin_posts(["a", "b"], rows=7)
    assert post.call_count == 1
    body = post.call_args.kwargs["json"]
    assert body["searchQueries"] == ["a", "b"]
    assert body["maxPosts"] == 7
    assert body["postedLimit"] == "week" and body["sortBy"] == "date"
    assert body["scrapeReactions"] is False and body["scrapeComments"] is False


# ---------- ingestion wiring ----------

def test_posts_are_never_swept_for_delistings():
    from workers.jobs import SWEEPABLE_SOURCES
    assert "linkedin_post" not in SWEEPABLE_SOURCES


def test_configured_queries_are_role_agnostic():
    from connectors import config
    assert config.LINKEDIN_POST_QUERIES and config.LINKEDIN_POST_ROWS > 0
    assert not any("product manager" in q.lower() for q in config.LINKEDIN_POST_QUERIES)


def test_a_mailto_job_never_reaches_the_extension_work_queue():
    """The extension driver opens `apply_url` and fills a form. A mailto: link has no form."""
    import models
    from tests.test_submission_loop import _auth, _bind, _client

    client, SessionLocal = _client()
    _bind(client, SessionLocal)
    headers = _auth(client, "post-mailto@example.com")
    profile = client.post("/profiles", headers=headers, json={"persona": "developer"}).json()
    db = SessionLocal()
    for i, url in enumerate(["mailto:jobs@acme.example", "https://acme.example/apply"]):
        job = models.Job(source="linkedin_post", external_id=f"p{i}", canonical_hash=f"ph{i}",
                         title="PM", company="Acme", apply_url=url)
        db.add(job)
        db.commit()
        db.add(models.Application(profile_id=profile["id"], job_id=job.id,
                                  status=models.ApplicationStatus.approved))
        db.commit()
    db.close()

    urls = [i["apply_url"] for i in client.get("/extension/work-queue", headers=headers).json()]
    assert urls == ["https://acme.example/apply"]
