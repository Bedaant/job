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

## 2. ~~ADR-015's reversal is still not reflected in the code~~ — **WRONG. Closed 2026-10-04.**

**This whole section was my diagnostic error**, and the third in this register (see also 6.1
and 4.4). I inferred a contradiction from the *presence* of `claim-submission` and
`submitApprovedApplication` in the extension without reading what they do or checking
`campaigns.py`.

Audited against the code:

| Was claimed | Actually |
|---|---|
| 2.1 "Per-item claim/approve machinery still gates every submission" | **§2 is implemented.** `campaigns.run_campaign` sets `approved` directly when `campaign.auto_submit` is true (`campaigns.py`), so campaign-level approval already replaced the per-item human gate. |
| 2.2 "Review queue is still effectively a hard gate" | **Already optional**, and pinned both ways by `test_run_campaign_marks_approved_when_auto_submit_true` and `..._leaves_applications_ready_for_review_when_auto_submit_false`. |
| 2.3 "`auto_submit` exists but has never run true end to end" | Accurate but belongs with 1.4 (no real submit has been watched yet), not as evidence of a contradiction. |

**The important correction: `claim-submission` must not be removed**, and ADR-015's
"Code to remove/change" bullet is dangerous as written — it is now amended in place. The
endpoint is a `with_for_update()` lock plus an `approved -> submitting` transition: the
**at-most-once guarantee for an irreversible outward-facing action**, pinned by
`test_claim_submission_still_cannot_fire_twice`, and the accounting that ADR-015's own
daily-caps rail needs. Removing it would allow duplicate applications to real employers.

What remains is cosmetic: comments in `submitApprovedApplication.ts` and
`main.py::claim_submission` still frame the mechanism in ADR-001 terms ("the human already
approved once", "the ADR-001 guard's ALLOWLIST"), which is exactly what misled me. Those are
reworded to ADR-015 terms so the next reader does not "finish the pivot" by deleting a safety
guarantee.

## 3. Source coverage — the biggest product gap

| # | Gap | Evidence | Blocks |
|---|---|---|---|
| 3.1 | **19 of 22 Indian consumer-tech companies have no board on Greenhouse/Lever/Ashby at all.** razorpay, swiggy, zomato, phonepe, flipkart, zepto, zerodha, myntra, nykaa, delhivery, paytm, urbancompany, lenskart, cars24, blinkit, rapido, licious, udaan. | VERIFIED — measured live 2026-10-03, 117 slugs probed, 42 live boards (latest+69). | **CEILING MEASURED 2026-10-05 — this avenue is now exhausted, not merely limited** (`docs/harness-reports/f5-classifier-and-ats-coverage-ceiling.md`). F5 was measured (1 correct of 9; its premise that a careers page names its ATS is false for SPA/bot-blocked sites) and all 19 companies were probed against greenhouse/lever/ashby/smartrecruiters/workable with the new `tools/ats_token_probe.py`. Result: **paytm reachable and added** (lever, 173 postings, 129 in India — found by F5, which COLLECT-B's slug list had missed), **swiggy** reachable but blocked on ADR-018 §7, **cars24** an abandoned 2018 account, and **the other 16 are on none of the five platforms at all**. More tokens and better ATS discovery cannot fix this. **The owner's search is India PM roles.** Reaching that market needs a new source class — other ATSs (Darwinbox, Keka, SmartRecruiters, Workday) or Indian boards (Naukri, Instahyre, Hirist, Cutshort). **Needs an ADR; none exists.** |
| 3.2 | **JobSpy is built but not wired into ingestion.** | VERIFIED — `workers/jobs.py:47` says "jobspy isn't wired into ingestion at all"; `main.py:1018` reports it to users as "Currently returns no results." | ADR-015 put Google/ZipRecruiter/Glassdoor in scope. Three source classes are dead code. Its Google scrape returned 0 rows (upstream issue, latest+6). |
| 3.3 | **Three ADR-015 tier-list portals remain unreachable.** YC WaaS returns HTTP 406 to non-browser clients (login-gated); Wellfound serves a Cloudflare Turnstile; HN "Who is hiring" is keyless but free-text comments with no company/title/apply_url. | VERIFIED — probed live 2026-10-03 (latest+68). | Each needs its own ADR: authenticated scraping, challenge evasion, or per-comment LLM spend. **Separately, the SmartRecruiters call deferred by ADR-018 §7 now has a written decision brief: `docs/smartrecruiters-decision-brief.md`** — the evidence, both readings of the robots.txt / vendor-docs tension, the unverified SAP API Policy that actually settles it, and the fact that the realistic yield is Swiggy alone. |
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

| # | Gap | Evidence | Blocks |
|---|---|---|---|
| 5.8 | **PII redaction misses uncommon Indian names.** `redact_pii` correctly replaces EMAIL_ADDRESS, PHONE_NUMBER and LOCATION, and PERSON works for "John Smith", "Priya Sharma", "Rahul Gupta", "Barack Obama" — but spaCy's `en_core_web_lg` classifies "Bedaant Srivastav" as **ORG**, so the name survives redaction. | VERIFIED 2026-10-04 — found by accident while verifying the presidio pin, using the owner's own name as test input. | Model-level, pre-existing, not caused by the 2.2.358 pin. It matters more than usual here: the product targets Indian users, and an un-redacted name in a cached dossier or generation history is the main thing redaction exists to remove. Options: add a custom `PatternRecognizer`/deny-list for known profile names (the profile already holds `full_name`, so the one name that matters is known), or accept and document. Redacting the *known* name directly is the cheap fix. |
| 5.7 | ~~**`apps/api/requirements.txt` cannot be installed from scratch.**~~ **CLOSED 2026-10-04** by pinning presidio to 2.2.358 (owner's choice of the three options). `pip install --dry-run --ignore-installed -r requirements.txt` now resolves, keeping `pydantic-2.9.2`. Verified after the change: 859 tests pass, `main`/`workers.jobs`/`pii.redact` all import, and `redact_pii` still redacts email, phone, location and PERSON live. **Original finding:** `presidio-analyzer==2.2.364` declares `pydantic<3.0.0,>=2.12.5`, while the file pins `pydantic==2.9.2`; pip exits `ResolutionImpossible`. It works locally only because this venv was built incrementally — presidio imports and runs fine against 2.9.2 at runtime, so the pin comment's "not a real runtime requirement" is correct about *runtime* and wrong about *installability*. | **VERIFIED — found by CI's very first run** (PR #8, api job failed in 16s at the install step, before any test ran). | Any clean environment: CI, a new dev machine, any deploy. **This is why the api CI job is currently red while web and extension are green.** Two fixes, both dependency changes needing the owner's approval: pin presidio to **2.2.358** (the newest release that declares no pydantic requirement, so it resolves against 2.9.2) or bump **pydantic to >=2.12.5** (keeps presidio current, but moves pydantic under fastapi/pydantic-settings/instructor/langfuse/anthropic — and WORKLOG already records one painful fastapi/starlette major bump). |

## 6. Verification gaps — things that have never been proven

| # | Gap | Evidence | Blocks |
|---|---|---|---|
| 6.1 | **CORRECTED AND PARTLY FIXED 2026-10-04 — the diagnosis here was wrong.** The harness was never pointed at Anthropic: its provider calls the real engine, which reads `LLM_PROVIDER=nvidia` from `.env`, and a live golden row tailored successfully through NIM in 5.7s. The real defect was worse: **all 30 golden rows' facts had no `id`**, so `known_fact_ids` was empty and `engine.py:370`'s `or not known_fact_ids` sent **every eval row down the unvalidated smoke path** — no `TailoredDraft` validation, no `source_fact_ids`, no KB-existence check. Observed before the fix: `source_fact_ids: []` on every bullet and the model's citation markers leaking into user-visible text ("...to FastAPI microservices [0]"). Fact ids added; the same rows now come back 4/4 and 6/6 bullets grounded with no markers. Guarded by `tests/test_eval_golden_set.py`. | VERIFIED | **SCORED 2026-10-04 — the first completed run in ADR-014's history** (`docs/harness-reports/adr014-first-eval-run.md`). A third blocker had to be cleared first: promptfoo spawned the provider with the *system* Python, so `import instructor` failed and the worker crash-looped — that was the 20-minute "hang" that looked like slow LLM calls. Now pinned via `config.pythonExecutable`. **Result: pass 1 is clean — 107 bullets, every one citing a real fact id, zero ungrounded. Pass 2 flags 29 of 30 rows**, all from `deterministic_unsupported` firing on tools/numbers in the **summary and cover letter**, not the bullets. Since `main.py:161` excludes flagged applications from the ready queue, **~97% of applications would never be sent** on this golden set. That is now gap 6.7, because it is an owner decision, not a patch. |
| 6.2 | **Migration 0022 has never run against a real Postgres.** | VERIFIED — ADR-017 consequences; no Docker, suite is SQLite. | Its `create_index` calls are non-concurrent and take a SHARE lock while building. Run the first `alembic upgrade` outside an ingestion window. |
| 6.3 | **`form_plans` routing is Greenhouse-only, and Lever/Ashby measured no gain.** latest+59: re-measured, "no gain on required fields". | DOC-CLAIM | `PLAN-MULTI-ATS.md` Phase 3 ("platforms by data") rests on a premise its own measurement undercut. **That plan needs revisiting before it is executed.** |
| 6.6 | **Two unreproduced, order/time-dependent test flakes.** `test_campaigns::test_run_campaign_does_not_rereport_jobs_it_already_looked_at` (seen 2026-10-03) and `test_activity::test_today_counts` (seen 2026-10-04, `AttributeError: 'float' object has no attribute ...`). Both passed in isolation and neither recurred across repeated full runs. | VERIFIED — observed; 4 consecutive clean 855-test runs afterwards | No traceback was captured for either, so the cause is unknown. `test_today_counts` is at least **day-boundary sensitive** — it captures `datetime.utcnow()` and asserts "today" counts, so a run spanning UTC midnight can disagree with the endpoint. That does not explain a `float` AttributeError. Capture the traceback next time one fires rather than re-running until green. |
| 6.4 | **None of the PLAN-MULTI-ATS §5 success metrics has been measured on a real platform** (0 wrong values, ≥95% required fields, ≥70% reaching submit, <60s median). | DOC-CLAIM | No platform can honestly be called "supported". |
| 6.5 | ~~Un-reviewed leftover worktree branch.~~ **CLOSED 2026-10-03** — reviewed and deleted. All four of its changes were already on master in better form (incl. the `PATCH status:"active"` it listed as BLOCKED, and the `score * 100` "8200%" fix). | VERIFIED | Nothing lost. |

| # | Gap | Evidence | Blocks |
|---|---|---|---|
| 6.7 | **The truth-check gate would block ~97% of applications.** **CAUSE CORRECTED 2026-10-04:** flags come from the **model checker**, not `deterministic_unsupported` — measured by calling the halves separately on 5 rows: **deterministic 0, model 31**. Both halves format flags identically, which is what misled the first write-up. The model checker is *working as specified*: `STRICT_CHECK_SYSTEM` explicitly tells it to flag "scope or scale", "titles, durations and praise adjectives". So it flags "Senior Backend Engineer with expertise in…" and "Proven ability to…". **The real problem is that pass 1 is asked for a "professional summary" and cover letter — prose that inherently carries titles and evaluative framing — while pass 2 is told to flag exactly that. The two prompts contradict each other.** Bullets remain 107/107 grounded. Fired on 29 of 30 rows. `main.py:161` filters the ready/work queue to applications with no `flagged_unsupported_claims`, so flagged means **not sent**. | VERIFIED 2026-10-04 — first completed ADR-014 run, `docs/harness-reports/adr014-first-eval-run.md`, raw data in `eval/results-run.json`, which is gitignored like all eval output — regenerate with the command in the report. | **An owner decision, not a bug to patch quietly** — ADR-006/009 are deliberately strict and this is their trade-off surfacing with a number for the first time. **Option (a) — a facts-only instruction for the prose — has been MEASURED AND ELIMINATED:** 10/10 rows flagged before and after, ~5.5 flags/row both arms, summary length 200→206 chars. Remaining options: (1) narrow `STRICT_CHECK_SYSTEM` so titles/praise/scope are not claims (but those are real fabrication vectors); (2) make the model half advisory and the deterministic half the hard gate (it had 0 false positives and is precise on unlisted tools/numbers, but by its own docstring cannot see invented outcomes in plain words); (3) rewrite pass 1's summary/cover-letter spec more strongly than the one-line attempt; (4) keep as-is and send almost nothing. |
| 6.8 | **The `llm-rubric` soft gate has no working grader, so every promptfoo run reports 0% regardless of quality.** promptfoo defaults to OpenAI (no key here); NIM was tried and does not return the JSON `llm-rubric` parses (16× "No output", 4× "Could not extract JSON" across 30 rows), and it would have been the same model grading its own output. | VERIFIED 2026-10-04 | The CLI pass rate is unusable — per-assertion results must be read out of `results-run.json`, which is documented in the config and the report. A real soft gate needs an **independent** grader key. |

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
