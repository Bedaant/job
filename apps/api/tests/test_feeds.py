"""Six public remote-job feeds (ADR-015 Tier A). Field names in the fixtures
below were taken from live responses on 2026-09-26, not from docs — each API's
real payload was fetched and its keys printed before these parsers were written.
Parsers are pure so this test needs no network.
"""
from datetime import datetime

from connectors import feeds


def _assert_normalized(job: dict, source: str):
    assert job["source"] == source
    for field in ("external_id", "title", "company", "apply_url"):
        assert job[field], f"{source}: {field} empty"
    assert isinstance(job["tags"], list)
    assert job["posted_at"] is None or isinstance(job["posted_at"], datetime)


def test_remoteok_parser_skips_legal_preamble_row():
    raw = [
        {"legal": "API Terms of Service: link back to Remote OK"},
        {
            "id": "1137431",
            "slug": "remote-backend-engineer-acme-1137431",
            "date": "2026-09-24T16:00:06+00:00",
            "company": "Acme",
            "position": "Senior Backend Engineer",
            "tags": ["python", "backend"],
            "description": "<p>Build things</p>",
            "location": "Worldwide",
            "apply_url": "https://remoteok.com/l/1137431",
            "salary_min": 120000,
            "salary_max": 160000,
            "url": "https://remoteok.com/remote-jobs/1137431",
        },
    ]
    jobs = feeds.parse_remoteok(raw)
    assert len(jobs) == 1
    _assert_normalized(jobs[0], "remoteok")
    assert jobs[0]["title"] == "Senior Backend Engineer"
    assert jobs[0]["salary"] == "120000-160000"


def test_himalayas_parser():
    raw = {"jobs": [{
        "guid": "https://himalayas.app/jobs/acme-backend",
        "title": "Backend Engineer",
        "companyName": "Acme",
        "employmentType": "Full Time",
        "minSalary": 100000, "maxSalary": 140000, "currency": "USD",
        "locationRestrictions": ["United States"],
        "categories": ["Software-Engineering"],
        "description": "<p>Work</p>",
        "pubDate": 1790265606,
        "applicationLink": "https://acme.com/apply",
    }]}
    jobs = feeds.parse_himalayas(raw)
    _assert_normalized(jobs[0], "himalayas")
    assert jobs[0]["location"] == "United States"
    assert jobs[0]["apply_url"] == "https://acme.com/apply"


def test_workingnomads_parser_derives_external_id_from_url():
    raw = [{
        "url": "https://www.workingnomads.com/job/go/1891955/",
        "title": "Acme - Account Manager",
        "description": "<p>Own accounts</p>",
        "company_name": "Acme",
        "category_name": "Marketing",
        "tags": "marketing,account",
        "location": "Anywhere",
        "pub_date": "2026-09-25T09:00:00",
    }]
    jobs = feeds.parse_workingnomads(raw)
    _assert_normalized(jobs[0], "workingnomads")
    assert jobs[0]["external_id"] == "1891955"


def test_jobicy_parser():
    raw = {"jobs": [{
        "id": 123456,
        "url": "https://jobicy.com/jobs/acme-backend",
        "jobTitle": "Backend Engineer",
        "companyName": "Acme",
        "jobGeo": "USA",
        "jobIndustry": ["Engineering"],
        "jobDescription": "<p>Work</p>",
        "pubDate": "2026-09-25 09:00:00",
        "salaryMin": 100000, "salaryMax": 0, "salaryCurrency": "USD",
    }]}
    jobs = feeds.parse_jobicy(raw)
    _assert_normalized(jobs[0], "jobicy")
    assert jobs[0]["salary"] == "100000"


def test_arbeitnow_parser_respects_remote_flag():
    raw = {"data": [{
        "slug": "acme-backend-269257",
        "company_name": "Acme",
        "title": "Backend Engineer",
        "description": "<p>Work</p>",
        "remote": False,
        "url": "https://www.arbeitnow.com/view/acme-backend-269257",
        "tags": ["python"],
        "job_types": ["full_time"],
        "location": "Cologne",
        "created_at": 1790265606,
    }]}
    jobs = feeds.parse_arbeitnow(raw)
    _assert_normalized(jobs[0], "arbeitnow")
    assert jobs[0]["remote"] is False


def test_wwr_rss_parser_splits_company_from_title():
    xml = """<?xml version="1.0" encoding="UTF-8"?>
    <rss version="2.0"><channel>
      <item>
        <title>Faire: Senior Machine Learning Engineer</title>
        <region>Anywhere in the World</region>
        <category>DevOps and Sysadmin</category>
        <type>Full-Time</type>
        <description>&lt;p&gt;Work&lt;/p&gt;</description>
        <pubDate>Sat, 26 Sep 2026 07:31:04 +0000</pubDate>
        <guid>https://weworkremotely.com/remote-jobs/faire-senior-ml</guid>
        <link>https://weworkremotely.com/remote-jobs/faire-senior-ml</link>
      </item>
    </channel></rss>"""
    jobs = feeds.parse_wwr(xml)
    _assert_normalized(jobs[0], "weworkremotely")
    assert jobs[0]["company"] == "Faire"
    assert jobs[0]["title"] == "Senior Machine Learning Engineer"


def test_keyword_filter_matches_on_substring_case_insensitively():
    jobs = [{"title": "Senior Product Manager"}, {"title": "Chef"}]
    assert feeds.filter_by_keywords(jobs, ["product manager"]) == [jobs[0]]
    # no keywords configured = no filtering, not zero results
    assert feeds.filter_by_keywords(jobs, []) == jobs
