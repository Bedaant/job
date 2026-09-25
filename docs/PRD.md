# Job Copilot — Product Requirements Document

- **Status:** Draft v1.0
- **Owner:** Bedaant Srivastav
- **Last updated:** 2026-08-15
- **Supersedes:** the single-user MVP described in the root `README.md`

---

## 1. Problem

Job seeking is a high-volume, low-signal grind. A candidate targeting mid-level roles
needs 150–400 applications to land an offer. Each application has five manual steps:

1. Find the listing (spread across 40+ boards, most with no search that works)
2. Read the company and figure out what they actually want
3. Rewrite the resume for the JD's keywords so it survives ATS parsing
4. Fill the same 30 form fields for the tenth time
5. Chase a referral, because cold applications convert at ~2% and referred ones at ~30%

Existing tools solve exactly one step. "Auto-apply" products solve step 4 by spraying
one generic resume everywhere — which is why their reply rates are worse than manual
applying. Nobody has connected the whole chain.

**Job Copilot is the chain.** Discovery → research → truth-grounded tailoring →
one-click submission → referral outreach → tracking, in one loop.

## 2. Who it's for

Three portfolios at launch. Each has a different resume grammar, a different set of
"what good looks like" signals, and a different ATS keyword space.

| Persona | Signal the resume must carry | Primary boards |
|---|---|---|
| **Developer** | Systems built, scale numbers, stack depth, OSS/GitHub | Greenhouse, Lever, Ashby, HN Who's Hiring, WWR |
| **Product Manager** | Outcomes and metrics, not features shipped; ownership scope | Greenhouse, Ashby, LinkedIn, Wellfound |
| **Marketing** | Channel performance, CAC/LTV/ROAS, content proof-of-work | Workable, SmartRecruiters, Uplers, LinkedIn |

Personas are a first-class object, not a dropdown. They drive the matcher's weights,
the resume template, the tailoring prompt, and the referral email tone.

### Non-users (explicitly)
- Recruiters / employer side. Not building a two-sided market.
- Executive search (C-level). Different game entirely, no volume.

## 3. Product principles

These are the tiebreakers. When a feature debate stalls, the higher principle wins.

1. **Never fabricate.** Every claim in every generated document traces to a fact the
   user entered. A second model pass verifies this and blocks the send if it can't.
   This is the product's whole moat — one hallucinated metric in an interview and the
   user is done.
2. **Human approves, machine executes.** The system drafts, batches, and submits — but
   a human clicks "approve" on the batch. Fully autonomous spraying is what makes
   existing tools useless, and it's what gets accounts banned.
3. **The user's identity, the user's reputation.** Emails send from the user's own
   Gmail. LinkedIn data comes from the user's own logged-in browser. We never operate
   shared scraping infrastructure or a shared sending domain.
4. **Boring, legal ingestion first.** Public ATS APIs cover more ground than people
   assume. Scraping is the last resort, not the first.
5. **Sounds like a person.** Generated text is specific because it's built from real
   facts, not because it's dressed up. Specificity is what reads as human; generic
   enthusiasm is what reads as AI.

## 4. What we're building — scope

### 4.1 In scope for v1

| # | Capability | One-line definition |
|---|---|---|
| F1 | Accounts & profiles | Signup, persona selection, one profile per persona |
| F2 | Resume intake | Upload PDF/DOCX → parsed into structured Facts KB; or build from template |
| F3 | Facts KB | Atomic, verifiable claims. The single source of truth for all generation |
| F4 | Job ingestion | 12+ ATS/board connectors + RSS + browser-extension capture |
| F5 | ATS discovery | Given a company domain, detect which ATS it uses and register its board |
| F6 | Matching | Hybrid: hard filters (visa/location/seniority) + pgvector semantic score |
| F7 | Company research | agent-reach-backed dossier: what they do, recent news, stack, people |
| F8 | Tailoring engine | Persona-aware resume + cover letter, grounded and truth-checked |
| F9 | ATS-safe export | Single-column DOCX/PDF that real parsers read correctly |
| F10 | Review queue | Batch approve N applications; diff view of what changed vs base resume |
| F11 | Submission | Extension-driven autofill on the user's browser; ATS-native where possible |
| F12 | Referral engine | Find a plausible referrer, draft the ask, send from user's Gmail |
| F13 | Tracker | Saved → Applied → OA → Recruiter → Interview → Offer → Rejected, with follow-ups |
| F14 | Analytics | Reply rate by source/persona/template. Tells the user what's actually working |

### 4.2 Explicitly out of scope for v1

- **Server-side scraping of LinkedIn/Wellfound.** Ban risk and legal exposure sit on us,
  and the maintenance cost is permanent. Extension capture gets most of the value.
- **Fully autonomous submission.** Ruled out by Principle 2.
- **Cold outreach to strangers with no connection.** The referral engine targets people
  with a real hook (shared school, shared employer, public OSS overlap). Everything else
  is spam and will burn the user's Gmail.
- **Interview prep / mock interviews.** Adjacent, big, and a v2 conversation.
- **Salary negotiation.** Same.
- **Mobile apps.** Responsive web only.

### 4.3 Deferred with a trigger

| Deferred | Add when |
|---|---|
| Workday/Taleo deep autofill | >15% of matched jobs are on Workday |
| Multi-language resumes | First non-EN market request |
| Team/agency accounts | Someone asks to manage 5+ candidates |
| Temporal for workflow orchestration | RQ retry semantics visibly fail in prod |

## 5. User journeys

### J1 — Onboarding (target: under 6 minutes to first match)
1. Sign up (email + password, or Google OAuth).
2. Pick persona(s): Developer / PM / Marketing.
3. Upload resume **or** answer a guided 12-question builder.
4. System parses into ~25–40 atomic facts. User reviews them on one screen —
   edit, delete, add metrics. **This screen is the product.** Facts quality caps
   everything downstream, so we make it fast and slightly gamified
   ("8 of your bullets have no number — add one?").
5. Set preferences: locations, remote/hybrid/onsite, min salary, visa needs, seniority,
   company size, exclude-list.
6. Install the browser extension (optional, unlocks LinkedIn + one-click autofill).
7. First discovery run fires. Matches appear.

### J2 — Daily loop (target: under 10 minutes/day)
1. Open dashboard. "18 new matches, 6 scored above 80."
2. Skim the six. Each card shows: score, why it scored (matched facts vs JD requirements),
   company one-liner, salary, and the gaps.
3. Click "Prepare" on the ones worth it → tailoring runs in background.
4. Review queue fills. For each: side-by-side diff of tailored vs base resume, the cover
   letter, and any **truth-check flags in red**. Nothing with an unresolved flag can be
   approved.
5. Approve the batch. Extension submits them one at a time in a visible tab.
6. For the top 2, click "Get referral" → dossier of plausible referrers → pick one →
   review the drafted email → send from own Gmail.

### J3 — Follow-through
- Day 5 after applying with no response: nudge to follow up, with a drafted note.
- Status changes are one click from the tracker or via a Gmail thread heuristic
  (a reply from `@company.com` on the application thread auto-suggests "Recruiter").
- Weekly digest: what converted, which persona/template performed, what to change.

## 6. Feature specifications

### F2/F3 — Resume intake and the Facts KB

The Facts KB is the constitution. Everything generated must be derivable from it.

A fact is atomic and verifiable:

```json
{
  "id": "uuid",
  "persona": "developer",
  "category": "experience | project | skill | certification | education",
  "claim": "Cut checkout API p99 latency from 1.4s to 180ms",
  "proof": "Payments team, Acme Corp, Q2 2025",
  "metric": "87% p99 reduction",
  "period": {"from": "2025-04", "to": "2025-07"},
  "tags": ["backend", "performance", "go", "postgres"],
  "confidence": "verified | self_reported",
  "embedding": "vector(1536)"
}
```

Parsing pipeline: `PDF/DOCX → text (pdfplumber / python-docx) → LLM structured
extraction → user confirmation screen → persisted`. We never keep the resume blob as
the generation source — only the parsed facts. This is what makes the truth-check
mechanically possible.

**Rejection rule:** a fact with no `proof` cannot be used in a cover letter, only in a
skills list. Forces the user to substantiate.

### F4/F5 — Ingestion

Three tiers, in priority order.

**Tier 1 — Official ATS APIs (no ToS risk, structured, reliable)**

| ATS | Endpoint shape |
|---|---|
| Greenhouse | `boards-api.greenhouse.io/v1/boards/{token}/jobs?content=true` |
| Lever | `api.lever.co/v0/postings/{token}?mode=json` |
| Ashby | `api.ashbyhq.com/posting-api/job-board/{token}` |
| Workable | `apply.workable.com/api/v1/widget/accounts/{token}` |
| SmartRecruiters | `api.smartrecruiters.com/v1/companies/{id}/postings` |
| Recruitee | `{token}.recruitee.com/api/offers/` |
| Teamtailor | `{token}.teamtailor.com/jobs.json` |
| Personio | `{token}.jobs.personio.de/xml` |
| Workday | `{host}/wday/cxs/{tenant}/{site}/jobs` (POST, JSON) |

**Tier 2 — Aggregator APIs and RSS**
Remotive, RemoteOK, Arbeitnow, Himalayas, Jobicy, WeWorkRemotely (RSS),
HN "Who is hiring" (via Algolia API), Uplers (RSS where available), Adzuna
(`apiKey`, broad multi-country aggregator), Reed (`apiKey`, UK-focused, official),
The Muse (`apiKey`, jobs + company profiles — doubles as a company-research input),
Jooble (`apiKey`, aggregator, evaluate overlap with Adzuna before enabling both),
ZipRecruiter (requires a publisher/affiliate agreement, not just an API key — heavier
onboarding than the others, evaluate after the free-key sources are live).

Deliberately excluded from this tier: GitHub Jobs (API discontinued 2021), Indeed's
public job-search API (closed to new third-party developers), LinkedIn (OAuth-gated,
partner-only in practice — already ruled out by ADR-002), and Upwork/Kaggle (freelance
marketplace and data-science competitions, not this product's job categories).

**Tier 3 — Browser extension capture**
LinkedIn, Wellfound, Indeed, and any portal the user is already logged into. The
extension reads the DOM of a page **the user opened themselves** and posts the
normalized job to our API. No headless browsers, no proxies, no credentials stored.

**The ATS discovery subsystem (F5)** is the unglamorous piece that makes Tier 1 scale.
Given a list of target companies, for each: fetch `{domain}/careers` and `/jobs`,
follow redirects, and pattern-match the resulting URL against known ATS signatures to
extract the board token. Store it in an `ats_boards` registry. This turns "20 hardcoded
tokens" into "5,000 companies polled nightly," and it's a solved problem — regexes over
redirect chains, not AI.

**Deduplication:** the same role appears on Remotive, the company's Greenhouse board,
and LinkedIn. Dedupe key is a content hash over
`normalize(company) + normalize(title) + normalize(location)`, with the Tier-1 record
winning as canonical and the others recorded as `job_sources` rows. Apply URL always
resolves to the canonical ATS link.

### F6 — Matching

Two stages, cheap before expensive.

1. **Hard filters (SQL, free):** work authorization, location/remote policy, seniority
   band inferred from title, salary floor, exclude-list, posted within N days.
2. **Semantic score (pgvector):** cosine similarity between the persona's fact-set
   embedding and the JD embedding, blended with a keyword-coverage term.

```
score = 0.55 * semantic + 0.30 * required_skill_coverage + 0.15 * recency_bonus
```

The card must always show **why**: "7 of 9 required skills matched. Missing: Kubernetes,
Terraform." Opaque scores destroy trust and get ignored.

### F7 — Company research

Runs once per company, cached 14 days. Backed by
[agent-reach](https://github.com/Panniantong/agent-reach) (MIT), which gives one CLI
over web/GitHub/Twitter/Reddit/RSS. Produces a dossier: what they sell, funding stage,
recent launches or news, public tech stack, engineering-blog themes, notable people.

Feeds two consumers: the cover letter's "why this company" paragraph (the only part
that can't come from the Facts KB, and therefore the only part that needs sourcing),
and the referral engine's hook-finding.

### F8 — Tailoring engine

Three passes. Pass 3 is new versus the MVP.

- **Pass 1 — Tailor.** Given Facts KB (persona-filtered) + JD + dossier, produce summary,
  ranked bullets, and cover letter. Constrained to the KB. Persona-specific system
  prompt: a PM bullet leads with outcome, a dev bullet leads with system and scale, a
  marketing bullet leads with channel and number.
- **Pass 2 — Truth-check.** Independent call, KB + draft, no memory of Pass 1. Returns
  unsupported claims with severity. **Any `high` severity blocks approval in the UI.**
- **Pass 3 — Voice.** Strips the tells: em-dash pile-ups, "leveraged", "spearheaded",
  "passionate about", tricolon padding, and the "I was drawn to X because Y" opener.
  Enforces the user's own register, sampled from their original resume's phrasing.
  This is not detector evasion — it's the difference between text built from specifics
  and text built from adjectives. Grounded, specific writing reads as human because it
  is; the pass just removes the LLM's habitual filler.

Every generation is versioned and stored so the analytics layer can attribute reply
rate to template version.

### F9 — ATS-safe export

Real ATS parsers (Taleo, iCIMS, Workday) still fail on: multi-column layouts, tables,
text boxes, headers/footers, graphics, and non-standard section names. Export rules:

- Single column, no tables, no text boxes, nothing in header/footer
- Section headings from a fixed vocabulary: Summary, Experience, Skills, Education, Projects
- Standard fonts, embedded; no icons or ligature tricks
- Dates as `MMM YYYY – MMM YYYY`
- Both `.docx` (python-docx) and `.pdf` (LibreOffice headless conversion, preserving the
  text layer)

Ships with a **parse-back check**: after generating, re-parse our own output and diff
against the source facts. If a bullet doesn't survive the round trip, the template is
broken. This runs in CI on every template change.

### F11 — Submission

- **Known ATS (Greenhouse/Lever/Ashby):** field maps are stable and public. The extension
  fills them deterministically from the profile, attaches the tailored files, pauses on
  anything it can't map (custom screening questions), and asks the user.
- **Unknown forms:** best-effort label-matching fill, then hand over to the user.
- Never auto-answers demographic/EEO questions. Never auto-answers "why do you want to
  work here" free-text — that pulls the tailored cover letter and waits for a look.
- Every submission is recorded with a screenshot for the user's own records.

### F12 — Referral engine

1. Identify candidates for the ask, ranked by hook strength: same university, same past
   employer, same OSS project, public post about the team, then finally "works there."
2. Find a reachable address: public GitHub commit email, personal site, company pattern
   inference (`first.last@company.com`) verified via MX/SMTP probe.
3. Draft: ≤120 words, names the specific role, one concrete reason the user fits
   (pulled from the Facts KB), makes the ask small ("would you be open to forwarding
   this?"), and offers an easy out.
4. Send from the user's own Gmail via OAuth.
5. Guardrails, non-negotiable: max 10 outreach emails per user per day; one follow-up
   maximum after 6 days; global suppression list; any reply containing an opt-out
   phrase permanently suppresses that address across the whole platform.

## 7. Data model (core tables)

```
users            id, email, password_hash, created_at, plan
profiles         id, user_id, persona, headline, location, work_auth, prefs_json
resume_facts     id, profile_id, category, claim, proof, metric, period, tags,
                 confidence, embedding
companies        id, name, domain, ats_type, ats_token, dossier_json, dossier_at
jobs             id, company_id, canonical_hash, title, location, remote_type,
                 salary_min/max, description, apply_url, seniority, posted_at
job_sources      id, job_id, source, external_id, raw_url, fetched_at
matches          id, profile_id, job_id, score, score_breakdown_json, state
applications     id, profile_id, job_id, status, submitted_via, submitted_at,
                 artifacts_json, next_follow_up_at
generations      id, application_id, pass, model, prompt_version, output_json,
                 flags_json, created_at
outreach         id, application_id, to_email, hook_type, subject, body,
                 sent_at, replied_at, suppressed
events           id, user_id, type, payload_json, created_at
```

Indexes that matter: `jobs(canonical_hash)` unique, `job_sources(source, external_id)`
unique, `matches(profile_id, score DESC)`, `resume_facts` ivfflat on `embedding`.

## 8. Non-functional requirements

| Area | Requirement |
|---|---|
| Latency | Dashboard p95 < 500ms. Tailoring is async with progress, target < 25s end to end |
| Ingestion | Full poll of all registered boards nightly in < 45 min; incremental every 4h |
| Cost | < $0.40 in model spend per application prepared (measure and enforce a per-user cap) |
| Availability | 99% for the app. Ingestion may lag; the user shouldn't notice |
| Security | Passwords argon2. OAuth tokens encrypted at rest. No resume file leaves our storage without a signed, expiring URL |
| Privacy | Full export and hard delete. Resume data never used for training. Explicit consent before any outreach send |
| Compliance | CAN-SPAM/GDPR for outreach: real identity, working opt-out, honored suppression |
| Observability | Every connector reports fetched/inserted/failed. Alert when a connector's yield drops >60% week-over-week — that's how you learn an API changed |

## 9. Success metrics

**North star:** applications that receive a human reply, per user per week.

| Metric | Target at 100 users |
|---|---|
| Onboarding → first match | < 6 min, 70% completion |
| Applications prepared per active user per week | 15 |
| Reply rate, cold applications | > 6% (baseline ~2%) |
| Reply rate, referred applications | > 20% |
| Truth-check high-severity flag rate | < 3% of generations (higher means prompts are broken) |
| Submission success (form filled without human takeover) | > 75% on Tier-1 ATS |
| Weekly retention, week 4 | > 40% |
| Reply-rate delta between prompt versions, tracked via the eval harness (§11, ADR-014) | Any new prompt version must not regress reply rate vs. the version it replaces — measured, not assumed |
| Measured cost per prepared application | ≤ $0.40 (the NFR in §8), confirmed against real token counts before Phase 2 scale-up, not assumed |

**Counter-metric:** outreach complaint/opt-out rate. If it crosses 0.5%, the referral
engine is spamming and gets throttled automatically.

## 10. Risks

| Risk | Severity | Mitigation |
|---|---|---|
| ATS APIs change or close | High | Connectors are isolated + yield-monitored; multi-source dedupe means losing one source degrades rather than breaks |
| LinkedIn blocks the extension | Medium | Extension only reads pages the user opened; no automation signature. Worst case: lose Tier 3, keep Tier 1+2 |
| Generated applications are recognizably templated | High | Pass 3 voice layer, per-application variance, and reply-rate monitoring by template version — via the eval harness (ADR-014), not just hoped-for |
| Outreach gets users' Gmail flagged | High | Hard daily caps, hook-required targeting, suppression list, one follow-up max |
| Model cost per user exceeds revenue | Medium | Cheap model for extraction/matching, expensive only for the tailoring pass; hard per-user monthly cap; measured (not assumed) before Phase 2 scale-up |
| Facts KB quality is low → output is generic | High | The fact-review screen is a first-class product surface, not a form. Nag on metric-less bullets |
| We are storing a lot of PII | High | Encryption at rest, short-lived signed URLs, delete-on-request, no third-party analytics on profile pages |
| **No feedback loop from outcomes back into the AI system** — match-score weights, tailoring prompts, and truth-check thresholds are hand-tuned once and never validated against reply/interview data | **High** | Eval/feedback harness (ADR-014) is core Phase 3-4 infrastructure, not a Phase 7 dashboard afterthought |
| Company dossier (agent-reach output, arbitrary web content) is a second, unguarded prompt-injection surface into Pass 1 — only the JD path has an adversarial fixture today | High | Adversarial fixtures extended to dossier content, tested via `garak` (ADR-014) before Phase 4 exits |
| Three personas (Developer/PM/Marketing) built in parallel validates none of them before tripling surface area | High | **v1 ships Developer only.** PM and Marketing personas are gated on Developer proving reply-rate lift — see build order below |
| Extension is a single point of failure for both LinkedIn/Wellfound capture (Tier 3) and unknown-ATS submission (F11); Chrome Web Store's elevated review for user-data-handling extensions could reject or stall it | High | F11's bounded-agent field-mapping validated against 15-20 real Greenhouse/Lever/Workday forms *before* Phase 5 exit, not assumed to work from the design alone. No extension-free fallback exists for Tier 3 capture — accepted risk, revisit only if CWS review is denied, not preemptively built |

## 11. Build order

**v1 ships one persona: Developer.** Richest ATS API coverage (Greenhouse/Lever/Ashby
skew tech-heavy), reuses the connectors already built, fastest path to a real reply-rate
number. Product Manager and Marketing personas are **gated on Developer proving
reply-rate lift** (§9's reply-rate targets actually hit, not just shipped) — they are not
built in parallel. This replaces the earlier "three portfolios at launch" framing in §2;
the persona *data model* stays multi-persona (§7), only the launch scope narrows.

| Phase | Contents | Exit criterion |
|---|---|---|
| **0. Foundation** | Alembic migrations, auth, multi-tenancy, tests, CI | Existing MVP data model migrated; every endpoint scoped to a user |
| **1. Facts & intake** | Resume upload, parsing, fact-review UI, Developer persona only | User can go from PDF to reviewed KB in under 5 min |
| **2. Ingestion at scale** | ATS discovery, 12 connectors, dedupe, background workers. **Gate: measured cost-per-application confirmed ≤ $0.40 before scaling ingestion volume** | 5,000+ live jobs from 500+ companies, deduped |
| **3. Match & research** | pgvector matching, explainability, agent-reach dossiers, **eval/feedback harness stood up (ADR-014) — Promptfoo + Langfuse Datasets, golden set of ≥30 JD/facts pairs** | Top-10 matches are ones the user agrees are good; eval harness can diff two prompt versions and report a pass/fail |
| **4. Tailor & export** | 3-pass engine, ATS-safe DOCX/PDF, parse-back check, **adversarial fixtures extended to dossier injection + `garak` scan added to CI** | Round-trip parse test green; zero high-severity flags on a 20-job sample; garak scan clean on both JD and dossier injection scenarios |
| **5. Review & submit** | Review queue, diff UI, extension autofill, **F11 field-mapping validated against 15-20 real ATS forms** | 20 applications submitted in one session, <10 min; F11 accuracy measured, not assumed |
| **6. Referral** | Person-finding, hook ranking, Gmail OAuth send, suppression | 10 referral asks sent, ≥1 reply, 0 complaints |
| **7. Track & learn** | Tracker, follow-ups, analytics, weekly digest, **scheduled scikit-learn recalibration job for match-score weights (ADR-014)** | Reply rate visible per source and per template; match weights are refit against real outcome data at least once |
| **8. PM/Marketing personas** | Only after Developer hits §9's reply-rate targets | Reuses the same pipeline with persona-specific prompts/weights, not a rebuild |

Phases 0–4 are the product. 5–7 are what make it worth paying for. Phase 8 doesn't start
on a calendar date — it starts when Phase 0-7's Developer-only numbers say the loop
actually works.

---

## Appendix A — Open questions

1. Pricing. Free tier with N applications/month, or flat monthly? Affects the model-cost cap design.
2. Do we host the browser extension in the Chrome Web Store from day one, or side-load for beta users?
3. Which company seed list feeds ATS discovery — YC directory, a public funding dataset, or user-submitted?
4. Does the user want one Facts KB shared across personas, or fully separate KBs? (Current design: shared facts, persona tags.)

## Appendix B — Related documents

- `docs/ARCHITECTURE.md` — system design, services, data flow
- `docs/SPEC.md` — module-level contracts and API surface
- `docs/DECISIONS.md` — architecture decision records
- `docs/DEPENDENCIES.md` — proposed dependencies, MCP servers, and skills (approval gate)
- `docs/CODE-REVIEW.md` — review of the existing MVP
- `docs/WORKLOG.md` — running change log and context-recovery doc
