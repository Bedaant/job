# Next work plan (everything except design)

Written 2026-10-12 from the council audit (`docs/council/2026-10-10-council-report.md`), the form-filling research (`reports/Job application form filling tools.md`), and the product decisions made since. **Status banner (2026-10-12): most of P0 and P1 is now implemented on branch `feat/next-work-plan` (PR #24). The plan text below is the original and is unchanged; the table right under this line says what is done. Nothing here has been deployed or exercised with an outside user.**

## Status by item (2026-10-12)

Source: `docs/WORKLOG.md` entries of 2026-10-12, plus a spot-check of the code. "Done" means built and tested on SQLite; none of it has run in production with a real user. Items marked *not checked* were not re-verified when this table was written.

| Item | Status |
|---|---|
| P0-1 `can_send()` and transition table | Done: `send_gate.py` |
| P0-2 pause switches and sent log | Done: `app_flags`, `users.sends_paused`, `sent_log` (migration 0034) |
| P0-3 auth hardening | Done: placeholder `JWT_SECRET` rejected at boot, Gmail OAuth nonce cookie, auth rate limit (fails open if Redis is down). *Not checked:* password minimum, case-insensitive email |
| P0-4 remove `facts.json` | Removed from the tree. **Git history not rewritten** (owner decision); the file is still in `origin/main` history |
| P0-5 onboarding without the extension | Done in code (Assisted path in `StepDone.tsx`). *Not checked at 390 px in a browser* |
| P0-6 non-PM yield | Done for one campaign: Data Analyst, Bengaluru, 38 relevant of 58 against a bar of 20. One role, one city, one run |
| P0-7 account deletion and consent | Done: `account.py`, migration 0035 |
| P0-8 planner binary | *Not checked* |
| P1-9 proof of submission | **Open** |
| P1-10 outcome capture, funnel | Done: `outcomes.py`, migration 0038 |
| P1-11 RLS on the four tables | Done and applied to Neon (migration 0040). Boot warning for unset `APP_DATABASE_URL` was **not** built (no startup hook exists). Postgres test written; its first CI run failed on two test bugs, since fixed on the branch |
| P1-12 auth rate limit | Partly: see P0-3 |
| P1-13 Langfuse redaction | Done in `tailoring/engine.py::_redact_for_trace`. Known ceiling: NER can miss an uncommon name |
| P1-14 extension uploads tailored resume and cover letter | **Open** |
| P1-15 attempt counter, stale `submitting` sweeper | Done: `supervisor.py`, `applications.prep_attempts` (migration 0039) |
| P1-16 campaign fan-out, queue age | Done: `/ops/health` reports queue age |
| P1-17 per-recipient cap, injection screening | Done: 2 cold notes per address per day across users, with an advisory lock; `untrusted.py`. Recipient domain checks skipped on purpose (no rule that would not also refuse real recruiters) |
| P1-18 hermetic tests, Postgres lane | Hermetic: done. Postgres lane exists in CI and has never been green yet |
| P1-19 digest links and opt-out | Opt-out done. Other items *not checked* |
| Section 4, form filling | Workday adapter and the grounded LLM fallback are done. Fixture corpus size and probe thresholds *not checked* |
| Section 5, LinkedIn and referrals | LinkedIn data-export import done (unconfirmed facts). Referral rules done (refuse with no specific signal, follow-up cap 2) |
| Section 6, metrics | Queue age done; the rest *not checked* |
| Sections 7 to 9 | Not started, by design |
| Section 8, owner-only | All still open |

## 0. Rules for whoever executes this (Claude or a person)
1. **No design work.** Do not restyle the UI, change colours, fonts or layout, or build the landing page. Functional UI changes that a task needs (for example the phone path in onboarding) are fine, using the existing components and tokens.
2. **Safety first.** Do P0 before anything else. Nothing may reach an employer or a recruiter unless the single `can_send()` check passes.
3. **Approval gates.** Do not deploy, spend money, change pricing, rotate secrets, rewrite git history, or create a pull request without explicit approval. Never print secret values.
4. **Evidence.** Each task ends with a test that fails before and passes after (unmocked where the task says so). Update `docs/WORKLOG.md` and `docs/GAPS.md` honestly: say what was verified and what was not.
5. **Numbering.** ADR numbers and Alembic revisions never get reused. The next ADR is **ADR-023**; the next migration is **0041** (Neon is at 0040).
6. **Branch.** Commit to the designated branch and push. Small commits, one task per commit.

## 1. Where the product stands (so nobody re-derives it)
- **What it is:** an AI job-application assistant for Indian job seekers (freshers to about six years). Promise: every resume line is backed by a fact the user confirmed; nothing is sent without approval.
- **Built:** resume upload and parsing, facts review, campaigns, discovery, matching, tailoring plus truth check, extension form fill and submit, tracker, digest, Gmail send. **Not built:** referral outreach UI, billing, deployment.
- **Not proven:** a real watched submission; tailoring quality (never measured); any interview outcome; any non-owner user.
- **Decisions made since the audit:**
  - Keep the user in control by default. Auto mode is an optional per-campaign setting, allowed only when the truth gate passes (ADR-015 already moved approval to per-campaign).
  - Extend our own filler (deterministic first, LLM only for unmapped fields as a constrained choice that can abstain). Do not embed WebBrain (GPL) or Skyvern (AGPL).
  - No scraping of LinkedIn. LinkedIn data comes only from what the user uploads.
  - Proof of submission (screenshots, confirmation text, receipt) is a feature.

## 2. P0: before any outside user (do in this order)

| # | Task | Where | Done when |
|---|---|---|---|
| 1 | One `can_send()` predicate (no hard flags, at least one grounded bullet, no pending questions, non-empty facts) called by every send path; batch select excludes flagged cards; status changes go through an allowed-transition table | `apps/api/main.py` (batch approve ~293-330, claim_submission ~333, list view ~191, PATCH), `campaigns.py::run_campaign`, send-email paths | Unmocked tests: auto-submit with one hard flag leaves the row `ready_for_review` and sends nothing; `submitting→approved` is rejected |
| 2 | Global and per-user "pause all sends" switch and a per-user sent log | API + a small settings control | Switch on = zero sends on every path in a test; the log lists every outbound email and submission |
| 3 | Auth hardening: login rejects non-access tokens; OAuth state bound to the starting browser (nonce cookie); fail boot on placeholder or short `JWT_SECRET` | `core/deps.py`, `outreach/gmail.py` | Reset/state tokens get 401 on API routes; callback without the cookie is refused |
| 4 | Remove `resume_kb/facts.json` from the repo (owner decides on history rewrite) | `apps/api/resume_kb/facts.json` | File absent, no references |
| 5 | Onboarding that works without the extension: phone users go to Assisted send; no `chrome://` or developer-mode instructions; a "searching for your matches" state | `apps/web/components/onboarding/StepDone.tsx:57-62`, `apps/web/lib/onboarding.ts` | At 390 px, StepDone shows the Assisted path; first matches appear or a clear "searching" message shows |
| 6 | Prove non-PM yield with one real test campaign (for example "Data Analyst, Bengaluru"); then move the remaining fixed PM lists to campaign roles | `connectors/config.py`, campaign search | Measured: at least 20 relevant Indian matches in one run |
| 7 | Account and data deletion plus a consent and privacy notice | API + settings | Deleting an account removes or anonymises profile, facts, applications, Gmail credential, outreach rows; tested |
| 8 | Fix the form-plan sweep for a missing planner binary | `workers/`, deploy image | No `failed` plans caused by a missing binary |

## 3. P1: during the pilot

| # | Task | Notes |
|---|---|---|
| 9 | Proof of submission in the extension: before screenshot, after screenshot, confirmation text, stored receipt tied to the application (migration 0034) | In the user's own browser; no cloud browser needed |
| 10 | Outcome capture: one-tap "heard back?" at 7 and 14 days; first-party funnel events | Needed to learn anything |
| 11 | RLS on `contacts`, `outreach`, `gmail_credentials`, `fill_snapshots`; boot warning if `APP_DATABASE_URL` unset; one real-Postgres RLS test | |
| 12 | Auth rate limiting (Redis), password minimum, case-insensitive email | |
| 13 | Redact or omit prompt inputs in Langfuse (use `pii/redact.py`); record processors that receive personal data | |
| 14 | Extension uploads the tailored resume and a cover letter (not the generic resume) | `apps/extension/src/content/formFill.content.ts` |
| 15 | Durable attempt counter and a sweeper for stale `submitting` rows | Also an alert count |
| 16 | Fan the campaign sweep out per campaign with explicit timeouts; add oldest-queued-job age to `/health` | `workers/run_scheduler.py`, `observability.py` |
| 17 | Per-recipient cap across users; recipient domain checks; prompt-injection screening for scraped job text (treat job text as data) | |
| 18 | Hermetic tests; run the Postgres lane once; one unmocked campaign→prep→send integration test | Pull the pgvector image first |
| 19 | Digest deep links and opt-out; extension popup labels and error handling; "Needs you" first | Functional only |

## 4. P1: better form filling (research-backed)
1. **Fixture corpus:** about 30 real application forms (Greenhouse, Lever, Workday, Ashby, custom pages), including 5 that need sign-up. Store as test fixtures (no personal data).
2. **ATS adapters** for Greenhouse, Lever, Workday and Ashby: deterministic mapping first (Workday uses `data-automation-id` selectors); question schema from the public posting endpoint where it exists (Greenhouse job endpoint with questions).
3. **LLM fallback only for unmapped fields:** send compact field JSON to the backend; the model must choose one of the form's own options or abstain ("ask the user"); never for demographic or EEO fields; never invents a fact.
4. **Native setters and ARIA-aware combobox handling;** highlight low-confidence fields; never click Submit or Next on the user's behalf unless the campaign is in approved auto mode and `can_send()` passes.
5. **Probes:** fabrication probes (questions whose answer is not in the facts) and prompt-injection probes (hostile text in a job page). Thresholds to try: at least 85% correct fields on known ATS, at least 70% on custom pages, zero fabricated answers, zero EEO fills. (My suggestions, not sourced.)

## 5. P1: LinkedIn, referrals, text quality
1. **Import and confirm:** accept a résumé PDF/DOCX, a LinkedIn "Save to PDF", or the LinkedIn data-export ZIP (`Profile.csv`, `Positions.csv`, `Skills.csv`; match files by partial name). Imported items become unconfirmed facts that the user reviews. Delete the raw file after parsing. No scraping, no stored LinkedIn session.
2. **"Sign in with LinkedIn"** (OpenID Connect: name, email, photo only) is optional. Check LinkedIn's current developer docs before building.
3. **Referral message rules** (from the `li-dm` idea): cite one specific real reason to reach out; give something before asking; one small ask; at most two follow-ups; refuse to write one with no specific reason.
4. **Style cleanup** of generated text: no em dashes, invisible characters or stock words. MIT-licensed lists can be reused with the notice. Do not claim text is "undetectable".

## 6. P1: metrics (proposal from `docs/ENGINEERING-PRINCIPLES.md`)
Oldest queued job age per queue; count of `submitting` rows older than N minutes; LLM calls per minute and 429 count; p50/p95 tailoring time and cost per tailoring; Redis client count (free cap is 30).

## 7. P2: after the pilot shows outcomes
- Optional cloud-browser auto-apply pilot, only for employer systems without login, no LinkedIn sessions, about 20 users, cost cap. First run a bake-off on 20 forms: our own loop on Browserbase/Kernel/Anchor with a computer-use model vs Browser Use Cloud vs Nova Act.
- Per-user ApplyScout mail alias (forwards to the user) so verification codes can be read without a Gmail read permission. Design only until legal review.
- Billing (Razorpay, pass-based), CTC fields, WhatsApp updates, Hindi, referral outreach web UI, Gulf/Southeast Asia, more workers once a backlog is measured.

## 8. Only the owner can do these
Domain and hosting; Google Cloud OAuth client and verification (100-user and 7-day-token limits apply until verified); Apify token; SMTP credentials; legal review (LinkedIn via Apify, Glassdoor via JobSpy, NVIDIA NIM production licence, DPDP: notice, consent and deletion, core duties start about May 2027; Chrome Web Store single-purpose and data-use wording; AGPL/GPL questions); recruit 10-20 pilot users with a mix of fresher and experienced and at least two non-PM roles; watch one real extension submission; add `reddit.com`, `linkedin.com` and other research domains to the environment's allowed list if Claude should read them; repair Docker Desktop; rotate the 21st.dev API key that appeared in a chat.

## 9. Do not do (decided)
DBOS, moving the database region, more workers without a measured backlog, paid ads before reply-rate data, building billing before willingness to pay is tested, scraping boards whose terms forbid it (ADR-020), embedding GPL/AGPL agent code, solving CAPTCHAs, storing users' LinkedIn sessions, any server-side submission without per-campaign approval and a passing `can_send()`.

## 10. Pilot exit tests (from the audit)
At least 70% of pilot users reach a first send within 48 hours; zero sends of flagged content; at least 50% answer the outcome prompt; a stranger on an Android phone completes signup → facts → active campaign → one Assisted send unaided.

## 11. Open research (needs network access or pasted data)
Will people use it, and what do job seekers complain about on Reddit and similar places? Needs Reddit access or pasted threads. Verify the unverified items in `reports/Job application form filling tools.md` (prices, benchmark numbers, official ATS docs, Chrome Web Store policy text).
