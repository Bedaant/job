# Plan: deployment (DEPLOY-A…D)

**Status:** not started. Closes `GAPS.md` 5.1, which is now the largest open item — stage
8 works, Gmail OAuth works, and 147 India roles are reachable, but none of it runs when
the owner's laptop is closed. *"Maggie works while you sleep"* is the one product claim
in `README.md` that is currently false.

**Stage prefix.** `DEPLOY-*`, per the naming convention in `PLAN-JOB-COLLECTION.md`.
Never write a bare "Phase N".

**Decisions, owner 2026-10-09.** A single small VPS running docker-compose, and the
Stagehand browser planner **deferred** rather than containerised.

---

## What actually has to run

| process | command | why it must be server-side |
|---|---|---|
| **API** | `uvicorn main:app` | the extension and the web app talk to it; the Gmail OAuth callback and the public unsubscribe route must be reachable |
| **Worker** | `workers/run_worker.py` | discovery, embedding, tailoring, outreach drafting and sending all run here |
| **Scheduler** | `workers/run_scheduler.py` | hourly discovery, the 2-minute embed backlog, the campaign sweep, the daily digest |

**Already hosted — nothing to deploy:** Postgres is Neon, Redis is Redis Cloud. The
existing `docker-compose.yml` at the repo root runs *local dev* copies of both and is not
a deployment artefact; the deployment compose file is a separate thing and must not be
confused with it.

**Consequence worth stating:** no state lives on the box. That makes it disposable — a
rebuild costs nothing but time, and there is no backup story to get wrong.

---

## DEPLOY-A — the five things that break on first boot

Each of these is a real break, found by reading the code rather than discovered after a
failed deploy. Three of them fail **silently**, which is why they are listed first.

### 1. `_JOBSPY_PYTHON` hardcodes a Windows interpreter path — **FIXED 2026-10-09**

`connectors/jobspy_connector.py:28` builds `.venv-jobspy/Scripts/python.exe`. On Linux
that is `bin/python`. `subprocess.run` raises `FileNotFoundError`, the connector logs it
and returns `[]` — so **JobSpy silently contributes nothing**, which is exactly the
failure shape GAPS 3.2 just spent weeks being unexplained by.

Fixed: `_jobspy_python()` resolves `Scripts/python.exe`, `bin/python` or `bin/python3` by
what EXISTS, and a missing venv now logs that it is missing rather than returning `[]`.

### 2. `gh` CLI is a runtime dependency, not a dev convenience

Both `outreach/contacts.py::GitHubContactSource` and `research/company_research.py` shell
out to `gh`. A container has no `gh` and no authenticated account, so **free contact
sourcing dies silently** — `GitHubContactSource` returns `[]`, which the engine correctly
reads as "nobody found" and records as a skip. Indistinguishable from a company genuinely
having no public members, which is the measured normal case.

**FIXED 2026-10-09** — now calls `api.github.com` directly with `httpx`. One fewer
binary, one fewer auth mechanism, and the 403/empty distinction is explicit the way the
JobSpy fix made it.

**And a correction to this plan's own earlier claim.** It said anonymous access "works at
GitHub's 60 req/hour — fine for a handful of lookups". **That is wrong.** Measured: on an
anonymous request `GET /users/{login}` returns `email: None` for **every** user, including
those who publish one — the field is only populated when authenticated. So without a
token the adapter finds nobody, every time, and the earlier 12-of-25 razorpay figure was
taken through an authenticated `gh`.

**`GITHUB_TOKEN` is therefore mandatory, not an optimisation.** The adapter now refuses to
spend a request without one and logs that it is a missing credential rather than an empty
company. Verified with a token: razorpay 3 candidates / 3 emails, zerodha 3/3 — identical
to the pre-rewrite numbers.

### 3. The extension points at `http://localhost:8000` — **FIXED 2026-10-09**

`apps/extension/manifest.json:10` — `host_permissions`. Chrome requires HTTPS for any
non-localhost host, so a deployed API was unreachable from the extension entirely,
failing with a permissions error rather than anything naming the cause.

Fixed: `host_permissions` now lists `https://api.applyscout.in/*` alongside localhost, and
`apiConfig.ts` reads `VITE_API_BASE_URL` at build time instead of hardcoding localhost
with a comment conceding production was unsolved. `src/deployConfig.test.mjs` pins both
halves, plus that no production host is granted over plain HTTP — the extension sends the
user's bearer token over it. Still needs a reissued extension build with the var set.

### 4. `API_BASE_URL` is still localhost — **GUARDED 2026-10-09**

**This is a hard gate, not a nice-to-have.** Every outreach email carries an unsubscribe
link built from `api_base_url`. Pointing at localhost means **a recipient cannot opt out**
— the one thing REACH-E exists to guarantee.

Now enforced in code rather than trusted to a checklist: `claim_outreach` refuses with
`unsubscribe_unreachable` when `api_base_url` is a local address and the recipient is not
the operator. Refused at CLAIM time, because once the mail has gone the dead link is
already in someone's inbox. The operator's own address stays exempt so delivery can be
proven before deploying — which is exactly how today's two live sends were done. The row
is left `approved`, not failed: it is a configuration problem and should send once the URL
is public.

### 5. `gmail.send`'s redirect URI is environment-specific — **SELF-DIAGNOSING 2026-10-09**

`outreach/gmail.py::_redirect_uri` builds from `api_base_url`, so deploying changes it —
and Google requires an **exact** match. The production URI has to be added to the OAuth
client's authorized redirect list alongside the localhost one, or connecting breaks with
`redirect_uri_mismatch`. Keep both: localhost for development, the domain for production.

---

## DEPLOY-B — the image

One image, three services, differing only by command. Python 3.11 slim base.

**Deliberately NOT in the image**, which is what keeps it under ~1GB instead of ~3GB:

- **Chromium and the Stagehand harness.** Form planning stays local by the owner's
  decision. The cost is honest and should be written where a user sees it: newly
  discovered jobs have no fill plan until the planner is run locally, so auto-apply
  covers the jobs already planned. Everything that must run *unattended* — discovery,
  embedding, matching, tailoring, truth-check, outreach, the digest — is server-side.
- **The `browser-use-harness`**, for the same reason.

**Must be in the image, and each costs real space:**

- `en_core_web_lg` (~400MB) for presidio. `pii/redact.py` loads it at import, so the API
  cannot start without it — it is not optional even though `redact_pii` currently has no
  production callers (GAPS 5.8).
- The second venv for JobSpy, because its `numpy==1.26.3` pin conflicts with this app's
  2.x. Built in the image, not at runtime.

**RQ gets simpler on Linux, and this is worth knowing rather than cargo-culting:**
`run_worker.py` uses `SimpleWorker` and `TimerDeathPenalty` purely because Windows has no
`os.fork` and no `SIGALRM`. On Linux the default `Worker` works, with real process
isolation per job and SIGALRM timeouts. **Do not change it as part of this deploy** —
change it separately, with the suite green, so a worker-model change is never tangled
with a first deploy. Note it and move on.

---

## DEPLOY-C — TLS and the domain

`applyscout.in` already resolves, so the prerequisite exists.

**Caddy** in front, for automatic TLS — one line of config per host and it renews by
itself. Nginx plus certbot is the alternative and is strictly more moving parts for the
same result.

Routes that must be publicly reachable:

| path | why |
|---|---|
| `/gmail/callback` | Google redirects a browser here |
| `/outreach/unsubscribe/{token}` | a recipient with no account must reach it |
| the rest of the API | the extension and web app |

**The unsubscribe route is the one with a real consequence if it is wrong**, and it is
also the only route that must work for someone who is not a user.

---

## DEPLOY-D — secrets, and the one that is different

`apps/api/.env` currently holds: `DATABASE_URL`, `APP_DATABASE_URL`, `REDIS_URL`,
`JWT_SECRET`, `VOYAGE_API_KEY`, `NVIDIA_API_KEY`, `REED_API_KEY`, `LANGFUSE_*`, `SMTP_*`,
`APIFY_TOKEN`, `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `ENCRYPTION_KEY`.

Delivered to the box as a file outside the image, never baked into a layer. An image layer
is readable by anyone who can pull it and survives in the build cache.

**`ENCRYPTION_KEY` is not like the others.** It decrypts the Gmail refresh tokens in
`gmail_credentials`. Losing it does not mean re-entering a key — it means **every user
must reconnect their Gmail**, because the stored ciphertext becomes undecryptable.
Rotating it has the same effect. Back it up somewhere that is not the box, before first
deploy, and record where.

ADR-003 specifies KMS and still defers it (GAPS 5.6). A file on a single box is the
interim, and it is a weaker interim once the box is internet-facing than it was on a
laptop — worth revisiting at the point there is a user who is not a friend of the owner's.

---

## Verification — what "deployed" has to mean

Not "the container started". Each of these failed silently somewhere today, which is why
each is listed:

- [ ] `/health` answers over HTTPS on the real domain
- [ ] `alembic current` against Neon reports `0026` **from the box**
- [ ] Scheduler registered its periodic jobs, verified by reading Redis — not by reading the log line that says it tried
- [ ] One discovery run completes from the box, and **JobSpy returns a non-zero count** (this is the `Scripts/python.exe` fix proving itself)
- [ ] `GitHubContactSource` returns candidates from the box (the `gh` fix proving itself)
- [ ] An outreach email sends via Gmail **from the box**, and its unsubscribe link resolves **from a browser that has never authenticated**
- [ ] The daily digest arrives without the owner's machine being on — the actual claim being made
- [ ] Laptop closed, worker still picking up jobs

---

## Open items for the owner

1. **Pick the box.** Hetzner CX22 (€~4) or DigitalOcean 2GB (~$12). 2GB RAM is the floor:
   spaCy's model is ~400MB resident before anything else runs.
2. **Add the production redirect URI** to the Google OAuth client, keeping localhost.
3. **Back up `ENCRYPTION_KEY` off the box** before first deploy. See DEPLOY-D for why this
   one is different.
4. **Decide what the UI says about unplanned forms**, given the planner stays local. A user
   who clips a job and finds auto-apply unavailable needs to be told why, not left
   guessing — the same "every refusal is visible" rule REACH-D follows.
