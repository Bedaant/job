# Apply Scout

**Upload your resume once. The app finds matching jobs, tailors your resume to each job, applies from your own browser, then drafts a referral email to someone inside the company. The goal is interviews, not just applications.**

Apply Scout (the browser extension is **ApplyScout**, the agent persona is **Maggie**) is a personal project built for the owner and about 5–7 friends. It is not a commercial product. We promise no interviews. We aim to raise the chance of a reply, and we measure it.

This README is the entry point for an engineer joining the repo. Read it top to bottom once, then use the [docs index](#8-the-docs-which-are-current-and-which-are-history) to find the rest.

---

## 1. Status, honestly (as of 2026-10-12)

| Area | State |
|---|---|
| Resume → Facts KB → campaign → discovery → match → tailor → review queue | Built and tested |
| Auto-apply through the Chrome extension | Built and tested. **No real, owner-watched submission has happened yet.** |
| Referral outreach (find a person, verify an email, draft, you approve, send from your Gmail) | Built and tested. Needs the owner's Apify token and a Google OAuth client to run for real |
| Row-level security in Postgres | Live on Neon (migrations 0010 and 0040) |
| Safety rails (send gate, daily caps, pause switches, supervisor, guard) | Built and tested |
| Deployment | **Not deployed.** The API, worker and scheduler run only while the owner's machine is on. Docker files exist (`Dockerfile`, `docker-compose.deploy.yml`, `Caddyfile`) but nothing runs from them yet |
| Tailoring quality | **Unmeasured.** The eval harness needs a provider it is not pointed at (see [`docs/GAPS.md`](docs/GAPS.md) 6.1) |

Tests at the last run: **API 1513 passed, 8 skipped** (SQLite in memory). **Web 159 passed.** **Extension 144 passed.** The Postgres lane (`api-postgres` in CI, or locally with `TEST_DATABASE_URL`) ran for the first time on PR #24 and failed 2 of 1520 tests, both bugs in the tests themselves (a UUID-versus-string comparison and a missing relationship attribute), not in the product. The fixes are on the branch; re-check CI. The cross-user isolation test did show RLS working: zero rows with no tenant set, one row per table once it is set.

Neon (the production database) is at Alembic revision **0040**.

What is open is listed in [section 9](#9-whats-left).

---

## 2. The loop

```
 ┌──────────┐   ┌──────────┐   ┌──────────┐   ┌──────────┐   ┌──────────┐
 │ 1 Resume │──▶│ 2 Facts  │──▶│3 Campaign│──▶│ 4 Find   │──▶│ 5 Match  │
 │  upload  │   │ review   │   │ (roles,  │   │  jobs    │   │ & explain│
 └──────────┘   └──────────┘   │ places)  │   └──────────┘   └────┬─────┘
                               └──────────┘                       │
 ┌──────────┐   ┌──────────┐   ┌──────────┐   ┌──────────┐        │
 │ 9 Learn  │◀──│ 8 Refer- │◀──│ 7 Apply  │◀──│ 6 Tailor │◀───────┘
 │ & track  │   │ ral email│   │ in your  │   │ + truth- │
 │          │   │          │   │ browser  │   │ check    │
 └──────────┘   └──────────┘   └──────────┘   └──────────┘
```

| # | Stage | What happens | Where it lives |
|---|---|---|---|
| 1 | Resume upload | PDF or DOCX is parsed. The raw file is **not stored**, only the parsed draft facts | `parsing/`, `routes/resume_facts.py`, `routes/profiles.py` |
| 2 | Facts review | The resume becomes 25–40 small checkable claims (the **Facts KB**). The user edits and confirms them. LinkedIn data-export import adds facts as *unconfirmed* | `models.ResumeFact`, `parsing/linkedin_export.py` |
| 3 | Campaign | Titles, locations, sources, a daily cap, and `auto_submit` (assisted: the user presses Send; automatic: it sends within the cap) | `campaigns.py`, `routes/campaigns.py` |
| 4 | Find jobs | Scheduled workers pull from many public sources into one deduplicated `jobs` table | `connectors/`, `workers/jobs.py` |
| 5 | Match | Each job is scored against the whole profile and explains why | `matching/` |
| 6 | Tailor | Rewrites the resume and cover letter from confirmed facts, then truth-checks the draft | `tailoring/engine.py`, `batch_prep.py`, `documents/` |
| 7 | Apply | A read-only server planner maps the form; the extension fills and submits it in the user's own browser | `formplans.py`, `formfill/`, `apps/extension/` |
| 8 | Referral email | Finds people at the company, ranks by a true connection, checks suppression, drafts. The user approves; it sends from the user's Gmail | `outreach/` |
| 9 | Track and learn | Kanban tracker, daily digest, "heard back?" prompts at 7 and 14 days | `outcomes.py`, `digest.py`, `apps/web/app/` |

### How matching works (stage 5)
Embedding similarity (Voyage, pgvector) is only **0.55** of the score. The rest is skill coverage (a set intersection, which is what makes "missing: Kubernetes" possible) and recency. Hard filters run first: location and remote policy, seniority, work-authorisation text, remote-but-country-limited. For campaigns, an LLM (`matching/role_judge.py`) decides whether a title is the role asked for; word rules only gather candidates. Near-duplicates (the same role on three boards) collapse to one.

### How tailoring works (stage 6)
1. **Tailor.** The model gets only the confirmed facts and the job. Every bullet must cite fact ids, enforced with Pydantic validation against the facts actually supplied, not by asking nicely.
2. **Truth-check.** A second, independent call compares the draft with the Facts KB. **It never sees the job description** (ADR-006), so an injected claim has nothing backing it. An unsupported claim blocks the application.
3. **Render.** An ATS-safe DOCX (single column, standard headings), re-parsed to prove the content survives a parser.

Job descriptions are fenced as data in the prompt, and `untrusted.py` stops hostile job text from being auto-sent.

### How applying works (stage 7)
- A Node tool (Stagehand, `tools/stagehand-harness`) reads each job's form once, **read-only**, and `formplans.py` stores the plan. A network guard blocks every non-GET request, and the plan holds no personal data.
- The extension runs the plan in the user's browser with the user's IP and logins. It verifies each field after writing it. **The server never submits.**
- It stops, and tells the user, at a sign-in wall. It never types a password, never answers EEO or demographic questions, and never invents essay answers. Those come from the **answer bank** (`answer_bank.py`: answer once, reuse) or it asks.
- A job counts as submitted only when the employer's confirmation page says so. Anything left `submitting` for 30 minutes becomes `submitted_unconfirmed` (never back to `approved`, because a retry could apply twice).
- Jobs whose apply link is `mailto:` are sent by `apply_email.py`, server-side, from the user's SMTP sender.

### How referral outreach works (stage 8)
`outreach/orchestrate.py` runs after an application goes out: find candidates (`sources_apify.py`, GitHub), rank by a connection that is actually true (`signals.py`), check suppression (`suppression.py`, fails closed), draft only from facts (`draft.py`), persist. Every refusal leaves a visible `skipped` row with a reason. The user approves each draft (`/outreach/{id}/approve`). Sending goes through the Gmail API with the user's own OAuth token (`gmail.py`, encrypted at rest by `crypto.py`), paced and capped, with a signed unsubscribe link (`optout.py`). A per-recipient advisory lock stops two workers both sending to an address that is at its cap.

---

## 3. Architecture in one page

```
                  ┌───────────────────────────────┐
  You ──────────▶ │ Web app (Next.js App Router)  │  onboarding, facts, campaign,
                  │ apps/web                      │  matches, review, today, tracker
                  └──────────────┬────────────────┘
                                 │ REST + SSE (/events)
 ┌──────────────┐   ┌────────────▼────────────────┐        ┌─────────────────────────┐
 │ ApplyScout   │◀─▶│ API (FastAPI)  apps/api     │◀──────▶│ Postgres + pgvector     │
 │ Chrome MV3   │   │ main.py + routes/ package   │        │ (Neon). Row-level       │
 │ apps/extens. │   │ auth, send gate, guard      │        │ security per user       │
 └──────────────┘   └────────────┬────────────────┘        └─────────────────────────┘
                                 │ enqueue
                    ┌────────────▼────────────┐   ┌──────────────────────────────────┐
                    │ Redis + RQ workers      │──▶│ Job sources (section 6)          │
                    │ queues: default,        │   ├──────────────────────────────────┤
                    │ background, effects     │──▶│ NVIDIA NIM (tailor, truth-check) │
                    │ + rq-scheduler          │   │ Voyage (embeddings)              │
                    └─────────────────────────┘   │ Apify, GitHub (contacts)         │
                                                  │ Gmail API, SMTP                  │
                                                  └──────────────────────────────────┘
```

Full detail, including tenancy and the send gate, is in [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md). The rules that shape everything:

1. **One database, one API, one queue.** No microservices.
2. **The server plans, your browser acts.** Submitting from the user's browser avoids captchas on server IPs and keeps personal data off server browsers.
3. **The Facts KB is the only source for generated text.** The resume file is never used to generate (ADR-009).
4. **Everything that reaches an employer or a recruiter goes through `send_gate.can_send`.** One gate, one status-transition table.
5. **Every outside call goes through `providers/guard.py`:** retries, rate limit, circuit breaker, daily USD cap. It fails open if Redis blips, because the workers run on Redis anyway.
6. **Tenancy is enforced twice:** in application code (every query is scoped by the resolved user) **and** by Postgres row-level security.

### Two database roles (read this before touching `database.py`)
| Engine | Role | RLS | Used by |
|---|---|---|---|
| `engine` / `SessionLocal` | owner (`DATABASE_URL`) | **bypassed** | Alembic, workers (`session_scope()`), `get_owner_db` (unauthenticated routes such as unsubscribe and the Gmail callback) |
| `app_engine` / `AppSessionLocal` | restricted (`APP_DATABASE_URL`) | **enforced** | Every authenticated request (`get_db`) |

`APP_DATABASE_URL` falls back to `DATABASE_URL` when unset, so on SQLite (tests) and a fresh machine nothing breaks, but then RLS is not actually exercised. The tenant is set per transaction with `set_config('app.current_user_id', …, true)` from `get_current_user`. Policies and the exact pattern are in migrations `0010` and `0040`.

---

## 4. Repo map

```
apps/api/                 FastAPI backend (Python 3.11)
  main.py                   61 lines: app, CORS, router includes. No endpoints
  routes/                   applications, campaigns, extension, feed (SSE, /today), matches,
                            profiles, resume_facts, _shared
  auth/                     signup, login, password reset (argon2id, JWT)
  core/                     config (Settings), deps (get_db, get_current_user, set_tenant),
                            security, grounding (never trust an LLM-cited id)
  models.py, schemas.py     SQLAlchemy models, Pydantic schemas
  database.py               the two engines (see above)
  alembic/versions/         migrations 0001–0040 (there is no 0036 or 0037)
  connectors/               job sources, normalise, dedupe, ATS detection (section 6)
  matching/                 filters, embeddings, scoring, skills, keyword gap, near-duplicate, role judge
  tailoring/                tailor + truth-check
  parsing/                  resume PDF/DOCX/LinkedIn export -> facts
  documents/                ATS-safe DOCX, parse-back check
  formfill/, formplans.py   field mapping, deterministic fills, per-job fill plans
  outreach/                 stage 8 (see section 2)
  providers/guard.py        the gate for outside calls
  send_gate.py              the gate for anything that reaches an employer; pause switches; sent_log
  supervisor.py             closes rows a crash left in `submitting`
  campaigns.py, batch_prep.py, apply_email.py, answer_bank.py, needs_input.py,
  outcomes.py, digest.py, account.py (delete my account), observability.py (/ops/health), crypto.py,
  untrusted.py              one module each, named for what they do
  events/                   transactional outbox, relay to Redis, SSE
  workers/                  run_worker.py, run_scheduler.py, jobs.py, outreach_tasks.py
  scripts/                  measure_campaign_yield.py (costs real money, asks first)
  tests/                    ~136 files, run on SQLite in memory
apps/web/                 Next.js dashboard (pages: onboarding, facts, campaign, matches, review,
                            applications, today, login, privacy, password reset)
apps/extension/           ApplyScout Chrome MV3 extension (Vite). Pure logic lives in *.mjs files
                            with node:test tests; the .ts files are thin glue
eval/                     Promptfoo eval for tailoring and the truth-checker
tools/                    stagehand-harness (the form planner), browser-use-harness (test only),
                            ats_token_probe.py
docs/                     see section 8
Dockerfile, docker-compose.yml (local db + redis), docker-compose.deploy.yml, Caddyfile
```

---

## 5. Run it locally

Needs Python 3.11, Node 22, Redis (and Docker Compose if you want a local Postgres).

```bash
cp .env.example apps/api/.env        # then fill in the values below

docker compose up -d db redis        # local Postgres 16 and Redis. Or point at Neon and Redis Cloud

cd apps/api
python -m venv .venv && .venv/Scripts/pip install -r requirements.txt     # Windows; use bin/ on Linux
.venv/Scripts/python -m alembic upgrade head
.venv/Scripts/python -m uvicorn main:app --port 8000        # API docs at http://localhost:8000/docs

.venv/Scripts/python -m workers.run_worker default          # terminal 2 (also: background, effects)
.venv/Scripts/python -m workers.run_scheduler               # terminal 3: recurring jobs

cd apps/web && npm install && npm run dev                   # http://localhost:3000
cd apps/extension && npm install && npm run build           # load dist/ as an unpacked extension
```

Without a running worker, **Run** and **Discover** return a 503 that says how to start one.

### Environment variables
Settings are defined in `apps/api/core/config.py` and read from `apps/api/.env`. `.env.example` lists only the first few, so use this table.

| Variable | Required | Notes |
|---|---|---|
| `DATABASE_URL` | yes | Owner role. Used by Alembic and workers |
| `APP_DATABASE_URL` | for RLS | Restricted role, no `BYPASSRLS`. Unset = falls back to the owner URL |
| `JWT_SECRET` | yes | **A real random value of 32+ characters.** Settings rejects placeholders, and Alembic loads Settings, so migrations fail without it. Also signs reset links, OAuth state and unsubscribe links |
| `ANTHROPIC_API_KEY` | yes (field exists) | May be a placeholder while `LLM_PROVIDER=nvidia`. Only the eval harness needs a real one |
| `LLM_PROVIDER`, `NVIDIA_API_KEY`, `NVIDIA_MODEL` | for tailoring | Production uses `nvidia` (nemotron-3-super) through NVIDIA NIM, not Anthropic |
| `REDIS_URL` | yes | Defaults to `redis://localhost:6379/0` |
| `VOYAGE_API_KEY` | for matching | No key = the embedding step does nothing |
| `ENCRYPTION_KEY` | for Gmail | Encrypts the Gmail refresh token. No key = refuses to store, never falls back to plaintext. Generate with `from crypto import generate_key` |
| `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET` | for Gmail | From the Google Cloud console. Consent screen stays in Testing mode |
| `APIFY_TOKEN`, `GITHUB_TOKEN` | optional | Contact sourcing. GitHub works anonymously at 60 requests/hour |
| `REED_API_KEY` | optional | Reed connector no-ops without it |
| `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `SMTP_FROM` | optional | Unset = digest and reset emails are only logged |
| `ALERT_EMAIL` | optional | The owner. Receives ops alerts, and is the only user allowed `GET /ops/health` |
| `API_BASE_URL`, `WEB_BASE_URL`, `CORS_ORIGINS` | prod | `API_BASE_URL` must be public before any outreach is sent, or recipients cannot unsubscribe |
| `DAILY_USD_CAP_APIFY`, `_VOYAGE`, `_LLM` | optional | Defaults $2, $1, $5 a day, enforced by `providers/guard.py` |
| `LANGFUSE_*` | optional | Tracing; no-ops without keys |
| `NEXT_PUBLIC_API_URL` | web | Where the web app finds the API |

Never commit `.env`. It is gitignored.

### Run the tests
```bash
cd apps/api
DATABASE_URL=sqlite:// APP_DATABASE_URL=sqlite:// .venv/Scripts/python.exe -m pytest -q -p no:cacheprovider   # ~1513 pass
cd apps/web && npm test && npx tsc --noEmit
cd apps/extension && npm test && npm run typecheck
```
The suite blocks the real network (`tests/conftest.py`), so no key is ever needed. For the Postgres lane, run `docker compose up -d db-test` (port 5433) and `TEST_DATABASE_URL=postgresql://… pytest -q`. CI (`.github/workflows/ci.yml`) runs four jobs: api (SQLite), api-postgres (pgvector, Alembic-migrated), web (vitest and `tsc`), extension (node:test and `tsc`).

> **Test-writing rule in this repo:** write the test first, watch it fail, then make it pass. Many tests were added after a production failure and carry the story in a comment. Read the comment before deleting a test.

---

## 6. Job sources

| Kind | Sources |
|---|---|
| Company ATS boards | Greenhouse, Lever, Ashby, Workday (ADR-018) |
| Aggregator APIs | Remotive, Reed |
| Keyless feeds | RemoteOK, Himalayas, Working Nomads, Jobicy, Arbeitnow, We Work Remotely |
| Search scrapers | JobSpy (Google, ZipRecruiter, Glassdoor; isolated venv), LinkedIn guest jobs and hiring posts (via Apify) |

Discovery stores **whole boards** (ADR-021). A job disappears when its source stops listing it, never by age (ADR-017). Campaign searches run as one union search, refreshed daily. Every connector returns the same `NormalizedJob`; one failing source never aborts the run.

India coverage has a measured ceiling (ADR-020). LinkedIn is not scraped from the server.

### What the scheduler runs
| Job | Every |
|---|---|
| embed backlog | 2 minutes |
| supervisor, ops alert check | 15 minutes |
| campaign sweep, form-plan sweep | hourly |
| discovery | 4 hours |
| daily digest | daily, just after UTC midnight |
| campaign searches refresh, canary | daily |

---

## 7. Safety rules

The owner accepts some account risk from auto-apply (ADR-015). Nothing guarantees no account is ever flagged. The rules keep volume low and the user in control.

- **One gate.** `send_gate.can_send` is called by every send path. It enforces the owner's global pause (`app_flags`), each user's own pause (`users.sends_paused`) and the readiness blockers (truth check flagged a claim, nothing grounded, an open question, no facts). It also owns the legal status transitions (an illegal one returns HTTP 409) and writes `sent_log`. Daily caps live next to the work they limit: `campaigns.remaining_quota` for applications, `outreach/send.py` for emails.
- **Applications:** daily cap, a digest of what went out, no re-applying to the same job, assisted mode for anyone who wants to press Send.
- **Email:** low daily volume, random spacing, no repeated text, an address is checked before send and again immediately before, a bounce, reply or opt-out suppresses that person, the unsubscribe link has no expiry on purpose. Plain text, no tracking pixels.
- **Truth:** no claim in any resume or email may lack support in the user's confirmed facts.
- **Never sent:** EEO and demographic answers, passwords, anything the model invented.
- **Privacy:** hard delete on request (`DELETE /account`), with a test that fails if a new table pointing at users is not listed for deletion. Refresh tokens are encrypted. No third-party analytics.
- **Self-healing:** the supervisor runs every 15 minutes. A preparation that fails 3 times stops retrying (`applications.prep_attempts`).

---

## 8. The docs: which are current and which are history

Start with this README, then [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md). Reach for the rest by need.

**Current. Keep these true.**

| Doc | Use it for |
|---|---|
| [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) | How the system is built today |
| [`docs/DECISIONS.md`](docs/DECISIONS.md) | Why it is built that way. ADR-001…022. Numbers are never reused |
| [`docs/GAPS.md`](docs/GAPS.md) | The open-items register. Each row says VERIFIED or DOC-CLAIM. Verify before acting; three entries have been wrong |
| [`docs/WORKLOG.md`](docs/WORKLOG.md) | The running log. **Ordering is mixed:** the 2026-10-12 entries are at the bottom, just above "Entry template"; older ones are newest-first near the top. Search by date |
| [`docs/NEXT-WORK-PLAN.md`](docs/NEXT-WORK-PLAN.md) | The 2026-10 work plan with done and open status |

**Plans. Each has a status line at the top.**

| Doc | Stages | State |
|---|---|---|
| [`docs/PLAN-JOB-COLLECTION.md`](docs/PLAN-JOB-COLLECTION.md) | COLLECT-A…F | Done (COLLECT-E rejected) |
| [`docs/PLAN-MULTI-ATS.md`](docs/PLAN-MULTI-ATS.md) | ATS-0…3 | ATS-0…2 done; plan routing is live for Greenhouse |
| [`docs/PLAN-GMAIL-CREDENTIALS.md`](docs/PLAN-GMAIL-CREDENTIALS.md), [`docs/PLAN-OUTREACH.md`](docs/PLAN-OUTREACH.md) | REACH-A…E | Built; waiting on the owner's credentials |
| [`docs/PLAN-DEPLOY.md`](docs/PLAN-DEPLOY.md) | DEPLOY-A…D | First-boot fixes done; image written; not deployed |

Always write the stage prefix (COLLECT-, ATS-, REACH-, DEPLOY-). A bare "Phase N" is ambiguous in this repo and stalled a session once.

**Historical. Read for context, do not treat as the spec.**

| Doc | Why it is old |
|---|---|
| [`docs/PRD.md`](docs/PRD.md), [`docs/SPEC.md`](docs/SPEC.md) | Written 2026-08-15, before the pivot to auto-apply (ADR-015). Good for intent and original contracts. Endpoint and table lists have moved on. Each carries a banner |
| [`docs/CODE-REVIEW.md`](docs/CODE-REVIEW.md) | A review of the original MVP. The blockers it lists were fixed |
| [`docs/DEPENDENCIES.md`](docs/DEPENDENCIES.md) | The approval gate for third-party tools (ADR-010). The "nothing installed" status line is out of date; the licence reasoning is still the reference |
| [`docs/LIVE-FORM-TEST.md`](docs/LIVE-FORM-TEST.md), [`docs/harness-reports/`](docs/harness-reports), [`docs/smartrecruiters-decision-brief.md`](docs/smartrecruiters-decision-brief.md) | Dated measurements and a decision brief |
| [`docs/diagrams/`](docs/diagrams) | Interactive diagrams, drawn from the docs, not checked against code. Parts show outreach as planned |

If a doc and the code disagree, the code is right. Fix the doc.

---

## 9. What's left

**Code, in priority order**
1. **Proof of submission:** capture the employer's confirmation as evidence on the application.
2. **The extension uploads the tailored resume and cover letter** instead of the generic resume (`NEXT-WORK-PLAN.md` item 14).
3. **Feed outcomes back into ranking.** A suggestion, not a committed item: the 7/14-day "heard back?" answers are collected but nothing reads them yet.
4. **Workday gaps:** button-style dropdowns, multi-selects, date pickers and "Add another" sections still stop and ask the user.
5. **A Postgres CI lane that gates merges,** and a Postgres test for the Gmail callback upsert under RLS `WITH CHECK`.

**Owner-only**
- A first real, owner-watched submission through the extension.
- Deploy the worker and scheduler off the laptop (`docs/PLAN-DEPLOY.md`).
- Google OAuth verification (needed beyond about 80 users), `APIFY_TOKEN`, a Google OAuth client.
- Rewrite git history for the old `facts.json` (it is public on `origin/main`).
- A legal read of the terms-of-service and email-law exposure before sharing wider.
- A real tailoring-quality measurement (point the eval at the production provider).

## 10. Before you share this wider
- Check the licence of any third-party code you add. MIT and Apache are fine. AGPL and no-licence code are not. Never add a dependency without the owner's approval (ADR-010).
- Auto-applying from a user's browser carries terms-of-service and account risk on job boards. That is an accepted decision (ADR-015). Caps and the digest bound it.
- Beyond friends, Google's OAuth verification, email-law compliance (CAN-SPAM, GDPR, India's DPDP) and a paid-provider plan become required work.
