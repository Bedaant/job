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
| 4.1 | **Five of six keyless feeds can never be swept for delistings.** himalayas needs 5,786 requests/run (`totalCount` 115,729 at a server-forced 20/page); arbeitnow 429s at page 21; remoteok/weworkremotely/workingnomads have no pagination knob. | VERIFIED — measured live 2026-10-03 (latest+68), pinned in `tests/test_feed_pagination.py`. | Those five accumulate stale rows forever. Accepted in ADR-017, but it means "fresh jobs" is true only for greenhouse/lever/ashby/jobicy. A per-job liveness probe (HTTP 404/410 on `apply_url`) would be direct evidence instead of inference — **not yet proposed as an ADR.** |
| 4.2 | **Removing a board token tombstones that board's entire inventory.** The sweep is source-wide; `Job` has no `board_token` column. | VERIFIED — documented at the token lists in `connectors/config.py`; ADR-017 consequences. | Editing config is a destructive data operation. The structural fix (a `board_token` column) is deferred with no ticket. |
| 4.3 | **Two live rows can share a `canonical_hash`.** The UNIQUE constraint was dropped in migration 0022. | VERIFIED — ADR-017 §5. | Nothing re-collapses such a pair. Accepted as strictly better than serving zero rows, but it is an un-reconciled duplicate path. |
| 4.4 | **Remote-country filtering covers India only.** An unknown `country_code` is not filtered at all. | DOC-CLAIM (latest+64) | Any non-India user gets the pre-fix behaviour: US-only "remote" roles in their matches. |
| 4.5 | **`connector_runs` has no pruning.** ~14 rows/hour, forever. | VERIFIED — `workers/jobs.py:312` inserts; no delete anywhere. | `/sources` reads the newest 200 rows, which is fine now, but the table grows unbounded. |

## 5. Infrastructure and ops

| # | Gap | Evidence | Blocks |
|---|---|---|---|
| 5.1 | **Everything runs locally, by hand.** API (no `--reload` — it hung on Windows and served stale code), worker, scheduler, logs in `D:\tmp\job-copilot-logs`. | DOC-CLAIM (latest+63, +65) | No deployment exists. Nothing runs when the owner's machine is off, so "Maggie works while you sleep" is not true yet. |
| 5.2 | **No CI.** `requirements-ci.txt` exists for garak, but PR #2 reported "no checks reported". | VERIFIED — `gh pr checks 2` → no checks. | The PR is the only review gate, and nothing runs the 824 tests automatically. |
| 5.3 | **Redis Cloud free tier caps at 30 clients.** | DOC-CLAIM — already caused a real socket leak; `get_redis_connection` is `lru_cache`d as the fix. | A second worker process or a leak reintroduction hits the cap again. |
| 5.4 | **No Docker ⇒ no real-Postgres test lane.** The suite is in-memory SQLite. | DOC-CLAIM (DEPENDENCIES.md §5), standing decision | See 6.2. |
| 5.5 | **ClamAV and LibreOffice never installed.** `clamd` client has no daemon; LibreOffice is a system installer. | DOC-CLAIM | Upload virus scanning and any LibreOffice-based conversion are inert. |
| 5.6 | **`ENCRYPTION_KEY` is reserved but unset**; real KMS deferred. | VERIFIED — not among the `.env` keys. | Whatever was meant to be encrypted at rest is not. |

## 6. Verification gaps — things that have never been proven

| # | Gap | Evidence | Blocks |
|---|---|---|---|
| 6.1 | **The ADR-014 eval harness produces no quality signal.** Mechanically live (promptfoo, 30-row golden CSV, Langfuse tracing) but pointed at Anthropic with a placeholder key, while production runs NVIDIA NIM. | VERIFIED — placeholder key present; `LLM_PROVIDER` is `nvidia`. | There is **no measurement of tailoring quality at all**, on the provider actually in use. Either repoint the harness at NIM or get a real Anthropic key. The docs still describe this as one blocker; it is really a mismatch. |
| 6.2 | **Migration 0022 has never run against a real Postgres.** | VERIFIED — ADR-017 consequences; no Docker, suite is SQLite. | Its `create_index` calls are non-concurrent and take a SHARE lock while building. Run the first `alembic upgrade` outside an ingestion window. |
| 6.3 | **`form_plans` routing is Greenhouse-only, and Lever/Ashby measured no gain.** latest+59: re-measured, "no gain on required fields". | DOC-CLAIM | `PLAN-MULTI-ATS.md` Phase 3 ("platforms by data") rests on a premise its own measurement undercut. **That plan needs revisiting before it is executed.** |
| 6.4 | **None of the PLAN-MULTI-ATS §5 success metrics has been measured on a real platform** (0 wrong values, ≥95% required fields, ≥70% reaching submit, <60s median). | DOC-CLAIM | No platform can honestly be called "supported". |
| 6.5 | **`worktree-agent-af607b1d421ec69ae` is an un-reviewed leftover branch**, superseded by master's `launchCampaign`. | VERIFIED — still in `git branch`. | Unknown whether it holds anything unmerged. Look, then delete. |

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
