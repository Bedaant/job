"""Find a company's ATS board token by probing the platforms, not by crawling
the company.

WHY THIS EXISTS, and why it is not F5 (`connectors/discovery.py::detect_ats`).

F5 asks "what ATS does company X use?" by fetching X's careers page and
regexing the HTML for an ATS URL. Measured 2026-10-05 on 9 companies whose ATS
we already knew: **1 correct, 8 no-match**. The cause is structural, not a bad
regex — the ATS link simply is not in the raw HTML of a modern careers page:

    okta.com/careers      200, 290 KB, no ATS string anywhere
    meesho.com/careers    200, 47 KB, and /jobs /join-us /work-with-us all
                          return the same shell (an SPA)
    swiggy.com/careers    403 on every candidate path (bot-blocked)

The board link appears only after JS runs, or sits on another host behind a
button, or the site blocks us. Fixing that needs a headless browser per
company, which this project has twice declined as too expensive.

This tool inverts the question: **"does platform P have a board for slug S?"**
Platform APIs are keyless, unblocked, JS-free and definitive — they return the
token and the postings in one call. That inversion is what actually found
coverage during COLLECT-B/C.

The two are COMPLEMENTARY, which is the real lesson: this tool needs a good
slug list, and F5 works from the domain side, so it can surface a company the
list forgot. F5's single hit (paytm -> lever, 173 postings, 129 in India) was a
company absent from COLLECT-B's 117-slug list.

LIVENESS, NOT EXISTENCE. An account existing proves nothing — three of four
SmartRecruiters hits in COLLECT-C had the right company name and postings from
2016/2018/2021. Anything this prints must be checked for recent postings before
it goes in `connectors/config.py`.

Usage:
    python tools/ats_token_probe.py slug1 slug2 ...
    python tools/ats_token_probe.py --file slugs.txt
"""
import argparse
import sys
import time

import httpx

UA = {"User-Agent": "ApplyScout/0.1 (+https://applyscout.in)"}
JSON_UA = {**UA, "Content-Type": "application/json"}
TIMEOUT = 20
PACE = 0.4

# Platforms we can already ingest. smartrecruiters/workable are probed too
# because knowing a company is there is useful even without a connector —
# but they are labelled, so nothing is added to config by mistake.
INGESTED = {"greenhouse", "lever", "ashby"}


def _get(url, params=None):
    return httpx.get(url, params=params, headers=UA, timeout=TIMEOUT)


def greenhouse(slug):
    r = _get(f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs")
    if r.status_code != 200:
        return None
    jobs = r.json().get("jobs") or []
    return (len(jobs), [j.get("title", "") for j in jobs]) if jobs else None


def lever(slug):
    r = _get(f"https://api.lever.co/v0/postings/{slug}", {"mode": "json"})
    if r.status_code != 200:
        return None
    jobs = r.json()
    return (len(jobs), [j.get("text", "") for j in jobs]) if jobs else None


def ashby(slug):
    r = _get(f"https://api.ashbyhq.com/posting-api/job-board/{slug}")
    if r.status_code != 200:
        return None
    jobs = r.json().get("jobs") or []
    return (len(jobs), [j.get("title", "") for j in jobs]) if jobs else None


def smartrecruiters(slug):
    """Needs the company IDENTIFIER, which is often the capitalised name
    (Swiggy, not swiggy) — so a miss here is weaker evidence than elsewhere.
    Also tier-dependent: lower plans have no public feed at all."""
    for ident in dict.fromkeys([slug.capitalize(), slug, slug.upper()]):
        r = _get(f"https://api.smartrecruiters.com/v1/companies/{ident}/postings",
                 {"limit": 100})
        time.sleep(PACE)
        if r.status_code != 200:
            continue
        d = r.json()
        if d.get("totalFound"):
            rows = d.get("content") or []
            newest = max((j.get("releasedDate") or "" for j in rows), default="")
            return (d["totalFound"], [j.get("name", "") for j in rows],
                    f"id={ident} newest={newest[:10]}")
    return None


def keka(slug):
    """Keka is the one Indian-market ATS with a real keyless public feed, so it
    is the only one of the three probed on 2026-10-08 (Darwinbox's recruitment
    API is employer-side and token-authenticated, with no public board feed —
    its careers page is JS-rendered, the same wall F5 hit; Zoho Recruit's API
    is OAuth and returns only your OWN org's openings, so public access would
    mean scraping `*.zohorecruit.com` HTML, which is an ADR-020 question, not
    an API).

    Three-way signal, which is why a miss here is strong evidence:
        302 -> /careers/Content/TenantNotFound.html  not a Keka customer
        302 -> /careers/Content/403.html             tenant exists, portal not public
        200 -> JSON list                             live public board

    Calibrated against jupiter.keka.com before use — an uncalibrated probe that
    can only ever return "no" is how F5 scored 1/9.

    The title key is read at runtime, not hardcoded: all three live boards found
    (jupiter, cars24, signzy) returned `[]`, so the populated schema was never
    observed and is not guessed here.
    """
    r = _get(f"https://{slug}.keka.com/careers/api/jobs/{slug}/active")
    if r.status_code != 200:
        loc = r.headers.get("location", "")
        if "403" in loc:
            return (0, [], "tenant exists, careers portal not public")
        return None
    jobs = r.json() or []
    if not jobs:
        return (0, [], "live portal, zero active postings")
    key = next((k for k in jobs[0] if "title" in k.lower() or "name" in k.lower()), None)
    return (len(jobs), [j.get(key, "") for j in jobs] if key else [], f"title_key={key}")


def workable(slug):
    r = _get(f"https://apply.workable.com/api/v1/widget/accounts/{slug}")
    if r.status_code != 200:
        return None
    jobs = (r.json() or {}).get("jobs") or []
    # An account with zero jobs is dormant: 17 of 19 Indian companies had one
    # of these in COLLECT-C, every single one empty.
    return (len(jobs), [j.get("title", "") for j in jobs]) if jobs else None


PLATFORMS = [
    ("greenhouse", greenhouse),
    ("lever", lever),
    ("ashby", ashby),
    ("smartrecruiters", smartrecruiters),
    ("workable", workable),
    ("keka", keka),
]

PM_WORDS = ("product manager", "product owner", "product lead", "head of product")
INDIA = ("india", "bengaluru", "bangalore", "mumbai", "hyderabad", "pune",
         "delhi", "gurgaon", "gurugram", "noida", "chennai")


def probe(slug):
    hits = []
    for name, fn in PLATFORMS:
        try:
            got = fn(slug)
        except Exception as exc:
            print(f"  {slug:18} {name:16} {type(exc).__name__}")
            time.sleep(PACE)
            continue
        time.sleep(PACE)
        if not got:
            continue
        total, titles, *extra = got
        pm = [t for t in titles if any(k in (t or "").lower() for k in PM_WORDS)]
        tag = "INGESTIBLE" if name in INGESTED else "no connector"
        print(f"  {slug:18} {name:16} postings={total:4} product_roles={len(pm):3} "
              f"[{tag}] {extra[0] if extra else ''}")
        for t in pm[:3]:
            print(f"      - {t[:70]}")
        hits.append((name, slug, total, len(pm)))
    if not hits:
        print(f"  {slug:18} -- nothing on any probed platform")
    return hits


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("slugs", nargs="*")
    ap.add_argument("--file", help="file with one slug per line")
    args = ap.parse_args()

    slugs = list(args.slugs)
    if args.file:
        with open(args.file, encoding="utf-8") as fh:
            slugs += [l.strip() for l in fh if l.strip() and not l.startswith("#")]
    if not slugs:
        ap.error("give at least one slug, or --file")

    print(f"probing {len(slugs)} slugs across {len(PLATFORMS)} platforms\n")
    all_hits = []
    for s in slugs:
        all_hits += probe(s)

    print("\n=== INGESTIBLE hits (candidates for connectors/config.py) ===")
    ingestible = [h for h in all_hits if h[0] in INGESTED]
    if not ingestible:
        print("  none")
    for name, slug, total, pm in ingestible:
        print(f'  {name:12} "{slug}"   postings={total} product_roles={pm}')
    print("\nBEFORE adding any of these: check recency (an account can exist and be "
          "years dead) and confirm the company identity — COLLECT-B rejected `slice`, "
          "`porter` and `navi` as entirely different companies.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
