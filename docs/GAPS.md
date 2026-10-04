# Gap register — what is open across all phases

**Created 2026-10-03**, after Phase 2 (WORKLOG latest+69). Compiled by sweeping
`docs/WORKLOG.md` (5,557 lines, entries latest+28 → latest+69), `DECISIONS.md` (ADR-001…017),
`PLAN-MULTI-ATS.md`, and the session memory, then **verifying each claim against the code as it
stands today** rather than trusting the entry that first recorded it.

Every row says what is missing, the evidence, and what it blocks. `VERIFIED` means checked
against current code/config while writing this. `DOC-CLAIM` means stated in an entry and not
re-checked here.

---

## 1. Blocked on the owner — nothing can proceed without these

| # | Gap | Evidence | Blocks |
|---|---|---|---|
| 1.1 | **No SMTP credentials.** `SMTP_HOST` is absent from `apps/api/.env`. | VERIFIED — env keys are `ANTHROPIC_API_KEY, JWT_SECRET, DATABASE_URL, REDIS_URL, REED_API_KEY, VOYAGE_API_KEY, LANGFUSE_*, NVIDIA_*, APP_DATABASE_URL, LLM_PROVIDER` — no `SMTP_*`. | Password-reset emails and the daily digest both only log their link to the API console (latest+65). Two shipped features that cannot reach a user. |
| 1.2 | **Voyage is on the no-billing 3 RPM / 10K TPM tier.** | DOC-CLAIM (latest+62, +63) | Embedding backlog clears ~6 jobs per 2 minutes. latest+62 recorded "0 matches in bounds" until this was worked around with a chunked backfill. Freshly discovered jobs are unmatchable for a while. |
| 1.3 | **`ANTHROPIC_API_KEY` is still `sk-ant-dev-placeholder`.** | VERIFIED — the literal string is still in `.env`. | See 6.1 — but note the production LLM is NVIDIA NIM now, so this blocks *only* the eval harness, not the product. The docs still call it "the single remaining blocker for ADR-014", which is now misleading. |
| 1.4 | **The first real submit has never happened.** | DOC-CLAIM (latest+64, +65: "The first real submit, which the owner watches") | Every auto-apply path has been exercised with the no-submit guard on. The end of the funnel is unproven by design — the owner has to watch the first one. |
| 1.5 | **No Workday account run.** | DOC-CLAIM (latest+66) | Workday multi-page step pages can't be captured, so Workday form support stays partial. |

## 2. ADR-015's reversal is still not reflected in the code

ADR-015 (2026-09-26) reversed ADR-001's per-application approval. `DECISIONS.md` lists the code
that must change to match. **It has not changed.**

| # | Gap | Evidence | Blocks |
|---|---|---|---|
| 2.1 | **Per-item claim/approve machinery is still in the extension.** `claim-submission` and `submitApprovedApplication` are still live routes and call sites. | VERIFIED — `apps/extension/src/background/apiProxyCore.mjs:16` allows `POST /applications/{uuid}/claim-submission`; `architectureInvariants.test.mjs:32-35` still pins `submitApprovedApplication.ts` as the single submit path. | The product's headline promise ("approve a campaign once, Maggie works autonomously") is contradicted by the code still gating every submission individually. |
| 2.2 | **Review queue is still effectively a gate, not optional.** ADR-015 says it "becomes optional, not a hard gate". | DOC-CLAIM — `campaigns.py:205` shows a skipped/kept branch, but whether a campaign can run end to end with review off is untested. | Autonomy claim again. Needs one test proving a campaign completes with review disabled. |
| 2.3 | **`auto_submit` exists but has never run true end to end.** | VERIFIED — `models.py:194` `auto_submit = Column(Boolean, default=False)`. | Combined with 1.4: the automatic mode is schema-only. |

## 3. Source coverage — the biggest product gap

| # | Gap | Evidence | Blocks |
|---|---|---|---|
| 3.1 | **19 of 22 Indian consumer-tech companies have no board on Greenhouse/Lever/Ashby at all.** razorpay, swiggy, zomato, phonepe, flipkart, zepto, zerodha, myntra, nykaa, delhivery, paytm, urbancompany, lenskart, cars24, blinkit, rapido, licious, udaan. | VERIFIED — measured live 2026-10-03, 117 slugs probed, 42 live boards (latest+69). | **This is the one that matters.** The owner's search is India PM roles. "Add more ATS tokens" has a low ceiling. Reaching that market needs a new source class — other ATSs (Darwinbox, Keka, SmartRecruiters, Workday) or Indian boards (Naukri, Instahyre, Hirist, Cutshort). **Needs an ADR; none exists.** |
| 3.2 | **JobSpy is built but not wired into ingestion.** | VERIFIED — `workers/jobs.py:47` says "jobspy isn't wired into ingestion at all"; `main.py:1018` reports it to users as "Currently returns no results." | ADR-015 put Google/ZipRecruiter/Glassdoor in scope. Three source classes are dead code. Its Google scrape returned 0 rows (upstream issue, latest+6). |
| 3.3 | **Three ADR-015 tier-list portals remain unreachable.** YC WaaS returns HTTP 406 to non-browser clients (login-gated); Wellfound serves a Cloudflare Turnstile; HN "Who is hiring" is keyless but free-text comments with no company/title/apply_url. | VERIFIED — probed live 2026-10-03 (latest+68). | Each needs its own ADR: authenticated scraping, challenge evasion, or per-comment LLM spend. |
| 3.4 | **Adzuna and The Muse never landed.** No working API key obtained. | DOC-CLAIM (Phase 2 original entry) | Two PRD Tier-2 connectors, plus ~6 others from that tier. |
| 3.5 | **agent-reach has only GitHub + web channels.** Twitter and Reddit need real credentials. | DOC-CLAIM | Company-research dossiers (the remaining Phase 3 item from the old numbering) are thinner than designed. |

## 4. Freshness and data quality

| # | Gap | Evidence | Blocks |
|---|---|---|---|
| 4.1 | **Five of six keyless feeds can never be swept for delistings.** himalayas needs 5,786 requests/run (`totalCount` 115,729 at a server-forced 20/page); arbeitnow 429s at page 21; remoteok/weworkremotely/workingnomads have no pagination knob. | VERIFIED — measured live 2026-10-03 (latest+68), pinned in `tests/test_feed_pagination.py`. | Those five accumulate stale rows forever. Accepted in ADR-017, but it means "fresh jobs" is true only for greenhouse/lever/ashby/jobicy. A per-job liveness probe was proposed, measured and **REJECTED (ADR-019, 2026-10-04)**: probing jobs that are live by construction returned 403 for 8/8 himalayas, 8/8 weworkremotely and 3/8 workingnomads — a 100%/100%/37.5% false-positive rate against a bar of 0. |
| 4.2 | ~~Removing a board token tombstones that board's entire inventory.~~ **CLOSED 2026-10-04 by COLLECT-D** (migration 0023, `Job.board_token`). The sweep is scoped per board, so an unfetched board is not swept; one silent board no longer blocks its source either. | VERIFIED | **Residue:** narrowing `FEED_KEYWORDS` still tombstones jobs whose titles stop matching — board_token does not address that. |
| 4.3 | **Two live rows can share a `canonical_hash`.** The UNIQUE constraint was dropped in migration 0022. | VERIFIED — ADR-017 §5. | Nothing re-collapses such a pair. Accepted as strictly better than serving zero rows, but it is an un-reconciled duplicate path. |
| 4.4 | **CORRECTED 2026-10-04 — this was described wrongly.** `_OPEN_WORDS` already filters "Remote - United States" for *any* known country; only the user's own country is needed, not a world list. The real hole is a profile with **`country_code` unset** (optional, parsed from the resume), which disables the filter entirely. | VERIFIED | The fix is product-side: make country required at onboarding. A country table would need a new dependency and is YAGNI at one user. Owner's call. |
| 4.5 | ~~`connector_runs` has no pruning.~~ **CLOSED 2026-10-04 by COLLECT-F** — one bulk DELETE per discovery run, 30-day window, and F5's classifier proposals are explicitly never pruned (they are a review queue, not a log). | VERIFIED | — |

## 5. Infrastructure and ops

| # | Gap | Evidence | Blocks |
|---|---|---|---|
| 5.1 | **Everything runs locally, by hand.** API (no `--reload` — it hung on Windows and served stale code), worker, scheduler, logs in `D:\tmp\job-copilot-logs`. | DOC-CLAIM (latest+63, +65) | No deployment exists. Nothing runs when the owner's machine is off, so "Maggie works while you sleep" is not true yet. |
| 5.2 | ~~No CI.~~ **CLOSED 2026-10-04** — `.github/workflows/ci.yml` runs three jobs on every PR and push to main: api (859 pytest), web (140 vitest + `tsc --noEmit`), extension (132 node:test + typecheck). All three verified green locally first. | VERIFIED | **Not included:** the garak lane (needs a real provider key in repo secrets plus a budget decision) and `next build` (typecheck covers the surface). Both noted in the workflow. |
| 5.3 | **Redis Cloud free tier caps at 30 clients.** | DOC-CLAIM — already caused a real socket leak; `get_redis_connection` is `lru_cache`d as the fix. | A second worker process or a leak reintroduction hits the cap again. |
| 5.4 | **No Docker ⇒ no real-Postgres test lane.** The suite is in-memory SQLite. | DOC-CLAIM (DEPENDENCIES.md §5), standing decision | See 6.2. |
| 5.5 | **ClamAV and LibreOffice never installed.** `clamd` client has no daemon; LibreOffice is a system installer. | DOC-CLAIM | Upload virus scanning and any LibreOffice-based conversion are inert. |
| 5.6 | **`ENCRYPTION_KEY` is reserved but unset**; real KMS deferred. | VERIFIED — not among the `.env` keys. | Whatever was meant to be encrypted at rest is not. |

## 6. Verification gaps — things that have never been proven

| # | Gap | Evidence | Blocks |
|---|---|---|---|
| 6.1 | **CORRECTED AND PARTLY FIXED 2026-10-04 — the diagnosis here was wrong.** The harness was never pointed at Anthropic: its provider calls the real engine, which reads `LLM_PROVIDER=nvidia` from `.env`, and a live golden row tailored successfully through NIM in 5.7s. The real defect was worse: **all 30 golden rows' facts had no `id`**, so `known_fact_ids` was empty and `engine.py:370`'s `or not known_fact_ids` sent **every eval row down the unvalidated smoke path** — no `TailoredDraft` validation, no `source_fact_ids`, no KB-existence check. Observed before the fix: `source_fact_ids: []` on every bullet and the model's citation markers leaking into user-visible text ("...to FastAPI microservices [0]"). Fact ids added; the same rows now come back 4/4 and 6/6 bullets grounded with no markers. Guarded by `tests/test_eval_golden_set.py`. | VERIFIED | **Remaining:** a full 30-row promptfoo run has still not been scored, so tailoring quality is measured on a sound path but not yet quantified. |
| 6.2 | **Migration 0022 has never run against a real Postgres.** | VERIFIED — ADR-017 consequences; no Docker, suite is SQLite. | Its `create_index` calls are non-concurrent and take a SHARE lock while building. Run the first `alembic upgrade` outside an ingestion window. |
| 6.3 | **`form_plans` routing is Greenhouse-only, and Lever/Ashby measured no gain.** latest+59: re-measured, "no gain on required fields". | DOC-CLAIM | `PLAN-MULTI-ATS.md` Phase 3 ("platforms by data") rests on a premise its own measurement undercut. **That plan needs revisiting before it is executed.** |
| 6.6 | **Two unreproduced, order/time-dependent test flakes.** `test_campaigns::test_run_campaign_does_not_rereport_jobs_it_already_looked_at` (seen 2026-10-03) and `test_activity::test_today_counts` (seen 2026-10-04, `AttributeError: 'float' object has no attribute ...`). Both passed in isolation and neither recurred across repeated full runs. | VERIFIED — observed; 4 consecutive clean 855-test runs afterwards | No traceback was captured for either, so the cause is unknown. `test_today_counts` is at least **day-boundary sensitive** — it captures `datetime.utcnow()` and asserts "today" counts, so a run spanning UTC midnight can disagree with the endpoint. That does not explain a `float` AttributeError. Capture the traceback next time one fires rather than re-running until green. |
| 6.4 | **None of the PLAN-MULTI-ATS §5 success metrics has been measured on a real platform** (0 wrong values, ≥95% required fields, ≥70% reaching submit, <60s median). | DOC-CLAIM | No platform can honestly be called "supported". |
| 6.5 | ~~Un-reviewed leftover worktree branch.~~ **CLOSED 2026-10-03** — reviewed and deleted. All four of its changes were already on master in better form (incl. the `PATCH status:"active"` it listed as BLOCKED, and the `score * 100` "8200%" fix). | VERIFIED | Nothing lost. |

## 7. Documentation gaps

| # | Gap | Evidence |
|---|---|---|
| 7.1 | **`WORKLOG.md`'s "Current state — read this first" header is 7 weeks stale.** It says "Phase 3, in progress (2026-08-16)" and describes `apps/extension/` as blocked by a stray `postcss.config.mjs` — which **is fixed** (`apps/extension/vite.config.ts` now has `css: { postcss: {} }`). | VERIFIED | 
| 7.2 | The same header still calls `ANTHROPIC_API_KEY` the blocker for ADR-014 without mentioning the NIM switch (ADR, latest+34). | VERIFIED |
| 7.3 | **Phase numbering collides.** "Phase 2" means both the job-collection plan's phase and `PLAN-MULTI-ATS.md`'s phase, and "Phase 3" is ambiguous today. The job-collection plan has no written doc at all — it lives only in WORKLOG "Next" notes. | VERIFIED — this ambiguity blocked a session on 2026-10-03. |
| 7.4 | README still describes a stale single-user MVP and redirects to WORKLOG. | DOC-CLAIM |

---

## What to do next, in order

1. **Fix the docs that mislead (7.1–7.3).** Cheapest, and it stops the next session re-deriving. Rewrite the WORKLOG header; give the job-collection plan a real doc with unambiguous phase names.
2. **ADR for India source coverage (3.1).** The single highest-value product gap. Decide: other ATSs, Indian boards, or neither.
3. **Make the measurement real (6.1).** Repoint the eval harness at NIM. Without it, tailoring quality is unknown.
4. **Close the ADR-015 contradiction (2.1–2.3).** Either remove the per-item approval machinery or amend the ADR to match the code. Right now the docs and the code disagree about what the product is.
5. **SMTP (1.1).** Two finished features are unreachable without it.
6. **CI (5.2).** 824 tests that nothing runs on a PR.

Items 1.4, 1.5 and 5.1 are the owner's to drive, not code problems.
