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

### 4. Tailor each application to the job's ATS (never fabricate)
Before each application, the app reads the job description and rewrites your resume to match what that employer's ATS and recruiter are looking for:

- **Title alignment:** if you are a *Product Manager* and the job says *Technical Product Manager*, the app notices the gap and uses the job's wording where your real experience supports it.
- **Skill alignment:** it pulls the skills and keywords the job description asks for and puts the ones you actually have in your skills section and bullets, in the job's wording (the keyword gap).
- **ATS-safe layout:** single column, standard section names, no tables or text boxes.

A three-step pipeline does this:
1. **Tailor:** reorder and reword your real facts for this job description.
2. **Truth-check:** a second, independent model call checks the draft against your Facts KB. If it finds a claim your facts don't support, the application is blocked. So "Technical Product Manager" is only written when your facts back it up, and a skill you don't have is flagged as a gap and never added.
3. **Voice:** strips the usual AI filler so the text sounds like you.

The output is a DOCX. The app re-parses its own output to confirm the content survives a parser.

### 5. Auto-apply from your own browser
The **ApplyScout Chrome extension** fills and submits application forms inside your own browser session, using your IP and your logins. The server never submits anything for you.

- A server-side **planner** (Stagehand, read-only, behind a network guard that blocks every non-GET request) studies each job's form once and saves a fill plan. The plan holds no personal data.
- The extension executes the plan with your real data, checking each field after it writes it.
- **Assisted mode:** the extension fills, you press Send. **Automatic mode:** it sends within your daily cap.
- It handles multi-page forms (Workday-style "Next" flows) and stops with a clear message when it hits a sign-in wall. It never types a password.
- It **never** answers EEO or demographic questions, and never answers essay or "How did you hear about us?" questions by guessing. Those come from your saved answers, or it asks you.
- An application is marked *submitted* only when the employer's confirmation page says so.

### 6. Referral outreach after you apply (planned, not built)
Once an application is submitted, the app reaches out to people already inside the company to ask for a referral:

1. **Pick who to contact.** For the role you applied to, find people at that company in the same function who can help. If you applied as a Developer I, that means a Developer II or III or an Engineering Manager. Company research uses [agent-reach](https://github.com/Panniantong/agent-reach).
2. **Find and verify an email.** Get a candidate address, then check it with an SMTP/MX email verifier before sending, so you don't bounce.
3. **Write it.** A short note (120 words or fewer): *"I applied for this role and I'm very interested. Here is my profile."* Every claim comes from your Facts KB.
4. **Send from your own Gmail** (OAuth), not from a shared domain.

**What the research found** (agent-reach and email verification):

| Piece | Finding |
|---|---|
| agent-reach (MIT) | A reader for the web, GitHub, Twitter/X, Reddit, RSS and more. For LinkedIn it reads public pages through Jina Reader, or profile details through a separate `mcp-server-linkedin`. It does **not** give you a list of employees with emails. Cookie or login access carries account-suspension risk, and its own docs advise a secondary account. |
| Email verification | Open-source options: AfterShip `email-verifier` (Go, MIT), `email-validator-js` (Node). They check syntax, MX records and, where the server allows, SMTP. `check-if-email-exists` is AGPL-3.0 (or paid commercial), so avoid it, in line with this project's AGPL rule. |
| Limits of verification | Outbound port 25 must be open, and many hosts block it. Catch-all domains accept any address, so a "valid" result isn't proof. Big providers often won't confirm a mailbox. Expect "risky" or "unknown" results, not certainty. |
| Finding the person | Public LinkedIn pages and search results can name people. An email still has to come from somewhere else: a public source, a pattern guess (`first.last@company.com`) that you verify, or a paid email-finder API. Logged-in LinkedIn scraping puts the user's account at risk and is parked by ADR-015. |

**Guardrails in the design:** a hard cap of 10 emails a day, at most one follow-up, an opt-out and suppression list, and sending only to people who match the role and seniority above. Full spec in [`docs/PRD.md`](docs/PRD.md) §6 F12 and ADR-003.

**Not built yet:** Gmail OAuth, the person-finder, the email verifier, the outreach table and the send step. Company research exists, but it only returns a basic dossier (GitHub repos and a web summary).

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
