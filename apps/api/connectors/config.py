# Edit this to match what you're targeting.

REMOTIVE_KEYWORDS = ["product manager", "associate product manager", "APM"]

# --- ADR-015 multi-source discovery ------------------------------------------
# Keyless public feeds (connectors/feeds.py). Each returns its whole board, so
# FEED_KEYWORDS filters client-side. Empty list = keep everything the feeds
# return (feeds.filter_by_keywords treats "no keywords" as "no filter", never
# as "no results").
FEED_KEYWORDS: list[str] = []

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
GREENHOUSE_BOARD_TOKENS = [
    # "notion", "ramp", "ashbyhq"   <- examples, replace with real tokens
]

LEVER_COMPANY_TOKENS = [
    # "netlify", "attentive"   <- examples, replace with real tokens
]

ASHBY_ORG_TOKENS = [
    # "linear", "vercel"   <- examples, replace with real tokens
]
