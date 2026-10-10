# Handoff: scaling ApplyScout to ~100 users

Paste this whole file into another chat (GPT etc.) as context. Written 2026-10-10.

## Repo context (what the other chat needs to know)

- Monorepo: `apps/api` (FastAPI + SQLAlchemy + Alembic), `apps/web` (Next.js), `apps/extension` (Chrome MV3).
- Postgres on Neon, Redis Cloud (free tier, **30 client cap**, see `docs/GAPS.md` 5.3), RQ workers.
- Deploy: `docker-compose.deploy.yml` — services `api`, `worker` (queue `default`, 1 replica),
  `worker-background` (discovery/embeds), `worker-effects` (irreversible sends), `scheduler` (must stay exactly 1), `caddy`.
- Workers: `apps/api/workers/run_worker.py` uses `SimpleWorker` (one job at a time per process, no fork).
- Tailoring = `batch_prep.prepare_application_for_review` → `workers/jobs.py::prepare_applications_task`
  (tailor + truth-check, two LLM calls). LLM provider is **NVIDIA NIM** (`LLM_PROVIDER=nvidia`), not Anthropic.
- Gmail: `apps/api/outreach/gmail.py` — scope `gmail.send` only (+ `openid`, `email`). Refresh token encrypted via `crypto.py`.
  Endpoints already exist: `/gmail/authorize`, `/gmail/callback`, `/gmail/status`, `DELETE /gmail/connection`.
- Per WORKLOG: only two credentials block stage 8 — `APIFY_TOKEN` and a **Google Cloud OAuth client**.

## Part 1 — Google sign-in for Gmail sending

Correction to an older doc: `docs/PLAN-GMAIL-CREDENTIALS.md` calls `gmail.send` "restricted". It is a
**sensitive** scope (README already says so). Sensitive = verification needed, **no paid CASA security assessment**.
Please double-check this against Google's current scope table when you do it.

### What to do now (no review needed)
1. Google Cloud Console → new project → **APIs & Services → Library → enable Gmail API**.
2. **OAuth consent screen**: External, app name, support email, logo optional.
   Add scopes `openid`, `email`, `https://www.googleapis.com/auth/gmail.send`.
3. **Credentials → Create OAuth client ID → Web application.**
   Authorized redirect URI = your API's `/gmail/callback` URL on the real HTTPS domain (and a localhost one for dev).
   Put client id/secret in `apps/api/.env` (see variable names in `apps/api/core/config.py`) and set `ENCRYPTION_KEY`
   (a Fernet key: `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`).
4. Add each user's Gmail as a **Test user** (max 100). This works today with zero review.
5. Test the full connect → send flow with your own account.

### The catch with "Testing" mode
Refresh tokens issued to an app in **Testing** publishing status expire after **7 days**, so every user would have to
reconnect Gmail weekly. Options:
- **Publish to "In production" without verification**: tokens stop expiring, users see a scary
  "Google hasn't verified this app" screen (Advanced → Go to app), and Google caps the app at **100 users total, ever**
  (the count never resets). For exactly 100 users this is a workable stopgap.
- **Submit for verification** (below) to remove the warning and the cap. Do this in parallel, it takes time.

### Verification checklist (start early — days to several weeks)
- A **domain you own**, verified in Google Search Console, used as the app homepage.
- Public **privacy policy** page on that domain stating Gmail data use (we only send; we never read mail) and
  Google API Services User Data Policy / Limited Use compliance.
- Public homepage that explains the app, and an authorized-domains entry for it.
- **Scope justification** text: why `gmail.send` and nothing broader.
- A **demo video (YouTube, unlisted is fine)** showing: the OAuth consent screen with the client ID visible,
  the full flow, and how `gmail.send` is used in the product.
- Expect back-and-forth emails from the Google reviewer. Answer fast.

### Code/product tasks that help the review
- Settings page with a visible "Disconnect Gmail" (already built: `DELETE /gmail/connection`).
- Privacy policy + terms pages in `apps/web`.
- Make sure the app never asks for more than `gmail.send`.

## Part 2 — Tailoring throughput

Math: 100 users × 10 applications/day = up to 1,000 tailorings/day × 30–90 s = 8–25 worker-hours/day.
One worker cannot do that, and traffic is bursty (people click "prepare" at the same time).

### Steps
1. Edit `docker-compose.deploy.yml`: `worker` → `deploy.replicas: 4` (all on the `default` queue).
   Each replica is one Redis client; check the Redis Cloud client count first (free cap 30). Upgrade the plan if needed.
2. **Check the real bottleneck first — it's probably the LLM rate limit, not CPU.** NVIDIA NIM free/dev tiers have
   requests-per-minute limits; 4 workers × 2 calls per tailoring can hit them. Measure, add retry/backoff
   (see `providers/guard.py`), or move tailoring to a paid provider key. Voyage embeddings free tier is also slow.
3. Neon connection limits: 4+ workers each hold DB connections. Use Neon's pooled connection string and keep pool sizes small.
4. Cap per-user daily applications (campaign caps already exist) so one heavy user can't starve the rest;
   consider fair scheduling (round-robin per user) if the queue backs up.
5. Keep `worker-effects` (sends) and `worker-background` (discovery) separate, as they are now.
6. Run a load test: enqueue 200 fake preparations, measure p50/p95 queue wait and jobs/hour per worker, then size from data.
7. Add queue-depth + oldest-job-age monitoring (`observability.py`) and alert when wait exceeds, say, 10 minutes.

Rule of thumb: 4 workers → ~2–6 h of wall-clock each for 1,000 jobs/day. Realistically most users won't hit 10/day.

## Part 3 — Other useful work while Claude's tokens are out (until Monday)

Safe to do in any other chat or by hand:
- **Do Part 1 steps 1–5 yourself** (Google Cloud console work; no code needed beyond pasting env vars).
- Buy/pick the domain, set up Search Console, deploy (see `docs/PLAN-DEPLOY.md`).
- Draft the privacy policy, terms, homepage copy and the verification demo-video script.
- Get `APIFY_TOKEN` (the other stage-8 blocker).
- Production Anthropic key + run `eval/` — tailoring quality is currently **unmeasured** (GAPS 6.1).
- **First real owner-watched submission** through the extension (README section 6, step 1).
- Person-finder spike: for 20 real jobs, can we name a person and get a verified email? (README section 6, step 2.)
- SMTP credentials for digest / password reset (currently log to console).
- Recruit the test users and collect their Gmail addresses for the Test-user list.

## Suggested prompt for the other chat

"Here is my repo context and plan (paste this file). Help me (a) set up the Google Cloud OAuth client and consent
screen step by step, (b) write a privacy policy and OAuth verification submission text for a gmail.send-only app,
(c) review my docker-compose worker scaling and Redis/Neon/LLM-rate-limit limits."
