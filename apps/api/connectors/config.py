# Edit this to match what you're targeting.

REMOTIVE_KEYWORDS = ["product manager", "associate product manager", "APM"]

# --- ADR-015 multi-source discovery ------------------------------------------
# FEED_KEYWORDS NO LONGER GATES INGEST (ADR-021, 2026-10-05). It used to filter
# both the keyless feeds and the ATS boards, which made it a GLOBAL ingest gate:
# a user's own description (campaign roles/locations, résumé-fact centroid,
# prefs) only filtered what this one hardcoded list had already collected. For a
# product the PRD calls multi-tenant, discovery was single-tenant. Measured
# before the change: 1,758 live jobs, 309 product roles, and only 6 SRE roles —
# while four campaigns asked for SRE, searching a pool never collected for them.
#
# Discovery now stores whole boards and filtering happens per user at MATCH time
# (matching/service.py::build_matches, campaigns.py::_in_bounds).
#
# WHAT THIS LIST STILL DOES, and it is the only thing:
#   connectors/workday.py filters on it BEFORE hydrating each job. Workday's
#   list endpoint is cheap but every posting needs its own detail request, so
#   storing a whole board there would be ~526 extra requests for Adobe alone.
#   That is a cost control, not an inconsistency — see that module's docstring.
#
# So editing this list changes WORKDAY coverage only — but **widen it freely and
# never narrow it casually.** Workday's payload is keyword-filtered, so removing
# a term drops matching jobs out of the payload. Workday was taken out of
# `SWEEPABLE_SOURCES` (workers/jobs.py) precisely so that can no longer tombstone
# live Adobe/Cisco roles, which is what would have happened on the next run.
#
# REMOTIVE_KEYWORDS and REED_KEYWORDS above/below are separate again: there the
# keyword IS the query parameter, so there is no unfiltered fetch to make.
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
# MEASURED LIVE 2026-10-09 on python-jobspy 1.3.0, which is why this list is one entry:
#
#   glassdoor      returned rows. Was HTTP 403 on the previously pinned 1.1.82.
#   zip_recruiter  0 rows. 403 ("forbidden aa", a Cloudflare CFRAY id).
#   google         0 rows, silently — no error, just nothing.
#   indeed         0 rows. Also Tier C and parked by ADR-015.
#
# A dead site in this list costs one subprocess per keyword per location and returns
# nothing, so it is removed rather than left hopefully in place. Re-probe before adding
# one back; the numbers above are pinned in tests/test_jobspy_connector.py.
# LinkedIn stays out regardless (ADR-015 parks it as a special case).
JOBSPY_SITES = ["glassdoor"]
JOBSPY_KEYWORDS = ["product manager", "associate product manager", "product owner"]

# CITY-QUALIFIED, and that is load-bearing rather than tidiness: `location="India"`
# returns **Indianapolis** jobs, because Glassdoor prefix-matches the string. A
# country-level query would quietly fill the pool with US roles — the same class of trap
# as COLLECT-B's three plausible slugs that turned out to be different companies.
#
# Per-city is also what makes this source worth having at all. Measured 2026-10-09 at 25
# results per city: **147 unique product-manager jobs across 101 distinct companies**,
# with every city still returning a full page — against the 23 live India product roles
# that were the measured ceiling before this (GAPS 3.1). This is the first source to
# move that number.
# LinkedIn job search via Apify (connectors/linkedin_jobs.py), GAPS 3.1.
#
# Unlike JOBSPY_LOCATIONS, a bare country is CORRECT here and city-splitting is not
# needed: measured 2026-10-09, location="India" returned 14 of 15 rows genuinely
# India-located, where the same string against Glassdoor returns Indianapolis. One
# request per keyword per location, so a country-level query is also far cheaper.
#
# This is the only source that reaches the companies GAPS 3.1 lists as having no
# greenhouse/lever/ashby board at all — PhonePe showed up in the first 15 rows.
LINKEDIN_JOB_KEYWORDS = ["product manager", "associate product manager"]
LINKEDIN_JOB_LOCATIONS = ["India"]
# Per keyword per location. ~$0.0015/row measured, so 50 rows is roughly $0.08 a pass and
# the whole default config is ~$0.15 — against a $5/month plan allowance. Raise
# deliberately, not hopefully.
LINKEDIN_JOB_ROWS = 50

JOBSPY_LOCATIONS = [
    "Bengaluru, India",
    "Mumbai, India",
    "Delhi, India",
    "Hyderabad, India",
    "Pune, India",
    "Gurgaon, India",
]

# Reed (PRD.md §6 Tier 2) — no-ops without REED_API_KEY set in .env
REED_KEYWORDS = ["product manager", "associate product manager"]

# Greenhouse and Lever require a company's "board token" — find it by visiting
# https://boards.greenhouse.io/<token> or https://jobs.lever.co/<token>
# Add the startups you're targeting here (seed-Series B companies you like).
# 2026-09-29: PM roles in India or globally remote, each token checked live against
# the ATS's public API (boards whose "remote" PM roles were US-only were left out).
#
# Removing a token is SAFE since COLLECT-D (migration 0023): `Job.board_token`
# scopes the delisting sweep per board, so a board that isn't fetched simply
# isn't swept and its jobs stay listed. It used to tombstone that board's entire
# live inventory on the next run, because the sweep was source-wide.
# Its jobs do go stale rather than disappearing — nothing delists them once we
# stop asking — which is the deliberate trade (ADR-017: stale beats tombstoning
# live jobs).
#
# Still true, and NOT fixed by board_token: narrowing FEED_KEYWORDS tombstones
# stored jobs whose titles no longer match, because they drop out of the
# keyword-filtered payload the sweep compares against. Widening is safe.
# 2026-10-03 (Phase 2 item 4b): 117 candidate slugs probed live across all three
# platforms; 42 had a live board, and these are the ones with a PM-track role
# actually reachable from India. THREE PLAUSIBLE SLUGS WERE A DIFFERENT COMPANY
# ENTIRELY — `slice` is a US/Macedonia pizza business, both `porter` boards are
# US firms, `navi` is SF-only — so never add a token because the slug matches a
# company name. A NEAR-MISS of a slug we already have is the same trap: `hevo`
# (lever) is ONE posting, "VP of Power Electronics", New York - a different
# company from the configured `hevodata` (52 postings, Bangalore/Pune, a
# Product Manager). Also rejected 2026-10-05: `kite` (Greenhouse, US-only, not
# Zerodha Kite) and `fi` (Lever, London/New York, not Fi Money).
# Fetch the board and read its locations first
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
    # netradyne: added 2026-10-05 from a tools/ats_token_probe.py sweep over ~85
    # Indian companies. Verified live: payload company "Netradyne", 24 postings,
    # Bengaluru/Bangalore locations, 2 product roles ("Product Manager -
    # Integrations", "Technical Product Manager - Integrations").
    "netradyne",
    # --- COLLECT-G, 2026-10-10: 69 tokens from the career-ops catalogue -------
    # Slugs harvested from career-ops-hq/career-ops' templates/portals.example.yml
    # (MIT) — facts only, no files copied, the same basis on which
    # kalil0321/ats-scrapers' host->ATS mapping was adopted (DEPENDENCIES.md).
    #
    # 86 slugs probed -> 77 live on a platform we ingest -> **69 added, 8 rejected.**
    # Every one re-fetched afterwards for RECENCY and IDENTITY, because the probe
    # proves only that a board answers. Bar used: newest posting within 60 days.
    #
    # REJECTED ON IDENTITY — the slug/= company trap, caught twice more:
    #   lovable (greenhouse)  61 postings in Modena, Savignano sul Rubicone and
    #                         Grassobbio. An ITALIAN company. The real Lovable is
    #                         the Ashby board below (Stockholm/London/New York).
    #                         Two different companies, one slug, on two platforms.
    #   sanctuary (ashby)     "Civil Engineer", department "Construction", Delhi +
    #                         Dripping Springs and Austin, Texas. A construction
    #                         firm, not Sanctuary AI (Vancouver robotics).
    #
    # REJECTED ON RECENCY — an account existing proves nothing (cf. cars24's 2018
    # SmartRecruiters account):
    #   hightouch (ashby)     1 posting, newest 2033 days old
    #   inngest (ashby)       1 posting, newest 541 days old
    #   glacis-ai (ashby)     2 postings, 92 days
    #   humeai (greenhouse)   5 postings, 94 days
    #
    # REJECTED AS A CROSS-PLATFORM DUPLICATE — the same company's inventory
    # reachable twice would double-ingest it, and GAPS 4.3 records that nothing
    # re-collapses two live rows sharing a canonical_hash:
    #   helsing  158 postings on BOTH greenhouse and ashby. Kept GREENHOUSE,
    #            because its payload carries `company_name` and the other two
    #            platforms carry none — one extra identity signal for free.
    #   qonto    49 postings on BOTH lever and ashby. Kept ASHBY, whose location
    #            strings are fuller ("Paris, France" vs "Paris"), which is what
    #            `passes_hard_filters` reads.
    #
    # HONEST ON COVERAGE: these are predominantly US/EU companies, so this is a
    # GLOBAL-REMOTE win and **not** an India one. GAPS 3.1's India gap is
    # addressed by connectors/linkedin_jobs.py, not by these tokens. That said it
    # is not zero — 10 of the 69 do carry India-located roles, led by celonis
    # (33), gleanwork (24), openai (8), moniepoint (8) and anthropic (4).
    "airtable", "amplemarket", "anthropic", "arizeai", "boomilp", "celonis",
    "contentful", "coreweave", "getyourguide", "gleanwork", "hellofresh", "helsing",
    "hootsuite", "intercom", "isomorphiclabs", "jumia", "later", "moniepoint",
    "n26", "physicsx", "planetscale", "safariai", "scandit", "speechmatics",
    "stabilityai", "sumup", "traderepublicbank", "vercel",
]

LEVER_COMPANY_TOKENS = [
    "meesho", "zeta", "fampay", "mindtickle",
    "cred", "hevodata",  # added 2026-10-03: Bengaluru/Hyderabad/Pune roles verified live
    # paytm: added 2026-10-05, and the only company F5 (connectors/discovery.py)
    # ever found that this project's hand-written slug lists had missed — "paytm"
    # was absent from COLLECT-B's 117 candidates. Verified live: 173 postings,
    # 129 India-located, incl. "Product Management - Associate Product Manager"
    # in Noida. One of the 19 companies COLLECT-B recorded as unreachable.
    "paytm",
    # COLLECT-G (see GREENHOUSE_BOARD_TOKENS for the full rejection record).
    "contentsquare", "palantir", "pigment", "spotify", "tinybird",
]

ASHBY_ORG_TOKENS = [
    "sarvam", "supabase",
    "atlan",  # added 2026-10-03: India + SF board, verified live
    # COLLECT-G (see GREENHOUSE_BOARD_TOKENS for the full rejection record).
    "andela", "attio", "bland", "causaly", "claylabs", "clerk",
    "cohere", "corti", "cradlebio", "decagon", "deepgram", "elevenlabs",
    "faculty", "forto", "klue", "langchain", "legora", "lovable",
    "mollie", "n8n", "openai", "perk", "perplexity", "photoroom",
    "pinecone", "pleo", "qonto", "resend", "runpod", "sierra",
    "synthesia", "temporal", "vapi", "wayve", "workos", "zapier",
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
    "paytm": "Paytm",
    "netradyne": "Netradyne",
    # Workday tenants (COLLECT-C)
    "adobe": "Adobe",
    "cisco": "Cisco",
    # COLLECT-G, 2026-10-10. Required, not optional: an unmapped token BECOMES
    # the company value and therefore part of canonical_hash, and Lever/Ashby
    # payloads carry no company name at all.
    "airtable": "Airtable",
    "amplemarket": "Amplemarket",
    "anthropic": "Anthropic",
    "arizeai": "Arize AI",
    "boomilp": "Boomi",
    "celonis": "Celonis",
    "contentful": "Contentful",
    "coreweave": "CoreWeave",
    "getyourguide": "GetYourGuide",
    "gleanwork": "Glean",
    "hellofresh": "HelloFresh",
    "helsing": "Helsing",
    "hootsuite": "Hootsuite",
    "intercom": "Intercom",
    "isomorphiclabs": "Isomorphic Labs",
    "jumia": "Jumia",
    "later": "Later",
    "moniepoint": "Moniepoint",
    "n26": "N26",
    "physicsx": "PhysicsX",
    "planetscale": "PlanetScale",
    "safariai": "Safari AI",
    "scandit": "Scandit",
    "speechmatics": "Speechmatics",
    "stabilityai": "Stability AI",
    "sumup": "SumUp",
    "traderepublicbank": "Trade Republic",
    "vercel": "Vercel",
    "contentsquare": "Contentsquare",
    "palantir": "Palantir",
    "pigment": "Pigment",
    "spotify": "Spotify",
    "tinybird": "Tinybird",
    "andela": "Andela",
    "attio": "Attio",
    "bland": "Bland",
    "causaly": "Causaly",
    "claylabs": "Clay",
    "clerk": "Clerk",
    "cohere": "Cohere",
    "corti": "Corti",
    "cradlebio": "Cradle",
    "decagon": "Decagon",
    "deepgram": "Deepgram",
    "elevenlabs": "ElevenLabs",
    "faculty": "Faculty",
    "forto": "Forto",
    "klue": "Klue",
    "langchain": "LangChain",
    "legora": "Legora",
    "lovable": "Lovable",
    "mollie": "Mollie",
    "n8n": "n8n",
    "openai": "OpenAI",
    "perk": "TravelPerk",
    "perplexity": "Perplexity",
    "photoroom": "Photoroom",
    "pinecone": "Pinecone",
    "pleo": "Pleo",
    "qonto": "Qonto",
    "resend": "Resend",
    "runpod": "RunPod",
    "sierra": "Sierra",
    "synthesia": "Synthesia",
    "temporal": "Temporal",
    "vapi": "Vapi",
    "wayve": "Wayve",
    "workos": "WorkOS",
    "zapier": "Zapier",
}
