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
GREENHOUSE_BOARD_TOKENS = [
    "okta", "druva", "mongodb", "rubrik", "inmobi", "databricks", "twilio",  # India offices
    "gitlab", "grafanalabs",  # remote across countries
]

LEVER_COMPANY_TOKENS = [
    "meesho", "zeta", "fampay", "mindtickle",
]

ASHBY_ORG_TOKENS = [
    "sarvam", "supabase",
]

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
}
