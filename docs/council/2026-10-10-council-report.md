# ApplyScout council report, 2026-10-10

**How this was produced.** Six advisors (founder/product, architect, engineer/QA, UX, growth, security) each audited the repository independently and read-only. Their reports were anonymized and every advisor's lens then peer-reviewed all six, checking disputed claims in the code. The chairman (the coordinating session) wrote this synthesis and spot-checked the most serious claims.

**Limits of the method.**
- All advisors are Claude sub-agents with different roles and instructions, **not independent models**, so their blind spots can be correlated.
- No user was interviewed.
- No production data was read and nothing was deployed or changed.
- Claims are labelled **VERIFIED** (checked in code), **DOC-CLAIM** (stated in project docs only) or **OPINION / HYPOTHESIS**.

---

## A. Executive summary and maturity

**Maturity: private alpha, one user.**
- The core pipeline is built and heavily tested, and works for the owner on the owner's machine: resume, confirmed facts, matching, tailoring with a truth check, review, and apply. Tests: 1,364 API, 143 web and 144 extension tests pass on SQLite. 8 failures are hermeticity/environment issues.
- Apply-by-email has been proven end to end once (DOC-CLAIM). Extension submission has never been watched on a real employer form (DOC-CLAIM).
- Nothing is deployed. There is no landing page, billing, analytics, outcome capture or account deletion (VERIFIED).

**The three findings that matter most, all VERIFIED by at least two advisors:**
1. **The product's central promise is not enforced.** The truth-check result (`flagged_unsupported_claims`) blocks nothing except one list view, `apps/api/main.py:191`. `campaigns.run_campaign` (auto-submit), `batch_approve_applications` (`main.py:293-330`, which enqueues email), `claim_submission`, the extension work queue and `apply_email.send_application_email` all ignore it. Separately, the extension uploads the generic profile resume (`apps/extension/src/content/formFill.content.ts:359`), so tailoring never reaches employers on that path.
2. **No one except the owner can activate.**
   - Onboarding's last step tells users to sideload an unpacked extension from `apps/extension/dist` (`apps/web/components/onboarding/StepDone.tsx:57-62`). That is impossible for real users and for Android.
   - Every job-source keyword list is hard-coded to Product Manager titles (`apps/api/connectors/config.py:3,31,58,79,108`).
   - Campaigns start as `draft`, so first matches are junk (DOC-CLAIM, GAPS 1.4).
3. **Auth and consent gaps that become real the moment outsiders join.**
   - Any validly signed token is accepted as a login, including reset tokens and Gmail OAuth state tokens (`core/deps.py:15-37`).
   - The Gmail OAuth state is not bound to the browser that started it (`outreach/gmail.py:108-122, 383-402`), so a consent link can attach a victim's Gmail to an attacker's account.
   - There is no account or data deletion.

**Direction the council converged on:** prove one safe, truthful loop with 10–20 real non-owner users before adding sources, markets, billing code or visual work.

---

## B. Verified implementation inventory

| Area | State | Evidence |
|---|---|---|
| Job discovery | Implemented. Fan-out per source, idempotent, timeouts | `workers/jobs.py::discover_jobs_task/discover_unit_task` (VERIFIED) |
| Source keywords | PM-only on every source | `connectors/config.py` (VERIFIED) |
| India sources | Glassdoor via JobSpy (6 cities), LinkedIn jobs/posts via Apify, ATS boards. No Naukri/Instahyre/Foundit (ADR-020) | `connectors/`, GAPS 3.1-3.2 (VERIFIED/DOC) |
| Dedup | `(source, external_id)` upsert, canonical hash, simhash per company | `connectors/pipeline.py::upsert_jobs` (VERIFIED) |
| Ranking | pgvector candidates (≤5,000), then 0.55 semantic + 0.30 coverage + 0.15 recency; 17–32 s per profile measured from a laptop | `matching/service.py::build_matches`, GAPS 2.6 (VERIFIED/DOC) |
| Resume parse | Implemented. Blocking LLM calls inside `async def`; text cut at 20k chars; 4,096 max tokens | `main.py::upload_resume`, `parsing/llm_extract.py` (VERIFIED) |
| Tailoring and truth check | Implemented; deterministic hard gate plus advisory model flags | `tailoring/engine.py`, `batch_prep.py` (VERIFIED) |
| Zero-facts branch | Skips validation, hard-codes empty flags | `engine.py:471-517` (VERIFIED) |
| Gate enforcement on send | **Missing** on every send path | see A1 (VERIFIED) |
| At-most-once submit | Implemented (`with_for_update`, `approved→submitting`) | `main.py::claim_submission` (VERIFIED) |
| Status changes | PATCH accepts any status, e.g. `submitting→approved` | `main.py::update_application` (VERIFIED) |
| Apply by email | Implemented, daily cap 10, proven live once | `apply_email.py` (VERIFIED), GAPS 1.4 (DOC) |
| Extension auto-apply | Partial. Plans route Greenhouse only; never watched; glue code untested; retry state in memory | `driver.ts`, `formplans.py` (VERIFIED), GAPS 1.4 (DOC) |
| Recovery of stuck `submitting` | Missing | (VERIFIED) |
| Outcome tracking | Manual Kanban statuses only; Gmail is send-only, so replies aren't detected | `models.ApplicationStatus`, `outreach/gmail.py::SCOPES` (VERIFIED) |
| Digest | Implemented. No retry, no deep link, no opt-out line | `digest.py` (VERIFIED) |
| Referral outreach | Backend built and gated (outreach does check flags); no web UI | `outreach/` (VERIFIED) |
| Auth | Argon2; single-use reset; no rate limit; no signup password minimum; tokens 7 days; purpose not checked | `core/security.py`, `auth/router.py`, `core/deps.py` (VERIFIED) |
| Tenancy | Ownership checks on routes. RLS on early tables only, not `contacts`, `outreach`, `gmail_credentials`, `fill_snapshots`. RLS tests use a fake connection | migrations 0010/0012/0014 vs 0025/0026/0030 (VERIFIED) |
| Secrets | `.env` not tracked. `resume_kb/facts.json` (owner's 24 career facts) is tracked | `git ls-files` (VERIFIED) |
| Billing, plans, analytics, deletion | None | grep (VERIFIED) |
| Deploy | Compose for API, workers and Caddy. No web-app hosting. Form-plan sweep will mark plans failed in the image (no Node) | `docker-compose.deploy.yml`, `formplans.py` (VERIFIED) |
| Tests | 1,364 pass / 8 fail (7 download a spaCy model at runtime). Postgres CI lane never run. Send-path tests mock flags empty | QA run (VERIFIED) |

---

## C. Critical findings

**Product**
- **P1:** the product is tuned to the owner's own PM search; a non-PM user's India feed would be close to empty.
- **P2:** there is no proof of the core promise (interviews). Outcomes are manual and replies are undetectable.
- **P3:** the revenue goal doesn't match the plan. ₹5 lakh a month needs about 455–626 payers; at 2–5% conversion that means 9k–23k signups (arithmetic on assumptions).

**Engineering**
- **E1:** the truth gate is not enforced on send paths (critical).
- **E2:** PATCH status can re-arm a claimed application, a path to duplicates.
- **E3:** retry and recovery are not durable, and stuck `submitting` rows are never swept.
- **E4:** the extension doesn't upload the tailored resume or a cover letter.
- **E5:** the campaign sweep is one serial job on the user-facing queue, falling back to RQ's 180 s default timeout (`run_scheduler.py:34,69-70`). It breaks at about 6–10 campaigns.
- **E6:** the form-plan sweep will fail permanently in the deploy image.
- **E7:** test gaps: no Postgres lane, mocked flags, non-hermetic redaction tests.

**Security and privacy**
- **S1 (high):** login accepts tokens of any purpose. The OAuth state token travels in URLs and works as a 15-minute login.
- **S2 (high):** Gmail OAuth state is not bound to the browser that started the flow.
- **S3 (high, defence in depth):** no RLS on the four newest PII tables, and RLS silently falls back to the owner role if `APP_DATABASE_URL` is unset.
- **S4:** no rate limiting on auth, no password minimum, account enumeration.
- **S5:** extension content scripts run on every site and frame.
- **S6:** full prompts with resume facts go to Langfuse unredacted; `pii/redact.py` is unused.
- **S7:** no deletion and no retention policy, which DPDP Act 2023 exposure makes urgent (legal advice needed).
- **S8:** the owner's facts file is tracked in git.
- **S9:** prompt injection. Scraped job text feeds an LLM whose output is emailed automatically (raised in peer review).

**UX**
- **U1:** activation dead-ends at sideloading the extension, and there's no phone path.
- **U2:** batch "Select all" includes cards flagged as possibly unsupported, while the copy says "she never makes anything up".
- **U3:** "Needs you" is buried on both Today and Review.
- **U4:** the extension popup and digest lack basics: labels, error handling, deep links.
- **U5:** a phone overflow on Today was reported earlier from a headless screenshot. **It was not reproduced in code and may be a capture artefact.** It stays unverified until a real-device or Playwright check.

**Market fit (India), raised in peer review**
- There's no current or expected salary (CTC) field, though notice period exists (`answer_bank.py`).
- There's no WhatsApp channel and no Hindi or other language support.
- Job search is episodic: users who succeed leave.

---

## D. Competitive positioning

- **Sourced competitor data (third-party pages accessed 2026-10-10; competitors' own sites were unreachable from the sandbox):**
  - LazyApply sells volume auto-apply for roughly $99–999 a year.
  - Jobright Turbo costs roughly $39.99 a month.
  - LinkedIn Premium Career costs roughly $29.99–39.99 a month (no INR price found).
  - Naukri paid services cost roughly ₹700–890 a month (weak sources).
  - Simplify, Teal, AIApply and Careerflow were **not verified**; no claims are made about them.
- **Differentiation that is real in code:**
  - tailoring grounded in facts the user confirmed, with a deterministic truth gate (once enforced on send)
  - submission from the user's own browser with at-most-once accounting
  - truth-gated referral drafts sent from the user's own Gmail
- **Differentiation only claimed:** "gets you interviews", "works while you sleep", Indian job coverage.
- **Positioning recommendation:** "fewer, truthful applications, each one tailored and traceable to your own facts". Do not compete on volume, where LazyApply wins on price and ApplyScout loses on job supply.

---

## E. Prioritized backlog

Effort: S = under 1 day, M = 2–5 days, L = 1+ week. "Gate" means it must be done before any non-owner user.

**P0, before any outside user**

| # | Item | Why (evidence) | Effort | Acceptance criterion |
|---|---|---|---|---|
| 1 | Single `can_send()` check (no hard flags, ≥1 grounded bullet, no pending questions, non-empty facts) on every send path; batch select excludes flagged cards; PATCH status uses an allowed-transition table | E1, E2, U2 | S–M | Unmocked tests: auto-submit with one hard flag leaves the row `ready_for_review` and sends nothing; `send_application_email` on a flagged row sends nothing; PATCH `submitting→approved` returns 409 |
| 2 | Global and per-user "pause all sends" switch, plus a per-user sent log ("what was sent in my name") | QA peer review | S | Switch on: zero sends across all paths in a test; the log lists every outbound email and submission |
| 3 | Reject non-access tokens at login; bind the OAuth state to the starting browser (nonce cookie); fail boot on a placeholder or short `JWT_SECRET` | S1, S2, L2 | S | Reset and state tokens get 401 on API routes; a callback without the matching cookie is refused |
| 4 | Onboarding works without the extension: phone users are sent to Assisted send; no `chrome://` instructions; campaign auto-activates after onboarding | U1, P1 | S–M | On a 390 px viewport, StepDone shows the Assisted path; a new user's campaign is `active` with role-based matches within one sweep |
| 5 | Source queries built from active campaigns' roles, with a per-source cost cap | P1 | M | A non-PM test campaign (e.g. "Data Analyst, Bengaluru") gets ≥20 relevant Indian matches in one discovery run (measured) |
| 6 | Remove `resume_kb/facts.json` from the repo; decide whether git history needs rewriting (owner's decision) | S8 | S | File absent; no code references it |
| 7 | Deploy the API and the web app; fix the form-plan sweep for a missing planner | P3, E6 | M | Public URL serves signup; no `failed` form plans caused by a missing binary |
| 8 | Account and data deletion, plus a consent and privacy notice | S7 | M | Deleting an account removes or anonymizes profile, facts, applications, Gmail credential and outreach rows; tested |

**P1, during the pilot**

| # | Item | Why | Effort |
|---|---|---|---|
| 9 | Outcome capture: one-tap "heard back?" at 7 and 14 days; first-party funnel events | P2 | S–M |
| 10 | RLS on `contacts`, `outreach`, `gmail_credentials`, `fill_snapshots`; boot warning if `APP_DATABASE_URL` is unset; one real-Postgres RLS test | S3 | S–M |
| 11 | Auth rate limiting (Redis), password minimum, case-insensitive email | S4 | S |
| 12 | Redact or omit prompt inputs in Langfuse; record which processors receive personal data | S6 | S |
| 13 | Extension uploads the tailored resume and cover letter | E4 | M |
| 14 | Durable attempt counter; sweeper for stuck `submitting` rows | E3 | M |
| 15 | Fan the campaign sweep out per campaign with an explicit timeout; add oldest-queued-job age to health | E5 | S |
| 16 | Per-recipient cap across all users; recipient domain checks; prompt-injection screening for scraped text | peer review, S9 | M |
| 17 | Make tests hermetic; run the Postgres CI lane once; unmocked campaign→prep→send integration test | E7 | M |
| 18 | Legal and terms check: LinkedIn via Apify, Glassdoor via JobSpy, NIM production licence, DPDP | S7, D's risk | owner/legal |
| 19 | Start Google OAuth verification (100-user and 7-day-token limits) | growth | calendar time |
| 20 | Digest deep links and opt-out; extension popup labels and error handling; "Needs you" first | U3, U4 | S–M |

**P2, after the pilot shows outcomes**
- Billing code (Razorpay; pass-based pricing).
- CTC fields.
- WhatsApp updates.
- Hindi.
- Landing page and the design system from `docs/design/`.
- Multi-ATS and Workday.
- Gulf and Southeast Asia.
- Referral outreach web UI.
- More workers once there's a measured backlog.

**Rejected or not now:**
- **DBOS:** no durability failure observed.
- **Moving the database region:** put the server in Neon's region instead.
- **More workers now:** no measured backlog.
- **Paid ads before reply-rate data.**
- **Further design rounds before activation works.**
- **Building billing before willingness to pay is tested.**
- **Scraping Foundit or other boards whose terms forbid it** (ADR-020).

---

## F. 30-day roadmap

| Week | Milestone | Depends on | Acceptance test |
|---|---|---|---|
| 1 | **Send safety and auth**: P0 1, 2, 3, 6 | none | All P0-1/2/3 tests green in CI; flagged content cannot leave through any path |
| 2 | **Usable by outsiders**: P0 4, 5, 7, 8; P1 10, 11, 12 | week 1; owner sets up domain and hosting | A stranger on an Android phone completes signup → facts → active campaign → one Assisted send without help; deletion works |
| 3 | **Pilot with 10–20 non-owner users** (free), mixed fresher and experienced, at least 2 non-PM roles; P1 9, 13, 20; owner watches one extension submit | week 2 | ≥70% of pilot users reach first send within 48 h; zero flagged-content sends; outcome prompts answered by ≥50% |
| 4 | **Measure and decide**: 14-day outcome data; willingness-to-pay test (30- or 60-day pass at 2–3 price points, refundable); P1 14, 15, 17; legal check under way | week 3 | Decision memo: price, persona and wedge, backed by pilot numbers |

---

## G. Metrics

| Stage | Metric | Source (to build) |
|---|---|---|
| Activation | % of signups with facts confirmed, campaign active and first application prepared within 48 h | events table |
| Successful workflow | prepared → sent rate; extension fill success; % blocked by the gate; % stuck in `submitting` | applications plus events |
| Quality | hard-flag rate per 100 prepared; user-reported errors; reply rate at 14 days | truth check plus outcome prompt |
| Outcome (north star) | applications with a human reply per active user per week | outcome prompt |
| Retention | weekly active users during their search; returns in weeks 2 and 3 (episodic, so measure within the search episode) | events |
| Monetization | pilot → paid conversion; measured cost per prepared application (tokens and Apify); gross margin per pass | billing (later), guard spend logs |

---

## H. Risk register

| Risk | Type | Likelihood | Impact | Mitigation |
|---|---|---|---|---|
| Fabricated claim emailed from a user's Gmail | Product / reputation | High (gate unenforced) | Severe | P0-1, P0-2 |
| Token misuse, Gmail OAuth hijack | Security | Medium once public | Severe (send as the user) | P0-3 |
| LinkedIn or Glassdoor terms enforcement; Apify actor changes | Platform / legal | Medium | High (sources vanish) | P1-18; avoid depending on one source |
| DPDP non-compliance (no deletion or consent; recruiter PII) | Privacy / legal | High as users grow | High | P0-8, P1-12, legal advice |
| Gmail bulk-sender or spam flags on shared recruiter inboxes | Reliability / reputation | Medium | High | P1-16, per-recipient caps, low daily caps |
| Google OAuth limits (100 users, 7-day tokens) | Growth | Certain without verification | Medium | P1-19; SMTP fallback |
| Thin Indian job supply outside PM | Business | High | High (empty feeds, churn) | P0-5; measure per-role yield |
| NIM free endpoint not licensed for production | Cost / legal | Unknown | Medium | P1-18; budget for a paid model |
| Extension submission unreliable on real forms | Reliability | Medium | Medium | Assisted mode as default; watched submits |
| Campaign sweep timeouts as users grow | Reliability | Low now, high at ~10 campaigns | Medium | P1-15 |
| Prompt injection from scraped job text | Security | Low–medium | High | P1-16 |
| Episodic churn undermines subscriptions | Business | High | Medium | Pass-based pricing |
| Advisors share one underlying model | Method | Certain | Medium | User interviews in the week 3 pilot |

---

## I. Council synthesis

**Where the council agreed** (independently, and confirmed in peer review):
- Flagged content can be sent today. Fix this before anything else touches real employers.
- Outsiders can't activate: sideload instructions, PM-only sources, draft campaigns.
- Proof of outcomes (replies or interviews) is the missing evidence for everything: pricing, marketing and direction.
- Scaling work (sweep fan-out, more workers, region, DBOS) is premature at one user. Four of six reviewers named the architect's report the biggest blind spot for this reason, though its findings are technically valid.

**Where it clashed**

| Question | Positions | Chairman's call and why |
|---|---|---|
| Charge now or later? | Growth: refundable pre-sale within 2 weeks. Product: manual ₹299–799 pilot charge. Four reviewers: no money until the gate is fixed and outcomes exist | **Free pilot first, then a refundable pass offer in week 4.** Charging before the gate is enforced puts paying users' names on possibly fabricated applications, and non-PM buyers would get empty feeds. |
| The wedge: LinkedIn "email your CV" posts plus apply-by-email | Product: lead with it. Security: PII to unverified addresses, injection, conflicts with ADR-020. Architect: shared-recruiter spam risk | **Unresolved.** It is the only path proven end to end and fits India, but it needs a legal read of LinkedIn's terms, recipient checks and a per-recipient cap before it becomes the headline. Pilot it with explicit per-recipient confirmation. |
| Phone-first Assisted or extension-first | UX: Assisted on phones, extension as a desktop upgrade. Counter: that hides the differentiator | **Assisted on phones, extension on laptops; drop neither.** Activation must work on the device users have. |
| Security first or gate first | Security: OAuth state plus RLS first. Others: send gate first | **Send gate and token-purpose check first** (both small, both live today), then OAuth state binding, then RLS. |

**Rejected ideas and why:**
- DBOS: no evidence of durability failure.
- Region migration: co-locate the server instead.
- More workers: no measured backlog.
- Paid ads: no reply data.
- More design rounds now: activation is the bottleneck.
- Scraping prohibited boards: ADR-020.
- Billing code now: willingness to pay is untested.

**What the council is least sure of:**
- Real job yield for non-PM roles in India.
- Whether LinkedIn sourcing is defensible.
- NIM licensing.
- Extension reliability on real forms.
- Whether users will accept the Assisted flow on phones.

All of these need real data, not more review.

**Single highest-value next action:** implement P0-1 together with P0-2 in one small, test-first change:
- one `can_send()` check on every send path
- an allowed-transition table for status changes
- a global pause switch
- a per-user sent log

It closes the only route by which the product can break its central promise in a recruiter's inbox under a real person's name. It is days of work, not weeks. Every later step (pilot, pricing, marketing) depends on it being true. The one-line token-purpose fix (P0-3) can ship the same day.
