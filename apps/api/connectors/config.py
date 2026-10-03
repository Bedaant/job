# Edit this to match what you're targeting.

REMOTIVE_KEYWORDS = ["product manager", "associate product manager", "APM"]

# --- ADR-015 multi-source discovery ------------------------------------------
# Keyless public feeds (connectors/feeds.py). Each returns its whole board, so
# FEED_KEYWORDS filters client-side. Empty list = keep everything the feeds
# return (feeds.filter_by_keywords treats "no keywords" as "no filter", never
# as "no results").
# Also filters the ATS boards below (workers/jobs.py): a board returns every opening.
FEED_KEYWORDS: list[str] = ["product manager", "product owner", "product lead", "head of product"]

# Which feeds run. Comment a line out to drop that source without touching code.
ENABLED_FEEDS = [
    "remoteok",
    "himalayas",
    "workingnomads",
    "jobicy",
    "arbeitnow",
    "weworkremotely",
]

# JobSpy sites (connectors/jobspy_connector.py). ADR-015: "linkedin" is parked
# as a special case and "indeed" is Tier C — test_jobspy_connector.py asserts
# neither appears here, so adding one has to be a deliberate, visible decision.
JOBSPY_SITES = ["google", "zip_recruiter", "glassdoor"]
JOBSPY_KEYWORDS: list[str] = []

# Reed (PRD.md §6 Tier 2) — no-ops without REED_API_KEY set in .env
REED_KEYWORDS = ["product manager", "associate product manager"]

# Greenhouse and Lever require a company's "board token" — find it by visiting
# https://boards.greenhouse.io/<token> or https://jobs.lever.co/<token>
# Add the startups you're targeting here (seed-Series B companies you like).
# 2026-09-29: PM roles in India or globally remote, each token checked live against
# the ATS's public API (boards whose "remote" PM roles were US-only were left out).
#
# REMOVING A TOKEN IS A DELISTING. The delisting sweep (workers/jobs.py) is
# source-wide, not per-board — `Job` has no board_token column — so the next
# trustworthy run marks every job from a removed board delisted, even though
# they are all still live. That is expiry by config edit, so drop a token only
# when you mean its jobs to disappear. To stop fetching a board without
# tombstoning its inventory, there is no switch today; a `board_token` column is
# the structural fix and is deferred to a later phase.
# 2026-10-03 (Phase 2 item 4b): 117 candidate slugs probed live across all three
# platforms; 42 had a live board, and these are the ones with a PM-track role
# actually reachable from India. THREE PLAUSIBLE SLUGS WERE A DIFFERENT COMPANY
# ENTIRELY — `slice` is a US/Macedonia pizza business, both `porter` boards are
# US firms, `navi` is SF-only — so never add a token because the slug matches a
# company name. Fetch the board and read its locations first
# (tests/test_board_tokens.py documents the rejects).
#
# Also measured: 19 of 22 Indian consumer-tech companies (razorpay, swiggy,
# zomato, phonepe, flipkart, zepto, meesho's own board aside, …) have NO board
# on Greenhouse/Lever/Ashby at all. More tokens here has a low ceiling for an
# India-focused search; that market is on other ATSs and on Indian job boards.
GREENHOUSE_BOARD_TOKENS = [
    "okta", "druva", "mongodb", "rubrik", "inmobi", "databricks", "twilio",  # India offices
    "gitlab", "grafanalabs",  # remote across countries
    "groww", "fivetran",  # added 2026-10-03: India-located PM roles verified live
]

LEVER_COMPANY_TOKENS = [
    "meesho", "zeta", "fampay", "mindtickle",
    "cred", "hevodata",  # added 2026-10-03: Bengaluru/Hyderabad/Pune roles verified live
]

ASHBY_ORG_TOKENS = [
    "sarvam", "supabase",
    "atlan",  # added 2026-10-03: India + SF board, verified live
]

# --- Workday (COLLECT-C, ADR-018) -------------------------------------------
# tenant -> "wd<N>/<site>". Both segments are per-employer and NOT guessable: 3
# of 6 guessed site names returned HTTP 422 during the COLLECT-C probe. Find a
# real pair by fetching https://<tenant>.wd<N>.myworkdayjobs.com/ and reading
# where it redirects — the first path segment is the site.
#
# Workday reaches a market the three ATS boards do not: multinational GCCs
# hiring product roles in Bengaluru/Hyderabad. See
# docs/harness-reports/collect-c-platforms.md.
#
# Removing a tenant here is a delisting, exactly as for the board tokens above.
# Verified live 2026-10-04: board found, paginated, and an India-located product
# role confirmed through the detail endpoint. "jobs" is the board size, which is
# also the per-run cost: ceil(jobs/20) list requests plus one detail request per
# keyword match. Adobe alone measured 67 requests / 126s.
#
#   adobe  wd5/external_experienced    526 jobs, 40 PM, 3 in India (Bangalore, Noida)
#   cisco  wd5/Cisco_Careers          1341 jobs, 22 PM, 1 in India (Pune/Bangalore/Mumbai)
#
# EXCLUDED, with the measurement:
#   target   wd5/targetcareers        2000 jobs for ONE PM role = 100 list requests,
#                                     and 2000 sits exactly on MAX_PAGES; it would
#                                     start raising the moment the board grows.
#   micron   wd1/External             3080 jobs, 0 India PM in the first 1200.
#   paypal   wd1/jobs                  291 jobs, 11 PM, 0 in India.
#   shell    wd3/shellcareers          132 jobs, 0 PM.
#   qualcomm wd12/External             returns total=0 — site name is probably wrong.
# A tenant with no India-reachable role is not worth its per-run cost; re-probe
# rather than adding speculatively.
#
# Found a wd host but NO site name matched a 15-candidate guess list, so they
# need their site read off the employer's careers link: mastercard (wd1),
# visa (wd5), autodesk (wd1), ebay (wd5), philips (wd3), unilever (wd3), lowes (wd5).
WORKDAY_BOARDS: dict[str, str] = {
    "adobe": "wd5/external_experienced",
    "cisco": "wd5/Cisco_Careers",
}

# Workday is fetched only when `utcnow().hour % this == 0`, not on every
# discovery run. Measured live: adobe ~95s and cisco 165s = ~4.3 minutes of
# mostly-paced requests for two boards. Discovery runs hourly and this machine
# runs a single RQ SimpleWorker, so an hourly Workday fetch would block campaign
# runs behind it for minutes at a time, every hour.
# 1 (or 0) means every run. Skipping is safe: it yields an empty payload and
# `_sweep_delisted` no-ops on empty, so a skipped run never delists anything.
WORKDAY_INTERVAL_HOURS = 6

# Board token -> real company name (Task 4, canonical_hash dedupe). This map WINS
# for every mapped token, including on Greenhouse, whose payload `company_name`
# carries board-page cruft that breaks the hash ("Rubrik Job Board" hashes
# differently from "Rubrik"); Greenhouse's payload is used only for a token that
# is absent here. Lever and Ashby payloads carry no company name at all, so their
# connectors always use this map. An unmapped token falls back to the raw token
# string (connectors/greenhouse.py, lever.py, ashby.py).
#
# Trade-off: a mapped company that rebrands upstream keeps the curated name here
# until someone edits this file — the payload cannot correct it. That is the
# price of a stable dedupe key; curated staleness is preferable to a hash that
# changes whenever a board renames itself.
TOKEN_COMPANY_NAMES: dict[str, str] = {
    "okta": "Okta",
    "druva": "Druva",
    "mongodb": "MongoDB",
    "rubrik": "Rubrik",
    "inmobi": "InMobi",
    "databricks": "Databricks",
    "twilio": "Twilio",
    "gitlab": "GitLab",
    "grafanalabs": "Grafana Labs",
    "meesho": "Meesho",
    "zeta": "Zeta",
    "fampay": "Fam",
    "mindtickle": "Mindtickle",
    "sarvam": "Sarvam",
    "supabase": "Supabase",
    # Added 2026-10-03. Fivetran's own payload returns "Fivetran " with a
    # trailing space, which is exactly the cruft this map exists to beat.
    "groww": "Groww",
    "fivetran": "Fivetran",
    "cred": "CRED",
    "hevodata": "Hevo Data",
    "atlan": "Atlan",
    # Workday tenants (COLLECT-C)
    "adobe": "Adobe",
    "cisco": "Cisco",
}
