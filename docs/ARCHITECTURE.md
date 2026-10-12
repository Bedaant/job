# Job Copilot — Architecture

- **Status:** Current. Rewritten 2026-10-12 to match the code. The 2026-08-15 draft had drifted (Better Auth, S3 storage, a 3-pass tailor, "no RLS"). That draft is in git history.
- **Read first:** `README.md` (what it is, how to run it, what is done and open).
- **Why each choice:** `docs/DECISIONS.md` (ADR-001 to ADR-022).

---

## 1. Shape of the system

One Postgres, one FastAPI app, one Next.js app, one worker pool plus a scheduler, one Chrome
extension. No microservices, no event bus. At the scale this product can plausibly reach, a
well-indexed Postgres and a queue is the right answer.

```
                      ┌───────────────────────────┐
   Browser  ─────────▶│  Next.js (App Router)     │   apps/web
   (user)             │  review UI, onboarding    │
                      └────────────┬──────────────┘
                                   │ REST/JSON + SSE (GET /events)
                      ┌────────────▼──────────────┐
   Chrome  ──────────▶│  FastAPI                  │◀──── Gmail OAuth (user's own account)
   extension          │  apps/api (routes/ pkg)   │
   (ApplyScout)       └──┬─────────┬──────────┬───┘
                         │         │          │
              ┌──────────▼──┐ ┌────▼─────┐   (no object store: the raw
              │ Postgres 16 │ │  Redis   │    resume file is never kept)
              │ + pgvector  │ │ RQ queues│
              │ (Neon in    │ │ + cache  │
              │  prod)      │ └────┬─────┘
              └─────────────┘      │
                      ┌────────────▼──────────────┐
                      │ RQ worker(s) + scheduler  │
                      │ queues: default,          │
                      │ background, effects       │
                      └────────┬──────────────────┘
                               │
        ┌──────────────────────┼──────────────────────────┐
   NVIDIA NIM (LLM)     Voyage (embeddings)     Job sources: Greenhouse, Lever, Ashby,
   tailor, truth-check  matching, dedupe        Workday, feeds, JobSpy, Reed, Remotive,
                                                LinkedIn (Apify), Apify contact lookup
```

The server never submits an application. All form automation runs in the user's own Chrome
session on pages the user can see (ADR-002). The only server-side browser use is a read-only
Stagehand planner that reads a form and returns a plan.

## 2. Stack as built

| Layer | Choice |
|---|---|
| Web | Next.js App Router, TypeScript, Tailwind, shadcn/ui (`apps/web`) |
| API | FastAPI + Pydantic v2, SQLAlchemy 2 (`apps/api`) |
| DB | Postgres 16 + pgvector (Neon in prod); SQLite in memory for the fast test lane |
| Migrations | Alembic, `apps/api/alembic/versions`, 0001 to 0040 (there is no 0036 or 0037) |
| Queue | Redis + RQ + rq-scheduler |
| Auth | Custom: argon2id passwords, JWT. `auth/router.py`, `core/security.py`. Not Better Auth. |
| LLM | NVIDIA NIM (nemotron-3-super) through the OpenAI-compatible client and `instructor`. Not Anthropic. |
| Embeddings | Voyage |
| Extension | Chrome MV3, Vite, pure logic in `.mjs` files tested with `node:test` (`apps/extension`) |
| Files | None stored. The uploaded resume is parsed, facts are extracted, the raw file is discarded. Tailored DOCX/PDF are rendered on demand. |
| Deploy | `Dockerfile`, `docker-compose.deploy.yml`, `Caddyfile` are written. Nothing is deployed yet. |

## 3. Module map (`apps/api`)

A module owns its tables and exposes functions; other modules call the function.

```
main.py              app construction, router registration, middleware
routes/              HTTP routes, split out of main.py (2026-10). Behaviour unchanged.
  applications.py  campaigns.py  extension.py  feed.py  matches.py
  profiles.py      resume_facts.py  _shared.py
auth/router.py       signup, login, reset, current user
core/                config.py (Settings), deps.py (get_current_user, tenant), security.py,
                     grounding.py
database.py          the two engines and sessions (see section 6)
models.py  schemas.py  alembic/
parsing/             resume + LinkedIn export + JSON Resume parsing, LLM extract
matching/            hard filters, embeddings, scoring, keyword gap, near-duplicate, role judge
connectors/          one file per job source, plus pipeline.py (upsert), normalize.py,
                     discovery.py, apply_target.py (which ATS an apply URL belongs to)
tailoring/engine.py  tailor pass + truth-check pass (section 4.3)
documents/           DOCX render, ATS-safety rules, parse-back check
formfill/            ATS field schemas, deterministic mapping, LLM field mapping
formplans.py         read-only form planner output, plan sweep
answer_bank.py  needs_input.py   saved answers and "ask the user" prompts
send_gate.py         the single gate every send goes through (section 5)
apply_email.py       email applications (SMTP or Gmail)
campaigns.py         campaigns, remaining_quota, campaign-search refresh
outreach/            contacts, draft, gmail, send, signals, opt-out, suppression, orchestrate,
                     Apify contact source, api (routes incl. the public unsubscribe)
research/            company research
providers/guard.py   retries, rate limit, circuit breaker, daily USD cap per provider
supervisor.py        stuck-row repair (every 15 min)
observability.py     ops alerts
digest.py  outcomes.py  account.py  crypto.py  untrusted.py  pii/
events/              outbox.py, relay.py, run_relay.py, sse.py
workers/             jobs.py, outreach_tasks.py, run_worker.py, run_scheduler.py
```

Other top-level directories: `apps/web` (UI), `apps/extension` (Chrome extension), `eval/`
(promptfoo golden-set harness for tailoring), `tools/`.

### The connector contract

A connector is one function that returns a list of plain dicts. It does not touch the
database. `connectors/pipeline.py` owns persistence (batched upsert, content-hash change
detection, source-trust ordering, cross-source collapse by `canonical_hash`). A connector that
raises is caught and logged by source name; one dead source does not stop the others. Calls
to external APIs go through `providers/guard.py`.

Dict keys, as Greenhouse returns them: `source`, `board_token`, `external_id`, `title`,
`company`, `location`, `remote`, `salary`, `description`, `apply_url`, `tags`, `posted_at`.
(The 2026-08 draft specified a `NormalizedJob` Pydantic model; it was never built.)

## 4. Data flow

### 4.1 Collection (scheduled, every 4 hours)

```
rq-scheduler tick
  → for each configured source/board: connector fetch (through guard.call)
  → normalize (location, posted_at) → canonical_hash(company, title, location)
  → upsert_jobs: insert / update-if-content-changed / collapse duplicates across sources
  → delisting sweep per board (jobs no longer on the board are marked gone)
  → embed backlog job (every 2 min) fills pgvector embeddings for new rows
```

### 4.2 Matching

Hard filters in SQL (location, salary, seniority, freshness, excludes), then a vector score
against the user's profile, a skill/keyword gap, a near-duplicate check and a role judge.
Each match keeps its score breakdown so the UI can say why. See `matching/service.py`.

### 4.3 Tailoring (async)

```
POST /applications/{id}/prepare → enqueue → worker (tailoring/engine.py, tailor_application)
  pass 1: tailor — summary, 4–6 bullets each citing fact ids, cover letter,
          from the Facts KB only (ADR-009), steered by the JD keyword gap
  pass 2: truth-check — audits every claim against the Facts KB.
          It is deliberately blind to the job description (ADR-006), so an injected
          claim in a JD has nothing backing it and is flagged.
  deterministic_unsupported(): number/entity check that does not trust the model
  split_gate_findings(): decides which findings BLOCK and which are advisory
  render DOCX → parse-back check (documents/) → application ready for review
```

Prep retries are capped at 3 (`applications.prep_attempts`, migration 0039). Results are
cached by a hash of prompt and inputs. Traces go to Langfuse with PII redacted first.

### 4.4 Applying

```
user approves in the UI → application "approved"
extension asks the API for the queue → opens apply_url in the user's tab
  → formfill: ATS-specific schema + deterministic mapping + API-supplied plan
  → fills fields; stops on anything unmapped or needing input
  → user clicks submit (the extension never submits for them)
  → extension reports the result → status moves through send_gate's transition table
```

Statuses that matter: `submitting` rows older than 30 min become `submitted_unconfirmed`
(supervisor). Proof of submission is NOT built yet (NEXT-WORK-PLAN P1-9).

### 4.5 Outreach (REACH-A to E, built, not exercised live)

```
campaign → contacts (Apify lookup, signals) → draft → user approves
  → send_gate.can_send → outreach/send.py → Gmail API as the user, or SMTP
  → sent_log row; suppression and opt-out checked at send time
public unsubscribe link → HMAC token → get_owner_db route (section 6)
```

Two limits are enforced in different places, so do not look for them in one file:
the per-campaign `remaining_quota` (campaigns, `outreach/send.py`) and a cap of 2 cold notes
per recipient address per day across all users, taken under
`pg_advisory_xact_lock(hashtext(lower(email)))`. `send_gate` does not enforce a daily cap.

### 4.6 Events: outbox + SSE replay

State changes write an `events` row in the same transaction. `events/relay.py` (run by
`events/run_relay.py`) publishes unpublished rows to Redis with `FOR UPDATE SKIP LOCKED`.
`GET /events` (`routes/feed.py`, `events/sse.py`) replays rows after `Last-Event-ID`, then
streams live. A browser that reconnects loses nothing.

## 5. Safety layers

| Layer | Where | What it stops |
|---|---|---|
| Send gate | `send_gate.py` | `can_send` checks the global pause (`app_flags`), the user's pause (`sends_paused`) and readiness blockers. It also owns the status transition table (an illegal transition returns 409) and writes `sent_log`. |
| Quotas | `campaigns.remaining_quota`, `outreach/send.py` | Daily send volume; 2 cold notes per address per day. |
| Provider guard | `providers/guard.py` | Retries, rate limit, circuit breaker, daily USD cap per provider (defaults Apify $2, Voyage $1, LLM $5). Fails open on Redis trouble. |
| Truth-check | `tailoring/engine.py` | Invented claims in generated documents. |
| Supervisor | `supervisor.py` | Rows stuck in `submitting`. Runs every 15 min. |
| Ops alerts | `observability.py` | Sends an alert on bad conditions. Runs every 15 min. |
| Untrusted text | `untrusted.py` | Job descriptions are data, fenced from instructions. |
| Tenancy | section 6 | One user reading another's rows. |

## 6. Multi-tenancy: two layers (ADR-022, supersedes ADR-007)

Layer 1, application code. Every route resolves the user with `get_current_user`; every query
is scoped to that user. A test generated from the route table asserts cross-user 404s.

Layer 2, Postgres row-level security. `ENABLE` + `FORCE ROW LEVEL SECURITY` with a
`tenant_isolation` policy on `app.current_user_id`. Migration 0010 covered the core tables;
migration 0040 added `contacts`, `outreach`, `gmail_credentials` and `fill_snapshots`. Neon is
at 0040 (verified by readback, 2026-10-12).

The API holds two engines (`database.py`):

| Engine | Role | RLS | Used by |
|---|---|---|---|
| `app_engine` / `AppSessionLocal` (`APP_DATABASE_URL`) | `job_copilot_app` | enforced | `get_db`: every authenticated request |
| `engine` / `SessionLocal` (`DATABASE_URL`) | `neondb_owner` | bypassed | Alembic, workers (`session_scope()`), `get_owner_db` |

`get_current_user` sets the tenant per transaction with
`set_config('app.current_user_id', …, true)`; `_reapply_tenant` re-applies it after a commit.
With no tenant set, the app role sees zero rows. The Gmail OAuth callback sets the tenant from
its signed state. The public unsubscribe route is the only web route on the owner role, and its
HMAC token authorises its one write.

Trap: `APP_DATABASE_URL` falls back to `DATABASE_URL` when unset. A deploy that forgets it
silently runs without RLS. Any scratch API or test that writes must override both URLs or it
writes to the real database.

## 7. Security posture

| Surface | Control |
|---|---|
| Passwords | argon2id (`core/security.py`) |
| Sessions | JWT; `jwt_secret` must be random, 32+ characters |
| Gmail tokens | Encrypted at rest with `encryption_key` (`crypto.py`), never returned by an endpoint |
| Extension ↔ API | Per-install token bound to the user |
| LLM input | Job text is untrusted and fenced; the truth-check never sees it |
| PII in traces | `pii/redact.py` before anything goes to Langfuse |
| Secrets | Env only. `.env.example` lists only a few keys, so read `core/config.py` for the full set. |
| Known gap | A secret-bearing file (`facts.json`) is removed from the tree but still in git history (NEXT-WORK-PLAN P0-4). Owner decision. |

## 8. Observability

Ops alerts every 15 min, a daily digest, a daily canary, and `providers/guard.py` spend
counters. Tailoring is traced in Langfuse. Per-source ingestion health is recorded in the
`connector_runs` table (`models.ConnectorRun`).

## 9. Environments and tests

| Env | State |
|---|---|
| Local | Run API, worker, scheduler, web by hand against Neon or a local Postgres + Redis. Steps are in `README.md`. |
| Test | `apps/api`: SQLite in-memory, 1513 pass / 8 skip. Opt-in Postgres lane via `TEST_DATABASE_URL` (service `db-test`, port 5433). Web vitest 159. Extension node:test 144. |
| CI | `.github/workflows/ci.yml`, 4 jobs: api (SQLite), api-postgres (pgvector pg16, Alembic-migrated), web, extension. |
| Prod | Neon Postgres and Redis Cloud are hosted and in use. The API, worker, scheduler and web are not deployed. DEPLOY-A first-boot fixes are done; image and compose are written (`docs/PLAN-DEPLOY.md`). |

## 10. What this architecture deliberately does not have

- No microservices, no GraphQL, no separate vector database, no Kafka, no Temporal.
- No server-side form submission (ADR-002).
- No stored resume files.
- No generated `packages/api-client`; the web app and extension keep their own typed clients.

---

## Related documents

`README.md` · `docs/DECISIONS.md` · `docs/NEXT-WORK-PLAN.md` · `docs/WORKLOG.md` ·
`docs/GAPS.md` · `docs/PLAN-DEPLOY.md`. Historical: `docs/PRD.md`, `docs/SPEC.md`,
`docs/CODE-REVIEW.md`.
