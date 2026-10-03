# Job Copilot

**Upload your resume once. Get matched jobs, tailored applications, and applications filled in from your own browser. Then get referrals from people inside the company, so you reach an interview and not a black hole.**

Job Copilot (the browser extension is called **ApplyScout**) is a multi-tenant web app that runs the whole job-search loop:

```
Resume ─▶ Facts KB ─▶ Campaign ─▶ Discover ─▶ Match ─▶ Tailor ─▶ Apply ─▶ Referral outreach ─▶ Interview
 upload    reviewed    "PM roles,   many job    score &   truth-    extension   (planned, not
 + parse   by you      India or     sources     explain   checked   fills the   built yet)
                       remote"                                      forms
```

The goal is simple: **get the user an interview.** Cold applications convert at about 2%. Referred ones convert at about 30%. So the product does two things at once. It applies well, and it gets a real person inside the company to look at the application.

> **Status in one line:** everything up to and including auto-apply is built and tested. Referral outreach (the cold-email step) is designed but **not built**. See [What works today](#what-works-today).

---

## The user flow

### 1. Upload your resume
You upload a PDF or DOCX. The app parses it into a **Facts KB**: 25–40 small, checkable claims such as *"Cut checkout API p99 latency from 1.4s to 180ms (Payments team, Acme, Q2 2025)"*.

You review and edit these facts on one screen. This screen matters most, because every document the app writes later can only use facts you confirmed. The resume file itself is never used as the source for generation.

### 2. Create a campaign
A campaign says what you are looking for: job titles (such as *product manager*, *product owner*), locations (such as *India*, *Remote*), and which sources to search. It also sets caps, and whether each application waits for your review (assisted) or goes out automatically within the cap.

The app doesn't match on titles alone. It scores each job against your **whole profile**:
- **Semantic match:** your facts compared to the job description using embeddings.
- **Skill coverage:** which required skills you have and which you lack (the "keyword gap").
- **Hard filters:** location and remote policy, seniority, visa or work-authorisation text, and remote roles restricted to another country.
- **Near-duplicate removal:** the same role listed on three boards shows up once.

Each match shows **why** it scored the way it did, for example "7 of 9 required skills matched, missing Kubernetes and Terraform". It never shows an opaque score.

### 3. Find jobs from many sources
Discovery pulls from public job APIs and feeds into one normalised, deduplicated job table:

| Kind | Sources |
|---|---|
| Company ATS boards | Greenhouse, Lever, Ashby |
| Aggregator APIs | Remotive, Reed |
| Keyless feeds | RemoteOK, Himalayas, Working Nomads, Jobicy, Arbeitnow, We Work Remotely |
| Search scraper (isolated) | JobSpy (Google, ZipRecruiter, Glassdoor). Currently returns nothing, pending a fix. |

LinkedIn is deliberately **not** scraped. It is parked as a later problem. See [`docs/DECISIONS.md`](docs/DECISIONS.md) (ADR-015).

### 4. Tailor each application (never fabricate)
For every job you choose, a three-step pipeline writes a tailored resume and cover letter:
1. **Tailor:** reorder and reword your real facts for this job description.
2. **Truth-check:** a second, independent model call checks the draft against your Facts KB. If it finds a claim your facts don't support, the application is blocked.
3. **Voice:** strips the usual AI filler so the text sounds like you.

The output is an ATS-safe, single-column DOCX. The app re-parses its own output to confirm the content survives a parser.

### 5. Auto-apply from your own browser
The **ApplyScout Chrome extension** fills and submits application forms inside your own browser session, using your IP and your logins. The server never submits anything for you.

- A server-side **planner** (Stagehand, read-only, behind a network guard that blocks every non-GET request) studies each job's form once and saves a fill plan. The plan holds no personal data.
- The extension executes the plan with your real data, checking each field after it writes it.
- **Assisted mode:** the extension fills, you press Send. **Automatic mode:** it sends within your daily cap.
- It handles multi-page forms (Workday-style "Next" flows) and stops with a clear message when it hits a sign-in wall. It never types a password.
- It **never** answers EEO or demographic questions, and never answers essay or "How did you hear about us?" questions by guessing. Those come from your saved answers, or it asks you.
- An application is marked *submitted* only when the employer's confirmation page says so.

### 6. Referral outreach (planned)
This is the step that turns an application into an interview. The design:

1. For a job you applied to, the app finds people at that company: the same role, a similar role, or someone more senior. Company research uses [agent-reach](https://github.com/Panniantong/agent-reach).
2. It finds a reachable email address from public sources.
3. It drafts a short note (120 words or fewer) in your own words: *"I found this role, I'm very interested, here is my profile."* Every claim comes from your Facts KB.
4. It sends from **your own Gmail** (OAuth), not from a shared domain. This keeps deliverability good, and keeps one user's mistakes from affecting anyone else.

Guardrails in the design: a hard cap of 10 emails a day, at most one follow-up, a global opt-out and suppression list, and ranking people by a real hook (same school, same previous employer, shared open-source work). Cold outreach with no hook is what gets Gmail accounts flagged, and it is also unpleasant for the recipient. The full spec is in [`docs/PRD.md`](docs/PRD.md) §6 F12 and ADR-003.

**Not built yet:** there is no Gmail OAuth, no person-finder, and no outreach table. Company research exists, but it only returns a basic dossier (GitHub repos and a web summary).

---

## What works today

Measured on the code in this repo (see [`docs/WORKLOG.md`](docs/WORKLOG.md) for the full log).

| Area | State |
|---|---|
| Accounts, multi-tenancy, password reset | ✅ Done. JWT auth, row-level security, every endpoint scoped to a user |
| Resume upload and parsing, Facts KB, fact review UI | ✅ Done |
| Onboarding (resume, facts, preferences, campaign) | ✅ Done |
| Campaigns | ✅ Done. Roles, locations, sources, caps, run and stats |
| Job discovery (ATS boards, feeds, Reed, Remotive) | ✅ Done. Runs on background workers with a scheduler |
| Matching and explanations | ✅ Done. Embeddings (Voyage AI), hard filters, skill gap, near-duplicate removal |
| Company research | 🟡 Basic. Only GitHub and web summary so far |
| Tailoring with truth-check, ATS-safe DOCX | ✅ Built. **Quality not yet measured at scale**, because the eval harness is waiting on a production Anthropic key |
| Review queue and application tracker (Kanban) | ✅ Done |
| Chrome extension: autofill and submit | ✅ Built. Tested on Greenhouse, Lever and Ashby. Workday multi-page flow is built but proven only on a local fixture |
| Daily digest and notifications | ✅ Built. Email needs SMTP credentials |
| **Referral outreach (cold email)** | ❌ **Not built.** Designed only |
| Real end-to-end submission by the owner | ⏳ Next milestone. No real application has been sent yet |

Tests: about 737 API tests and 132 extension tests pass at the last logged run.

### Known gaps and near-term next steps
1. **Run the first real, owner-watched submission** through the extension.
2. **Build referral outreach** (Gmail OAuth, person-finder, draft, send, suppression list).
3. Add SMTP credentials so digests and password-reset emails actually send.
4. Get a production Anthropic key, so the eval harness can measure tailoring quality.
5. Workday: button-style dropdowns, multi-selects, date pickers and "Add another" sections still stop and ask the user.
6. Only the Developer persona is planned for v1, and PM and Marketing personas come later. The author's own campaign is currently set up for PM roles in India or remote.

---

## Principles

1. **Never fabricate.** Every generated claim traces to a fact you confirmed. A second model call checks this, and unsupported claims block the application.
2. **Your identity, your reputation.** Applications go out from your browser. Emails (when built) go out from your Gmail.
3. **Bounded autonomy.** You approve a campaign once. The agent works inside its caps, and you get a digest of what went out.
4. **Boring, legal ingestion first.** Public APIs and feeds before any scraping.
5. **Sounds like a person.** Specific facts read as human. Generic enthusiasm doesn't.

---

## Architecture

```
Next.js web app ──REST──▶ FastAPI ──▶ PostgreSQL (+ pgvector, row-level security)
Chrome extension ────────▶   │   ──▶ Redis + RQ workers (discover, embed, prepare, plan forms)
                             └─────▶ Claude (tailor, truth-check) · Voyage (embeddings)
```

```
apps/api/         FastAPI backend
  connectors/       job sources (ATS boards, feeds, Reed, JobSpy), normalise and dedupe
  matching/         filters, embeddings, scoring, skill gap, near-duplicate detection
  tailoring/        tailor and truth-check pipeline
  parsing/          resume PDF/DOCX to Facts KB
  documents/        ATS-safe DOCX export and parse-back check
  formfill/         field mapping, deterministic fills, per-ATS schemas
  formplans.py      per-job fill plans from the planner
  research/         company dossier
  campaigns.py      campaign bounds and runs
  workers/          RQ worker and scheduler
  alembic/          database migrations
apps/web/         Next.js dashboard (onboarding, facts, campaign, matches, review, tracker, today)
apps/extension/   ApplyScout Chrome extension (Manifest V3): autofill, multi-page, verify
eval/             Promptfoo eval harness for tailoring and the truth-checker
tools/            Stagehand form planner, and a guarded browser-use harness (fills, never submits)
docs/             product and engineering docs (see below)
```

| Layer | Tech |
|---|---|
| Frontend | Next.js, TypeScript, Tailwind, shadcn/ui |
| Backend | FastAPI, SQLAlchemy, Alembic |
| Database | PostgreSQL 16 with pgvector (Neon in the author's setup) |
| Queue | Redis with RQ and rq-scheduler |
| AI | Anthropic Claude (tailoring), Voyage AI (embeddings), Stagehand (form planning) |
| Extension | Chrome MV3, Vite, TypeScript |

---

## Running it locally

```bash
cp .env.example .env     # set DATABASE_URL, REDIS_URL, JWT_SECRET, ANTHROPIC_API_KEY
                         # embeddings need a Voyage key; see docs/WORKLOG.md for the free-tier limits

docker compose up -d db redis

# API
cd apps/api
pip install -r requirements.txt
alembic upgrade head
uvicorn main:app --port 8000

# Background workers (needed for discovery, campaign runs and embeddings)
python -m workers.run_worker       # in a second terminal
python -m workers.run_scheduler    # in a third terminal

# Web
cd apps/web && npm install && npm run dev       # http://localhost:3000

# Extension
cd apps/extension && npm install && npm run build   # load dist/ as an unpacked extension
```

API docs: http://localhost:8000/docs

Tests: `cd apps/api && pytest` · `cd apps/web && npm test` · `cd apps/extension && npm test`

Without a running worker, **Run** and **Discover** return a 503 that says how to start one.

---

## Docs

Start with [`docs/WORKLOG.md`](docs/WORKLOG.md) for the current state. It is the running log, and the top section says where the project stands.

| Doc | What it is |
|---|---|
| [`docs/PRD.md`](docs/PRD.md) | What we are building and why: personas, journeys, features, metrics, build order |
| [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) | System design and module boundaries |
| [`docs/SPEC.md`](docs/SPEC.md) | Module contracts and API surface |
| [`docs/DECISIONS.md`](docs/DECISIONS.md) | Architecture decision records, including the pivot to auto-apply (ADR-015, ADR-016) |
| [`docs/DEPENDENCIES.md`](docs/DEPENDENCIES.md) | Third-party tools and the reasons for each |
| [`docs/LIVE-FORM-TEST.md`](docs/LIVE-FORM-TEST.md) | How auto-apply is tested against real forms |
| [`docs/harness-reports/`](docs/harness-reports) | Measured results from the form planner |

## Notes before you deploy or share this
- Check the licence of any third-party code you add. MIT and Apache are fine. AGPL code (such as AIHawk) is deliberately not used, and a repo with no licence isn't safe to reuse.
- Auto-applying from a user's browser carries Terms-of-Service and account risk on the job boards. That is an accepted product decision (ADR-015). Caps and the digest exist to bound it.
- This repo stores resumes and personal data. Before going public, confirm encryption at rest, hard delete on request, and no third-party analytics on profile pages.
