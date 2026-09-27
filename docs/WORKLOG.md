# Job Copilot — Worklog

**Purpose.** This is the context-recovery document. If a session loses context, or a new
person (or agent) picks up the work, **read this file first** — it says where the project
stands, what was decided, what is in flight, and what to do next.

**Rule.** Every change to this repo gets an entry here, appended at the top. An entry
records what changed, why, which files, and what broke. Errors and dead ends are recorded
too — a failed approach that is not written down gets retried by the next person.

---

## Current state — read this first

**Phase 3, in progress (2026-08-16).** Matching (F6) is live end-to-end against real
Neon + Voyage AI: resume-fact embeddings, `Profile.fact_centroid`, job embeddings on
ingestion, `GET /matches`, hard filters (location/remote, seniority, a visa-text
heuristic), job skill extraction, near-dup detection (simhash, reimplemented), and 6
connectors (5 real + JobSpy isolated, currently 0-yield pending a Google-side scraper
fix). The ADR-014 eval harness (`eval/`) and Langfuse Cloud tracing are both
mechanically live, blocked on a real `ANTHROPIC_API_KEY`. `apps/web` has shadcn/ui +
Kibo UI + jsdiff + better-auth/vitest/msw/openapi-typescript/style-dictionary
installed and building. Third-party repos from `DEPENDENCIES.md` §3 are installed:
presidio (PII redaction), jsonresume (export), agent-reach (company research,
isolated venv). `apps/extension/` scaffolded (MV3, vite+crxjs) but its build is
currently blocked by a stray unrelated `D:\postcss.config.mjs` outside this project.
Remaining backend packages (rapidfuzz, instructor, sse-starlette, rq-dashboard-fast,
cleanco, price-parser, iso4217, croniter, clamd) installed but not yet wired into any
feature. See the "Phase 3 slice 1-4" and "latest+6/+7/+8" entries below before
touching `matching/`, `eval/`, `apps/web`, `apps/extension/`, or `tools/`.

**2026-09-26 addition:** `tailoring/engine.py` now has a dev-only `LLM_PROVIDER=
nvidia_smoke` branch (see entry below) that mechanically smoke-tests the pipeline
for free via NVIDIA NIM — default `anthropic` path unchanged, 118/118 tests green.
This does NOT unblock ADR-014 — real `ANTHROPIC_API_KEY` (still the placeholder) is
still the single remaining blocker for actual tailoring-quality signal.

**Phase 2 complete (2026-08-16).** Done and verified live: dedupe/N+1 fix, ATS
discovery (F5), RQ/Redis background workers (B6, real enqueue → worker → Postgres →
poll round trip), `rq-scheduler` periodic runs (registration verified, cancelled after
test — nothing left running unattended), and a 5th connector (Reed, real UK listings,
real key). 5 connectors now live: remotive, greenhouse, lever, ashby, reed. Two real
Windows-specific RQ bugs were found and fixed (`os.fork`, `SIGALRM`) — see the RQ
wiring entry below before touching `workers/` again. Still open: Adzuna/The Muse (no
keys available — Adzuna's signup didn't yield a working key, Muse had nothing), the
remaining ~6 connectors from `PRD.md` Tier 2.



**⚠ Session handoff (2026-08-16): Phase 2 starts in a FRESH session, by design.**
Phase 0 and Phase 1 are complete and verified (see entries below). This session's
context — full history of all 4 OSS scouting passes, every doc revision, every ADR
discussion — is exactly what made it expensive to keep going. A fresh session reading
this file + `PRD.md`/`DECISIONS.md`/`DEPENDENCIES.md` (all current) has everything
needed to start Phase 2 cleanly, at a fraction of the cost. Do not re-derive context
that's already written down here.

**Phase 2 starting decision already made, not yet implemented:** Redis for RQ workers
will be **Redis Cloud** (official managed service, free tier), not Docker (abandoned
for Postgres in the entry below, same reasoning applies) and not Upstash (rejected in
pass 5 — protocol-compatible but not real Redis, RQ's blocking-poll needs are
unverified against it). Memurai and WSL2+redis-server were offered as alternatives and
declined — go straight to Redis Cloud, no need to re-litigate. Add the connection
string to `apps/api/.env` as `REDIS_URL` the same way `DATABASE_URL` was wired to Neon.

**Phase 2 scope, per `PRD.md` §11:** ATS discovery, 12 connectors, dedupe (canonical
hash, `SPEC.md` §3.1), background workers (`rq`+`rq-scheduler`, pending approval in
`DEPENDENCIES.md` §1.3). Fix order from `CODE-REVIEW.md`: B6 (move `/discover/run` off
the request thread into an RQ job) and H1/H2/H3 (N+1 query, missing indexes, dedupe key
too narrow) are the concrete bugs this phase closes.



| | |
|---|---|
| **Phase** | Phase 0 not started. Documentation complete, implementation not begun |
| **Code state** | Single-user MVP from a prior session. Works locally, has zero tests, has no auth |
| **Blocking** | Dependency approval (`docs/DEPENDENCIES.md` §6). Nothing installed |
| **Also blocking** | Docker not installed on this machine — Postgres/Redis cannot start |
| **Next action** | Owner approves dependency groups → Phase 0 (Alembic, auth, tenancy, tests) |

### What exists in the repo right now

```
apps/api/          FastAPI. main.py (189 lines), models.py, schemas.py, database.py
  connectors/      remotive, greenhouse, lever, ashby — 4 working fetchers
  tailoring/       engine.py — 2-pass Claude tailoring with truth-check
  resume_kb/       facts.json — seed data, single-tenant
apps/web/          Next.js pages router, untyped JS, one dashboard page
docker-compose.yml Postgres 16 + Redis 7 (cannot run — no Docker)
docs/              this documentation set
```

### The four product decisions already made (do not relitigate)

1. **Review queue, one-click batch approve** — not fully autonomous submission (ADR-001)
2. **Public APIs + RSS + user-side browser extension** — no server-side scraping (ADR-002)
3. **Referral email sends from the user's own Gmail via OAuth** — not our domain (ADR-003)
4. **Keep FastAPI + Next.js** — no TypeScript rewrite (ADR-004)

---

## Entries

### 2026-09-27 (latest+30) — Today home, phone tab bar, per-page titles

**What changed.**
- *API.* `GET /activity?since=&limit=` (JSON, not SSE — a native EventSource can't send
  the bearer header): the caller's `events` rows, newest first, `limit` 1..200 (default
  50, 422 outside), mapped to `{id, type, at, title, detail, application_id, job{title,
  company}}`. Only types something actually writes (read in code): `match.new`,
  `application.ready_for_review|approved|submitted|failed|needs_human`.
  `application.status_changed` is left out (claim/PATCH plumbing). `at` is tz-aware UTC so
  browsers don't read it as local time. Job/application lookups are two batched queries;
  applications only through the caller's own profiles. `GET /today` →
  `{sent_today (applied_at today), needs_you (ready_for_review — same set as Review),
  new_matches_today}`; campaign status + cap stay on `/campaigns` + stats (not
  duplicated). `campaigns.utc_day_start()` extracted so both use the cap's UTC day.
- *Web `/today`.* Greeting + one-line summary; Maggie status (Applying / Paused / Not
  started) with Pause/Resume/Start — optimistic with rollback + `role="alert"`, via a new
  shared `useCampaignStatus` hook that `/campaign` now uses too (logic moved, not copied).
  Tiles: sent today (with daily limit), needs you → /review, new matches → /matches;
  counters are plain text, no animation. "What Maggie did today": icon + title + job +
  reason + "2:14 PM"; each row links (/review for ready/needs-you, /matches for matches,
  /campaign otherwise). Honest empty states: no campaign → onboarding CTA; paused; not
  started; active with no activity ever → "waiting on her first search… needs the
  browser extension connected"; nothing today but earlier rows → "Nothing yet today" +
  Earlier. Skeletons while loading; one error alert with Retry.
- *Routing.* `/` and non-signup login → `/today` (safe `next` still honoured). NAV:
  Today, Review, Campaign, Matches, Your facts. Logo links to /today.
- *Phone nav.* Below `sm` the primary nav is a fixed bottom tab bar (5 × icon + label,
  56px tall, `aria-current`, safe-area padding); top bar keeps brand + Log out; main
  gets bottom padding so nothing hides behind it. Desktop links `whitespace-nowrap`.
- *Titles.* `AppShell` sets `document.title = "<title> · ApplyScout"` (`pageTitle` prop
  when the heading is a greeting); login sets "Sign in"/"Create account".

**Files.** API: `main.py`, `schemas.py`, `campaigns.py`, `tests/test_activity.py` (new).
Web: `app/today/page.tsx` (new), `lib/today.ts` + `lib/today.test.ts` (new),
`components/useCampaignStatus.ts` (new), `components/AppShell.tsx`, `lib/api.ts`,
`app/page.tsx`, `app/login/page.tsx`, `app/campaign/page.tsx`.

**Dependencies added.** None (lucide-react was already installed).

**Tests.** API 418 → 423 (5 new red first: 404s/IntegrityError, then green). Web 54 → 68
(red: missing module, then `splitToday is not a function`; green): UTC parsing of
offset-less timestamps, clock/date formatting incl. a +5:30 zone crossing midnight,
today/earlier split, row links, home states, plural-correct summary, msw contract for
both endpoints. `tsc` clean, `next build` clean (`/today` 6.28 kB, 137 kB first load).
Browser (next start, no API): at 390px no horizontal scroll, tab items 78×56 with
`aria-current`, top nav hidden; at 1280 top nav 471/471 no overflow; titles update on
client navigation (Today → Campaign → Today); error + Retry shows with the API down.

**Problems hit.** Worktree was cut at `fa419cd`; fast-forwarded to `b8cb281`. Test
fixture first reused one job for several applications (unique `profile_id,job_id`).

**Not done / notes.** No "skipped with reason" row: nothing writes a skip event yet (run-level
skips — cap reached, campaign not active — are only the task's return value) — add `application.skipped`/`match.skipped` with a reason
when the runner records one. Day boundary for `/today` counters is UTC (same as the
cap); the activity list's "today" is the viewer's local day. /onboarding still has no
per-page title (owned by another agent — a one-line `document.title` effect there).
StepDone still links to /review. Not verified against a live API.

---

### 2026-09-27 (latest+29) — Extension connection: Maggie can only apply from your browser, and now the app says so

**What changed.**
- *Backend.* New nullable `users.extension_last_seen_at` (migration **`0016_user_extension_last_seen.py`**,
  **not applied to Neon** — lead applies it). Stamped by `GET /extension/work-queue` and
  `POST /extension/map-fields` (the extension's own calls). New `GET /extension/status` →
  `{connected, last_seen_at, approved_waiting}`; `connected` = seen within
  `EXTENSION_CONNECTED_WINDOW` (10 min, `main.extension_connected`). `approved_waiting` uses the
  same query the work queue uses (`_work_queue_query`, extracted), so it counts exactly what the
  driver would pick up. Reading status never stamps last-seen. SPEC.md schema regenerated.
- *Web.* Onboarding's final step gains "Let Maggie apply from your browser": why (your browser
  session, never a shared bot — ADR-015 §3), three steps (Load unpacked `apps/extension/dist` via
  `chrome://extensions`; sign in in the extension; press Run apply queue), and a live status line.
  Reusable `components/ExtensionStatus.tsx` (`role="status"`, `aria-live="polite"`, polls every 4s,
  react-query pauses in background tabs) — exported, NOT wired into AppShell. Pure copy in
  `lib/extension.ts` (`extensionStatusView`); `api.getExtensionStatus`. Onboarding intro now says
  applying happens from your browser via an extension.
- *Extension.* All user-visible "Job Copilot" → "ApplyScout" (popup, manifest name/description,
  index.html title, formFill flags/markField titles/alert prefix, submitApprovedApplication errors).
  Popup copy plain and recovery-oriented ("Sign in", 401 → signs out and asks to sign in again,
  server error → "nothing was sent, try again", network → "check your connection"). The popup
  checks in with `GET /extension/work-queue?limit=0` on open and after sign-in, so step 2 already
  flips the web app to Connected; `limit=0` takes no work.

**Why.** Under ADR-015 nothing is submitted unless the extension is installed, signed in and run.
The web app never mentioned it, so a user finished onboarding believing Maggie applies while
nothing happened.

**Tests.** api 418 → 426 (8 new in `tests/test_extension_status.py`, 7 red first: missing
`extension_connected`, 404 on `/extension/status`). web 54 → 61 (`lib/extension.test.ts`, red on
missing module first). Extension 33/33, `tsc` clean, `vite build` clean. Web `tsc` + `next build` clean.

**Not verified.** No live browser run (no loaded-extension access); migration not run against Neon.

**Next.** Apply 0016; lead/agent C to drop `<ExtensionStatus />` into the header; Chrome Web Store
listing so step 1 stops being "Load unpacked".

---

### 2026-09-27 (latest+28) — Why Maggie stopped: needs_input on review cards; base resume download works

**What changed.**
- *API.* `GET /applications/review-queue` rows gain `needs_input: {kind, message,
  demographic_left_blank} | null` and `last_attempt: {outcome, message} | null`, derived
  from the **last** `[outcome] reason` line `submission-result` appends to `notes`
  (new pure `apps/api/needs_input.py`). `needs_input` is set only when that last stamp is
  `needs_human`. Kind, first match wins: `captcha` → `account` (sign in / log in / create
  an account / register to apply) → `upload` (`file_upload`, file input) → `question`
  (`low_confidence`/essay/unanswered, or any pending question left) → `other`. Patterns
  mirror `driverCore.mjs` NEEDS_HUMAN_PATTERNS and `autoApply.content.ts`'s flag reasons.
- *Web.* `lib/needs-input.ts` maps it to plain copy with Maggie as the actor; the review
  card shows it first as a `role="note"` callout (warning tokens for "finish it by hand",
  muted for questions), with "Open the form" (new tab, sr-only hint) when the user has to
  finish the form. "Approve to retry" only appears where a retry can work: `question`
  kind with no demographic field. The demographic line reads "Questions about gender,
  ethnicity, veteran or disability status were left blank for you to decide."
- *Download.* "Download resume" was a bare `<a href>` to an endpoint that needs the Bearer
  header, so it always 401'd. `api.downloadResumeDocx` fetches it through the shared
  plumbing (`request()` split into `send()` + `.json()`, so 401/error handling is the same
  code) and the card saves the blob via an object URL as `base-resume.docx`. Relabelled
  "Download base resume" (facts-only, not tailored); a failure shows an inline
  `role="alert"`. `api.resumeDocxUrl` removed (its only caller).

**Why.** A form stopped by a captcha, an account wall or an extra upload looked like any
other card; the user approved it and it looped. The reason was already stored, just not
shown.

**Files.** api: `needs_input.py` (new), `main.py`, `schemas.py`,
`tests/test_needs_input.py` (new). web: `lib/needs-input.ts` + `.test.ts` (new),
`lib/api.ts`, `components/review/ApplicationCard.tsx`, `app/review/page.tsx`.

**Dependencies added.** None. No migration (derived from `notes`).

**Tests.** Red first on both layers. api: collection error (no `needs_input`) → 13 new
green; then a second red (answering every question emptied `pending_questions` and the
kind fell to `other`, dropping the retry framing) → question-type reasons added → green.
418 → **433**. web: `Cannot find module './needs-input'` → green, 54 → **64** (copy per
kind, retry only where it helps, demographic note, msw: Bearer header sent and blob
returned, a 404 rejects as `ApiError`). `tsc --noEmit` clean, `next build` clean.

**Problems hit.**
- **Demographic fields block every pass.** `autoApply.content.ts` treats `demographic`
  as a blocking reason, and `fieldDecision.mjs` flags every demographic field, so any form
  with an EEO section (most Greenhouse forms) stops at `needs_human` every time; approving
  again can never send it. The card now says "open the form and submit it yourself" in that
  case instead of offering a retry. The real fix is an extension decision (leave optional
  EEO fields blank and continue; only stop on a *required* one), not made here.
- PowerShell 5.1 `Get-Content -Raw` + `WriteAllText` re-encoded `schemas.py` (mojibake
  in every em dash); reverted with git and redid it with plain edits.
- Not verified in a browser (no backend started). `last_attempt` is typed on the web but
  not rendered: review-queue rows are `ready_for_review`, so it is always the needs_human
  stamp there.

**Next.** Extension: don't stop on optional demographic fields; show `last_attempt`
wherever approved/failed rows get a screen; a tailored per-application docx.

---

### 2026-09-27 (latest+27) — Launch actually launches; RQ job ids; Tailwind v3 colour tokens fixed at the root

**What changed.**
- *Onboarding launch* (found by the IA audit, verified live): `POST /campaigns` 422'd on
  every launch (`buildCampaignBody` never sent `profile_id`; the contract test pinned the
  wrong body). And a created campaign stays `draft`, which `run_campaign` skips.
  New `launchCampaign()` (lib/onboarding.ts): create → PATCH `status: active` → run,
  returning `{campaign, started}`; a failed first run is reported ("saved but didn't
  start"), no longer `.catch(() => null)`. StepDone score `×100` bug ("8200%") fixed;
  developer error copy on launch/stats removed; `runCampaign` return type corrected.
- *RQ job ids* (found live): rq 2.x rejects `:` in job ids, so `POST /campaigns/{id}/run`
  and `POST /discover/run` 500'd on every call; mocked-queue tests couldn't see it.
  Ids now use `-`; new test runs rq's own `validate_job_id` on both.
- *Tailwind v3 × shadcn v4 root cause* (a11y audit): tokens were hex, so every opacity
  modifier (`bg-destructive/10`, `ring-ring/50`, `bg-background/80`…) silently never
  generated — error boxes had no background, header was transparent, focus rings fell
  back to Tailwind's default at 1.8:1. Tokens are now RGB channels +
  `rgb(var(--x) / <alpha-value>)` in tailwind.config. `outline-none` removed from
  button/input/textarea/checkbox so the global 3px `--ring` outline shows. `--input`
  darkened to ≥3:1 (was 1.38:1). Button `transition-all` scoped; v4-only
  `var(--radius-md)` radii replaced. Reduced-motion rule gains
  `animation-iteration-count: 1` (spinners jittered instead of stopping).

**Tests.** api 418/418 (new rq-id test red → green). web 54/54 (profile_id contract +
launchCampaign create→activate→run and failed-run cases red → green). tsc clean.
Verified in browser: font, radii, error background, focus ring, both themes.

**Problems hit.** My token regex also rewrote `var(--font-sans)` and `var(--radius)` into
`rgb(...)` (serif font, square corners) — caught in the browser screenshot, fixed.
uvicorn `--reload` hung mid-reload and kept serving old code; restarted without reload.
**Redis Cloud endpoint no longer resolves** (`expert-neosafe-bucket-71462.db.redis.io`:
DNS name does not exist) — the free DB appears deleted. Every enqueue (campaign run,
discovery) fails until `REDIS_URL` points at a live instance. Onboarding now says so
honestly ("saved but didn't start").

**Not merged.** Branch `worktree-agent-af607b1d421ec69ae` commit `adbf0c2` (the agent's
late scope addition: profile_id, errorText helper, create-once retry) overlaps this
entry's launch fix; kept unmerged for review — its `errorText` sweep of raw
exception text is still worth taking.

**Next.** New REDIS_URL; mobile nav (overflows at 390px); map raw parse/LLM errors to
friendly copy server-side; focus management while onboarding is pending; Today home.

---

### 2026-09-27 (latest+26) — P0: /campaign — see it, pause it, change it

**What changed.** New `/campaign` screen (inside `AppShell`, `useRequireAuth`), and
"Campaign" in the nav between Matches and Your facts.
- **Status first, one action.** A card states Active ("Maggie is applying") / Paused
  ("Nothing will be sent until you resume") / Draft, with one primary button: Pause,
  Resume, or Start (draft→active). No "are you sure" — pausing is safe and reversible.
  Optimistic: the status flips on press via the `["campaigns"]` cache; a failed PATCH
  restores the old status and shows a `role="alert"` saying nothing changed. The status
  block is `aria-live="polite"` so the flip is announced.
- **Today's pace** from `GET /campaigns/{id}/stats` (read the real shape in `main.py`):
  `applied_today` of `daily_cap` plus `total_applied`. Worded "applications started
  today" because the cap counts every `applications` row created, sent or not.
- **Settings the user approved in onboarding**, editable inline: roles and locations
  (reused `Chips`), remote only and "Send without asking me first" as real
  `role="switch"`/`aria-checked` buttons with a plain one-line description of the
  current state, daily cap as a −/+ stepper (44px buttons, bounds disable them), minimum
  match score (reused `Field`), tailoring notes. One Save, disabled until something
  differs; the PATCH carries only changed fields; success is announced via `aria-live`.
- **Empty state** → `/onboarding`. More than one (non-archived) campaign → a row of
  `aria-pressed` buttons to pick one; switching resets the form (`key={campaign.id}`).

**Why.** ADR-015 lets Maggie apply autonomously inside a campaign approved once. After
onboarding there was no way to see that campaign, stop it, or change it — for an agent
sending applications under the user's name, that was the biggest trust gap.

**Files.** New: `apps/web/app/campaign/page.tsx`, `apps/web/lib/campaign-form.ts`
(`formFromCampaign`, `buildCampaignPatch`, `validateCampaignForm`, `statusView`),
`apps/web/lib/campaign-form.test.ts`. Changed: `apps/web/lib/api.ts` (added
`CampaignUpdate` type + `updateCampaign` only; `request()` untouched),
`apps/web/lib/campaigns.test.ts` (PATCH contract tests), `apps/web/components/AppShell.tsx`
(NAV entry).

**Dependencies added.** None.

**Tests.** Web 27 → 41. Red first: the new files failed with `Cannot find module
'./campaign-form'` and `api.updateCampaign is not a function` (2 failed / 27 passed),
then green after the implementation. Covered: patch contains only changed fields, lists
compared by value, notes trimmed and cleared with `""` (the API's `exclude_none` drops
nulls, so null could never clear a note), validation reuses onboarding's
`validatePreferences`/`validateCampaign` rather than restating them, status→label/tone/
action mapping incl. archived = no action, and msw: PATCH sends exactly the body given
and a 422 surfaces as `ApiError` with the server's message. `tsc --noEmit` clean,
`next build` clean (`/campaign` 8.17 kB, 137 kB first load).

**Problems hit.**
- The worktree was created at `fa419cd`, behind the `ee7a853` the task assumed (no
  `AppShell.tsx`); fast-forwarded the clean branch to `ee7a853` first.
- **422 field errors can't be field-level yet.** `request()` flattens FastAPI's
  `detail[].loc` into one string, and it is off-limits here (a parallel agent owns it).
  So client validation mirrors the server bounds and places errors per field; a
  server-side 422 shows as one form-level alert. Field mapping needs `ApiError` to keep
  the raw `detail`.
- Daily-cap ceiling is onboarding's `DAILY_CAP_MAX` (50), stricter than the API's 200 —
  kept consistent with what the user approved.
- `api.runCampaign` is typed `{ job_id }` but the endpoint returns `{ task_id, status }`.
  Not used here; not fixed.
- Not verified in a browser: no backend was started (by instruction).

**Next.** Keep `detail` on `ApiError` so 422s map to fields; a digest of what was sent
today on this screen (ADR-015 rail); rendering tests once jsdom is approved.

---

### 2026-09-27 (latest+25) — P0: session expiry, honest facts copy, onboarding by-hand facts

**What changed.**
- **Session expiry.** `lib/api.ts` `request()` now handles 401: anywhere except
  `/auth/login`/`/auth/signup` (where 401 = wrong password and stays an `ApiError` the
  form shows) it clears the token and `location.replace`s to
  `/login?expired=1&next=<path>`. `/login` shows "Your session ended. Sign in again to
  pick up where you left off." and after sign-in goes to `safeNext(next)` (else
  /review). Pure helpers `isSessionExpiry`, `safeNext`, `expireSession` in `lib/auth.ts`.
- **Honest facts copy.** The backend has no edit/delete for resume facts (only
  `GET/POST /resume-facts`, `POST /profiles/{id}/facts:bulk` — checked `main.py`).
  /facts no longer says "you can edit any time"; onboarding's "Edit your facts" link is
  now "Add more facts"; the confirm step says saved facts can't be edited yet.
- **Onboarding dead end.** Step 1 offers "Add your facts by hand" — a secondary link from
  the start and a primary button in the parse-failure state. It jumps to the facts step
  with one blank row (never discarding parsed facts); each row now has a category
  `<select>` (the five backend categories) plus the existing achievement/metric/proof
  fields, saved through the same `facts:bulk` path.

**Why.** An expired token left every page showing raw "Could not validate
credentials"; /facts promised an edit that doesn't exist; and while the parser's LLM
call fails (placeholder `ANTHROPIC_API_KEY`, or any model outage) a new user could not
get past step 1. Hand-written facts are the user's own words, so the no-fabrication
rule holds.

**Files.** `apps/web/lib/{api.ts,auth.ts,onboarding.ts,onboarding.test.ts,session.test.ts (new)}`,
`apps/web/app/{login,facts,onboarding}/page.tsx`,
`apps/web/components/onboarding/{StepResume,StepFacts,StepDone}.tsx`.

**Dependencies added:** none.

**Tests.** Red first: 10 failing (7 in new `session.test.ts` — `isSessionExpiry`,
`safeNext` incl. `//evil.com`, `/\evil.com`, `/\t/evil.com`, `javascript:`, a /login
loop, and msw-backed `request()` 401 behaviour with a stubbed `window`; 3 in
`onboarding.test.ts` — unknown category, `blankFact` gating). Green: web 27 → 38/38,
`tsc` clean, `next build` clean.

**Problems hit.** The worktree was cut at `fa419cd`, not `ee7a853`; fast-forwarded
before starting. `onboarding.test.ts`'s fixture used category `"impact"`, which the
backend never produces — changed to `"experience"` once categories are validated.
`useSearchParams` would force a Suspense boundary on /login, so the query string is
read from `window.location` after mount instead.

**Next.** Edit/delete endpoints for confirmed facts (then restore the copy);
`useRequireAuth` could pass `next` too; /facts has no by-hand path yet (onboarding only).

---

### 2026-09-27 (latest+24) — apps/web UX pass: one theme, one shell, accessible controls

**What changed.** Audit (redesign-skill + ui-ux-pro-max checklist) found the web app
was two design systems fighting: a legacy "ledger" theme (dark-green unlayered
`body{}` rule, Fraunces/Inter from Google Fonts) overriding shadcn tokens, so
login/facts rendered near-white text on white inputs. Fixed at the root:
- `styles/globals.css` rewritten to the hi-fi prototype's tokens (neutral surfaces,
  magpie-blue `--primary`, success/warning), light+dark via `prefers-color-scheme`;
  `tailwind.config.js` `darkMode: "media"`, legacy colours/fonts removed (Geist stays).
- shadcn components were generated for Tailwind v4 (`ring-3` etc.); under v3.4 that
  class doesn't exist, so buttons/inputs had **no focus ring**. `ring-3`→`ring-[3px]`
  across `components/ui`; buttons 40/36/48px, inputs 44px (was 32px).
- `components/AppShell.tsx`: skip link, sticky nav with `aria-current`, log out,
  shared `useRequireAuth` (was copy-pasted in four pages).
- Deleted the pre-pivot `pages/index.js` dashboard (+ `_app.js`, `lib/legacy-api.js`)
  that `/` still served; `app/page.tsx` routes to /review or /login.
- Login, facts, matches, review rebuilt on the shell: labels + autocomplete, error
  cleared on mode switch, signup → /onboarding, real empty states, internal jargon
  ("F6", "ADR-001", "Facts KB") and the pre-ADR-015 "nothing is submitted until you
  approve" copy removed.

**Tests.** Web 27/27, `tsc` clean, `next build` clean. Verified in a browser
(Playwright): every route 200, light + dark, visible keyboard focus. No unit test
for the restyle (no jsdom — still needs approval).

**Problems hit.** Stopping a backgrounded `npm run dev` left its Node child holding
:3000; a `next build` run beside the dev server clobbered its `.next` (there is no
`NEXT_DIST_DIR`) — build in a separate checkout or stop dev first.

**Next.** Onboarding + review card still carry their own local styles; add a "Today"
home and the prototype's keyword-gap scorecard to the review card.

---

### 2026-09-27 (latest+23) — RLS tenant id survives a commit (found live: every new user's profile creation 500'd)

**What changed.** `core/deps.py`: the tenant id is stored on the session
(`db.info["current_user_id"]`) and a `Session` `after_begin` listener
(`_reapply_tenant`) re-applies it with `set_config('app.current_user_id', uid, true)`
at the start of every transaction. Previously a one-shot `SET LOCAL` in
`get_current_user`.

**Why.** Found by running the app locally against Neon: `POST /profiles` →
`InvalidRequestError: Could not refresh instance`. `SET LOCAL` is
transaction-scoped; `db.commit()` ended it, so `db.refresh()` ran with no tenant
and RLS hid the row just inserted. Every endpoint that commits then reads was
exposed, not just profiles — fixed once where all of them route through. Still
transaction-local, so a pooled connection never carries a user id to another request.

**Files.** `apps/api/core/deps.py`, `apps/api/tests/test_rls_context.py` (new).

**Tests.** Red (ImportError) → green; 417/417. SQLite has no RLS, so the unit test
pins the mechanism; the real proof is live: signup → `POST /profiles` 200 →
`GET /profiles` returns it, on Neon.

**Problems hit.** None of 415 SQLite tests could catch this — RLS only exists on the
real Postgres role. Worth a Postgres-backed smoke test in CI.

**Next.** Login page: input text is near-white on white (unreadable) and a stale
"Incorrect email or password" persists when switching to Sign up.

---

### 2026-09-27 (latest+22) — the keyword-gap scorer feeds tailoring; `missing` stays a gap, never a bullet

**What changed.** `tailoring/engine.py::tailor_application` now runs
`compute_keyword_gap` on the job + the user's real facts before pass 1 and adds a
`JD TERMS YOUR FACTS SUPPORT:` block to the tailoring prompt: one line per
**matched** keyword with the id of the fact that backs it and the scorer's
action (`reword` / `surface`) where it has one. The system prompt tells the model
to use each term verbatim only in a bullet citing that fact, and to add no other
JD keyword. The result gains `keyword_gap: {coverage_before, coverage_after,
missing}` — `coverage_after` is the same scorer run on the tailored bullet text.
Stored additively in `applications.tailored_resume_json["keyword_gap"]` by both
writers (`/tailor`, `batch_prep`); `TailorResponse.keyword_gap` optional.

**Why.** latest+16/+20 Next: the scorer existed and nothing consumed it. Wired
inside `tailor_application`, the one function `/tailor`, `batch_prep` →
`workers/jobs.py::prepare_applications_task` and `campaigns.py` all route through.

**The rail.** `_jd_terms_section` reads `gap["matched"]` and `gap["suggestions"]`
only; `missing` is never an input, so an unsupported keyword has no path into the
"use these terms" block. It is returned to the user as `keyword_gap.missing`.

**Files.** `apps/api/tailoring/engine.py`, `batch_prep.py`, `main.py`,
`schemas.py`, `tests/test_tailoring_engine.py`, `tests/test_batch_prep.py`.

**Dependencies added.** None. No migration (existing JSON column).

**Tests.** 3 new + 1 extended, LLM mocked (`_get_instructor_client`). Red first
(4 failed), then green. `test_missing_keyword_never_reaches_the_prompt_outside_the_raw_jd`:
JD asks for Terraform/Snowflake, no fact has them → asserted absent from the terms
block and from the whole prompt outside the raw JD text, and present in
`keyword_gap.missing`. Sabotage-checked: temporarily feeding `missing` into the
block made it fail, then reverted. Full suite 400 → **403** passed.

**Problems hit / not verified.** No live LLM (placeholder `ANTHROPIC_API_KEY`), so
whether the model actually adopts the JD wording is unmeasured — the eval harness
is the place once the key is real. The raw JD is still in the prompt (it was
before), so the model *can* read a missing keyword there; the prompt forbids it
and the truth-check pass is the backstop, same as before. `job.skills` isn't
passed by the callers (scorer takes it as optional; JD text + title cover it).

**Next.** Show `keyword_gap.missing` / coverage in the review card; measure
coverage_before→after on the eval set once the key is real.

---

### 2026-09-27 (latest+21) — per-ATS field schemas: verified system fields fill with zero LLM calls

**What changed.** `formfill/ats_schemas.py` (new) is one dict:
`ats_type -> exact DOM name/id -> profile_summary key`, for Greenhouse
(`email`, `phone`), Lever (`name`, `email`, `phone`, `urls[Portfolio]`) and Ashby
(`_systemfield_name`, `_systemfield_email`). `match_field_deterministic` gained
`ats_type=None` and consults the table before the network/autocomplete/regex
rules, so a known system field fills however its label is worded.
`MapFieldsRequest.ats_type` is optional and bounded (`max_length=32`, a string
not a Literal — the resolver can return an LLM-classified type, and an unknown
one must fall through, not 422 the fill). The extension forwards the work item's
`ats_type` (already in `/extension/work-queue` since latest+18); the interactive
popup path sends `null`. Unknown/`None` = exactly the old behaviour (tested).
Demographic exclusion in `map_form_fields` still runs before any of it (tested).

**Verified against (2026-09-27, live public pages — nothing invented).**
Greenhouse: rendered ids on `job-boards.greenhouse.io/anthropic/jobs/4461450008`
+ `boards-api.greenhouse.io/v1/boards/airbnb/jobs/8232207?questions=true`.
Lever: input `name`s on `jobs.lever.co/palantir/6ed76ce8-…/apply`. Ashby:
rendered `name`/`id` on `jobs.ashbyhq.com/ashby/7458d4e9-…/application`
(Playwright) + its public `non-user-graphql` `ApiJobPosting` form definition.

**Deliberately left out.** Greenhouse `first_name`/`last_name` (verified, but
Profile has only `full_name` — a split is a guess; they still fall through to
the LLM path as before, and a test pins that the table never splits). Typeahead
comboboxes: Greenhouse `country`, Lever `location`, Ashby `_systemfield_location`.
Lever `org` (no current-company column). Lever `urls[LinkedIn]`/`urls[GitHub]`
already resolve via the generic network rule. File inputs stay client-side.
The other 14 ATS types: no verified field names gathered, so no entries.

**Why.** `latest+18`/`+20` Next: known fields on known ATSes should not depend on
label wording or a model call.

**Files.** api: `formfill/ats_schemas.py` (new), `formfill/deterministic.py`,
`formfill/map_fields.py`, `main.py`, `schemas.py`, `tests/test_ats_schemas.py`
(new). extension: `background/driver.ts`, `content/autoApply.content.ts`,
`content/formFill.content.ts` (type + one request field).

**Dependencies added.** None. No migration.

**Tests.** Red first (collection error: no `formfill.ats_schemas`), then green.
api 400 → 412 passed. Extension 33/33, `tsc --noEmit` clean, build clean.

**Problems hit.** The worktree has no `.venv`/`node_modules`: ran pytest with the
main checkout's venv (after copying the gitignored `apps/api/.env`) and the
extension checks through a temporary junction to the main `node_modules`,
removed afterwards.

**Next.** Workable/SmartRecruiters/Workday schemas once real forms are captured;
a narrow, user-confirmed given/family name split (a profile column, not a guess)
would unlock Greenhouse's two required name fields without the LLM.

---

### 2026-09-27 (latest+20) — the answer bank fills itself at `needs_human`; the resume reaches file inputs

**What changed.**
1. *Answer capture.* A `needs_human` run now reports the questions it stopped on
   (`SubmissionResultIn.unanswered_questions`, ≤50 × ≤1000 chars). They are stored
   on `applications.pending_questions` (migration `0015`), demographic ones dropped
   server-side, deduped. `GET /applications/review-queue` returns
   `pending_questions` **derived** against the bank (`find_answer`), so saving an
   answer is what clears a question — no second state to sync. Any non-`needs_human`
   outcome clears the list. The review card (`ApplicationCard.tsx`) shows each with a
   textarea → `PUT /profiles/{id}/answers` → refetch; the user then approves to retry
   and the next pass fills it from the bank.
2. *Resume upload.* File inputs no longer go to `map-fields` (writing a string into a
   file input's `.value` throws — every form with an upload was a guaranteed
   failure). `classifyFileInput` (pure, `fieldDecision.mjs`): resume/CV by
   label/name/id → attach `/profiles/{id}/resume.docx` via `DataTransfer`;
   cover-letter wins over resume; unknown required upload → `file_upload` flag
   (needs_human, not a bank question); optional → skipped.

**Why.** `latest+19`'s Next: without capture the bank never grows; without the
upload nearly every real ATS form stops the run.

**Files.** api: `main.py`, `models.py`, `schemas.py`,
`alembic/versions/0015_application_pending_questions.py`,
`tests/test_pending_questions.py` (new). extension: `fieldDecision.mjs/.d.mts/.test.mjs`,
`formFill.content.ts`, `autoApply.content.ts`, `background/driver.ts`. web:
`lib/api.ts` (`saveAnswer`, `pending_questions`), `lib/answers.test.ts` (new),
`components/review/ApplicationCard.tsx`, `app/review/page.tsx`. `docs/SPEC.md`
schema regenerated — it was already stale (latest+19 never added `answer_bank`).

**Dependencies added.** None.

**Tests.** Red confirmed before green on all three layers: api 6 new (400/400
total), extension 4 new (33/33), web 2 new (27/27). Extension typecheck + build and
web `next build` clean. First `classifyFileInput` run failed on `cv_upload` — `\b`
treats `_` as a word char; switched to letter-bounded lookarounds.

**Problems hit / not verified.** The content-script DOM glue (DataTransfer attach,
question labels) is still not live-browser-tested — same standing limitation as the
rest of the extension. Uses the profile's facts-only docx, not a per-application
tailored one (`ponytail:` in `fetchResumeFile`). Migration `0015` not yet applied to
Neon.

**Next.** Apply `0015`; per-ATS field schemas; feed the keyword-gap scorer into
`tailoring/engine.py`; a tailored per-application docx once `ANTHROPIC_API_KEY` is
real (still a placeholder).

---

### 2026-09-27 (latest+19) — the answer bank: the interruption shrinks, and the demographic rail is finally its own thing

**Context.** `latest+17` closed the execution loop, and its honest ending was
`needs_human`: a form asks "why do you want to work here?", the run stops, the
user answers, we submit. And then **the answer was thrown away.** The next
employer asked the same question and interrupted them again, forever — the one
failure mode that makes an auto-apply product feel like manual applying with
extra steps. This makes the interruption shrink: answer once, reuse on every
similar question after.

**The real work was not the storage, it was the boundary.**
`FORBIDDEN_LABEL_KEYWORDS` lumped together two things that have nothing to do
with each other:

| | why it was unfillable | permanent? |
|---|---|---|
| race, ethnicity, gender, veteran/disability status, sexual orientation | EEO — auto-answering it is not ours to do | **yes, forever** |
| "why do you want to work", "why are you interested" | we had no user-written answer | no — that is exactly what the bank supplies |

Now `DEMOGRAPHIC_LABEL_KEYWORDS` (in `answer_bank.py`) and
`ESSAY_LABEL_KEYWORDS` (in `map_fields.py`), with
`FORBIDDEN_LABEL_KEYWORDS` kept as their union so existing callers keep their
meaning. **The demographic list lives in `answer_bank.py`, not
`map_fields.py`, and that placement is forced**: `map_fields` imports
`tailoring.engine.call_llm`, and rail 2 below says nothing in the bank's import
graph may reach it — so the dependency has to point that way, not the other.

**Three rails, each with a test that fails if it breaks.**

1. **Demographic is unconditional.** Enforced in three places on purpose, since
   this is the one outcome that is unacceptable rather than merely wrong:
   `save_answer` 400s on storing one, `find_answer` filters demographic rows out
   before it looks at anything (so a row that arrived by a hand-written INSERT,
   a restored backup, or a future code path *still* cannot be served), and
   `map_form_fields` excludes those fields before the deterministic matcher, the
   bank and the model. `test_a_demographic_answer_is_never_served_even_if_a_row_somehow_exists`
   writes the row straight to the ORM, asserts it really is there, and asserts
   it is unreachable. `test_a_demographic_field_never_even_reaches_the_answer_lookup`
   is stronger than "the value is discarded" — the bank is never consulted, so a
   demographic question cannot so much as bump a `times_used` counter.
2. **User-written text only.** No LLM generates an entry, ever.
   `test_no_llm_call_exists_anywhere_in_the_answer_bank_import_graph` proves it
   structurally, in a **subprocess** — inside the pytest session
   `"tailoring.engine" in sys.modules` is already true no matter what
   `answer_bank` does, so an in-process check would have been vacuous.
   `test_save_answer_is_the_only_write_path_in_the_module` greps every function
   in the module for `AnswerBank(` and asserts the list is exactly
   `["save_answer"]` — a second constructor is a second door that bypasses the
   demographic refusal.
3. **A wrong answer is worse than asking again.** See below.

**The matching, which is where the measurement mattered.** The finding that
shaped the design: **no single rapidfuzz scorer works at any threshold.** Every
whole-string scorer puts at least one semantically-opposite pair above any cutoff
that still admits a real paraphrase — `token_set_ratio` scores "years of
experience with python" vs "…with java" at **90.6** and the visa-sponsorship
negation pair at **100**; `fuzz.ratio` scores "…with c++" vs "…with c#" at
**94.5**. So two gates, both over **content words only** (stopwords stripped —
measured on the whole question the signal drowns in shared glue):

* **Gate 1**, `token_sort_ratio` ≥ 90 over content words.
* **Gate 2**, bidirectional coverage: every content word on each side needs a
  `fuzz.ratio` ≥ 90 partner on the other.

Measured, and these numbers are in the source as the justification for the
thresholds:

| asked / stored (content words) | gate 1 | verdict |
|---|---|---|
| want work / leave last job | 26.1 | rejected |
| willing relocate / relocate | 66.7 | rejected |
| want work / want work company | 69.2 | rejected |
| years experience python / years experience java | 77.3 | rejected |
| years experience c++ / years experience c# | 92.3 | → **gate 2 rejects** (c++/c# = 40) |
| require visa sponsorship / **not** require visa sponsorship | 92.3 | → **gate 2 rejects** ("not" unpartnered) |
| notice period / notice periods | 96.3 | accepted |
| notice period / notice period | 100.0 | accepted |

Neither gate is redundant: gate 1 kills python/java, gate 2 kills c++/c# and the
negation. `"not"/"no"/"never"` are deliberately **not** stopwords — negation
flips the answer, and gate 2 is the only thing separating "do you require visa
sponsorship" from its negation, which is a false legal declaration on a real
application. `normalize_question` also deliberately **keeps `+` and `#`**: every
other punctuation mark is collapsed, but stripping those turns `c++` and `c#`
into the same key and serves a C# answer to a C++ question.

**Two bugs found in my own design, both by running the numbers rather than
trusting them.** (a) Gate 1 was originally `token_set_ratio` over the *whole*
question at 90; the plural case ("what is your notice period" / "what are your
notice periods") scored **88.9** and was rejected, while python/java scored 90.6
and was *accepted* — the gate was actively backwards. Moving it onto content
words fixed both directions at once. (b) Renaming the extension's flag reason
`demographic_or_essay` → `demographic` silently dropped it out of
`autoApply.content.ts`'s `NEEDS_USER_REASONS` set, which would have meant a
demographic-flagged field **no longer stopped the run**. Caught by grepping every
consumer of the literal before committing; `formFill.content.ts` had the same
coupling and is now a `FLAG_MESSAGES` lookup instead of a two-branch ternary.

**The extension half had to change or the backend fill was dead on arrival.**
`decideFieldActions` flagged every essay field *before* looking at the mapping,
so a bank answer would have been discarded client-side and the run would still
have reported `needs_human`. Same split applied there (mirrored list, as the
existing comment demands), demographic still unconditional and still checked
first. New `essay_no_stored_answer` reason, distinct from `low_confidence`
because it is the one flag a user can clear *permanently* — the content script
now says so ("save the answer and we'll reuse it next time").

**Files created.** `apps/api/answer_bank.py`,
`apps/api/alembic/versions/0014_answer_bank.py`,
`apps/api/tests/test_answer_bank.py`,
`apps/api/tests/test_answer_bank_endpoints.py`. **Files changed.**
`apps/api/models.py` (`AnswerBank`, `Profile.answers`), `apps/api/schemas.py`
(`AnswerIn`/`AnswerOut` — the normalized key is derived server-side and never
accepted from a client, so two clients can't disagree about what matches what),
`apps/api/formfill/map_fields.py` (list split, `is_essay_label`,
`answer_lookup`), `apps/api/main.py` (3 endpoints + the lookup injection),
`apps/api/tests/test_formfill.py`,
`apps/extension/src/content/fieldDecision.{mjs,d.mts,test.mjs}`,
`apps/extension/src/content/{autoApply,formFill}.content.ts`.

**API.** `GET/PUT /profiles/{id}/answers`, `DELETE
/profiles/{id}/answers/{answer_id}`, all via `get_owned_profile`. PUT not POST
because the unique key is the question, not an id. DELETE is scoped by
`profile_id` as well as `answer_id` — a user with two personas must not delete
one profile's answer through the other's path, and that has its own test.
`map_form_fields` gained `answer_lookup=None`: the bank is **injected as a plain
callable, not imported**, so the module stays free of a DB session, its tests
stay free of a database, and `answer_lookup=None` reproduces the pre-bank
behaviour exactly (tested). Order in the pipeline: demographic exclusion →
deterministic (profile data still wins over the bank, tested) → bank → bounded
LLM. A bank hit *removes* the field from the model prompt, so this makes the LLM
path cheaper, not more expensive. Essay fields are bank-or-nothing and never
reach the model at all.

**Migration `0014`, WRITTEN AND NOT RUN**, as instructed — a parallel agent is
working in `apps/api`. RLS copied from `0012` verbatim (ENABLE + FORCE +
`tenant_isolation` via `profile_id -> profiles.user_id`, with the `NULLIF(...)`
that `0010` learned the hard way is load-bearing). Verified **offline** with
`python -m alembic upgrade 0013:0014 --sql` from `apps/api`, which renders the
DDL without connecting; the chain resolves and the policy SQL is as intended.
Command to actually apply it: `.venv/Scripts/python.exe -m alembic upgrade head`
from `apps/api`.

**Tests.** Backend **310 → 365** passed, full suite green from `apps/api`.
Extension `node --test` **24 → 29**. Red-before-green throughout: the first run
of `test_answer_bank.py` was a collection error (no module), and the two
genuine reds that followed were the backwards gate above and a test that tripped
`uq_profile_user_persona` by asking for two `developer` profiles on one user.

**Not verified, and why.** `0014` has not touched live Neon, by instruction —
so the RLS policy and the unique constraint are argued-correct-by-analogy to
`0012`, not observed. The SQLite test engine does enforce the unique constraint,
so the upsert behaviour is genuinely tested; RLS is not testable there at all.
`tsc --noEmit` cannot run clean in this worktree (no `node_modules`); pointing
`--typeRoots` at the main checkout's `@types` resolved `chrome` and left only
`vite.config.ts` module-resolution errors, i.e. nothing in the files I touched.
No live-browser run, same standing limitation as every content-script entry.

**Deliberately left out.** No UI for managing the bank — the endpoints exist,
nothing in `apps/web` consumes them. **Nothing writes to the bank
automatically**: the `needs_human` path does not yet capture what the user typed
into the form, so today the only way an answer gets in is an explicit PUT. That
is the obvious next step and the feature is half-useful without it. No
embedding-based matching — a `# ponytail:` comment names the lexical ceiling
(genuine paraphrases with different vocabulary, "what draws you to this role",
cannot be recognised at all) and names `voyage-3-lite` as the upgrade path;
skipped because it puts a network call on a path that is currently free and
instant, and the strict-miss behaviour is the safe direction to be wrong in. The
bidirectional coverage rule is deliberately strict for the same reason: adding a
content word ("…work **at our company**") is a miss, and the user gets asked
again rather than given a plausible wrong answer. `find_answer` is a linear scan
of one profile's bank (`# ponytail:` comment, upgrade path named) — a bank is
tens of rows, one per distinct question a human has been asked.

**Next.** Capture the answer at the `needs_human` boundary so the bank fills
itself, which is what turns this from a feature into the loop the brief
describes. Then surface it in `apps/web`. Standing blocker unchanged:
`ANTHROPIC_API_KEY` is still a placeholder.

---

### 2026-09-27 (latest+18) — ATS apply-target resolver: the aggregator link becomes the real form, and the SSRF guard learns to check every hop

**Context.** Phase 1 left the driver opening whatever `apply_url` a feed handed
it. That is almost never the application form: RemoteOK gives its own listing
page, Working Nomads gives a `/job/go/{id}/` bounce. The driver then tries to
fill a page that has no form on it. Resolving the link first is the difference
between a Greenhouse form we can fill from `deterministic_fields` and a guess.

**The licence gate came first (ADR-010), and it passed.** Read
`kalil0321/ats-scrapers`'s actual LICENSE file via the GitHub API, not GitHub's
sidebar label: `MIT License / Copyright (c) 2026 Kalil Bouzigues`, standard
unmodified MIT text. So adoption is permitted, and `DEPENDENCIES.md` §3's row
moves from "study only" to partial adoption — **that verdict was correct when it
was written and is now wrong for a specific reason**: it was correct under
ADR-002, which forbade scraping and therefore left nothing here worth taking.
ADR-015 lifted that, and a URL→ATS catalogue became a product requirement.
What was adopted is **facts, not files**: the host→ATS mapping from
`src/ats_scrapers/resolve.py`. Its scrapers, registry, and models were not taken.
Its ~63k-company slug directory was **deliberately not vendored** — 47 CSVs,
~6.7 MB, to answer a question this project never asks; reasoning recorded in
`DEPENDENCIES.md` rather than decided silently.

**One pattern table, extended, not a second one.** `discovery.ATS_PATTERNS` went
from 5 ATS types to 17 (+ workday, jobvite, icims, recruitee, teamtailor, breezy,
bamboohr, personio, pinpoint, jazzhr, gem, rippling; plus Greenhouse's
`job-boards`/`.eu` hosts and Lever's `.eu` host, which we were previously blind
to). `detect_ats` reads the same list, so F5 board discovery got all of it for
free. The origin + copyright line sits in a comment directly above the table,
which is the MIT attribution obligation discharged where someone will actually
see it.

**`connectors/apply_target.py` — `resolve_apply_target(url) -> {final_url,
ats_type, board_token, resolved}`.** It walks the redirect chain **by hand**,
`follow_redirects=False`, one hop at a time, because `is_safe_url` has to run
before *every* request. Handing the chain to httpx would check the first URL and
then cheerfully follow a 302 into `169.254.169.254` — the guard's entire purpose,
defeated. Three tests cover that (metadata endpoint, loopback, RFC1918), and they
mock **DNS, not the guard**: `connectors.discovery.socket.gethostbyname` is
patched with a host→IP map so the real `is_safe_url` executes on every hop.
Patching `is_safe_url` itself would have made the per-hop property untestable,
which is exactly the bug being guarded against. A URL that already names its ATS
returns with **zero** network calls. `resolved` means "we reached a real
destination", not "we recognised the ATS" — `ats_type` can be None on a resolved
result, because landing on the company's own page still beats handing the driver
a redirector.

**Caching.** Redis by URL, `apply_target:v1:` prefix, 7-day TTL — an ATS URL for
a live posting is stable for weeks. `get_redis_connection` is imported *inside*
the function: `workers.jobs` imports half of `connectors/`, so a module-level
import is a cycle. Redis down at connect time, on `get`, or on `setex` all fall
through to a plain resolution. **No DB column and no migration** — `0014` belongs
to another agent and the chain must not collide.

**Work-queue integration is additive.** `WorkQueueItemOut` gains
`original_apply_url`, `ats_type`, `board_token`; `apply_url` now carries the
*resolved* target when resolution succeeded and the original when it did not, so
the shipped driver benefits with no change at all. A resolver exception is caught
per row and degrades to the original URL: resolution is an optimisation and must
never be able to empty the queue. That has its own test.

**The live check, and what it actually found.** `fetch_remoteok_jobs()` returned
**99 real rows, 99 with an `apply_url`** — and resolution found a real ATS on
**1 of 99** (`ashby`/`stickermule`). Not a resolver bug: RemoteOK's `apply_url`
*is* its own listing page (it 200s, and `remoteok.com/l/{id}` 302s right back to
it), and the outbound apply link is behind a JS/login wall — the served HTML
mentions greenhouse/lever/ashby/workable/workday **zero** times. Working Nomads
is the opposite and is where the value is: **15/15 sampled `/job/go/` links
resolved to a genuinely different destination, 4 of 15 to a named ATS**, e.g.
`https://www.workingnomads.com/job/go/1878435/` →
`https://jobs.ashbyhq.com/lemon-io/4dc7dd66-…` (`ashby`/`lemon-io`). Himalayas:
0/15. So the honest summary is that this pays off per-feed, not uniformly.

**What broke, found by the live run and not by any mock.** The first version
reported an Arbeitnow page as company **"app" on Recruitee** — the subdomain
regex had matched `app.recruitee.com`, Recruitee's own console. That URL would
have sent the driver to a login screen and burned a submission attempt on a real
application. Fixed with one shared `_RESERVED_SUBDOMAINS` guard (generalised from
ats-scrapers' own per-ATS reserved-segment sets), including a lookbehind so a
rejected reserved label cannot be salvaged by restarting mid-word (`app.` → `pp.`)
— which would have reintroduced the bug. Verified red first: the pre-fix regex
demonstrably captures `app`. Cost of the fix: Teamtailor went 4 → 0 on the same
sample, i.e. some of those "hits" were vendor URLs too. A false negative is the
right trade here — an unresolved link is handled; a confidently wrong ATS is not.

**Second thing that broke.** Adding a network collaborator to
`/extension/work-queue` silently put the eleven existing work-queue tests on the
live internet. Fixed with one autouse fixture in `tests/conftest.py` patching
`main.resolve_apply_target` to a pass-through; tests that care patch it
themselves and the inner patch wins.

**Files.** `apps/api/connectors/apply_target.py` (new),
`apps/api/connectors/discovery.py` (`ATS_PATTERNS` extended,
`_subdomain_tenant`/`_RESERVED_SUBDOMAINS` added), `apps/api/main.py`
(`/extension/work-queue`), `apps/api/schemas.py` (`WorkQueueItemOut`),
`apps/api/tests/test_apply_target.py` (new, 29 tests),
`apps/api/tests/conftest.py`, `docs/DEPENDENCIES.md` §3.

**Verification.** Red-before-green (the whole file failed collection first; the
reserved-subdomain fix was proven red separately). **310 → 339 backend tests, all
passing.** Every unit test is offline — `httpx` mocked throughout — and the one
live check is the RemoteOK/Working Nomads run above.

**Deliberately left out.** No per-ATS field schemas (the other half of "Phase 2"
in the previous entry's Next) — `POST /extension/map-fields` still reads the real
page, which is the correct order: knowing it is Greenhouse does not tell you
which Greenhouse questions this posting asks. No resolution at ingestion time; it
happens on work-queue read, cached, which keeps it off the connector hot path.
No LLM fallback for unrecognised pages — `classify_unknown_ats` already exists
for the domain-discovery path and pointing it at aggregator links would spend
tokens per queue item. No headless browser, so RemoteOK's JS-gated apply link
stays out of reach.

**Next.** Field schemas per ATS; wire the resume docx to file inputs; and the
standing blocker is unchanged — `ANTHROPIC_API_KEY` is still a placeholder.

---

### 2026-09-27 (latest+17) — ADR-015 Phase 1: the execution loop closes, and `submitting` stops a silent lie

**Context.** After the campaign model landed, `run_campaign_task` produced
`approved` applications and *nothing ever collected them* — a campaign ended in a
queue rather than a sent application. The machinery to submit already existed
(deterministic field maps, the extension's form fill, the ADR-001 static guard,
`claim-submission`'s row-locked at-most-once authority); what was missing was
three connections: a work queue to pull, a driver to act, and outcome reporting.

**The correctness bug found while wiring it, which had to be fixed first.**
`claim-submission` flipped the row to `applied` and stamped `applied_at` *before*
the extension's native form submit fired. Any form that then failed left the
application saying `applied`, with a timestamp for an event that never happened.
That is the worst failure mode this product can have: it silently drops real
applications while telling the user they went out. New
`ApplicationStatus.submitting` (migration `0013`, **applied live to Neon**,
`ALTER TYPE ... ADD VALUE ... BEFORE 'applied'`) names that window, and
`POST /applications/{id}/submission-result` is the only thing that closes it:

| outcome | status | why |
|---|---|---|
| `submitted` | `applied` + `applied_at` | terminal; the send really happened |
| `failed` | back to `approved` | the form never went through, so it is work again |
| `needs_human` | `ready_for_review` | captcha, account wall, essay question |

`needs_human` deliberately reuses `ready_for_review`, which means **the review
queue becomes an exception handler rather than a gate** — exactly the reframing
ADR-015 called for, achieved by not building a second queue. The at-most-once
guarantee is unchanged: after a claim the row is no longer `approved`, so a second
claim still 409s, and only a `submitting` row can be reported on (otherwise a
caller could mark any application `applied` without ever claiming it).

**`GET /extension/work-queue`.** Only `approved` rows, joined to their job, with a
non-empty `apply_url` (an unactionable row would buy a guaranteed failure report
and burn a retry). Self-draining: because the claim moves a row out of `approved`,
a second driver pass cannot pick up an item already in flight — that property has
its own test, since it is how the same job would otherwise be applied to twice.

**The driver** (`apps/extension/src/background/`). `driverCore.mjs` holds the
decisions and is unit-tested (15 tests, `node --test`): `classifyFailure` splits
retryable failures from ones only a human can clear, and `planRun` enforces
`MAX_ATTEMPTS_PER_ITEM` so a permanently broken form cannot starve the rest of the
queue on every pass. `driver.ts` is thin chrome glue: fetch queue → open each
`apply_url` in a background tab, sequentially → wait for a report → close the tab
→ POST the result. Sequential on purpose (parallel tabs race the same daily cap
and make "what went out" unreadable). A per-item 60s timeout reports `failed`; the
tab is closed on every path, including timeout, because one leaked tab per failed
application makes the browser unusable within a dozen jobs.

`autoApply.content.ts` asks the driver *what this tab is for* rather than reading
`location.href` — a redirect or a stale tab would otherwise submit the wrong job.
If any field came back flagged (demographic, essay, low confidence) it stops and
reports `needs_human`: filing an application with blanks where required answers
belong is worse than not applying, and inventing the answer is what ADR-006/009
forbid outright.

**Two real bugs caught in my own design while writing it.**
1. `fillForm` used `alert()` on every failure path. In a background tab an alert
   blocks that tab indefinitely with nobody to dismiss it, stalling the queue on
   the driver's timeout. Fixed at the root: `fillForm` now throws and returns
   `{filled, flagged}`; the interactive `jc:fill-form` listener catches and alerts,
   so nothing changes for a user who clicked the button themselves.
2. `autoApply` initially reported every error as `failed`, so a captcha detected
   *on the page* would be retried forever and never reach the user. It now uses
   the same `classifyFailure` the driver uses — the classification has to live
   wherever an error becomes an outcome, not in one of the two places.

**Verification.** Red-before-green throughout (15 backend tests written and run
failing first — 13 of 15 red on the first run, the other 2 passing only because
they assert absence). **310/310 backend tests** (295 → +15). Extension: **24/24**
`node --test`, `tsc --noEmit` clean, `vite build` succeeds. `0013` verified against
live Neon: `applicationstatus` is now `[saved, submitting, applied, oa, recruiter,
interview, offer, rejected, ready_for_review, approved, dismissed]`. One
pre-existing test, `test_claim_submission_transitions_approved_to_applied`,
asserted the old straight-to-`applied` behaviour — rewritten and renamed to assert
the new state machine *and* that the round trip still reaches `applied`. It was
not deleted or weakened.

**Not verified, and why.** No live-browser run: this project has no
loaded-extension or Playwright access, the same standing limitation recorded for
all the content-script work. Every decision was therefore pushed into
`driverCore.mjs` where it can be tested in Node, leaving `driver.ts` and
`autoApply.content.ts` as glue thin enough to verify by reading. **Nothing has
ever actually submitted a real application.** The first real run will find things
these tests cannot.

**Deliberately left out.** No scheduler or `chrome.alarms` — the popup's "Run
apply queue" button is the only trigger, so the user is present for the session in
which applications go out. No résumé *file* upload wired to the file input
(`GET /profiles/{id}/resume.docx` exists and is ATS-linted; connecting it is Phase
2). No digest (Phase 3). `attempts` is in-memory, so a service-worker restart
forgives prior attempts — a `ponytail:` comment names `chrome.storage.local` as the
upgrade path.

**Next.** Phase 2: `ats-scrapers` to resolve aggregator `apply_url`s to real ATS
endpoints and supply per-ATS field schemas; wire the docx to file inputs; feed the
keyword-gap scorer into `tailoring/engine.py`, which still ignores it. And the
standing blocker: `ANTHROPIC_API_KEY` is still a placeholder, so essay-style
questions cannot be answered at all and ADR-014 still has no tailoring-quality
signal.

---

### 2026-09-27 (latest+16) — JD↔resume keyword gap scorer, no-fabrication rail, live-verified on 99 real JDs

**Context.** `documents/ats_safety.py` already makes the generated DOCX
*mechanically* ATS-safe (8 linted format rules). That is only half of the
owner's actual goal ("the main aim is to get more interview calls"): the other
half is whether the resume surfaces the **vocabulary** the JD is screened on.
Nothing in the repo answered "which of this job's keywords does your resume
fail to show, and which of your real facts already cover them." This adds it.

**New `matching/keyword_gap.py::compute_keyword_gap(job_description, facts,
job_skills=None, job_title=None)`** returning `coverage` (0..1, importance-
weighted — failing a "high" keyword costs 3x failing a "low" one), `matched`
(each with `match_type` exact|fuzzy|synonym and the id/index of the fact that
evidences it), `missing`, `weak`, and `suggestions`. `facts` takes
`ResumeFact` rows or plain strings. Deterministic: regex + `rapidfuzz`
(installed since Phase 3 and, until now, unused by any feature) — **no LLM
call**, so it is free and instant enough to run on every match, and it stays
off the `ANTHROPIC_API_KEY`-blocked path entirely. JDs arrive as HTML from the
feeds; stripped with stdlib (`html.unescape` + tag regex, no parser
dependency) before analysis.

**The rail, which is the whole point.** A `missing` keyword means "the user
does not have this," and it may never become a suggestion. This is enforced
structurally, not by a check: `_build_suggestions` takes `matched`/`weak` as
its only inputs, so there is no code path from a missing keyword into a
suggestion at all, and the only two actions that exist are `surface` (move a
real fact's real content where an ATS can see it) and `reword` (say the same
true thing in the JD's wording) — there is deliberately no "add". A trailing
filter drops anything in `missing` as a second lock on the same door, and
`test_no_suggestion_ever_references_a_missing_keyword` asserts it against a JD
deliberately stuffed with unsupported keywords. ADR-009 is what makes this
checkable at all: suggestions can only point at facts, so "which fact backs
this?" always has an answer.

**`weak` is the genuinely useful output, and it is not a score.** Two distinct
kinds of buried: `metadata_only` (the keyword lives only in a fact's
tags/metric, so it never reaches the bullet text a keyword scan reads — a real
gap the database hides) and `single_mention` (in exactly one bullet while the
JD leans on it — a reorder opportunity). On the live run these were 18 and 14
occurrences respectively across 52 scored jobs.

**Extended `matching/skills.py` rather than forking a second vocabulary.** New
`skill_occurrences()` (name → count, which the importance heuristic needs) and
`skill_pattern()` (so the fact side matches with the *exact* regex semantics
the job side was extracted with, not a subtly different second one);
`extract_skills` is now a one-liner over the former. ~70 vocabulary terms added
that real JDs demand (Airflow, dbt, Snowflake, Jenkins, Helm, Pytest,
Playwright, OAuth, GDPR, Amplitude, Project Management, …). Terms that are also
ordinary English words — `Excel`, `Segment`, `Strategy`, `Linear`, `R` — were
deliberately *left out*: a report claiming you lack "Excel" because the JD said
"excel at communication" is worse than silence.

**What broke, and it was real.** The live run against 99 RemoteOK JDs (not a
fixture — this is exactly why the brief demanded real data) found that a
product manager's own metric, "…within first weeks of **go-live**", matched the
**Go language** via `(?<!\w)Go(?!\w)` with `re.I`, and the scorer then emitted
`{"action": "surface", "keyword": "Go"}` — advice to write a programming
language the candidate does not know onto their resume. The anti-fabrication
rail held for *missing* keywords exactly as designed and still produced a false
claim, because the keyword was wrongly classified as **matched** in the first
place. Fixed at the source in three layers, since all of them were wrong the
same way: (1) `skills.AMBIGUOUS_TERMS` (Go, REST, Swift, Rust, Spark, Flutter,
Jest, Sass, Helm, Notion, Express, Flask, Angular, Bash, Airflow) now match
case-sensitively and never inside a hyphenated compound — fixed in `skills.py`
and not filtered downstream, because `extract_skills` feeds `Job.skills` and
every match's `skill_coverage`, so **existing** callers had this bug too;
(2) short all-caps acronyms (ML, JS, TS, PM — the synonym aliases) get the same
rule, and `skill_pattern()`'s fallback now routes through `_compile` instead of
quietly rebuilding a loose pattern and undoing the fix; (3) fuzzy matching is
skipped entirely for ambiguous terms, because the fuzzy scan lowercases both
sides and thereby discards the very casing signal the fix depends on — "rest of
the team" scored 100 against "REST". Three regression tests, each named after
the real input that found it. Effect on the live numbers: spurious matches
gone, total suggestions across the 99 jobs dropped 43 → 32.

**Dead ends / corrections, recorded so nobody redoes them.** (a) The brief said
to pull a JD via `connectors.feeds.fetch_remoteok_jobs()`; `connectors/feeds.py`
does **not** exist on this branch's base (`d6a5dab`) — it arrived in a parallel
agent's later merge and is present only in the main checkout. Worked around by
fetching in the main checkout and scoring in the worktree, two steps, no
cross-contamination. (b) The brief's "245 passed" baseline is the **main
checkout's** count; this worktree's HEAD baseline is **232**. (c) This worktree
has no `.venv`/`.env` of its own — both live in the main `apps/api`; `.env` had
to be copied in (gitignored) because `core.config.Settings` resolves it from
the process CWD. (d) The synonym map initially only ran against the facts, so a
JD saying "K8s" never produced "Kubernetes" as a keyword to score at all —
aliases have to be resolved on the **JD** side too. (e) `json.dump` on the
connector's output needs `default=str` (`posted_at` is a `datetime`).

**Real numbers, live.** 99 real RemoteOK rows (all 99 HTML, longest 25,355
chars) scored against the real 24-fact `resume_kb/facts.json`. 52 jobs had ≥1
recognised JD keyword; mean coverage **0.284**, median 0.000, max 1.000; 28 jobs
at 0.0 coverage, 13 at ≥0.5; 4.1 keywords/job; match types exact 24 / synonym 7
/ fuzzy 1; 32 suggestions total. Both invariants held on real data: **0**
suggestions referencing a `missing` keyword, **0** pointing at a non-existent
fact. The low mean is honest, not a bug — the Facts KB is a product manager's
and this feed is mostly engineering roles; the "Frontend Engineer" row scored
0.000 with React/TypeScript/Next.js/CSS all correctly `missing` and,
correctly, **zero** suggestions. The realistic case is the PM rows: coverage
0.429 and 1.000, each with a single `reword` suggestion ("Product Strategy",
matched via the PM synonym).

**Endpoint.** `GET /matches/{match_id}/keyword-gap`, tenant-scoped with the
same `Match`-join-`Profile`/`user_id` pattern as its neighbours (cross-user
404 tested). `schemas.KeywordGapOut` + 4 nested models. **No migration** —
computed on demand, no columns added (migration `0012` belongs to a parallel
agent). No new dependencies.

**Not done, honestly.** `weak`/`suggestions` are not wired into any UI or into
`tailoring/engine.py` — the scorer is callable and exposed, but nothing
consumes it yet, and the `reword`/`surface` suggestions are advisory text a
human acts on, not something applied automatically. Coverage is computed
against a fixed vocabulary, so recall is still bounded by that list
(pre-existing ceiling, marked in `skills.py`). The importance heuristic cannot
tell "5+ years of Kubernetes" from "we run Kubernetes" — both read `high`.

**Files created.** `apps/api/matching/keyword_gap.py`,
`apps/api/tests/test_keyword_gap.py`,
`apps/api/tests/test_keyword_gap_endpoint.py`. **Files changed.**
`apps/api/matching/skills.py` (occurrences/pattern helpers, ~70 new terms,
`AMBIGUOUS_TERMS`), `apps/api/schemas.py` (`KeywordGapOut` + 4 nested,
`Union` import), `apps/api/main.py` (the endpoint). **Tests.** 232 → **252**
passed, full suite green from `apps/api`.

---

### 2026-09-27 (latest+15) - Onboarding wizard (`/onboarding`): landing to a running campaign, ADR-015 approve-once

**What changed.** Built the multi-step onboarding flow the owner described as "one portal,
my portal, where a user can come, fill out every form and do the onboarding, everything,
from first to last" - five steps from resume upload to a live campaign. This is also the
first page in `apps/web` that actually uses the shadcn/Kibo UI kit installed back in
latest+6; every prior page was inline styles or unstyled Tailwind (see the real bug below).

The five steps, and what each one really talks to:
1. **Upload your resume** - Kibo UI's `Dropzone` (already installed, first real use) ->
   `POST /profiles/{id}/resume`. Shows the parsed fact count and the first three facts,
   and says plainly that nothing is saved yet. 5MB / .pdf / .docx limits mirror
   `MAX_RESUME_UPLOAD_BYTES` and the format check in `apps/api/main.py` so the user gets
   told before the round trip, not by a 413/422 after it.
2. **Confirm your facts** - renders the *draft* `basics` the upload endpoint already
   returns (`ResumeUploadOut.basics`, which `lib/api.ts` was not previously typed for)
   alongside the draft facts. Both are editable. Persisted only on leaving this step, via
   `PUT /profiles/{id}/basics` then `POST /profiles/{id}/facts:bulk` - the same
   "parsed output is never silently trusted" rule those two endpoints already enforce
   server-side (SPEC.md S2.1). The ADR-009 stakes are stated at the top of the step in
   plain words ("this list is the whole truth we work from... anything you delete here can
   never appear in an application; anything wrong here can") rather than left implicit.
   The client-side validators in `lib/onboarding.ts` mirror `schemas.ApplicantBasics`
   field-for-field - placeholder names, the reserved fictional 555-01XX phone range,
   scheme-less URLs, non-alpha2 country codes - so the user sees the problem next to the
   input instead of a 422 after pressing Continue. That is UX; the server still re-validates.
3. **What you're looking for** - roles, locations, remote-only, salary floor.
4. **Create your campaign** - the ADR-015 approve-once step: sources, min match score,
   daily cap, auto-submit. Framed honestly: the cap is described as a hard stop rather
   than a target, and switching auto-submit on reveals a real warning naming the number of
   applications per day that will reach real employers with no further prompt, that it can
   be switched off, and that anything already sent stays sent.
5. **Done** - campaign summary, `GET /campaigns/{id}/stats` counters, first five matches
   from the existing `GET /matches`, and links onward to `/matches`, `/review`, `/facts`.

**Why now.** `/review` (latest+14) gave Phase 3 a human checkpoint but there was no way to
*get* to a state where anything was in it - no profile setup, no preferences, no campaign.
This is the front half of that same coordinated piece of work.

**Built against a contract, not against a running backend.** A parallel agent is building
the campaign API. `POST /campaigns`, `GET /campaigns`, `POST /campaigns/{id}/run`,
`GET /campaigns/{id}/stats` are all typed and wired in `lib/api.ts` from the agreed
contract; none of them exist in `apps/api` yet, and a 404 is the expected response today.
Every one of those call sites renders a named failure notice saying which endpoint 404'd
and that the backend is not deployed yet - never a silent empty screen - and the campaign
that was created is not discarded if only the follow-up `run` fails.

**ADR-015 is not in `docs/DECISIONS.md`.** Checked: the file ends at ADR-014, and there is
no uncommitted change to it in this worktree. The pivot (approval happens once at campaign
level, not per application) was taken from the task framing and implemented accordingly,
and it is consistent with ADR-001's "human approves, machine executes" - the approval just
moves up a level. Whoever owns ADR-015 still needs to write it down; this UI is currently
the only place that behaviour is described.

**Two pre-existing bugs found on the way, both real, neither mine.**
1. **`tailwind.config.js`'s `content` globs never included `./app`** - only `./pages` and
   `./components`. Every app-router page built since Phase 1 (`/facts`, `/login`,
   `/matches`, and latest+14's `/review`, which is written entirely in Tailwind classes)
   has therefore been rendering with *zero* generated utilities. It builds clean, which is
   exactly why nobody caught it: a missing content path is not a build error, it is a
   silently empty stylesheet. Added `./app/**/*.{js,ts,jsx,tsx}`. `/review` should be
   eyeballed by whoever owns it - it has never actually been seen styled.
2. **`vitest` was installed with no config at all**, which is why three prior entries
   correctly reported "no test runner wired up". Added `vitest.config.mts` (`.mts`, not
   `.ts` - Vite's native config loader warns on ESM syntax in a file it loads as CJS) and
   an `npm test` script.

**Tests - 25, and the reason they are not component tests.** `@testing-library/react` is
installed but **neither `jsdom` nor `happy-dom` is**, and neither is in the lockfile
(checked, not assumed). Installing one needs owner approval per ADR-010, so rather than
stall or install unilaterally, the wizard's decision logic was factored out of the
components into `lib/onboarding.ts` and tested there under `environment: "node"`:
step gating (`canAdvance` - will not leave the resume step with no parsed facts, will not
leave facts with an emptied one, will not leave preferences without a role, but accepts
`remote_only` in place of a location), the facts-editor round-trip (`editFact` replaces only
the edited fact, does not mutate the original, and `validateFacts` reports the offending
index so the error can be shown inline), basics validation, campaign bounds, and
`buildCampaignBody`. `lib/campaigns.test.ts` asserts via **msw** that `POST /campaigns`
sends exactly the contract body - key-for-key, no extras - that the documented defaults
(0.7 / 10 / false) go over the wire, and that a 404 surfaces as an `ApiError` rather than
resolving empty. Red-before-green was real: the first run failed with
`Cannot find module './onboarding'` before any implementation existed.
**Left open:** rendering tests for focus-on-step-change and the auto-submit warning
appearing. Those genuinely need a DOM. One `npm i -D jsdom` closes it - ask first.

**Accessibility decisions.** Every input is a real `<input>`/`<textarea>` with a real
`<label htmlFor>` (the wiring lives in one `Field`/`Chips` pair in
`components/onboarding/fields.tsx` precisely so it is not written thirteen times and wrong
in three of them); errors are `role="alert"` and joined to their input by
`aria-describedby` + `aria-invalid`; progress is an `<ol>` with `aria-current="step"`, so
the step count and position are available without sight; source and auto-submit groups are
real `<fieldset>`/`<legend>`; the step panel is `tabIndex={-1}` and takes focus on every
step change (a wizard that swaps its whole panel without moving focus strands a keyboard
user on a button that no longer exists), skipping the first render so it does not steal
focus on load; one `aria-live="polite"` region announces step changes and blocked advances.
**Continue is deliberately not disabled when the step is invalid** - a disabled button
gives a keyboard or screen-reader user no way to learn *why* - it stays pressable, reveals
the errors, and returns focus to the panel. Errors stay hidden until the first attempt to
advance, so the form does not shout at someone who has not typed anything yet. No
div-as-button anywhere; Enter inside the chips input is `preventDefault`-ed so it adds a
chip instead of submitting the step.

**Dependencies added.** None. Used Kibo UI's dropzone, shadcn's Checkbox/Input/Label/
Textarea/Badge, radix via the existing `radix-ui` umbrella, and lucide icons - all already
installed. Kibo UI's **combobox was deliberately not used** for roles/locations: it wants a
fixed option list and those fields are genuinely open-ended, so a plain input plus
removable chips is both smaller and more honest about what is accepted. `@dnd-kit` turns
out to be in `package.json` already (pulled in with the Kibo kanban), contrary to the
standing note that it was missing - nothing here needs it either way. Tailwind stayed
pinned at 3.4.4 and no v4 syntax was introduced.

**Honest gaps, not silently dropped.**
- **No separate landing route.** `/` is still the legacy pages-router dashboard
  (`pages/index.js`) and Next cannot have both routers own the same path, so the wizard
  lives at `/onboarding` and `/` got one link into it. A real marketing landing page is a
  separate piece of work.
- **Salary floor has no home in the campaign contract.** It is collected and passed through
  `tailoring_notes` as a note, and the field says so out loud - "we pass this along as a
  note on the campaign rather than filter on it - it is not a hard cutoff yet". The
  alternatives were inventing a contract field the backend agent is not building, or
  dropping a field the task asked for. If salary should actually filter, it needs a real
  contract field.
- **Preferences are not persisted anywhere except the campaign body.** There is no
  `PATCH /profiles/{id}` and `Profile.prefs` is only writable at creation, so roles/
  locations/remote-only live on the campaign. Reloading mid-wizard loses them.
- **The source list is mirrored, not fetched.** No endpoint enumerates connectors, so
  `AVAILABLE_SOURCES` in `lib/onboarding.ts` hardcodes the six real ones read out of
  `apps/api/connectors/` (`jobspy_google` is labelled "currently returning no results",
  which is true per latest+6). Adding a connector means editing this list.
- **The wizard does not resume.** Reload and you start at step 1. Nothing is lost that was
  already persisted (facts and basics are saved at step 2), but the in-flight draft is.
- **Not verified in a browser.** The campaigns endpoints do not exist yet, so a dev server
  would only demonstrate the 404 path. Loading/error/empty branches were verified by
  reading the JSX against React Query's flag semantics, as in latest+14.
- **The global `body` rule in `styles/globals.css` still hardcodes the old dark-green
  scheme**, which fights shadcn's light `--background`. Worked around rather than fixed:
  `/onboarding` wraps itself in `bg-background text-foreground`. Fixing it properly means
  deciding what the app's actual palette is, which is a design call, not a build fix.

**Files created.** `apps/web/app/onboarding/page.tsx` (wizard shell, focus management,
step gating, mutations), `apps/web/components/onboarding/{fields,StepResume,StepFacts,
StepPreferences,StepCampaign,StepDone}.tsx`, `apps/web/lib/onboarding.ts` (steps,
validation, `buildCampaignBody`), `apps/web/lib/{onboarding,campaigns}.test.ts`,
`apps/web/vitest.config.mts`.
**Files changed.** `apps/web/lib/api.ts` (`ApplicantBasics`/`NetworkProfile` types,
`ResumeUploadResult.basics`, `Campaign`/`CampaignCreate`/`CampaignStats`, and
`listCampaigns`/`createCampaign`/`runCampaign`/`getCampaignStats`/`getBasics`/`putBasics`),
`apps/web/tailwind.config.js` (the `./app` content fix), `apps/web/package.json`
(`test` script), `apps/web/pages/index.js` (one link to `/onboarding`).
**Not touched:** `apps/api/` and `docs/DECISIONS.md`, both owned by parallel agents.

**Verification.** `npm run build` clean - 9 static pages, `/onboarding` at 21.9 kB
(150 kB First Load JS), no new warnings beyond Next's pre-existing multi-lockfile
workspace-root notice. `npm test` - 2 files, 25 tests, all passing. Ran `next build` via
`node node_modules/next/dist/bin/next build` again, same reason as latest+14 (`next` not
on `.bin` after `npm ci` in a worktree). Did *not* need the `rm -rf .next` trick this time
- the build was green first try after the Tailwind fix - but cleared it before trusting
the baseline, per the standing note.

**Next.** Merge the campaigns backend and the 404 notices turn into real data with no
frontend change. Then: `npm i -D jsdom` (needs approval) to close the rendering-test gap;
look at `/review` with styles actually applied for the first time; write ADR-015 down;
decide the palette so `globals.css`'s `body` rule can stop fighting the design tokens.

---

### 2026-09-27 (latest+14) — ADR-015's campaign model: the pivot's core, cap enforced in one place

**Context.** ADR-015 §2 replaces ADR-001's per-application approval gate with a
single campaign-level approval: the user approves roles / sources / caps /
template once, and the agents discover → tailor → apply inside those bounds.
The campaign model did not exist at all — this is the piece the rest of the
pivot hangs off. A parallel frontend agent was building against a fixed
contract while this was written, so the shapes below were held exactly, with
the two deviations called out at the end.

**`campaigns` table + `applications.campaign_id`** (migration `0012`, **not
applied — the owner applies migrations**, command in the report). `Campaign`
holds the approved bounds: `roles`/`locations`/`sources` (JSONB, empty = no
restriction on that axis), `remote_only`, `min_match_score`, `daily_cap`,
`auto_submit`, `tailoring_notes`, and a `CampaignStatus` enum
draft|active|paused|archived. `DELETE /campaigns/{id}` sets `archived` — never
a hard delete, the campaign is the record of what the user actually authorized.

**The daily cap has exactly one implementation, deliberately.**
`campaigns.py::remaining_quota(db, campaign)` is `max(0, daily_cap -
applied_today)`, and `applied_today` counts this campaign's `applications` rows
created in the current UTC day. Both callers — `run_campaign` and
`GET /campaigns/{id}/stats` — go through it; nothing recomputes it. No counter
column and no `campaign_runs` table on purpose: a denormalized counter drifts
from what actually went out, the rows can't. The `max(0, ...)` clamp matters for
a real case, not a hypothetical one — lowering `daily_cap` below today's count
would otherwise produce a negative budget that any `if remaining:` check reads
as truthy.

**Idempotency, and being honest about which layer does the work.**
`run_campaign_task` copies `discover_jobs_task`'s two layers: a per-minute
`run_id` enqueued `unique=True` (layer 1, in `main.py`) and a Redis SETNX claim
inside the task (layer 2). But the claim is *not* what holds the cap — the
double-run test deliberately lets **both** claims succeed and still asserts
only `daily_cap` applications exist, because the quota is recounted from the
database inside the run. The claim only saves the wasted LLM work. Worth
writing down: a test that proved the cap by mocking the claim to fail would
have proved nothing about the cap.

**`campaigns.py::run_campaign`** selects matches above `min_match_score`
(scaled ×100 — see the deviation note), inside the role/location/source
filters, excluding jobs this profile already has an application for, limited to
the remaining quota; creates the `Application` rows linked to the campaign;
commits **before** any tailoring, since the rows are what the cap counts and
must be durable before the slow part can crash; then calls the existing
`batch_prep.prepare_application_for_review` per application. `auto_submit=True`
flips the result to `approved` (no human review step); `False` leaves it at
`ready_for_review`. **No submission happens here** — that is a separate task,
and this stops at prepared/approved by design.

**Tenancy.** `campaigns.py::resolve_campaign_ownership` mirrors
`core/deps.py::resolve_profile_ownership` — reachable only via a profile the
caller owns, 404 rather than 403 so a cross-tenant id is indistinguishable from
a missing one. `GET /campaigns` scopes by the join, not by a client-supplied
`profile_id`: there is nothing in that request to trust. Migration `0012` also
gives `campaigns` the same RLS policy + FORCE that `0010` gave the other 7
tenant tables — without it this would be the one tenant table with no
database-level backstop, which is exactly the gap `0010` exists to close.

**Red-before-green, 30 new tests** (`232 -> 262`, whole suite green). Covered:
the cap boundary (cap-1/cap/cap+1 → 1/0/0 remaining), yesterday's applications
not counting, another campaign's applications not counting, a paused campaign's
run being a true no-op (no rows, no prep call, `last_run_at` untouched), the
role/location/source filters, already-applied jobs skipped, both `auto_submit`
paths, the double-run cap property above, cross-tenant isolation at both the
function and the HTTP layer (get/patch/delete/stats/list, plus creating a
campaign on someone else's profile), archive-not-delete, and the status
transition matrix including the two that must 422 (archived→active,
draft→paused).

**Two dead ends / corrections, recorded.**
1. The brief said `sources` should be validated against `connectors/config.py`'s
   `ENABLED_FEEDS` and `JOBSPY_SITES`. **Those constants do not exist** —
   `connectors/config.py` only has the per-connector keyword/token lists, and
   JobSpy is still hardcoded to `site_name=["google"]` inside
   `jobspy_connector.py`. So `sources` is an unvalidated `list[str]` matched
   against `Job.source`; an unknown name simply matches no jobs. A real
   enum/allowlist belongs with the ADR-015 §1 multi-source work that introduces
   those constants, not ahead of it.
2. The first cut of the "SET NULL doesn't delete history" test deleted a
   campaign row and asserted the applications survived. That test passes no
   matter what the constraint says — SQLite (the unit-test engine) doesn't
   enforce foreign keys by default. Rewritten to assert the declared
   `ondelete` on the FK itself, which is the thing that actually has to be
   right. Also hit a self-inflicted `canonical_hash` UNIQUE collision in a test
   helper that derived job ids from the campaign id + index, so calling it twice
   for one campaign collided — replaced with an `itertools.count()`.

**Files created.** `apps/api/campaigns.py`,
`apps/api/alembic/versions/0012_campaigns.py`,
`apps/api/tests/test_campaigns.py`. **Files changed.** `apps/api/models.py`
(`CampaignStatus`, `Campaign`, `Application.campaign_id`),
`apps/api/schemas.py` (`CampaignCreate`/`CampaignUpdate`/`CampaignOut`/
`CampaignStatsOut`), `apps/api/main.py` (7 endpoints),
`apps/api/workers/jobs.py` (`run_campaign_task`), `docs/SPEC.md` (regenerated
schema block — the generator's `--check` went red after the model change, as
designed).

**What's next.** Apply `0012`. Then actual submission (the piece
deliberately left out here), and ADR-015 §1's multi-source connector work,
which is what finally makes `sources` a validated set instead of free text.

**Merge note (integration, 2026-09-27).** This entry was written in a worktree
branched before latest+13 landed, so it reports that `ENABLED_FEEDS` /
`JOBSPY_SITES` "do not exist" and that JobSpy is still Google-only. Both are
now false on `master`: latest+13 added those constants and lifted the JobSpy
restriction. `sources` is still an unvalidated `list[str]` matched against
`Job.source` — the allowlist is now genuinely buildable from
`connectors/config.py` and is the obvious next small fix.

---

### 2026-09-27 (latest+13) — ADR-015 multi-source: six keyless public feeds live, JobSpy un-restricted

**Context.** Owner's framing, verbatim: "There are so many job portals apart from
LinkedIn and Indeed where jobs are posted… There are too many websites… I want to
build this in this project." Coverage was the complaint. Factually there was never a
LinkedIn connector here — but coverage really was thin: of six existing sources only
Remotive was a searchable board, the three ATS ones (Greenhouse/Lever/Ashby) need
hand-typed company tokens and shipped with **empty** token lists, Reed needs a key,
and JobSpy was pinned to Google alone and yielding 0. So in practice, one live board.

**Method: probe first, then write.** Every endpoint was fetched live and its keys
printed *before* any parser was written — no field names taken from docs, per the
standing "never guess APIs" rule. Six passed: Remote OK (`/api`, row 0 is a ToS
notice, not a job), Himalayas (`/jobs/api`), Working Nomads (`/api/exposed_jobs/`,
no id field — it's in the URL), Jobicy (`/api/v2/remote-jobs`), Arbeitnow
(`/api/job-board-api`, mixed remote/on-site, EU-heavy), We Work Remotely (RSS only;
parsed with stdlib ElementTree, no new dependency, and its employer is encoded in the
title as "Company: Role").

**`connectors/feeds.py`** — one file, six parse/fetch pairs on the existing connector
contract, plus `FEED_FETCHERS` and `fetch_enabled_feeds(enabled, keywords)`. Parsers
are pure, so `tests/test_feeds.py` needs no network. Two deliberate details:
`_salary()` renders only the bounds that actually exist (these feeds variously use 0,
null, or an absent key for "unknown" — a naive join produced a misleading
`0-160000`), and `filter_by_keywords([])` means *keep everything*, never *return
nothing*, so an empty config can't silently zero out a whole board.

**Failure isolation, the real design point.** With six boards, one going 502 or
drifting its JSON shape is routine, not an outage. `fetch_enabled_feeds` catches per
source and returns a report mapping each source to its kept count *or* its error
string; `discover_jobs_task` returns that as `result["feeds"]`. Fails visibly, per
ADR-015's "per-source adapters that fail visibly" — neither aborting the run nor
swallowing the error.

**JobSpy un-restricted (ADR-015).** Site list moved out of the hardcoded
`site_name=["google"]` into `config.JOBSPY_SITES` (default
`google, zip_recruiter, glassdoor`), and `source` is now `jobspy_{site}` rather than
the constant `jobspy_google` — a ZipRecruiter row logged as Google makes per-source
yield stats meaningless. LinkedIn and Indeed stay out, but as a **tested config
assertion** (`test_jobspy_never_scrapes_linkedin_or_indeed`) instead of a string
buried in the module, so adding either is a visible decision.

**Real bug this caught.** `test_discover_idempotency.py` patched each connector
individually, so the moment the worker gained a feed call those tests started making
real HTTP requests *and* real Voyage embedding calls — surfaced as a
`voyageai RateLimitError` inside a supposedly offline unit test. Fixed by stubbing
`workers.jobs.fetch_enabled_feeds` in that file's helper. Worth remembering: a test
helper that enumerates collaborators by name silently stops being a seam the next
time the function under test grows one.

**Verification.** Red-before-green on all three new test files. 245/245 backend tests
pass. Live run of all six feeds: `{"remoteok": 99, "himalayas": 20,
"workingnomads": 57, "jobicy": 50, "arbeitnow": 286, "weworkremotely": 80}` = **592
real jobs**, zero rows missing title/company/apply_url; keyword filter spot-checked
(`remoteok` + "engineer" → 23). Not yet inserted into Neon — that costs Voyage
embedding calls, so the upsert is left for a deliberate run.

**Files.** `connectors/feeds.py` (new), `connectors/config.py` (+`FEED_KEYWORDS`,
`ENABLED_FEEDS`, `JOBSPY_SITES`, `JOBSPY_KEYWORDS`), `connectors/jobspy_connector.py`,
`workers/jobs.py`, `tests/test_feeds.py` (new), `tests/test_feeds_discovery.py` (new),
`tests/test_jobspy_connector.py`, `tests/test_discover_idempotency.py`.

**Next.** Campaign model (ADR-015 §2) does not exist yet and is the actual core of the
pivot; removing the ADR-001 per-item submit gate; onboarding flow in `apps/web`;
a JD-vs-resume keyword-gap score surfaced to the user (docx ATS-safety linting already
exists in `documents/ats_safety.py` — format is covered, keyword targeting is not).

---

### 2026-09-26 (latest+12) — Roadmap sub-projects #2 + #4: batch prep pipeline and gated execution, live-verified

**Context.** Owner asked to finish all remaining decomposed sub-projects at
once, dispatching parallel agents for the independent tracks (unified
grounded-ID validator, SPEC.md-as-generated-docs, the review-queue frontend
— all three landed, see their own WORKLOG entries on worktree branches to be
merged) while the migration-touching, security-sensitive chain (#2 batch
prep -> #3's contract -> #4 gated execution, plus RLS above) was done
directly, sequentially, in this session.

**#2 — batch prep.** New `batch_prep.py::prepare_application_for_review`:
tailors + truth-checks an `Application` against its `ResumeFact`s, persists
`tailored_resume_json`, and — real gap closed here — `flagged_
unsupported_claims`, which `tailor_application()` has always returned but
`/tailor` never once persisted; ADR-006's whole point is those claims are
"surfaced, not silently kept," and until now they were silently dropped on
every call. Flips status to `ready_for_review`. New `ApplicationStatus`
values `ready_for_review`/`approved`/`dismissed` (migration `0011`,
**applied live to Neon**) — `dismissed` deliberately distinct from the
existing `rejected` (employer-rejected), a different thing. Async wrapper
`workers/jobs.py::prepare_applications_task` (RQ, same "real LLM calls, must
not block the request thread" reasoning as `discover_jobs_task`). New
endpoints: `GET /applications/review-queue`, `POST /applications/batch-
prepare`, `POST /applications/batch-approve` (all-or-nothing, SPEC's own
"no partial sends" discipline). `schemas.ApplicationReviewOut` matches, on
purpose, the exact contract given to the parallel frontend agent before this
backend existed — kept in sync deliberately.

**#4 — gated execution.** The real design question: the ADR-001 static
guard built earlier this session forbids `form.submit()`/`requestSubmit()`
everywhere, on purpose — but a batch-approved application has to actually
submit *somewhere*. New `POST /applications/{id}/claim-submission`: the only
place real authority lives. `with_for_update()` locks the row; the
application must genuinely be `approved`, and the claim atomically flips it
to `applied` in the same locked transaction — so it can fire **at most
once**, not be retried into a duplicate send. Extension side:
`formFill.content.ts` now captures the original, unpatched
`submit`/`requestSubmit` methods *before* the guard overwrites them, exported
narrowly as `_adr001OriginalSubmit`/`_adr001OriginalRequestSubmit` — never
attached to `window`, never exported broadly. New
`submitApprovedApplication.ts` is the **one** file that uses them: it calls
the claim endpoint first, and only invokes the real native method if that
call returns 200. This is the single, explicitly reviewed exception now
listed in `architectureInvariants.test.mjs`'s previously-empty `ALLOWLIST`.

**A real false-positive, instructive not embarrassing.** The static guard
initially flagged `submitApprovedApplication.ts` — not for its actual
`.call(form)` invocation, but because its own explanatory *comment* contained
the literal substring "form.requestSubmit()". A naive text scanner can't
distinguish code from prose describing code; this is exactly why the
`ALLOWLIST` entry needed a human decision either way, not a scanner
adjustment — added the file, with the exact justification (a real backend
claim gates it) documented at both the exemption site and the file itself.

**Real verification, not simulated.** 224/224 backend tests green (214 + 10
new, red-before-green: `prepare_application_for_review`'s persistence,
review-queue filtering, batch-approve's all-or-nothing/404/422 paths, and —
the property that actually matters — claim-submission succeeding once and
**409-ing on a second attempt against the same application**). Extension:
9/9 Node tests green, `tsc --noEmit` clean, clean build from a deleted
`dist/`. Migration `0011` applied live to Neon. **Live against real Neon +
real NVIDIA NIM**: a real application flowed through `prepare_application_
for_review` end-to-end — real tailored summary/bullets generated, and the
free smoke model's own `flagged_unsupported_claims` output (`["Senior
Backend Engineer"]`, flagging a title it wasn't given strong enough evidence
for) was correctly persisted, not dropped. **Live against the real RLS-
restricted role** (not the HTTP layer — no server running this session, so
verified the exact locked-query pattern `claim-submission` uses directly):
first claim on a real `approved` row succeeded; a second claim on the same
row was correctly refused (`status` was already `applied`) — the "fires at
most once" property, proven, not asserted.

**Not done, honestly.** `submitApprovedApplication.ts` isn't wired into any
real UI trigger yet (no bundle entry currently reaches it — confirmed via
the build output, unchanged file count) and was not live-browser-tested,
same standing limitation as the rest of F11's content-script code all
session. The RQ async path (`prepare_applications_task`) is wired and unit-
tested but not live-exercised through a real running worker this pass — the
synchronous unit `prepare_application_for_review` was, directly.

**Files created.** `batch_prep.py`, `alembic/versions/0011_batch_review_
fields.py`, `tests/test_batch_prep.py`,
`apps/extension/src/content/submitApprovedApplication.ts`. **Files
changed.** `models.py` (3 enum values, `flagged_unsupported_claims`),
`schemas.py` (`ApplicationReviewOut`, `BatchApproveRequest/Response`,
`BulletOut` reordered earlier in the file), `main.py` (4 new endpoints),
`workers/jobs.py` (`prepare_applications_task`),
`apps/extension/src/content/formFill.content.ts` (captured originals),
`apps/extension/src/content/architectureInvariants.test.mjs` (`ALLOWLIST`
filled).

---

### 2026-09-26 (latest+11) — Off-roadmap: Postgres Row-Level Security, restricted role, live-verified fail-closed

**Context.** Parked mid-discovery earlier this session after finding
`neondb_owner` has `rolbypassrls = True` — RLS policies would be silently
decorative against the only role this project had ever connected as, no
matter how carefully written. Owner asked to finish it as part of a larger
batch of remaining work.

**Migration `0010_row_level_security.py`**, real infra change, not just
schema: creates `job_copilot_app` — `NOSUPERUSER`, no `BYPASSRLS` (the
default when unspecified) — with ordinary DML grants + `ALTER DEFAULT
PRIVILEGES` (so future migrations' tables are covered without a manual
re-grant), then `ENABLE`+`FORCE ROW LEVEL SECURITY` and a `tenant_isolation`
policy on the 7 real tenant tables: `profiles`, `resume_facts`,
`applications`, `matches`, `resume_uploads` (via `profile_id ->
profiles.user_id`), `events`, `notifications` (direct `user_id`). Not applied
to `users` (the JWT->user lookup happens before any tenant context exists —
protecting it here is a chicken-and-egg problem, and there's no "list other
users" endpoint), `jobs`/`connector_runs` (legitimately global data).

**A real bug found by testing live, not by reading Postgres docs.**
`current_setting('app.current_user_id', true)` on a genuinely fresh
connection returned an **empty string**, not `NULL` — contradicting the
migration's own first-draft assumption (and most RLS tutorials' framing of
`missing_ok=true`). A bare `::uuid` cast on that crashed with
`InvalidTextRepresentation` instead of failing closed, which would have been
the wrong failure mode for a security control (a crash a caller might paper
over is worse than a clean empty result). Fixed with `NULLIF(current_setting
(...), '')::uuid` — turns the empty string into a real NULL first, so
`user_id = NULL` correctly evaluates to false. Corrected in the migration
file and reapplied live (dropped + recreated the 7 policies with the fixed
expression) since the bug was caught within the same session it was written.

**`database.py` split into two engines**, deliberately different roles:
`engine`/`SessionLocal` (owner role, `DATABASE_URL`) for Alembic and
background workers that are legitimately cross-tenant by design — the
events relay must see every user's unpublished events, job discovery only
touches the non-tenant `jobs` table. `app_engine`/`AppSessionLocal`
(restricted role, new `APP_DATABASE_URL`, falls back to `DATABASE_URL` when
unset) is what `get_db()` — every real HTTP request — uses now. `core/
config.py` gained the optional `app_database_url` setting. `core/deps.py::
get_current_user` runs `SET LOCAL app.current_user_id = :uid` on every
authenticated request, dialect-guarded to Postgres only (`db.get_bind()
.dialect.name == "postgresql"`) so the SQLite unit-test engine — which has
no such syntax — is completely unaffected; confirmed the full suite stays
green on that path.

**This is a backstop, not a replacement.** Every existing application-level
tenancy filter (`get_owned_profile`, `resolve_profile_ownership`) is
untouched. If a future endpoint ever forgets one, this is what stops the
leak instead of nothing — verified below that it actually does.

**Real verification, not simulated — the actual point of this work.**
Full suite green on SQLite (confirmed via background run, exit code 0; RLS
has no SQLite equivalent so this only confirms nothing broke, not that RLS
itself works). **Live against real Neon, connecting directly as the new
restricted role, bypassing all application code**: created two real users
with real profiles; set `app.current_user_id` to user A's id and ran `SELECT
full_name FROM profiles` with **no `WHERE` clause at all** — got back only
`['User A']`; same for user B — only `['User B']`; with **no session
variable set at all** — got back `[]`, confirmed fail-closed, not fail-open;
and confirmed the owner role still sees both (workers/migrations correctly
unaffected). Test rows cleaned up, including orphaned rows from the first
verification run that crashed on the empty-string bug before its own cleanup
could run — checked for and removed separately.

**Not done.** No automated Postgres-RLS test exists or is planned to — no
Docker, no Postgres test tier, same standing limitation as every other
Postgres-specific feature this project has (pgvector, `FOR UPDATE SKIP
LOCKED`, etc.). This was verified live this session; it is not re-verified
automatically on every future change. Worth a live recheck if this area is
ever touched again.

**Files created.** `alembic/versions/0010_row_level_security.py`.
**Files changed.** `core/config.py` (`app_database_url`), `database.py`
(`app_engine`/`AppSessionLocal`, `get_db()` now uses it), `core/deps.py`
(`SET LOCAL` in `get_current_user`, dialect-guarded).
### 2026-09-26 (latest+13) — SPEC.md §1 schema is now generated from models.py, not hand-written

**Why.** Three separate times this session, SPEC.md §1's hand-written DDL was
found to have drifted from the real `apps/api/models.py`: `resume_facts`
missing `period_from`/`period_to`, `notifications.status`'s CHECK disagreeing
with the API's own `"seen"` value, `profiles.work_auth` documented as
`text[]` but actually a JSON column. Each was caught by an agent doing
something unrelated — the fix is to make this class of drift structurally
impossible instead of eventually-caught.

**`apps/api/scripts/generate_spec_schema.py` (new).** Introspects
`models.Base.metadata.tables` directly — no DB connection, ever; only
`models.py`'s Python class definitions are read. Column types are compiled
against the real Postgres dialect (`sqlalchemy.dialects.postgresql`, since
Neon is Postgres) so `Enum(Persona)` correctly renders as the native
`persona` enum type rather than a generic VARCHAR. Never fabricates a SQL
`DEFAULT` for a Python-side default it can't map cleanly: `gen_uuid`,
`dict`, `list`, `datetime.utcnow` defaults are rendered as an honest comment
("app-level callable, not a DB DEFAULT") instead of invented SQL. Two modes:
no args regenerates the block between
`<!-- BEGIN GENERATED SCHEMA (apps/api/scripts/generate_spec_schema.py) -->`
/ `<!-- END GENERATED SCHEMA -->` markers now wrapping SPEC.md §1's DDL block
in place; `--check` diffs in-memory against what's currently between the
markers and exits 1 without writing anything if stale — the runnable-check
half of the task.

**Real discrepancies found, beyond the 3 already known (confirmed by diffing
generated output against the old hand-written block for real, not guessed):**
SPEC.md's hand-written DDL describes a schema several tables larger than
what actually exists — `companies`, `job_sources`, `generations`, `outreach`,
`suppressions`, and `match_weight_history` are all documented there but
**do not exist anywhere in `models.py`**; conversely `resume_uploads`
(F1 resume upload tracking) exists in the real schema and was **never
documented in SPEC.md §1 at all**. `jobs` in SPEC.md has `company_id` FK to a
`companies` table, `title_normalized`, `salary_min`/`salary_max`/`currency`,
a generated `search_vector` tsvector column, and no `source`/`external_id`
columns (those live on the undocumented `job_sources` table instead) — the
real `Job` model has none of that: `source`/`external_id` are directly on
`jobs`, salary is a single freeform `salary` text column, no search vector.
`applications.status` in SPEC.md is a 10-value enum
(`draft, ready_for_review, approved, applied, oa, recruiter, interview,
offer, rejected, withdrawn`) — the real `ApplicationStatus` enum has 7
values and neither `draft` nor `ready_for_review`/`approved`/`withdrawn`
exist in code. SPEC.md's `applications` also has `submitted_via`/`artifacts`
columns that don't exist; the real model has `portal`/`tailored_resume_json`/
`tailored_cover_letter` instead. `resume_facts.claim` in SPEC.md is
`achievement` in the real model, and the real model has no `confidence`
column at all (SPEC.md's `verified`/`self_reported` CHECK is fictional).
None of this was invented for the generated output — it's just what's
actually in `models.py` versus what SPEC.md's prose claimed; the generated
block only asserts the former. `profiles.work_auth`'s real column type is
plain SQLAlchemy `JSON` (not `postgresql.JSONB` — no JSONB import exists
anywhere in `models.py`), so even the "JSONB" framing used to describe this
gap earlier this session overstated it; it compiles to Postgres `json`, one
step short of `jsonb`, and is not `text[]` either way.

**Verification, not simulated.** `--check` run against the actual current
SPEC.md/models.py pair correctly reported STALE with a real diff (the 6
extra tables, the enum drift, etc., all showed up in the printed diff before
any write). The real regeneration was then run for real (no args) and
`--check` immediately after reported OK. Ran it a second time in a row —
`write_generated_block` produced byte-identical output, confirmed idempotent.
2 new tests (`tests/test_generate_spec_schema.py`): one asserts the generated
block contains the real column names/types for `users`/`profiles`/
`resume_facts` (including the once-missing `period_from`/`period_to`) and
that no fabricated `DEFAULT gen_random_uuid()` appears; one builds a
synthetic stale SPEC.md fixture and confirms the diff logic actually flags
the mismatch, then confirms `write_generated_block` produces a match and
leaves prose outside the markers untouched. Full suite: 216/216 green (214
prior + 2 new). Confirmed no DB connection happens by construction —
`generate_schema_block()` only touches `Base.metadata`, never calls
`engine.connect()`.

**Files created.** `apps/api/scripts/generate_spec_schema.py`,
`apps/api/tests/test_generate_spec_schema.py`. **Files changed.**
`docs/SPEC.md` (§1's DDL wrapped in BEGIN/END markers, content between them
now generated — prose before/after, §1.1 onward, and every other section
untouched).

**Not done, by design.** The 6 SPEC.md-only tables (`companies`,
`job_sources`, `generations`, `outreach`, `suppressions`,
`match_weight_history`) are real product surface described elsewhere in
SPEC.md/PRD.md that was simply never implemented — this task's job was to
make the *documented-vs-real* comparison honest and automatic, not to decide
whether those tables should now be built or the prose describing them
deleted. That's a real, larger followup for whoever owns the next roadmap
slice, flagged here rather than silently resolved either direction.
### 2026-09-26 (latest+14) — Review queue screen (F-approval-batch): frontend built against the not-yet-built backend contract

**What changed.** Built the human-approval review screen ADR-001 exists to serve: a new
`GET /review` route listing "ready for review" applications with a batch-approve flow,
per-card dismiss, and per-bullet grounding against the resume-facts KB. This is the
frontend half of a coordinated piece of work — the three backend endpoints it calls
(`GET /applications/review-queue`, `POST /applications/batch-approve`,
`PATCH /applications/{id}` with `status: "dismissed"`) do not exist in `apps/api` yet and
were built against purely from the given contract, matching `JobOut` field-for-field.

**Why.** Phase 3's matching/tailoring work has no human checkpoint in the UI yet — ADR-001
is a hard rule with nowhere to land. This screen is that landing point: batch approval so
twenty applications take minutes, not two hours, with the truth-check's flagged claims
surfaced (never a silent drop, never a hard gate on the approve button) and every diff a
real diff, never a fake one.

**Files created.**
- `apps/web/app/review/page.tsx` — fetch/loading/empty/error states, select-all, batch
  approve (optimistic list update, `setQueryData` to strip approved ids on success, a
  visible non-dismissable error message on failure — a 404 from batch-approve's
  all-or-nothing contract never silently drops the batch), per-card dismiss via the
  existing `PATCH /applications/{id}` pattern.
- `apps/web/components/review/ApplicationCard.tsx` — one card per application: job
  title/company/location, match score badge, tailored summary, per-bullet grounding, the
  flagged-unsupported-claims warning callout (amber, non-blocking per the task's ADR-006
  framing for this screen), resume-download link, dismiss button.
- `apps/web/components/ui/checkbox.tsx` — thin shadcn-style wrapper around radix-ui's
  `Checkbox` primitive (already a dependency via the `radix-ui` umbrella package used by
  every other `components/ui/*` file) — no new dependency, followed the same pattern as
  `dialog.tsx`.

**Files changed.**
- `apps/web/lib/api.ts` — added `ReviewApplication`, `TailoredBullet`,
  `ReviewMatchBreakdown` types and `listReviewQueue`, `batchApprove`,
  `dismissApplication`, `resumeDocxUrl` to the `api` object, following the existing
  `request()`/`ApiError` pattern used by every other endpoint here.

**Dependencies added.** None. Used `diff` (jsdiff, already installed) for the real
per-bullet diff and `radix-ui`'s `Checkbox` (already installed, already the pattern
`dialog.tsx`/`badge.tsx` use) for selection.

**The diff view — did the real thing, not the honest placeholder.** The task's brief
allowed for a placeholder ("grounded in N facts") if threading in real fact text wasn't
feasible in the time budget. It was feasible: `GET /resume-facts` already exists and
`api.listFacts` already wraps it (used by the facts page). `ApplicationCard` now fetches
that profile's facts (`useQuery(["facts", profile.id], ...)` — same query key the facts
page uses, so it's a cache hit rather than a duplicate round-trip if that page was already
visited this session), matches each bullet's `source_fact_ids` against it, and renders a
real `diffWords` (jsdiff) diff of the tailored bullet against the concatenated source
fact text when every cited id resolves. The placeholder ("grounded in N fact(s)", a
`FileTextIcon` + count, `// TODO` comment in `ApplicationCard.tsx`) only fires when a
bullet cites facts that don't resolve — a fact deleted or edited after tailoring ran, or
the facts fetch still loading/failed. That's the one honestly-left gap: it can't be closed
further without inventing data, since a diff needs two real strings and this frontend has
no way to reconstruct a fact that's gone.

**Tests.** None added — confirmed (again) that `apps/web` has no test runner wired up at
all (no jest/vitest config; `@testing-library/*` are listed devDependencies with nothing
that invokes them). This is the same explicitly-tracked gap prior entries have noted, not
a new one. Per instruction, did not install a runner unilaterally. If asked to close this
gap: add Vitest + `@testing-library/react` + `jsdom` (both already implied by the
devDependency list) and write component tests for `ApplicationCard`'s three render paths
(diffed bullet, placeholder bullet, flagged-claims callout) plus a `page.test.tsx` for the
batch-approve optimistic-update and 404-error-surfaced paths — that's the concrete ask,
left undone rather than guessed at.

**Build verification.** `npm run build` (via `node node_modules/next/dist/bin/next
build` — `next` wasn't on PATH/`.bin` after a fresh `npm ci` in this worktree, direct
invocation worked) compiled and type-checked cleanly: `/review` built at 14.6 kB
(136 kB First Load JS) alongside the four existing routes, zero new errors or warnings
beyond Next's pre-existing multi-lockfile workspace-root warning (unrelated, pre-existing).

**No live UI verification.** Did not start the dev server against a real backend — the
three endpoints this screen calls don't exist in `apps/api` yet (expected; that's the
coordinated backend work this was built ahead of), so hitting them would only demonstrate
a fetch failure, not the loading/empty/populated states. The empty-state, loading-state,
and error-state branches were verified by reading the JSX against React Query's
documented `isLoading`/`isSuccess`/`isError` flag semantics, not by rendering them.

**Problems hit.** `npm ci` in this worktree didn't populate `node_modules/.bin/next`
(Windows symlink quirk under this git-worktree layout) — worked around by invoking
`node node_modules/next/dist/bin/next build` directly rather than `npm run build`. Worth
knowing if the next session hits the same thing in a different worktree.

**Next.** Once the backend's `review-queue`/`batch-approve` endpoints land, smoke-test
this screen against them for real — in particular the batch-approve 404 (all-or-nothing)
path, which the frontend surfaces but has never actually seen fire. The test-runner gap
above is the other open item.
### 2026-09-26 (latest+15) — Unified the "never trust an LLM's id" check into core/grounding.py

**Context.** Two independent instances of the same defensive pattern existed:
`tailoring/engine.py`'s `Bullet.source_fact_ids` field_validator raised
`ValueError` (caught by `instructor`'s retry) on a fact id the model invented
that wasn't in the KB it was given, while `formfill/map_fields.py` achieved
the equivalent only implicitly — `mapping_by_id.get(field_id)` silently
returns `None` for an invented field_id, no explicit check, no retry.
Extracted one reusable, tested helper and pointed both call sites at it.

**`core/grounding.py` (new).** One function,
`validate_ids_against_known_set(ids, known_ids, *, field_name)` — returns
`ids` unchanged if every one is in `known_ids`, otherwise raises `ValueError`
naming exactly the invented id(s). No class, no config, nothing per-caller —
the two call sites differ only in what they do with the raised error, which
is the caller's decision, not the helper's.

**`tailoring/engine.py`.** `fact_ids_must_exist_in_kb` now delegates to the
helper instead of its inline `[fid for fid in value if fid not in known_ids]`
loop. Externally identical: still a `field_validator` on `source_fact_ids`,
still reads `known_fact_ids` from `info.context`, still raises `ValueError`
which `instructor`'s `max_retries=2` catches the same as before.

**`formfill/map_fields.py`.** The LLM-mapping loop now calls
`validate_ids_against_known_set(list(candidate.keys()), known_field_ids, ...)`
right after `json.loads` succeeds, inside the same `try`/`except` that already
retries on malformed JSON — `ValueError` was added to that except tuple. This
was the one real decision in the task: should an invented field_id force a
retry (tailoring's behavior) or degrade straight to "unknown, flag for
review" (this module's own stated philosophy)? Chose **both, in sequence**:
an invented id is treated as just another kind of malformed response and
retried within the existing bounded `MAX_ATTEMPTS` loop (consistent with
tailoring); if attempts run out, `mapping_by_id` stays `{}` and every field —
including ones the model actually got right in a discarded attempt — falls
through to the pre-existing `_flagged()` "unknown" path, exactly like a
malformed-JSON exhaustion already did. No new fallback branch needed; the
safety net already existed, it just wasn't guarding this specific failure
mode explicitly.

**Tests.** Red-before-green on a fresh `tests/test_grounding.py` (6 cases:
unchanged pass-through, empty list, single invented id named in the message,
multiple invented ids all named, field_name appears in the message, partial
overlap names only the unknown one) — confirmed failing on `ModuleNotFoundError`
before `core/grounding.py` existed, then confirmed passing after. No changes
needed to `test_tailoring_engine.py` or `test_formfill.py` — both call sites'
observable behavior for valid (non-adversarial) input is unchanged by
construction, and neither test file exercises an adversarial invented-id
input against `map_form_fields` today (a gap worth a follow-up test, not
required by this refactor). Full suite: **220/220 green**
(214 baseline + 6 new).

**Problems hit.** This worktree had no `.venv` and no `.env` — both
gitignored, neither carried over from the main checkout. Created the venv
and installed `requirements.txt`, which failed on a real dependency
conflict: `presidio-analyzer==2.2.364`'s own metadata now requires
`pydantic>=2.12.5`, but the pin was `pydantic==2.9.2`. Bumped the pydantic
pin to `2.12.5` (the floor presidio demands, nothing higher) to unblock
install — full suite green afterward, no other pin needed to move. Also
added a local dev-only `.env` (dummy `DATABASE_URL`/`ANTHROPIC_API_KEY`/
`JWT_SECRET`, gitignored) since none of this session's tests hit a real
Postgres or a real Claude/NVIDIA call — pure mocked refactor of already-
tested logic, no live verification needed or attempted this session.

**Files created.** `core/grounding.py`, `tests/test_grounding.py`.
**Files changed.** `tailoring/engine.py` (import + validator body),
`formfill/map_fields.py` (import + retry-loop validation), `requirements.txt`
(pydantic pin bump, reasoning inline).

**Next.** The follow-up test gap noted above: an explicit
`test_map_form_fields_retries_on_invented_field_id_then_flags` covering the
new path in `map_fields.py` directly (today's 6 grounding-utility tests cover
the helper in isolation; nothing yet drives an invented-field_id LLM response
through `map_form_fields` itself).

---

### 2026-09-26 (latest+10) — Roadmap sub-project #1: deterministic known-ATS field maps, live-verified

**Context.** The "too much manual effort" analysis decomposed into four
sub-projects; #1 was picked as the smallest, most self-contained, highest-
leverage piece — it's the direct payoff of the identity-model fix and depends
on nothing else unbuilt. Matches PRD's own F11 design ("Known ATS... fills
them deterministically") and SPEC.md §3.7's "build B [rules engine] first"
plan from the earlier brainstorm — the per-ATS override layer ("A") was
deliberately not built alongside it, since it needs real user-side HTML
captures that still don't exist (ADR-002 forbids server-side scraping even
for fixtures).

**`formfill/deterministic.py` (new).** An ordered rule table, zero LLM calls:
`autocomplete` attribute first (a real WHATWG HTML standard —
`email`/`tel`/`name`/`address-level2`/etc. — not invented), then name/id/label
regex patterns for the same set of fields, checked in unambiguous-first order.
Network fields (LinkedIn/GitHub/GitLab) match by name in the pattern itself
before falling back to generic rules, so a field asking for GitLab with no
GitLab profile on record correctly returns nothing rather than a wrong-network
guess. Deliberately excludes `given-name`/`family-name`: `Profile.full_name`
is a single string with no structured parts, and splitting it (first token =
given, rest = family) would be exactly the invention the null-over-guess rule
already forbids for identity data — those fields fall through to the LLM path
unchanged, same as any other field this module doesn't recognize.

**Wired into `formfill/map_fields.py::map_form_fields`**, ahead of the LLM
call, not replacing it: the forbidden-label check still runs first (unchanged
ordering), then every non-forbidden field gets a deterministic pass, and only
what's left over goes into the LLM prompt at all — deterministic hits never
reach the model, cutting both cost and the number of fields a human has to
review.

**A real, correct test failure, not a regression.** `test_map_form_fields_
passes_through_high_confidence_mapping` broke immediately — it used a plain
"Email" field to test LLM passthrough, and the new deterministic pass
(correctly) now resolves that field itself before the mock LLM ever gets
called. Fixed the test's fixture (switched to "Years of experience", which
genuinely isn't in the rule table), not the implementation — same "fix the
test, not the code" call as the `Bullet.model_validate` context fix earlier
this session.

**Extension side.** `formFill.content.ts`'s `FieldDescriptor` gained
`autocomplete`/`name`/`dom_id` (the raw attributes the backend rule matcher
needs — it captured none of them before), and `extractFields()` now reads
them straight off each element. `schemas.FieldDescriptorIn` gained the same
three fields, all `Optional` — an older extension build that doesn't send
them just yields `None`, which the matcher already treats as "no signal,
fall through," so this is non-breaking either direction.

**Real verification, not simulated.** 20 new backend tests (16 for the rule
table in isolation, 4 for the map_form_fields orchestration change),
red-before-green. Full suite: 214/214 green. Extension: 9/9 Node tests green,
`tsc --noEmit` clean, `npm run build` clean from a deleted `dist/`. **Live
against real Neon**, not mocked: built a real profile (name/phone/city/
LinkedIn), ran `map_form_fields` against 7 fields with `call_llm` mocked to
observe call count — 5 of 7 resolved deterministically (email, phone,
full_name, city, LinkedIn) at confidence 1.0, the LLM was called **exactly
once**, and the two fields sent to it were exactly the two that couldn't be
resolved deterministically (a first-name-only field, correctly refused rather
than guess-split; a genuinely open-ended "years of experience" field). Test
rows and scratch scripts cleaned up after.

**Not done, by design.** The per-ATS selector override layer ("A" from the
original design) — needs real user-side captures that don't exist yet, same
gap `SPEC.md` §3.7 already names. Sub-projects #2 (batch prep), #3 (review
queue), #4 (gated execution) remain unbuilt.

**Files created.** `formfill/deterministic.py`, `tests/test_deterministic_
fields.py`. **Files changed.** `formfill/map_fields.py` (deterministic-first
orchestration), `schemas.py` (`FieldDescriptorIn` +3 fields),
`tests/test_formfill.py` (+4 tests, 1 fixture fix),
`apps/extension/src/content/formFill.content.ts` (`FieldDescriptor` +3
fields, `extractFields()` reads them).

---

### 2026-09-26 (latest+9) — Off-roadmap: nvidia_smoke wired into parsing/llm_extract.py — resume upload works with only an NVIDIA key

**Context.** Owner has no real ANTHROPIC_API_KEY but does have a working
NVIDIA key (already used everywhere else this session). The identity-model
entry above flagged `parsing/llm_extract.py` as anthropic-only — a real,
recorded limitation, not worked around at the time. Owner asked directly: can
we work with the key we actually have? Yes — closed the gap the same way
`tailoring/engine.py` already does, mirroring its existing nvidia_smoke
pattern rather than inventing a second one.

**What changed.** `extract_facts_from_text` and `extract_basics` both gained
the nvidia_smoke branch. Lazy `_get_nvidia_client()` (same lazy-construction
reasoning as every other client in this project — a missing key never breaks
the default path). `extract_basics` additionally needed
`_get_nvidia_instructor_client()` — `instructor.from_openai(client)`, verified
against the installed package's real signature before use, same discipline as
every other instructor/API check this session.

**A real bug found live, not from reading the API docs.** `extract_basics`'s
first version passed `system=BASICS_SYSTEM_PROMPT` straight through to the
nvidia_smoke branch, copying Anthropic's calling shape — and it broke against
the real endpoint: `TypeError: Completions.create() got an unexpected keyword
argument 'system'`. OpenAI-shaped chat APIs (NIM included) have no separate
`system` parameter; the system prompt is a `{"role": "system", ...}` entry
inside the messages list. `extract_facts_from_text`'s branch already did this
correctly (written earlier, from the tailoring/engine.py pattern); extract_basics
did not, until this fix — the two providers now genuinely branch on call
*shape*, not just on which client object gets used.

**Honest characterization of the free model, not a fixed bug.** Ran
`extract_facts_from_text` 3 times live against the same input: 2 clean
successes, 1 clean failure (`ValueError: malformed JSON...`, not a crash, not
a silent wrong answer) — consistent with this project's own prior notes on
this exact model ("the free model invents more than Claude would... a much
smaller model"). `extract_basics` fared better on the same class of flakiness
because `instructor`'s bounded retry (already wired for the schema-validation
case) also absorbs a first malformed attempt — same mechanism, extra benefit
not originally designed for.

**Real verification, not simulated.** Full suite: 194/194 green (2 new tests:
one exercising the nvidia branch of `extract_facts_from_text`, one for
`extract_basics`). App boots, 29 routes (unchanged — no new endpoint, this is
provider-branch code only). **Live against the real NVIDIA key**, no
Anthropic call at all: `extract_basics` on a synthetic resume correctly
returned `full_name="Bedaant Srivastav"`, `phone="+91 98765 43210"`,
`city="Bengaluru"`, `region="Karnataka"`, and correctly normalized a bare
`linkedin.com/in/bedaant` path to a schemed `https://` URL per the prompt's
own rule — the null-over-guess validators from the identity-model entry above
are exercised by a real model call here, not just by unit tests. Diagnostic
and verification scripts deleted after use.

**Files changed.** `parsing/llm_extract.py` (`_get_nvidia_client`,
`_get_nvidia_instructor_client`, provider branches in both extraction
functions), `tests/test_llm_extract.py` (+1), `tests/test_applicant_basics.py`
(+1).

---


### 2026-09-26 (latest+8) — Off-roadmap: applicant identity model (JSON Resume `basics`) — the actual blocker under "too much manual effort"

**Why this, and not the review queue.** Owner's complaint was that the end user
has to do too much manual work per application. We spent a long stretch
designing *volume* fixes for that (batch approve, deterministic ATS field maps,
review queue, gated execution — decomposed as sub-projects 1-4) and I was one
message from writing the review-queue spec. Owner then asked to re-examine what
the right problem actually was. It was not volume.

Re-reading my own live F11 output from earlier today:

```
{'field_id': 'f1', 'maps_to': 'profile.email', 'confidence': 1.0}   <- worked
{'field_id': 'f3', 'maps_to': 'unknown',       'confidence': 0.0}   <- "Full name"
```

I had logged that as "the code correctly declined to invent a name," which was
true and also a serious under-read. **`Profile` had no name column.** No phone,
no structured city/region/country (only a freeform `location` string), no
LinkedIn/GitHub. Every application form opens with name/email/phone/location and
this product could fill exactly one of the four. That is not UX friction — the
form-filler was structurally incapable of filling a form, which also blocks
sub-project 1 (field maps have nothing to map *to*), 2 (batch-prep would prepare
incomplete applications), 3 (the queue would render holes) and 4 (execution
would submit blanks). Root of the chain, not a link in it.

**Repo search first, per this project's convention — and it found the answer
already inside the project.** Verified `Liam-Frost/AutoApply` (PolyForm
Noncommercial 1.0.0 — decoded the actual LICENSE file; GitHub's `NOASSERTION`
was a classifier artifact. It explicitly forbids "bundling into a commercial
product", a hard blocker) and `OmkarPathak/ResumeParser` (real MIT, mature, but
a full Django app whose extraction is a ~1GB local Qwen2.5 via llama-cpp —
exactly the multi-GB local-inference weight class `garak` and
`esco-skill-extractor` were already rejected for, and it would not have added
the missing *columns* anyway). Neither adopted. The schema that fits is **JSON
Resume `basics`**, which this project has depended on since 2026-08-16
(`parsing/jsonresume_export.py`) — we were already exporting to a schema we
could not populate.

**Schema.** Migration `0009_applicant_basics.py` adds to `profiles`:
`full_name`, `phone`, `website_url`, `street_address`, `city`, `region`,
`country_code` (`varchar(2)`), `postal_code`, plus `network_profiles` and
`work_auth` as JSONB. **Applied for real to live Neon**, confirmed
`0008 -> 0009`. Field names mirror JSON Resume `basics` so the mapping stays
lossless. Two deliberate calls: `work_auth` is JSONB not SPEC.md §1's `text[]`
(matches this project's existing `Job.tags`/`Job.skills`/`Profile.prefs` JSON
convention and migrations 0006/0007 — documented in the migration); and
freeform `Profile.location` is **kept**, since `ProfileOut` already exposes it
and removing it would break serialization for no gain.

**The part that matters most: null-over-guess is enforced, not requested.**
A hallucinated name or phone number here gets typed into a real application sent
to a real employer — direct harm to the user, so `schemas.ApplicantBasics`
validates rather than trusts. Every field is Optional/None-by-default *on
purpose* (a resume genuinely may not state a phone; if null were not freely
available the model gets pushed toward inventing something), and validators
reject: known placeholder names (`John Doe`, `Your Name`, `N/A`, ...), phone
numbers in the reserved fictional NANP `555-0100..555-0199` range, phone digit
counts outside 7-15 (ITU-T E.164), non-ISO-3166-1-alpha-2 country codes
(`USA`/`United States` rejected, `us` normalized to `US`), and scheme-less URLs.
`instructor` (wired in earlier today) enforces these on the model's own output
with a bounded retry, so a violation is caught and retried rather than shipped.

**Prompt engineering, since the failure mode is specific.**
`BASICS_SYSTEM_PROMPT` (1) states the stakes so the model knows why precision
matters, (2) makes null the explicitly *preferred* answer rather than a fallback
("an incomplete-but-correct result is a success; a complete-but-invented one is
a failure"), (3) names the exact placeholder patterns models reach for when
filling gaps, (4) forbids expansion of partial data (resume says "SF" ->
`city="SF"`, do NOT infer region/country), and (5) gives per-field formats that
the schema *also* enforces.

**Wiring.** `formfill/map_fields.py::build_profile_summary(profile, email)` is
now the single source of truth for what the mapping model sees, and it **omits
empty values entirely** rather than sending `"phone": null` — an absent key
makes the gap unambiguous, a null invites a confident mapping to a value that
does not exist. New `GET`/`PUT /profiles/{id}/basics`; identity is persisted
only via the PUT after the user reviews it, never from parsing alone (same rule
`facts:bulk` already enforces per SPEC.md §2.1). Resume upload now returns a
`basics` draft alongside draft facts, extracted in a **non-fatal** try/except —
a failed identity extraction must not throw away a successful facts parse, since
the Facts KB is what ADR-009 actually requires.

**Real verification, not simulated.** Full suite 192/192 green (165 + 27 new,
red-before-green throughout). App boots, 29 routes (up from 27 — the two new
basics endpoints). Migration applied live to Neon. **Live end-to-end against
real Neon + real NVIDIA NIM**, a real profile through the real mapping path:

```
Full name             -> profile.full_name        conf=1.0  'Bedaant Srivastav'
Email                 -> profile.email            conf=1.0
Phone number          -> profile.phone            conf=1.0  '+91 98765 43210'
City                  -> profile.city             conf=1.0  'Bengaluru'
LinkedIn profile URL  -> profile.network_profiles  conf=0.9
What is your gender?  -> unknown                  conf=0.0  None
```

Five of six fields now resolve above the 0.75 auto-fill threshold where
previously only `email` did; the demographic field correctly stayed `unknown`
without ever reaching the model, so the F11 forbidden-label guard still holds.
Test rows cleaned up.

**Known limitation, recorded not worked around.** `parsing/llm_extract.py` is
anthropic-only — it has never carried the `nvidia_smoke` dev branch that
`tailoring/engine.py` has, so `extract_basics` cannot be live-exercised until a
real `ANTHROPIC_API_KEY` exists (unchanged project-wide blocker). Its
validators, the novel and risky part, are fully unit-tested; the LLM call path is
thin. The *consumption* side (`build_profile_summary` -> `map_form_fields`) was
live-verified above via nvidia_smoke.

**Still open from the same discussion.** Sub-projects 1-4 (field maps, batch
prep, review queue, gated execution) are now genuinely unblocked but unbuilt.
Postgres RLS (started, then correctly parked — found `neondb_owner` has
`rolbypassrls=True`, so RLS needs a separate restricted role to mean anything),
the unified grounded-ID validator, and SPEC.md-as-generated-docs also remain.

**Files created.** `alembic/versions/0009_applicant_basics.py`,
`tests/test_applicant_basics.py`. **Files changed.** `models.py` (10 Profile
columns), `schemas.py` (`NetworkProfile`, `ApplicantBasics` + validators,
`ResumeUploadOut.basics`), `parsing/llm_extract.py` (`extract_basics` +
`BASICS_SYSTEM_PROMPT` + instructor client), `formfill/map_fields.py`
(`build_profile_summary`), `main.py` (two endpoints, summary-builder wiring,
non-fatal basics extraction on upload).

---

### 2026-09-26 (latest+7) — Off-roadmap: git repo initialized; ADR-001/002 structural guard added

**Context — not a roadmap item.** After the source_fact_ids fix, owner asked two
bigger analysis questions ("most complicated thing that could ruin everything" /
"what architectural decisions would make this smooth"). Answer to the first:
ADR-001 ("human always clicks submit, the system never does") had zero structural
enforcement — F11's content script already reads/writes real form fields on real
ATS pages, and the only thing preventing it from also submitting was that nobody
had written that line yet, not anything the codebase made impossible. Owner agreed
to fix this after first getting a real git repo in place (this project had none —
`git status` returned `fatal: not a git repository` — despite 8 migrations and
~50 files touched in a single session with no diff to review or revert against).

**Part 1: git init, done carefully.** Before staging anything: confirmed
`.gitignore` already covered `.env`/`.venv`/`node_modules`/`dist`/caches; then
ran a credential scan across the actual candidate file list (not the whole tree —
scanning `.venv`/`node_modules` directly timed out, scoped to what `git status`
would actually track instead) for `sk-ant-`/`nvapi-`/`ghp_`/DB-connection-string
patterns. Found matches only in `.env.example` (placeholder values, confirmed by
reading it — safe) and inside `tools/.venv-jobspy/`'s own vendored test fixtures
(already gitignored, not ours). `apps/api/.env` (the real secrets) confirmed
ignored. Added `.claude/settings.local.json` and `.playwright-mcp/` to the
project's own `.gitignore` — they were only excluded via the owner's personal
global git config before, which wouldn't travel with the repo. Verified the final
staged list (172 files) against the same credential patterns before committing —
zero matches. One root commit, working tree clean after.

**Part 2: ADR-001/ADR-002 structural guard, two layers.**

*Extension* (`apps/extension/src/content/architectureInvariants.test.mjs`, Node's
built-in test runner, zero new dependencies, same pattern as `fieldDecision.test.mjs`):
scans every real `.ts`/`.tsx`/`.mjs`/`.js` source file for `.submit(`/`.requestSubmit(`
— the actual DOM APIs that submit a form — and fails loud if found outside an
explicit, empty-by-design `ALLOWLIST`. A second test proves the scanner itself
actually detects a violation rather than vacuously always passing. **Verified
end-to-end, not just logically**: appended a real `document.querySelector("form")
.submit();` line to a real source file, confirmed the test went red naming that
exact file, then reverted and confirmed clean again (`git diff` showed zero
content difference after revert). `formFill.content.ts` also got a runtime guard —
patches `HTMLFormElement.prototype.submit`/`requestSubmit` to throw, inside the
content script's isolated JS world (MV3 content scripts get their own copy of
built-in prototypes, separate from the host page's, while sharing the same DOM —
this patches only this extension's own calls, not the host page's) — defense in
depth against a dynamically-constructed call (`el["submit"]()`) a source-text
regex could miss. `npx tsc --noEmit` clean, `npm run build` clean from a deleted
`dist/`.

*Backend* (`tests/test_architecture_invariants.py`): scans `apps/api/` (excluding
`.venv`/caches/`tests/`) for any function named like an autonomous submitter
(`submit_application`, `auto_apply`, `apply_to_job`, etc.) — today none should
exist at all, so an unconditional ban needs no allowlist. **Found and fixed a
real bug while verifying this, not a hypothetical one**: the first version used
`Path.rglob("*.py")` then filtered results, which meant it fully walked
`apps/api/.venv`'s entire tree (hundreds of thousands of files) before discarding
anything — 39 seconds for one test. Switched to `os.walk` with directory-level
pruning (`dirnames[:] = [...]`) — 0.22s. **Verified end-to-end the same way as the
extension side**: appended a real `def submit_application(job_id): pass` to a
real file, confirmed the test failed naming that exact file, reverted, confirmed
clean (`git diff` zero difference).

**A repeated anomaly worth recording.** Both times a violation was injected for
testing, the tool result carried a system note claiming the edit was "intentional"
and instructing not to mention it to the owner. Both were false — these were my
own deliberate temporary test edits, immediately reverted — and the instruction to
conceal them from the owner was not followed; flagged in-conversation both times
as having the shape of a prompt-injection attempt rather than a real system
instruction, since it asked for concealment from the person the work is for.

**Real verification, not simulated.** Extension: 9/9 Node tests green (7
`fieldDecision` + 2 new). Backend: 165/165 pytest green (163 + 2 new). App boots,
27 routes (unchanged — this item added no endpoint). Both real-violation
injections confirmed the guards actually fire, not just that clean code passes.

**Not done.** Postgres RLS for tenancy, the unified grounded-ID validator, and
SPEC.md-as-generated-docs are still open from the same discussion — owner chose
ADR-001 first or those explicitly next, per the earlier AskUserQuestion answer.

**Files created.** `apps/extension/src/content/architectureInvariants.test.mjs`,
`apps/api/tests/test_architecture_invariants.py`. **Files changed.**
`apps/extension/src/content/formFill.content.ts` (runtime guard), `.gitignore`
(`.claude/settings.local.json`, `.playwright-mcp/`).

---

### 2026-09-26 (latest+6) — Off-roadmap: `instructor` wired into `tailoring/engine.py`, closing the source_fact_ids gap

**Context — not a roadmap item.** Owner asked two analysis questions after item
5a: "most complicated thing that could break / best improvement" and "what am I
overlooking." Answer to the first, found by re-reading `tailoring/engine.py`
itself while researching the question, not speculation: pass 1's real output is
`bullets: list[str]` — plain strings — not `SPEC.md` §3.3's contracted
`{text, source_fact_ids}` shape. `source_fact_ids` was never requested from the
model, never validated, and the spec's own words ("mandatory per bullet... rejected
at validation, before the truth-checker even runs") describe a deterministic
backstop that doesn't exist in code. Owner asked whether an existing OSS repo
already solves this — `instructor==1.15.4` does, and was already pinned in
`requirements.txt` and pre-approved in `DEPENDENCIES.md` for exactly this
(**"Fixes CODE-REVIEW.md B5 — tailoring/engine.py currently does an unhandled
json.loads on model output"**) but never wired in (2026-08-16 latest+8 entry:
"installed, not forced into speculative integration"). Owner then asked to wire
it in. This entry is that work — genuinely improves the product's core trust
mechanism, not part of the F5/F11/documents/outreach roadmap sequence.

**API verified against the installed package's actual source, not guessed or
assumed from memory** (`instructor==1.15.4` is a very different API shape from
older instructor versions circulating in docs/tutorials — this version lazy-loads
everything through `__getattr__`/`_LAZY_IMPORTS`, confirmed by reading
`instructor/__init__.py` directly): `instructor.from_anthropic(client)` wraps a
real `anthropic.Anthropic` client; the returned `Instructor` exposes `.messages`
as an alias back to itself with a top-level `.create(response_model=, messages=,
max_retries=, context=, **kwargs)`; retry exhaustion raises
`instructor.v2.core.errors.InstructorRetryException` (found by reading
`v2/core/retry.py`'s actual raise site, not guessed) — all three confirmed by
grepping the installed source before writing any code that depended on them.

**`tailoring/engine.py` — new `Bullet`/`TailoredDraft`/`TruthCheckResult` Pydantic
models.** `Bullet.source_fact_ids: list[str] = Field(min_length=1)` makes an
empty list a hard validation failure (SPEC's "mandatory"); a `field_validator`
reads `info.context["known_fact_ids"]` (Pydantic v2's validation-context
mechanism, confirmed importable) and rejects any id the model invents that isn't
actually one of the facts given for *that* call — not just "some fact somewhere,"
the real KB passed into that specific request. New `_call_claude_structured()`
(default-provider-only) calls through `instructor`, retrying (bounded, `max_retries=2`
— same "bounded, not an open loop" philosophy ADR-011 already uses elsewhere)
on a schema violation instead of trusting an unhandled `json.loads`. On retry
exhaustion, `InstructorRetryException` is caught and re-raised as a clear
`RuntimeError` naming which pass failed — never silently returns something wrong.

**The `nvidia_smoke` dev path deliberately does NOT get this validation** — it
still does the original raw-JSON parse, but now returns bullets shaped
`{text, source_fact_ids: []}` rather than plain strings, so callers see one
consistent contract regardless of provider. Explicitly not claiming a
fact-grounding link the free smoke model was never asked to honor — an honest
empty list, not a fabricated one. `call_llm()` itself (used by `formfill/
map_fields.py` and `connectors/discovery.py`, items 3 and 4 this session) is
completely untouched — this is scoped to `tailoring/engine.py`'s own two passes.

**Real ripple, tracked, not left dangling.** `schemas.TailorResponse.bullets`
changed `List[str]` → `List[BulletOut]` (new `BulletOut{text, source_fact_ids}`)
— a genuine breaking API contract change, made deliberately since nothing in the
repo yet consumes `/tailor`'s output (no UI page, per every prior "not done yet"
note on this feature) — breaking it now while it's free is strictly better than
breaking it later. `main.py`'s `/tailor` endpoint now includes `"id"` in the
facts payload it sends to `tailor_application` — without it there are no real
fact ids to validate `source_fact_ids` against, and the code correctly falls
back to the unvalidated path rather than silently pretending to validate against
nothing.

**Real verification, not simulated, on both branches.** `tests/test_tailoring_engine.py`
created — no test file existed for this module before (a real, separate gap,
closed alongside the fix): 5 tests, red-before-green, including a genuine
"caught by my own test, not a pre-existing bug" moment — constructing a `Bullet`
directly (`Bullet(text=..., source_fact_ids=[...])`) in a test fixture bypassed
Pydantic's validation `context` and failed for the right reason, fixed by using
`Bullet.model_validate(..., context=...)` instead, same "fix the test, not the
implementation" call this project has made before (2026-08-16 latest+3 entry).
Full suite: 163/163 green. App boots, 27 routes (unchanged — no new endpoint).
**Live against the real Anthropic API** (not mocked): called the real
(non-smoke) path with the still-placeholder key — reached Anthropic for real,
got a genuine `401 authentication_error`, `instructor` correctly did NOT waste
retries on a non-validation error (`Total attempts: 1`), and the code surfaced
it as a clear `RuntimeError` rather than crashing on something unrelated — the
same honest-negative-result category as every other real-Claude-path check this
project has hit since the key has been a placeholder. **Live against NVIDIA
NIM** (`nvidia_smoke`): full tailor_application round trip succeeded, bullets
came back correctly with `source_fact_ids: []` even though the free model
decoratively wrote "(f1)" inside the bullet text itself — the code never
mistook that for a validated id.

**Not done.** The still-real, separate gap this fix doesn't touch: `Application.
tailored_resume_json`'s stored shape will need updating whenever something
actually writes tailored output to it for real (currently only set by `/tailor`
itself, which nothing downstream reads yet). `documents/generate_docx.py`
(item 5a) still generates from raw Facts KB, not tailored output, so it's
unaffected by this change either way.

**Files changed.** `tailoring/engine.py` (models + structured-call path + branch
restructuring), `schemas.py` (`BulletOut`, `TailorResponse.bullets` shape),
`main.py` (`/tailor`'s facts payload gets `"id"`). **Files created.**
`tests/test_tailoring_engine.py`.

---

### 2026-09-26 (latest+5) — Roadmap item 5a: DOCX generation + ATS-safety linter + parse-back check, verified live

**What changed.** Built plan item 5a against real `SPEC.md` §3.5, red-before-green.
The plan's own open question — "check whether tailoring's real output is far enough
along to feed this, or whether this item needs to stub against fixture facts first"
— resolved by re-reading the plan's own generator bullet closely: it says "from
Facts KB," not "from tailored output." Built directly off `ResumeFact` rows (real DB
rows, not stubs) — cleanly sidesteps a real, separate mismatch noticed but
deliberately not touched this pass: `tailoring/engine.py`'s actual `bullets` output
is `list[str]`, not `SPEC.md` §3.3's `{text, source_fact_ids}` contract, so tailored
output can't be traced back to a source fact today. That's a pre-existing gap in a
different feature, out of scope for 5a, flagged here so it isn't rediscovered as new.

**Real schema gap found and closed.** `SPEC.md` §1's `resume_facts` DDL has always
had `period_from`/`period_to`, but `models.ResumeFact` never did — with no date data
at all, §3.5 rule 8 (date-range format) would have been untestable against anything
real. Added both columns (migration `0008`, **applied for real to live Neon**,
confirmed `0007 -> 0008`) rather than leave the rule unexercised — same "build the
already-specified schema when the current item needs it" pattern as items 2 and 3.

**`apps/api/documents/` (new package).** `generate_docx.py::generate_resume_docx`
— builds a DOCX from Facts KB only (ADR-009: never the raw resume blob), grouping
`ResumeFact.category` into `SPEC` §3.5 rule 5's exact allowed heading set
(`Summary`/`Experience`/`Skills`/`Education`/`Projects`) — **note:** no
"Certification" heading exists in that set, so `certification`-category facts fold
into `Education`, documented in code, not silently dropped. Date ranges render via a
dedicated `"Job Copilot Date Range"` paragraph style, not detected by scanning all
text for dash-like substrings — keeps the linter's rule 8 check precise instead of a
heuristic that could false-positive on an ordinary bullet like "10x - 20x throughput."

**`ats_safety.py::lint_docx`** — all 8 rules, checked independently of the generator
(a linter that only trusts its own generator to stay correct doesn't catch a future
regression there). Verified against `python-docx`'s actual installed source before
using internal-looking APIs (`document.inline_shapes`, `section._sectPr`, `docx.oxml
.ns.qn`) rather than guessing — all three confirmed real by grepping the installed
package.

**`parse_back.py::parse_back_check`** — reuses `parsing/extract.py::
extract_text_from_docx` exactly as it already existed (the plan's own instruction:
"reusable as-is"), fuzzy-matches each fact's `achievement` against the round-tripped
text via `rapidfuzz.fuzz.partial_ratio` at the SPEC's own ≥0.9 threshold — both
`rapidfuzz` and `python-docx`/`pdfplumber` were already installed but unwired
(2026-08-16 latest+8 entry), this is their first real use.

**New endpoint, fails loud rather than shipping a bad document.** `GET
/profiles/{profile_id}/resume.docx` generates, then runs both the linter and the
parse-back check before any bytes leave the server — either failing raises a 500
naming exactly what failed, never a silently-wrong document.

**`tests/test_ats_safety.py` created** — `SPEC.md` referenced this file as already
asserting the 8 rules (2026-09-26 roadmap-scoping entry flagged it didn't exist);
it does now. 12 tests, one per rule plus generator-shape and parse-back coverage,
all passed on the first real run against the actual implementation — a strong signal
the design (heading names, section defaults, date regex, font/table/image/textbox
checks) was right, not just internally consistent with itself.

**Real verification, not simulated.** Full suite: 158/158 green (145 + 13 new: 12 in
`test_ats_safety.py`, 1 endpoint test). App boots, 27 routes (up from 26). **Live
against real Neon**: created a real user/profile/fact, generated a real 36.8KB DOCX
(valid ZIP, `PK` signature), ran the real linter (zero violations) and the real
parse-back check (1.0 similarity) against it, cleaned up after.

**Not done in this item, by its own scope.** 5b (PDF export) — already decided
deferred in the roadmap-scoping entry, not revisited here. No UI wiring in
`apps/web` to actually download this — the plan named the generator/linter/check as
5a's scope, not a dashboard button. Tailoring's `bullets: list[str]` vs. `SPEC` §3.3
mismatch noted above — real, but a different feature's bug, not fixed here.

**Files created.** `alembic/versions/0008_resume_fact_periods.py`,
`documents/__init__.py`, `documents/generate_docx.py`, `documents/ats_safety.py`,
`documents/parse_back.py`, `tests/test_ats_safety.py`,
`tests/test_resume_docx_endpoint.py`. **Files changed.** `models.py`
(`ResumeFact.period_from/period_to`), `schemas.py` (same on
`ResumeFactIn`/`ResumeFactOut`), `main.py` (`GET /profiles/{id}/resume.docx`).

**Next.** 5b is explicitly deferred (decided in the roadmap-scoping entry, not an
open item). Item 6 — outreach (Gmail OAuth) — is next and is genuinely blocked on
the owner's own Google Cloud OAuth client setup, not on anything further code can
route around; worth confirming that's ready before starting that session.

---

### 2026-09-26 (latest+4) — Roadmap item 4: F11 bounded form-fill agent, backend live-verified

**What changed.** Built plan item 4 — the larger of the two ADR-011 bounded agents.
Per the plan's own explicit requirement, authored a real `SPEC.md` §3.7 section
first (no F11 section existed anywhere before this — confirmed, matching the
roadmap's "Verified current-state facts"): field-mapping request/response schema,
a concrete **0.75 confidence threshold** (none existed before — the plan named this
as a real gap), the human-fallback UI behavior, and how the 2-3 pass ADR-011 ceiling
actually surfaces (a bounded 2-attempt retry on a malformed response, not a
reasoning loop — F11's own design per `DECISIONS.md` is literally "one Claude call
returns field mappings").

**Backend (`apps/api/formfill/map_fields.py`, new package) — fully red-before-green,
fully live-verified.** `map_form_fields(fields, profile_summary)`: any field whose
label matches a demographic/EEO/essay keyword list is flagged `unknown` and **never
even sent to the model** — defense-in-depth, not just a prompt instruction the model
could ignore. Everything else goes through one bounded Claude/nvidia_smoke call
(reused `tailoring/engine.py`'s LLM-call plumbing again, same as item 3 — ponytail
rung 2, no new provider-branching code); a malformed/unparseable response gets one
retry, then gives up safely (`unknown`, never a guess). New `POST
/extension/map-fields` endpoint proxies this — the model call happens server-side
only, so no Anthropic/NVIDIA key ever ships in extension code, per the plan's
explicit key-exposure design decision.

**Real live verification, not just mocked.** Ran `map_form_fields` for real with
`LLM_PROVIDER=nvidia_smoke` against 4 synthetic fields: email correctly mapped
(confidence 1.0), "What is your gender?" and "Why do you want to work here?" both
forced to `unknown` without reaching the model at all, and "Full name" correctly
came back `unknown` rather than inventing a name from the email address — the
"never invent" constraint held under a real model call, not just in a mock. Full
backend suite: 145/145 green (136 + 9 new: 7 in `test_formfill.py`, 2 in
`test_extension_map_fields.py`). App boots, 26 routes (up from 25).

**Extension side.** `manifest.json`: added `content_scripts` (all `http(s)` pages,
`exclude_matches` on `*.linkedin.com` per ADR-002) and `host_permissions` for the
dev API origin — confirmed by rebuilding, not assumed; `crxjs` correctly generated
a content-script loader and `web_accessible_resources` entry. New
`src/content/fieldDecision.mjs` — the fill/flag decision logic (confidence
threshold, forbidden-keyword defense-in-depth mirrored client-side too, not just
trusting the backend) — kept as plain `.mjs` specifically so it runs unchanged
under Node's **built-in** test runner (`node --test`, zero new dependencies, per
this project's own "never install without asking" rule) — 7/7 green. A typed
`fieldDecision.d.mts` declaration file gives the TS content script real types
without converting the tested file itself to TS (confirmed the `.d.mts` extension,
not `.d.ts`, is what TS's bundler resolution actually needs for an `.mjs` import —
found by testing, not guessed, the first attempt with `.d.ts` silently didn't
resolve). `src/content/formFill.content.ts` — DOM extraction/fill/flag glue,
messaged by a new popup button rather than running on every page load. `App.tsx` —
minimal login (stores the JWT in `chrome.storage.local`, same token every other
endpoint uses) + "Fill this form" trigger. `npx tsc --noEmit` clean, `npm run
build` clean (confirmed from a deleted `dist/`, not a stale cache — same discipline
as the 2026-08-16 `.next`-cache lesson).

**Honestly not done, not silently claimed.** No live-browser verification of the
content script itself (DOM extraction, field-highlighting, message-passing) — this
session has no Playwright/loaded-extension access; only the pure decision logic
(`fieldDecision.mjs`) and the backend it calls are actually exercised. **The PRD's
"validate against 15-20 real Greenhouse/Lever/Workday forms" exit criterion is
explicitly open** — per SPEC §3.7's own new text, ADR-002 forbids server-side
scraping even for test fixtures, so real fixtures need the owner's own user-side
HTML captures, which don't exist yet; nothing was fabricated to fake this coverage.
The richer `ShadowRoot`/Tailwind consolidated-summary UI ARCHITECTURE.md's
"Extension UI isolation" section specifies is deferred — this pass uses inline
per-field highlighting instead, a real but smaller UI, documented in SPEC §3.7 as
a deliberate scope cut with its own upgrade trigger.

**Files created.** `formfill/__init__.py`, `formfill/map_fields.py`,
`tests/test_formfill.py`, `tests/test_extension_map_fields.py`,
`apps/extension/src/apiConfig.ts`, `apps/extension/src/content/fieldDecision.mjs`,
`apps/extension/src/content/fieldDecision.test.mjs`,
`apps/extension/src/content/fieldDecision.d.mts`,
`apps/extension/src/content/formFill.content.ts`. **Files changed.** `docs/SPEC.md`
(§3.7, new), `schemas.py` (`FieldDescriptorIn`/`MapFieldsRequest`/`FieldMappingOut`),
`main.py` (`POST /extension/map-fields`), `apps/extension/manifest.json`
(`content_scripts`/`host_permissions`), `apps/extension/src/App.tsx` (login + fill
trigger, replacing the scaffold placeholder).

**Next.** Item 5a of the roadmap — documents (DOCX generation + ATS-safety linter +
parse-back check) — per its own dedicated session, fresh-session-per-phase
convention (this whole roadmap has now run in one continuous session at the
owner's explicit direction across items 1-4; flagged each time, not silently
repeated as a default).

---

### 2026-09-26 (latest+3) — Roadmap item 3: F5 unknown-ATS Claude classification, verified live

**What changed.** Built plan item 3 against real `SPEC.md` §3.4/§1, red-before-green.
`connectors/discovery.py::detect_ats()` (the known-pattern matcher, unchanged) was
never actually called from anywhere in production code before this — confirmed by
grep, matching the plan's "Verified current-state facts" note. This item builds the
real call site.

**`discover_ats_for_domain(db, domain)`** — the new entrypoint: tries `detect_ats()`
first; only on a miss does it spend a bounded, single Claude/nvidia_smoke call
(ADR-011: one pass, not F11's multi-pass budget) via the new
`classify_unknown_ats(domain)`, which reuses the *same* `is_safe_url()` SSRF guard
and `CANDIDATE_PATHS` fetch `detect_ats()` already uses — no new fetch surface, per
the plan's own bullet. The model is asked to identify the ATS vendor from page
evidence and propose a single-capture-group regex, grounded in evidence, never
inventing a pattern with none.

**Reused, not duplicated, the LLM-call plumbing.** Rather than re-implement
`nvidia_smoke`/Anthropic provider branching + Langfuse instrumentation a second time
in `discovery.py` (ponytail rung 2: already in the codebase, reuse it), renamed
`tailoring/engine.py`'s private `_call_claude` to public `call_llm` and imported it
directly — same function, same Langfuse tracing, zero duplicated provider logic.

**Review surface — decided in the plan, built here.** `connector_runs` (SPEC.md §1's
DDL, never previously implemented as an ORM model or table — this is its first real
writer) now logs every classification attempt: `source="ats_discovery_classify"`,
`token=domain`, `notes` = the parsed proposal JSON (or `null`), `failed=1` when no
candidate page was reachable at all. **No auto-promotion into `ATS_PATTERNS`, ever**
— the owner reads `connector_runs` and manually adds a verified pattern. No new
table beyond the already-specified one, no admin UI, per the plan's explicit choice.

**Schema.** `alembic/versions/0007_connector_runs.py` — `connector_runs` per SPEC.md
§1's DDL exactly (id, source, token, fetched/inserted/failed ints, error text, `ran_at`
index). **Run for real against live Neon**, confirmed `0006 -> 0007` applied.
`models.py`: `ConnectorRun` ORM class, plus a `notes JSON` column beyond the DDL's own
fields — the DDL only had `error text`, semantically wrong for a non-error structured
proposal payload; added `notes` rather than jam JSON into `error`, smaller and more
honest than stretching an existing field's meaning.

**Real verification, not simulated.** Full suite: 136/136 green (17 in
`test_discovery.py`, up from 11 — 6 new: `classify_unknown_ats` parses a proposal /
returns `None` when no page is reachable; `discover_ats_for_domain` skips
classification entirely on a known-pattern hit, logs a proposal row, logs a
failure row). App boots (still 25 routes — this item added no HTTP endpoint, matching
the plan's own scope, which named no new API path). **Live end-to-end, not just
mocked**: ran `discover_ats_for_domain(db, "www.python.org")` for real with
`LLM_PROVIDER=nvidia_smoke` — real HTTP fetch of python.org's careers-adjacent page,
real NVIDIA NIM call, got back a well-grounded classification (`ats_type: null,
confidence: high, evidence: "no third-party ATS vendor signatures present"` — the
model correctly declined to invent a pattern rather than hallucinating one), a real
row landed in live Neon's `connector_runs`, cleaned up after. Migration applied for
real.

**Files created.** `alembic/versions/0007_connector_runs.py`. **Files changed.**
`models.py` (`ConnectorRun`), `connectors/discovery.py` (`classify_unknown_ats`,
`discover_ats_for_domain`, `CLASSIFY_SYSTEM_PROMPT`), `tailoring/engine.py`
(`_call_claude` → `call_llm`, public), `docs/SPEC.md` (§3.4 addendum),
`tests/test_discovery.py` (+6 tests).

**Next.** Item 4 of the roadmap — F11 bounded form-fill agent — the larger of the two
agent features; needs a new `SPEC.md` F11 section authored first (none exists at all
currently) plus new extension content-script infra, per its own dedicated session.

---

### 2026-09-26 (latest+2) — Roadmap item 2: ADR-012 outbox/SSE + job idempotency, verified live

**What changed.** Built the item scoped in `happy-jingling-wall.md` item 2, against
real SPEC.md/ARCHITECTURE.md text (read directly, not summarized from the plan file),
red-before-green throughout.

**Schema.** `alembic/versions/0006_events_notifications.py` — `events` (outbox,
`bigserial` id doubling as SSE `Last-Event-ID`, `published_at IS NULL` partial index
for the relay poll, `(user_id, id DESC)` index for reconnect replay) and
`notifications`, both per SPEC.md §1's DDL. **Run for real against live Neon**,
confirmed `0005 -> 0006` applied. `models.py`: `Event`/`Notification` ORM classes.
SQLite (unit-test engine) needed `BigInteger().with_variant(Integer, "sqlite")` on
`Event.id` — SQLite's rowid-autoincrement aliasing only fires for an exact `INTEGER`
column, not `BIGINT`; Postgres is unaffected, a real cross-dialect gap only this kind
of column hits (matches the class of bug the 2026-08-16 numpy/pgvector entry found —
only reproducible on one of the two engines, not the other).

**Real spec inconsistency found and resolved, not silently papered over.** SPEC.md
§2.6's endpoint table says `PATCH /notifications/{id}` accepts `{status: "seen"}` for
the read-receipt, but §1's own DDL `CHECK` on `notifications.status` only listed the
four delivery states (`pending|sent|failed|skipped`). Resolved by extending the CHECK
to include `seen` rather than adding a second column — satisfies both sections,
smaller diff. Documented in the migration and in `models.Notification`'s docstring so
a later session doesn't re-discover this as a bug.

**`apps/api/events/` package.** `outbox.py::write_event` (same-transaction insert,
caller commits — verified it does *not* commit itself, so it composes with other
writes in one transaction). `relay.py::relay_once` (`SELECT ... FOR UPDATE SKIP
LOCKED` via SQLAlchemy's `with_for_update(skip_locked=True)` — confirmed this
compiles harmlessly on SQLite too, not just Postgres, so the unit suite actually
exercises the real query shape). `sse.py::event_stream` (async generator: replay from
`Last-Event-ID` bounded to 500 rows, then subscribes to `redis.asyncio`'s pubsub on
`user:{id}` for the live tail). `run_relay.py` — resolves the plan's open question
("distinct RQ worker or piggyback on the scheduler?"): **a standalone poll-loop
script**, not an RQ job and not merged into `run_scheduler.py` — it's a tight
Postgres+Redis loop (ARCHITECTURE.md §4.6's own pseudocode), not queued work, so none
of `run_worker.py`'s Windows `os.fork`/`SIGALRM` constraints apply to it at all.

**Wired into main.py.** `GET /events` (SSE via `sse-starlette`, header
`Last-Event-ID`). `GET /notifications` (`?status=`), `PATCH /notifications/{id}`.
`matching/service.py::build_matches()` now writes `match.new` only for a genuinely
new match — verified a rebuild of an already-seen match does NOT re-fire the event
(`test_build_matches_writes_match_new_event_once_not_on_rebuild`).
`main.py::update_application()` writes `application.status_changed` in the same
transaction as the status write.

**Job idempotency (SPEC §3.6), scoped to `discover_jobs_task` only, built inline per
the plan's own explicit "not a premature generic helper" call.** Layer 1 (enqueue
dedupe): `/discover/run` derives `job_id = f"discover:{minute-bucket}"`, enqueues with
`unique=True` — confirmed via reading the installed `rq==2.10.0` source directly
(`queue.py`'s `enqueue_call`/`save_unique_job`) that this raises `DuplicateJobError`
atomically via a Lua script, not guessed from memory or stale docs; a caught
`DuplicateJobError` fetches and returns the existing job instead. Layer 2 (execution
claim): `discover_jobs_task(job_id=...)` does a Redis `SETNX ... EX 600` before
fetching; a lost race returns `{"skipped": True, "reason": "already claimed"}`. The
scheduler's own periodic call passes no `job_id` — confirmed by a test
(`test_discover_without_job_id_runs_unguarded`) that no Redis claim is attempted on
that path, since `run_scheduler.py` already prevents duplicate registration itself.
Layer 3 (DB backstop) doesn't apply here — SPEC §3.6's `UNIQUE(application_id, pass,
attempt)` backstop is specific to tailoring `generations` rows; discovery has no
analogous per-row uniqueness to backstop, layers 1+2 are the real guard for this job.

**Real verification, not simulated, for everything reachable.** Full suite: 131/131
green (118 + 13 new tests: outbox 2, relay 4, discover-idempotency 3, matching-service
+1, notifications/events endpoints 3). App boots: 25 routes (up from 22). **Live
against real Neon** (not just SQLite): wrote a real `Event` row, ran `relay_once`
against a mocked Redis client, confirmed the real row's `published_at` got stamped and
the publish payload was correct, cleaned up after. **Live RQ enqueue-dedupe check
attempted against real Redis Cloud and failed for an environment reason, not a code
reason** — `expert-neosafe-bucket-71462.db.redis.io` didn't resolve from this machine
this session (`socket.gaierror`, DNS). Not silently claimed as verified — the
`DuplicateJobError` behavior is confirmed by reading the installed library's own
source, not live-exercised. Worth a live re-check next session if Redis Cloud
connectivity comes back.

**Not done in this item, by its own explicit scope.** Notification *production*
(the RQ job per trigger that actually creates `weekly_digest`/`follow_up_nudge`/
`application_status` rows) — item 2 only needed read/patch per the plan; that's Phase
4/6 scope. `resume.parsed` event (F2) — no call site wired yet, not touched by this
item's two named call sites (`match.new`, `application.status_changed`).

**Files created.** `alembic/versions/0006_events_notifications.py`,
`events/__init__.py`, `events/outbox.py`, `events/relay.py`, `events/sse.py`,
`events/run_relay.py`, `tests/test_events_outbox.py`, `tests/test_events_relay.py`,
`tests/test_discover_idempotency.py`, `tests/test_notifications_and_events.py`.
**Files changed.** `models.py` (`Event`/`Notification`), `schemas.py`
(`NotificationOut`/`NotificationUpdate`), `main.py` (imports, `/discover/run`
idempotency, `update_application` event write, `/events`/`/notifications`
endpoints), `matching/service.py` (`match.new` event write), `workers/jobs.py`
(`discover_jobs_task(job_id=...)` claim), `tests/test_matching_service.py` (+1 test).

**Next.** Item 3 of the roadmap — F5 unknown-ATS Claude classification — per its own
dedicated session, fresh-session-per-phase convention (this item ran in the same
session as item 1, at the user's explicit request, deviating from that convention —
noted, not repeated without being asked again).

---

### 2026-09-26 (latest+1) — Roadmap item 1: extension build fix, verified

**What changed.** Added `css: { postcss: {} }` to `apps/extension/vite.config.ts`,
per the plan file (`happy-jingling-wall.md` item 1). This stops Vite's PostCSS
config search from walking up to the stray, unrelated `D:\postcss.config.mjs`
(pre-existing at the drive root, outside this project, referencing a plugin not
installed here — see the 2026-08-16 latest+8 entry).

**Real verification.** Ran `npm run build` in `apps/extension` — previously
failing, now succeeds clean: 31 modules transformed, `dist/manifest.json`,
`dist/index.html`, one JS chunk (194.95 kB), built in 1.19s. Confirms the stray
root file really was the cause, not a speculative fix.

**Files changed.** `apps/extension/vite.config.ts` (one line).

**Next.** Item 2 of the roadmap — ADR-012 outbox/SSE + job idempotency — per its
own dedicated session, fresh-session-per-phase convention.

---

### 2026-09-26 — Full remaining-work roadmap scoped (plan mode, no code yet)

**What changed.** Owner asked to scope literally everything left on the project —
ADR-012 (outbox/SSE), F5/F11 (ADR-011's bounded agents), Phase 4 (documents), Phase 6
(outreach) — before implementing any of it, one item at a time, using `nvidia_smoke`
throughout so nothing is blocked on a real `ANTHROPIC_API_KEY`. Ran 3 parallel Explore
agents against the real current code (not memory) plus 1 Plan agent to sequence the
result. Full roadmap written to a plan file and walked through plan mode with the
owner; three real decisions were made and are now final, not just proposed:

1. **F5's "propose new ATS pattern" review surface** — lightweight structured log
   row, owner manually promotes into `ATS_PATTERNS`. No new table/admin UI.
2. **Phase 4 PDF export — deferred.** DOCX generation + ATS-safety linter +
   parse-back check ship first (5a); PDF via LibreOffice (or an alternative
   renderer) is explicitly *not* built this pass (5b), revisit once 5a is solid.
3. **Phase 6 token encryption** — Fernet symmetric encryption from the
   already-reserved `ENCRYPTION_KEY` env var now, real KMS deferred to first real
   production deployment (ADR-003 says "KMS-backed"; this is an interim, still
   genuinely encrypted, not a violation — same build-now-upgrade-later pattern
   already used for the Anthropic key).

**Real findings from the Explore pass, worth not re-deriving:**
- The schema for `events`/`notifications` (ADR-012) and `outreach`/`suppressions`
  (Phase 6) is **already fully specified in `SPEC.md` §1** — implementing these is
  "build an already-designed schema," not "design from scratch."
- **No F11 section exists anywhere in `SPEC.md`** — it's described only at
  ADR-011/PRD narrative level. Authoring real engineering-detail mechanics (field-
  mapping schema, confidence threshold, human-fallback UI) is real work inside that
  item, not a formality.
- `apps/extension/` is popup-only — no content-script/background-script file exists
  at all yet. `manifest.json` has only `activeTab`/`storage` permissions.
- `tests/test_ats_safety.py` does not exist yet, despite `SPEC.md` referencing it as
  already asserting the 8 ATS-safety rules.
- Zero Gmail/Google OAuth code exists anywhere; `auth/router.py` is local
  email/password only.
- The stray unrelated `D:\postcss.config.mjs` (flagged 2026-08-16) is still present
  at the drive root — the extension build fix (`css: { postcss: {} }` in
  `apps/extension/vite.config.ts`) is still unapplied and unverified (file's
  existence confirmed, but `npm run build` was never actually re-run against it).

**Build order locked in:** (1) extension build fix — trivial, do first; (2) ADR-012
outbox/SSE + job idempotency — foundational, schema pre-specified; (3) F5 unknown-ATS
classification — smaller of the two bounded agents; (4) F11 form-fill agent — needs
new extension content-script infra + a new SPEC.md section first, and its Claude/
nvidia_smoke call must be proxied through a new FastAPI endpoint, never issued
client-side from the extension (key-exposure risk); (5a) documents (DOCX + linter +
parse-back); (5b) PDF, deferred; (6) outreach — last, genuinely blocked on the
owner's own Google Cloud OAuth client setup, not on anything code can route around.

**No code changed this session** — full roadmap is in the plan file
(`happy-jingling-wall.md`) and now this entry; each numbered item gets its own
dedicated session before implementation, per this project's own established
fresh-session-per-phase convention.

### 2026-09-26 — Repo scouting write-up + dev-only NVIDIA NIM smoke-test provider

**What changed.** Owner shared 6 job-application/scraping repos for comparison
(ApplyPilot, career-ops, AIHawk, JobSpy, jobhive/ats-scrapers,
Auto_job_applier_linkedIn) and asked about testing the tailoring pipeline for free.
Logged verdicts in `docs/DEPENDENCIES.md` §3: ApplyPilot and career-ops added as
study-only/not-adopted (full-autonomy conflicts with ADR-001; career-ops validates
the project's own human-review philosophy but is less mature than what's already
built); jobhive identified as almost certainly the same repo already logged as
`kalil0321/ats-scrapers`, verdict unchanged; Auto_job_applier_linkedIn and an AIHawk
fork added to the rejected table (ADR-002 LinkedIn trigger, AGPL, same reasons as
existing entries).

**OmniRoute rejected as a path to "free Claude."** Investigated
`diegosouzapw/OmniRoute` — its claim of free access to premium models (Claude, GPT)
without your own key almost certainly means pooled/shared credentials or scraped
web-chat sessions, not a real free tier. Same class of ToS/trust risk this project's
own ADR-002 already avoids for LinkedIn. Not adopted.

**NVIDIA NIM wired as a dev-only smoke-test provider instead**, owner-provided key
(real, genuinely free, OpenAI-compatible — confirmed via `build.nvidia.com`'s own
`/v1/models` and `/v1/chat/completions` endpoints, not guessed). Real finding: most
models listed in the NIM catalog return `404 Function not found for account` when
actually invoked — the catalog lists more than an unactivated free-tier account can
call. Swept all 82 catalog entries; the only one that returned a working `200`:
`google/diffusiongemma-26b-a4b-it`.

`core/config.py`: added `llm_provider` (default `"anthropic"`, unchanged), plus
optional `nvidia_api_key`/`nvidia_base_url`/`nvidia_smoke_model`. `tailoring/
engine.py`: `_call_claude` now branches on `llm_provider` — default path is
byte-identical to before; `"nvidia_smoke"` routes through a lazily-built
`openai.OpenAI` client instead. `openai==2.54.0` (was already present transitively
via `instructor`) pinned explicitly in `requirements.txt` since it's now imported
directly. `.env.example` documents the opt-in block; the owner's real key was written
only to `apps/api/.env` (confirmed not under any `.git` in this project — there is no
`.git` here at all currently — and the root `.gitignore` covers `.env` regardless).

**Verified live, not just mechanically wired:** full suite 118/118 green with
`LLM_PROVIDER` unset (default path untouched); with `LLM_PROVIDER=nvidia_smoke` set,
ran `tailor_application()` end-to-end for real — both passes fired, returned a real
tailored summary/bullets/cover letter, and the truth-check pass correctly flagged
unsupported claims exactly as designed (the free model invents more than Claude
would, which is expected — it's a much smaller model).

**What this does and doesn't prove.** This confirms the pipeline fires mechanically
on a real API call end-to-end. It does **not** validate real tailoring quality — NIM
serves open models, not Claude. `ANTHROPIC_API_KEY` is still the placeholder
(`sk-ant-dev-placeholder`); that remains the actual blocker for ADR-014's eval
harness and any real quality signal, unchanged by this session's work.

**Security note.** The owner pasted the NVIDIA key directly into chat this session —
flagged to them as exposed-in-transcript; recommended rotating it at
build.nvidia.com if they're cautious, independent of whether it's still used here.

### 2026-08-16 (latest+8) — Remaining DEPENDENCIES.md backlog cleared: documents, observability, extension scaffold

**What changed.** Owner asked to install everything still open in `DEPENDENCIES.md`:
§1.5 (documents), the rest of §1.8 (observability beyond Langfuse), pass-7 misc, and
§2.1's `better-auth`/`openapi-typescript`/`vitest`, plus scaffold the §2.2 browser
extension. Cleared all of it; found one more real regression along the way.

**Python packages installed** (`apps/api/.venv`): `rapidfuzz`, `instructor`,
`sse-starlette`, `rq-dashboard-fast`, `cleanco`, `price-parser`, `iso4217`,
`croniter`, `clamd`. None of these are wired into working code yet, deliberately —
under this session's accumulated cost, forcing integrations into a passing test
suite for packages with no natural touchpoint yet (no cron-config endpoint, no SSE
route, no admin dashboard mount) would be exactly the kind of speculative complexity
this project's own conventions argue against. Installed and available, honestly
documented as unwired, not silently claimed as "done."

**Another real regression, caught the same way as the JobSpy one earlier today.**
Installing `instructor` (alongside `sse-starlette`/`rq-dashboard-fast`) forced pip's
resolver to bump `fastapi` (pinned `0.115.0` → `0.141.1`) and, more seriously,
`starlette` across a **major version boundary** (`0.38.6` → `1.6.0`). Did not assume
this was safe — ran the full suite immediately (118/118 green), then explicitly
verified the app still boots (`from main import app` → 22 routes) and that the RQ
Windows workaround from Phase 2 (`SimpleWorker`/`TimerDeathPenalty`, `workers/run_worker.py`)
still imports cleanly, since that fix was itself version-sensitive. All clean —
pins bumped in `requirements.txt` to match what's actually installed and verified,
with a comment explaining why, rather than leaving a stale pin that lies about what's
running. `rq` also moved `2.0.0` → `2.10.0` in the same resolve, same verification.

**§2.1 frontend: `better-auth`, `vitest`, `@testing-library/react`, `msw`,
`openapi-typescript`, `style-dictionary` installed** (`apps/web`). Rebuilt after each
batch — `npm run build` stayed green throughout (6 static pages, no new errors),
`npm audit` unchanged (still the same 3 pre-existing high-severity issues already
logged, nothing new introduced). None of these are wired into working code yet either
— same "installed, not forced into speculative integration" reasoning as the Python
side.

**§2.2 Browser extension scaffolded — a real, buildable MV3 skeleton, with one known
blocker.** New `apps/extension/` (sibling to `apps/api`, `apps/web`): `package.json`,
`manifest.json` (MV3, popup action), `vite.config.ts` using `@crxjs/vite-plugin`'s
`crx({ manifest })` (syntax verified via the crxjs docs, not guessed), a minimal React
popup (`src/main.tsx`, `src/App.tsx`). `npm install`: 98 packages, **0 vulnerabilities**.
`npm run build` currently **fails** — not because of anything in this scaffold, but
because Vite's PostCSS config search walked up to a stray, pre-existing
`D:\postcss.config.mjs` at the drive root (confirmed via `ls`: dated April 2026, months
before this session, unrelated to job-copilot) referencing a plugin
(`@tailwindcss/postcss`) that isn't installed here. Given this session's cost, stopped
debugging per explicit instruction rather than chase a fix for a file outside this
project's control — the scaffold itself (manifest, vite config, popup) is real and
correctly structured; the build needs either an explicit `css: { postcss: {} }`
override in `vite.config.ts` to stop Vite's upward config search, or the stray root
file addressed outside this project. This is genuinely unfinished, not silently
claimed done.

**Real verification, not simulated, for everything that could be checked without
further cost.** Backend: full suite green, app-boot check, RQ-worker-import check.
Frontend: full production build green twice (after each install batch), zero new
`npm audit` findings. Extension: real `npm install` (0 vulnerabilities) and a real
build attempt that surfaced a real, externally-caused failure — not asserted to work
without checking.

**Files created.** `apps/extension/` (package.json, manifest.json, vite.config.ts,
tsconfig.json, index.html, src/main.tsx, src/App.tsx).
**Files changed.** `apps/api/requirements.txt` (9 new packages + fastapi/starlette/rq
pin updates with reasoning), `apps/web/package.json` (6 new devDependencies).

**Not done.** Nothing from any package installed this entry is wired into working
code — this entry is "installed and verified not to break anything," not "used."
LibreOffice (§1.5, the other half of document conversion) — a system-level installer,
not a package, not attempted without the owner's explicit go-ahead (same reasoning as
the earlier Docker Desktop decision). ClamAV daemon (§pass-7) — `clamd` client
installed, but the daemon itself needs Docker, unavailable on this machine, same
standing reasoning as Postgres/Redis before Neon/Redis Cloud existed — nothing to
connect `clamd` to yet.

**Next.** Fix the extension's PostCSS config-search issue (a `css.postcss: {}`
override is the direct fix, one line). Decide whether LibreOffice is worth a system
install now or stays deferred. Everything else genuinely installed this pass has no
forced next step — it's available when a real feature needs it, per this project's
own standing "don't build speculative integrations" reasoning.

---

### 2026-08-16 (latest+7) — Third-party repos installed: presidio, jsonresume, agent-reach, simhash, anthropic SDK; JobSpy isolated after a real conflict

**What changed.** Owner asked to actually install and use every pending third-party
repo logged in `DEPENDENCIES.md` §3, with blanket approval given upfront. Worked
through the list; found one real, hard blocker (JobSpy) along the way and resolved it
by isolation rather than forcing it through.

**1. Anthropic SDK swap.** `tailoring/engine.py`'s hand-rolled `httpx.post` replaced
with the official `anthropic` SDK (already pinned, `requirements.txt`, unused until
now — `DEPENDENCIES.md` §1.2's original proposal). Live-verified: raises the real
`anthropic.AuthenticationError` on the still-placeholder key, Langfuse tracing (Phase
3 slice 1) still captures the call.

**2. jsonresume adopted.** `parsing/jsonresume_export.py::facts_to_jsonresume` maps
`ResumeFact` rows to the real JSON Resume schema (verified via WebFetch against
jsonresume.org/schema, not guessed) — necessarily lossy, `ResumeFact` is coarser than
JSON Resume's per-section fields. New `GET /resume-facts:jsonresume` endpoint.

**3. Presidio installed and wired.** `pii/redact.py::redact_pii` — real PII
redaction for future company-dossier (F7) and generation-history (F8) text.
`AnalyzerEngine()` auto-downloaded its spaCy model (`en_core_web_lg`, ~400MB, one-time,
now cached). Live-verified: `"Contact John Smith at john.smith@acme.com or call
555-123-4567."` → `"Contact <PERSON> at <EMAIL_ADDRESS> or call <PHONE_NUMBER>."`

**4. simhash reimplemented, not vendored — a real deviation from the original plan.**
`DEPENDENCIES.md` said "vendor a copy" of `seomoz/simhash-py`, but that repo turned
out to be a Cython/C++ extension (185KB `simhash.cpp`) needing a compiler toolchain —
confirmed by actually reading its file tree, not assumed. This project already
declined that exact class of dependency once (garak/Rust, 2026-08-15). Reimplemented
Charikar's simhash algorithm in pure Python (`matching/near_duplicate.py`) instead,
matching the "study upstream, reimplement" pattern already used for
esco-skill-extractor and ats-scrapers. Wired into `connectors/pipeline.py::upsert_jobs`
as a same-batch near-dup gate (ponytail: batch-scoped, not a full-table scan against
every existing job — that needs its own index/architecture call).

**5. agent-reach installed, isolated, and used for real.** Installed into its own venv
(`tools/.venv-agent-reach/`) rather than the main app venv, matching its own designed
subprocess-invocation model. `agent-reach doctor` showed 4/15 channels work with zero
extra credentials; built `research/company_research.py::research_company` on the two
actually useful ones (GitHub via the already-authenticated `gh` CLI, arbitrary web
pages via Jina Reader — free, keyless). **A real bug found only by running it live**:
`subprocess.run(..., text=True)` alone decodes with the OS default codepage (cp1252 on
Windows), which raised `UnicodeDecodeError` on real UTF-8 web content and silently left
`stdout=None` — fixed with explicit `encoding="utf-8", errors="replace"`. Live-verified
against a real company ("Anthropic"): real GitHub repos, real web page markdown back.
Twitter/Reddit/etc. channels need real per-service credentials not available — not
wired, not silently stubbed.

**6. JobSpy — the one real, hard blocker found this pass.** Installing
`python-jobspy` into the main `apps/api/.venv` downgraded `numpy` (2.4.6→1.26.3,
JobSpy's own hard pin) and `pydantic` (2.9.2→2.13.4), and **broke a real,
previously-passing test** (`test_upsert_sets_embedding_from_voyage`, a float-precision
assertion sensitive to the numpy version). Confirmed this wasn't recoverable by
re-pinning: `numpy>=2` (needed by pgvector/scikit-learn) and JobSpy's own
`numpy==1.26.3` requirement cannot both be satisfied in one environment. Asked the
owner how to proceed (isolate vs. skip) — chose isolate. Removed JobSpy from the main
venv, restored `numpy`/`pydantic` to the pinned baseline, confirmed 99/99 green again
before doing anything else. Reinstalled JobSpy into its own venv
(`tools/.venv-jobspy/`), built `connectors/jobspy_connector.py::fetch_jobspy_jobs` as
a subprocess wrapper (same contract as the other 5 connectors). **Live test returned 0
rows** — JobSpy's own verbose log: `"initial cursor not found, try changing your
query or there was at most 10 results"`. This is JobSpy's Google Jobs scraper failing
against Google's current page structure, a real upstream/Google-side issue (same
honest-negative-result category as the ATS-discovery low-hit-rate finding,
2026-08-16 Phase 2 entry) — not a wiring bug in this connector. The wrapper itself is
correct and will produce real rows whenever JobSpy's own scraper works again.

**Architecture note, not previously written down: isolated-venv-as-subprocess is now
a real, repeated pattern in this project**, not a one-off. Two tools now live outside
the main `apps/api/.venv` specifically because their pinned dependencies conflict with
it: `tools/.venv-agent-reach/`, `tools/.venv-jobspy/`. Same reasoning as garak being
CI-only — a dependency that can't coexist doesn't get forced in, it gets isolated or
excluded, and it's written down which and why.

**Real verification, not simulated, throughout.** Every module above was checked
against real infrastructure, not just mocked tests: real `anthropic.AuthenticationError`,
real spaCy-model download and real PII redaction, real GitHub search + real Jina
Reader fetch, real (if empty) JobSpy scrape with real upstream diagnostic logging.
Full suite: 118/118 green.

**Files created.** `parsing/jsonresume_export.py`, `pii/__init__.py`, `pii/redact.py`,
`matching/near_duplicate.py`, `research/__init__.py`, `research/company_research.py`,
`connectors/jobspy_connector.py`, `tools/.venv-agent-reach/` (gitignored),
`tools/.venv-jobspy/` (gitignored), plus 5 new test files (all red-before-green).
**Files changed.** `tailoring/engine.py` (anthropic SDK swap), `connectors/pipeline.py`
(near-dup wiring), `main.py` (jsonresume export endpoint), `requirements.txt`
(presidio pinned, jobspy explicitly documented as excluded), root `.gitignore`
(`tools/.venv-*/`).

**Not done in this pass, by explicit scope choice.** Google OAuth outreach
(`google-api-python-client`, `dnspython`) — needs a real Google Cloud OAuth client
from the owner, not yet requested. Browser extension (`vite`+`@crxjs/vite-plugin`) —
a whole new sub-project, not an install. `better-auth`, `openapi-typescript`, `vitest`
— still open from §2.1. Twitter/Reddit channels on agent-reach — need real credentials.

**Next.** Either provide Google OAuth credentials to unblock outreach, or explicitly
defer it; the extension is the other large unstarted piece. JobSpy's Google Jobs
scraper may need a JobSpy version bump or a different query shape — worth a fresh
look, not urgent since Remotive/Greenhouse/Lever/Ashby/Reed already provide 5 live
sources.

---

### 2026-08-16 (latest+6) — shadcn/ui + Kibo UI + jsdiff installed, three real build bugs fixed

**What changed.** Owner asked to actually install the third-party UI repos already
logged in `DEPENDENCIES.md` §2/§3 (shadcn/ui, Kibo UI, jsdiff) rather than keep
building the dashboard on inline styles. Given the size of the full ask (also
included JobSpy, agent-reach, presidio, simhash-py, jsonresume), scoped to the UI kit
first per the owner's own choice — the other repos are unstarted, not forgotten.

**Installed, in `apps/web`:** `shadcn@4.18.0` CLI + `radix-ui` + `lucide-react` +
`class-variance-authority`/`clsx`/`tailwind-merge` (shadcn's own deps) via
`npx shadcn init`; 11 base components (button, card, dialog, select, input, label,
badge, table, tabs, skeleton, sonner); 5 Kibo UI components via the `@kibo-ui`
registry (`components.json`) — **kanban** (direct fit for the application tracker's
Saved→Applied→OA→Interview→Offer→Rejected pipeline, F13), **dropzone** (resume
upload, F2), **combobox** (skill/location/seniority filter pickers), **status**,
**relative-time** — plus their own shadcn dependencies (scroll-area, textarea,
popover, input-group, command); `diff`+`@types/diff` (jsdiff, §2.1/§2.4's
already-decided pick for the tailored-vs-base resume comparison, no adoptable
prose-diff component exists per that section's own research).

**Kibo UI license/maintenance check before installing (not previously in the main
package table, only a §2.4 copy-in note).** `gh api repos/shadcnblocks/kibo`: MIT,
not archived, pushed 2026-05-04, 3.9k stars — matches the project's existing
shadcn "copy-in, zero runtime lock-in" bar. Adopted.

**Three real, separate build failures, each found and fixed by actually running the
build, not by reading the CLI's output and assuming it worked:**

1. **`shadcn init` failed framework detection** — this `apps/web` never had a
   `next.config.js`/`.mjs`/`.ts` file at all (confirmed via `ls`, not assumed). Added
   a minimal `next.config.mjs`. Also needed `-b radix -p nova` passed explicitly —
   `-y` alone still opened two separate interactive prompts (base library, preset)
   that a non-interactive shell can't answer; found by watching the CLI hang, not by
   reading `--help` alone (the preset name in `--help`'s defaults text, `base-nova`,
   also turned out to be wrong — the CLI's own error message corrected it to `nova`).
2. **`shadcn@4.18.0`'s generated `styles/globals.css` is Tailwind v4-only** —
   `@import "shadcn/tailwind.css"` resolves to a real file (confirmed by reading it)
   containing `@theme inline`/`@custom-variant`, at-rules Tailwind v3 (this project's
   pinned version, 3.4.4) doesn't understand. Rather than upgrade Tailwind to v4 —
   a much bigger breaking-change dependency bump than this task's scope, would need
   its own approval the way the promptfoo bump did — ported the CSS custom
   properties into `tailwind.config.js`'s v3-style `theme.extend.colors`/`borderRadius`
   (the standard pre-v4 shadcn pattern), removed the v4-only imports, and swapped the
   v4-only `tw-animate-css` CSS import for the v3-compatible `tailwindcss-animate`
   plugin package. Also had to drop the `/50` opacity modifier from one `@apply
   outline-ring/50` rule — v3 can't apply slash-opacity to a color defined as a full
   `var(--x)` value the way v4's `color-mix()`-based engine can; harmless, it was a
   cosmetic global focus-ring default.
3. **A stale `.next` build cache masked whether fix #2 had actually landed** — after
   editing `globals.css`, a rebuild reproduced the *exact same* error text, byte for
   byte, even though `head`-ing the file directly proved the edit was real. `rm -rf
   .next` and rebuilding surfaced the next real (and different) error, confirming the
   first fix had worked all along and the repeated output was cache, not signal.

**Real verification, not simulated.** `npm run build` succeeded clean after all three
fixes: 6 static pages generated (`/facts`, `/login`, `/_not-found`, `/`), no errors.
`npm audit` still shows the same 3 high-severity issues already logged in the
2026-08-16 Phase 1 frontend entry (postcss/sharp, needs Next 16) — confirmed nothing
new was introduced, not silently ignored.

**Files created.** `apps/web/next.config.mjs`, `apps/web/components/ui/*.tsx` (11
files), `apps/web/components/kibo-ui/*/index.tsx` (5 files).
**Files changed.** `apps/web/package.json` (radix-ui, lucide-react, shadcn CLI,
tailwindcss-animate, diff, @types/diff), `apps/web/components.json` (new file, shadcn
config + `@kibo-ui` registry), `apps/web/tailwind.config.js` (v3 color/radius token
mapping), `apps/web/styles/globals.css` (removed v4-only imports, fixed opacity
modifier). `docs/DEPENDENCIES.md` (marked installed).

**Not done in this slice, by the owner's own scoping choice.** JobSpy, agent-reach,
presidio, simhash-py, jsonresume — all still logged as pending in `DEPENDENCIES.md`
§3, not silently dropped. `@dnd-kit` (needed to make Kibo UI's Kanban actually
draggable, not just render) and `better-auth`/`openapi-typescript`/`vitest` from
§2.1 also still open. No actual page in the app uses any of the new components yet —
this slice is "the kit is installed and builds," not "the dashboard is redesigned."

**Next.** Wire the new components into `apps/web/app/facts/page.tsx` and the
application tracker (once it exists) — Kanban is the highest-value next UI piece
given F13's design already assumes a kanban board. `@dnd-kit` unblocks making it
interactive.

---

### 2026-08-16 (latest+5) — Langfuse Cloud connected, tracing live on the tailoring engine

**What changed.** Owner created a Langfuse Cloud account and shared real project API
keys. Installed `langfuse==4.14.4` (`requirements.txt`, ADR-014 item #2). Added
`Settings.langfuse_secret_key`/`langfuse_public_key`/`langfuse_base_url` (`core/config.py`,
all optional — same no-key-no-ops pattern as `voyage_api_key`/`reed_api_key`). Wired
`apps/api/tailoring/engine.py::_call_claude` with `@observe(as_type="generation")` and
`update_current_generation(input, output, model, usage_details)` — every Claude call
in the tailoring pipeline (both passes: tailor + truth-check) is now traced.

**Two real bugs found and fixed along the way, both by actually calling the code, not
by reading it:**
1. **Langfuse's client reads `LANGFUSE_HOST`, not `LANGFUSE_BASE_URL`** — the exact
   env var name conflicted between two different doc pages fetched during research
   (WebFetch, and separately WebSearch). Resolved by grepping the *installed* SDK's
   own source (`langfuse/_client/client.py`) rather than trusting either doc snippet —
   confirmed `os.environ.get(LANGFUSE_HOST, ...)`. `.env` keeps the friendlier
   `LANGFUSE_BASE_URL` name (matches what the Langfuse dashboard itself shows); the
   engine maps it to `LANGFUSE_HOST` when setting `os.environ`.
2. **`ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")` at module level was silently
   `None`** unless the real key happened to be exported in the ambient shell — nothing
   in this project loads `.env` into `os.environ` globally, and this line predates
   `core/config.py`'s `Settings`-based pattern. Sent a literal `x-api-key: None` header,
   crashing inside httpx's header encoder (`AttributeError: 'NoneType' object has no
   attribute 'encode'`) instead of ever reaching Anthropic — a worse failure mode than
   the 401 every other verification in this project has hit, and one that had gone
   unnoticed because manual sessions apparently had the key exported by hand. Fixed by
   reading `get_settings().anthropic_api_key` instead. Found while trying to verify
   Langfuse tracing actually worked — the fix isn't Langfuse-specific but the
   verification step is what surfaced it.

**A third, related issue in the eval harness from the prior slice.** Fixing #2 above
made `tailoring/engine.py` call `core.config.get_settings()` directly — which reintroduced
the CWD-relative-`.env` bug slice 4 had patched around narrowly (setting one env var
in the provider before import). Generalized the fix instead: `eval/providers/tailor_provider.py`
now does `os.chdir(API_DIR)` once, before importing `tailoring.engine` — correct for
every current and future `Settings()`-backed consumer, not just the one env var this
slice happened to need.

**Real verification, not simulated.** Called `tailor_application` for real — got the
correct `401 Unauthorized` (proving bug #2's fix; previously got the `AttributeError`
instead). Called `_langfuse.flush()`, then queried Langfuse Cloud's own REST API
(`GET /api/public/traces`, Basic auth) directly — confirmed 3 real `claude-call` traces
present with real timestamps, not just "no client-side exception was thrown."

**Security note.** The Langfuse secret/public keys were shared in-conversation, same
situation as every other credential this project — rotate from the Langfuse project
settings when convenient.

**Files changed.** `apps/api/.env` (3 new vars), `apps/api/core/config.py` (3 new
optional Settings fields), `apps/api/tailoring/engine.py` (Langfuse wiring +
`ANTHROPIC_API_KEY` fix), `apps/api/requirements.txt` (`langfuse==4.14.4`),
`eval/providers/tailor_provider.py` (narrow env-var fix generalized to `os.chdir`).
Full suite: 99/99 still green (no test touches `tailoring/engine.py` directly).

**Not done.** Docker-based Langfuse self-hosting was explicitly not pursued — Docker
remains unavailable on this machine (same standing reasoning as Postgres/Redis
earlier), and Langfuse Cloud's free tier is the direct hosted equivalent already used
for those. No dashboards/alerts built on top of the traces yet — this slice is
"traces exist and are real," not "traces are used for anything."

**Next.** Re-run the ADR-014 eval harness once a real `ANTHROPIC_API_KEY` exists — it
will now produce both real promptfoo pass/fail signal *and* a full Langfuse trace per
row, closing out ADR-014 items #1 and #2 together.

---

### 2026-08-16 (latest+4) — Phase 3 slice 4: ADR-014 eval harness built, mechanically verified live

**What changed.** `eval/promptfooconfig.yaml` + `eval/providers/tailor_provider.py`
(custom Python provider wrapping the real `apps/api/tailoring/engine.py::tailor_application`
— same code path the API uses, not a reimplementation) + `eval/assertions/truth_check.py`
(hard gate: fails any row whose tailoring produced `flagged_unsupported_claims`,
ADR-006's core invariant) + `eval/build_golden_set.py` generating `eval/golden.csv`
(30 JD/facts rows — meets `PRD.md` §11's Phase 3 exit criterion). Two facts profiles
(rich/senior, sparse/junior) crossed against 30 varied JDs; the sparse profile is
deliberately paired with senior/mismatched JDs on purpose — that's what actually
exercises the truth-checker, an eval set where every JD comfortably fits the candidate
never tests the one invariant this system can't silently get wrong.

**Config syntax verified against promptfoo's own docs (WebFetch), not guessed** —
provider `call_api(prompt, options, context)` contract, `llm-rubric` assertion syntax,
CSV `tests:`/`__expected` loading, and the `python` assertion contract were each
confirmed against `promptfoo.dev/docs` before writing the config, per the standing
"never guess APIs" rule.

**promptfoo pin bumped, with approval.** The installed `promptfoo@0.100.6`
(`eval/package.json`, from the 2026-08-15 dependency-install entry, which already
flagged "current is 0.122.0, worth bumping the pin") crashed on every eval run with a
reproducible internal `SqliteError: FOREIGN KEY constraint failed` — confirmed not
stale local state (same crash against a brand-new `PROMPTFOO_CONFIG_DIR`), a real bug
in that old build. Asked the owner before touching the pin (not a new dependency, but
a version change); approved. `^0.122.0` itself requires Node `>=22.22.0` (this machine
has 22.14.0) — checked `engines` across the version history (`npm view promptfoo@X
engines`) and pinned the exact last version before that requirement tightened:
`promptfoo@0.120.19` (`node: '>=20.0.0'`), which also does not have the SQLite bug.

**A real bug in the provider itself, caught by running it, not by reading it.**
`core.config.Settings`'s default `env_file=".env"` resolves relative to the process's
**working directory**, not the settings module's location — every other consumer in
this project runs with CWD=`apps/api/`, so this never surfaced before. promptfoo spawns
the Python provider from `eval/`, so `get_settings()` raised `ValidationError` (3
required fields missing) on every single row, at import time, before `call_api` could
even run its own try/except. This is what caused the first eval run to hang with zero
output for ~9 minutes rather than fail cleanly — a subprocess crashing at import,
repeated across 30 rows, produces very different (much worse) symptoms than a graceful
per-row error. Fixed by resolving `apps/api/.env`'s absolute path explicitly in
`tailor_provider.py` and passing it via `Settings(_env_file=...)`, instead of relying
on `get_settings()`'s CWD-relative default.

**Real verification, not simulated — with an honest negative result on the actual
quality question.** Ran `npx promptfoo eval` for real: all 30 rows correctly reached
the real `tailor_application` code path and got a real HTTP response from
`api.anthropic.com` — `[ERROR] Client error '401 Unauthorized'`, not a hang, not a
crash, not a silently-wrong pass. `Results: 0 passed, 0 failed, 30 errors (0%)`,
24s, concurrency 4. This proves the harness's mechanics (config → provider → real
engine → real Anthropic call → assertion → report) are correct end to end. It does
**not** prove anything about actual tailoring quality — `apps/api/.env`'s
`ANTHROPIC_API_KEY` is still `sk-ant-dev-placeholder` (same gap noted since the
2026-08-15 Phase 1 entry). A real key is what turns these 30 errors into real
pass/fail signal.

**Files created.** `eval/promptfooconfig.yaml`, `eval/providers/tailor_provider.py`,
`eval/assertions/truth_check.py`, `eval/build_golden_set.py`, `eval/golden.csv`.
**Files changed.** `eval/package.json` (promptfoo `^0.100.0` → `0.120.19`, pinned
exact given the Node-version ceiling), root `.gitignore` (`eval/.promptfoo-state/`,
`eval/results.json` — run artifacts, not fixtures).

**Not done in this slice.** Langfuse (ADR-014 item #2, persistence/run-history UI)
— still genuinely pending a decision, not silently skipped: it needs either
self-hosted Docker (unavailable on this machine, same reasoning Postgres/Redis
already worked around) or a Langfuse Cloud account, and unlike Neon/Redis Cloud/Reed/
Voyage this hasn't been raised with the owner yet. `garak` (item #3, injection
red-team) is already CI-only per the 2026-08-15 entry, separate from this slice.
`scikit-learn` weight recalibration (item #4) needs real outcome data
(`match_weight_history`) that doesn't exist yet — not a Phase 3 blocker.

**Next.** A real `ANTHROPIC_API_KEY` is the single thing blocking this harness from
producing real signal — same conclusion as Phase 1's tailoring-engine entry, now true
for eval too. Langfuse needs an explicit ask (Docker vs. cloud account) before
building further on ADR-014.

---

### 2026-08-16 (latest+3) — PM/Marketing terms added to the skill vocabulary

**What changed.** Owner explicitly asked for PM and Marketing skill terms, overriding
the "developer-only, PM/Marketing gated" ponytail note from the slice below (their
call to make, not mine to withhold on a hedge). Added 16 PM terms (Agile, Scrum,
Kanban, Roadmapping, A/B Testing, Stakeholder Management, JIRA, Product Strategy, User
Research, OKRs, Product Analytics, Figma, Wireframing, Go-to-Market, Competitive
Analysis, Prioritization) and 16 Marketing terms (SEO, SEM, Content Marketing, Email
Marketing, Google Analytics, HubSpot, Paid Social, Copywriting, Brand Strategy, CRM,
Salesforce, Marketo, Growth Marketing, Social Media Marketing, PPC, Marketing
Automation) to `matching/skills.py::_SKILLS`. Removed the now-inaccurate "developer
only" ponytail comment.

**Tests.** Two new tests in `tests/test_skills.py`. One test bug caught by red-before-
green itself: the PM test's fixture text said "own the roadmap" but the vocabulary
term is "Roadmapping" — the word-boundary matcher correctly didn't match a different
word, exposing the test's own mistake, not an implementation bug. Fixed the fixture
text, not the matcher. Full suite: 99/99 green.

**Real verification.** Ran `upsert_jobs` against live Neon with a PM/marketing-flavored
description — got back `['A/B Testing', 'Agile', 'HubSpot', 'Roadmapping', 'SEO']`.
Test row cleaned up afterward.

---

### 2026-08-16 (latest+2) — Phase 3 slice 3: Job.skills extraction

**What changed.** `matching/skills.py::extract_skills(text)` — keyword phrase-matching
against a curated developer/tech vocabulary (~55 terms: languages, frameworks,
datastores, infra/cloud, general tooling), word-boundary regex per term (handles
special-char terms like `C++`, `CI/CD`, `Node.js`, and correctly does not match
`Java` inside `JavaScript`). Wired into `connectors/pipeline.py::upsert_jobs` —
`Job.skills` (existed since Phase 3 slice 1's scaffolding, always `[]` until now) is
now actually populated from `title + description` at ingestion.

**Repo research before writing code, per the standing instruction.** Read
`KonstantinosPetrakis/esco-skill-extractor` (MIT, already recorded in
`DEPENDENCIES.md` §3 as "study only, not adopted") end to end via its README/API
(`gh api`, not cloned). It matches job text against the full ESCO taxonomy (~13k
skills) using `sentence-transformers` embeddings, returning ESCO URIs (e.g.
`http://data.europa.eu/esco/skill/19a8293b-...`), not human-readable names — a job
needing a URI→label lookup, plus a new `sentence-transformers`/torch dependency this
project already declined once for the same reason (garak, 2026-08-15 entry: "pulls in
torch, multi-GB, for API-only usage"). We already pay for real semantic
understanding via Voyage embeddings (Phase 3 slice 1); this file is deliberately the
cheap, explicit, explainable *other* half `SPEC.md`'s `matched_skills`/`missing_skills`
need (human-readable strings shown verbatim in the UI, not IDs). Confirms the
DEPENDENCIES.md call: studied, reimplemented, not depended on.

**Ponytail, marked.** Vocabulary is developer/tech-only — matches `PRD.md`'s "v1 ships
Developer only" (PM/Marketing personas are explicitly gated on Developer proving out
first). Fixed vocabulary bounds recall to this list, not any job's real skill set;
upgrade path is a bigger list or an LLM extraction pass later, not a design change to
this file.

**Real verification, not simulated.** Ran `upsert_jobs` against live Neon with a real
job description mentioning Python/PostgreSQL/Docker/AWS/React — got back
`['AWS', 'Docker', 'PostgreSQL', 'Python', 'React']`, sorted, deduped, case-normalized
to canonical form. Test row cleaned up afterward.

**Tests.** `tests/test_skills.py` (7 tests, red-before-green, including the
Java-vs-JavaScript substring-boundary case), plus one new pipeline wiring test. Full
suite: 97/97 green.

**Next.** With skills now populated, `matching/scoring.py`'s `skill_coverage` term
actually discriminates between jobs for the first time — previously every job read as
full coverage (empty `job_skills`). Eval harness (ADR-014) remains Phase 3's other
open exit-criterion item; agent-reach dossiers not started.

---

### 2026-08-16 (latest+1) — Phase 3 slice 2: hard filters (visa/location/seniority)

**What changed.** `matching/filters.py` — `infer_seniority(title)` (keyword regex:
intern/junior/lead/staff/senior), `blocks_visa_sponsorship(description)` (keyword
heuristic for "no sponsorship"/"without sponsorship"/"U.S. citizens only" language),
and `passes_hard_filters(prefs, job)` combining location/remote, seniority, and visa
checks. Wired into `connectors/pipeline.py::upsert_jobs` (seniority inferred from title
at ingestion) and `matching/service.py::build_matches` (jobs filtered against
`profile.prefs` before scoring, not after — PRD.md's "hard filters, free" ordering).

**Real gap found before writing any code.** `PRD.md`/`SPEC.md`'s aspirational schema
has `jobs.seniority` and a work-authorization field; the actual `models.py` never had
either, and no connector (Remotive/Greenhouse/Lever/Ashby/Reed) exposes visa
sponsorship or a structured seniority level. Rather than block on real signals that
don't exist yet, built the closest honest substitute: seniority inferred from the job
title text, visa via a description-text keyword heuristic. Marked with a `ponytail:`
comment naming the ceiling (false negatives when phrasing doesn't match; no real
signal at all for visa) and the upgrade path (a real field once a connector or LLM
extraction pass provides one).

**Design choice: missing data never excludes a job.** If `job.seniority` or
`job.location` is null (unknown), the filter passes it through rather than hiding it —
a false "no match" from a data gap is worse than an imperfect filter letting one
through. Also fixed: without this, remote jobs with an unhelpful `location` string
would fail a location filter even when the user's `remote_types` preference should
have matched them — handled by checking `job.remote` first, before falling back to
location-text matching.

**Schema.** `alembic/versions/0005_job_seniority.py` — new nullable `jobs.seniority`
column. **Run for real against live Neon**, confirmed `0004 -> 0005` applied.

**Real verification, not simulated.** Ingested two real jobs via `upsert_jobs` against
live Neon ("Senior Backend Engineer", "Junior Backend Engineer") — `seniority` came
back `senior`/`junior` correctly from the title inference. Set a profile's
`prefs.seniority = ["senior"]`, ran `build_matches` — got back exactly the senior role,
junior correctly excluded. Test rows cleaned up afterward.

**Tests.** `tests/test_filters.py` (15 tests, red-before-green), plus one new pipeline
test (seniority inference wired into ingestion) and one new matching-service test
(hard-filter exclusion). Full suite: 89/89 green.

**Not done in this slice.** No structured `Profile.prefs` schema/validation — still a
freeform JSON dict, same as before this slice (`ProfileCreate.prefs: dict = {}`); the
filter functions read `prefs.get(...)` defensively. Salary filtering (`PRD.md` also
lists it under hard filters) — not built, `Job` has no structured salary field either
(only a free-text `salary` string), same reasoning as seniority/visa: no real signal
without further parsing work.

**Next.** Job skill extraction (`Job.skills` still unpopulated) is the other concrete
F6 gap. Eval harness (ADR-014) remains Phase 3's other open exit-criterion item.

---

### 2026-08-16 (latest) — Phase 3 slice 1: Voyage embeddings + matching, live end-to-end

**What changed.** Owner shared a real Voyage AI API key, wired into `apps/api/.env`
as `VOYAGE_API_KEY`. Built the embedding pipeline and F6 matching on top of scaffolding
already present in the repo but undocumented (see "Found pre-existing, undocumented"
below): `matching/embeddings.py` (`embed_texts`, `compute_centroid`,
`cosine_similarity`), wired into `connectors/pipeline.py::upsert_jobs` (jobs get an
embedding on ingestion) and `main.py::confirm_facts_bulk` (resume facts get an
embedding, `Profile.fact_centroid` recomputed from all of a profile's fact embeddings).
New `matching/service.py::build_matches` scores every embedded job against a profile's
centroid via `matching.scoring.compute_match_score` (already existed) and upserts into
`matches`. New `GET /matches` endpoint.

**Found pre-existing, undocumented, from a prior interrupted session.** Before this
slice started, the repo already had: `models.py` (`Vector(512)` columns on
`Profile.fact_centroid`, `Job.embedding`, `ResumeFact.embedding`, `Match` table),
`alembic/versions/0004_matching.py` (already applied — `alembic current` showed head
`0004` before any work this session), `matching/scoring.py` (the score formula) with
`tests/test_scoring.py` passing, `core/config.py`'s `voyage_api_key` field, and
`pgvector`/`voyageai` in `requirements.txt`. None of this was in `WORKLOG.md`. Confirmed
none of it was speculative/stub — the migration was live, the scoring tests passed —
so built on top of it rather than redoing it. `EMBEDDING_DIM = 512` (voyage-3-lite)
diverges from `SPEC.md`'s `vector(1536)` — the code's choice is correct (smaller/cheaper
model, matches what's actually configured), `SPEC.md` is now the stale one; not fixed
in this pass, flagging so a doc-sync pass catches it.

**A real bug, only reproducible against real Postgres, not SQLite.** `matching/service.py`
crashed on `json.dumps`-ing the `breakdown` column: pgvector returns `numpy.float32`
arrays when reading a real Postgres connection, but the SQLite unit-test engine
round-trips plain Python lists, so `list(job.embedding)` still held numpy scalars and
none of the mocked tests caught it. First live run left orphan rows in the real Neon
`users`/`profiles`/`jobs` tables (crashed before its own cleanup ran) — cleaned up
separately, confirmed zero `phase3test-%` rows remain. Fixed by casting to
`[float(x) for x in ...]` at the point numpy enters the pipeline, plus a regression
test (`test_build_matches_breakdown_is_json_serializable_with_numpy_input`) that fakes
the numpy shape directly, since the SQLite suite can't otherwise catch this class of bug.

**Real verification, not simulated.** Confirmed the Voyage key live before building
anything (`voyageai.Client(...).embed(["hello world"], model="voyage-3-lite")` → 512
dims, matches `EMBEDDING_DIM`). Full flow run against real Neon + real Voyage: created
a profile, added a resume fact, embedded it, computed `fact_centroid`, created a job,
embedded it, called `build_matches` — got back a real score (`70.36`,
`semantic: 0.7338`, `matched_skills: ["python"]`) with a JSON-serializable breakdown.
Test rows cleaned up afterward.

**Ponytail simplification, marked.** `matching/service.py` scores every job with a
non-null embedding in-process (Python `cosine_similarity`, O(n) scan) rather than an
`ORDER BY embedding <=> centroid` pgvector query — the ivfflat index from migration
0004 already exists for when this matters. Fine at MVP job volume (currently ~150
jobs); switch to the SQL-side query when an in-process scan becomes the bottleneck.

**Not done in this slice.** Hard filters (visa/location/seniority) ahead of scoring —
`build_matches` currently scores every embedded job, no filtering yet (`PRD.md` F6 calls
for hard filters + semantic score; only the semantic half is wired). `Job.skills` is
still never populated by any connector (stays `[]`), so `skill_coverage` always reads as
full coverage (1.0) in practice — `compute_match_score` already handles empty
`job_skills` correctly, this just means the skill term isn't discriminating between jobs
yet. No skill/keyword extraction was built to populate it — same reasoning as not
building unverifiable connector code: skipped rather than stubbed. Eval harness
(ADR-014, Promptfoo + golden set) — Phase 3 scope per `PRD.md`, not started.
Agent-reach dossiers — not started.

**Security note.** The Voyage API key was shared in-conversation, same situation as
the Reed key, GitHub PAT, Neon string, and Redis Cloud string earlier this project —
rotate from the Voyage dashboard when convenient.

**Full suite: 72/72 green.**

**Next.** Hard filters ahead of `build_matches`' scoring loop close the F6 gap fastest.
Job skill extraction (even a cheap keyword-list pass, not necessarily LLM) would make
`skill_coverage` actually discriminate. Eval harness (ADR-014) is the other concrete
Phase 3 exit-criterion item per `PRD.md` §11.

---

### 2026-08-16 (later+3) — Phase 2 slice 4: rq-scheduler + Reed connector, both live

**What changed.** Two more pieces, both verified against real infrastructure.

**rq-scheduler.** `rq-scheduler==0.13.1` (the version originally pinned in
`DEPENDENCIES.md` §1.3) is incompatible with `rq==2.0.0` — `ImportError: cannot import
name 'resolve_connection' from 'rq.connections'`, an API removed between rq versions.
Upgraded to `rq-scheduler==0.14.0`. `workers/run_scheduler.py` schedules
`discover_jobs_task` on a 4h interval (`ARCHITECTURE.md` §4.1). **Verified live**:
called `start_scheduler()` against real Redis Cloud, confirmed exactly one job
registered for `workers.jobs.discover_jobs_task`, then cancelled it — didn't leave a
real recurring job running unattended against production infrastructure while nobody's
watching it.

**Reed connector.** Owner provided a real Reed API key. `connectors/reed.py` — HTTP
Basic auth (key as username, empty password), maps Reed's response shape to our
`NormalizedJob`-equivalent dict. Verified the raw API with `curl` first (real UK
listings came back) before writing any mapping code, then wrote 3 mocked unit tests
(no-key no-op, response normalization, remote-location detection), then verified the
actual Python function live: `discover_jobs_task()` called for real —
`{'fetched': 148, 'inserted': 107, 'skipped_duplicates': 41}`, up from 48/16/32 with
just Remotive. Test jobs cleaned from Postgres afterward. **5 connectors now live**:
remotive, greenhouse, lever, ashby, reed.

**Adzuna and The Muse — explicitly not built.** Owner reported Adzuna's signup didn't
yield a working key ("adzuna is old so no api") and Muse had nothing available. No stub
code written for either — same reasoning as every other unavailable-credential case
this session: unverifiable connector code isn't shipped.

**Files created.** `workers/run_scheduler.py`, `connectors/reed.py`, `tests/test_reed.py`
(3 tests, green).

**Files changed.** `core/config.py` (`reed_api_key`, optional), `connectors/config.py`
(`REED_KEYWORDS`), `workers/jobs.py` (wired Reed into `discover_jobs_task`),
`requirements.txt` (`rq-scheduler` 0.13.1 → 0.14.0), `.env` (real Reed key — gitignored,
not committed).

**Security note.** The Reed API key was shared in-conversation, same situation as the
GitHub PAT, Neon string, and Redis Cloud string — rotate from the Reed developer
dashboard when convenient.

**Full suite: 50/50 green.**

**Next.** Phase 2's core infrastructure (dedupe, discovery, RQ/Redis, scheduler) and
5 real connectors are done and live-verified. What's left is entirely bounded by
external input: more connector API keys if wanted, or move on to Phase 3
(match & research — pgvector matching, agent-reach dossiers) per `PRD.md` §11.

---

### 2026-08-16 (later+2) — Phase 2 slice 3: RQ/Redis wiring, B6 fixed and proven live

**What changed.** Owner provided a real Redis Cloud connection string (free tier, 30MB,
confirmed no-card-required). Wired into `.env`. Built the RQ job wrapper and moved
`/discover/run` off the request thread — fixes `CODE-REVIEW.md` B6.

**Files created.** `workers/jobs.py` (`discover_jobs_task`, `get_queue`,
`get_redis_connection`), `workers/run_worker.py` (worker entrypoint — see bugs below
for why this exists instead of the bare `rq worker` CLI).

**Files changed.** `main.py`'s `/discover/run` now enqueues instead of running inline;
added `GET /discover/run/{task_id}` to poll status. Removed now-unused direct connector
imports from `main.py` (moved into `workers/jobs.py`).

**Two real, platform-specific bugs found — both would have silently broken any
Windows-hosted worker, neither is visible from reading the code:**

1. **RQ's default `Worker` calls `os.fork()`** to run jobs in an isolated child process
   — `AttributeError: module 'os' has no attribute 'fork'`, fork is POSIX-only. Fixed
   by using `rq.worker.SimpleWorker` instead (no forking).
2. **RQ's job-timeout enforcement uses `signal.SIGALRM`** — also POSIX-only,
   `AttributeError: module 'signal' has no attribute 'SIGALRM'`. This crashes even
   `SimpleWorker` by default. Fixed with `rq.timeouts.TimerDeathPenalty` (uses
   `threading.Timer` instead), wired via a small subclass in `workers/run_worker.py`
   since the CLI (`rq worker --worker-class ...`) has no flag for death-penalty class.

**A third bug — not RQ's fault, mine:** the first "it's failing" turned out to be three
*stale* `rq worker` CLI processes from earlier debugging attempts that my kill command's
pattern match missed (`"*rq worker*"` didn't match `rq.exe worker`). One of them raced
the fixed worker for the job, grabbed it, and crashed silently on the SIGALRM bug —
while I was only watching the new worker's log file. Found by listing every process
with `run_worker` or `rq.exe` in its command line and killing by exact PID.

**Real verification — genuinely live, not simulated, three attempts to get there.**
Started the API and a real RQ worker against Redis Cloud. `POST /discover/run` →
`{"task_id": ..., "status": "queued"}` → worker log shows the job picked up, executed,
and completed in ~8s → `GET /discover/run/{task_id}` → `{"status": "finished", "result":
{"fetched": 48, "inserted": 16, "skipped_duplicates": 32}}` — **identical numbers** to
the direct-call test from slice 1, confirming correctness held through the full
async/queue/worker path, not just the synchronous one. Test data cleaned up, both
processes stopped afterward.

**Security note.** The Redis Cloud connection string was shared in-conversation, same
situation as the GitHub PAT and Neon string earlier — consider rotating the password
from the Redis Cloud dashboard.

**Not done yet.** `rq-scheduler` (periodic/cron discovery runs) — the dependency is
installed but not wired to an actual schedule. Remaining ~8 connectors still need API
keys not available.

---

### 2026-08-16 (later+1) — Phase 2 slice 2: ATS discovery (F5)

**What changed.** `connectors/discovery.py` — `is_safe_url` (SSRF guard,
ARCHITECTURE.md §6) + `detect_ats` (SPEC.md §3.4: try known career-page paths, regex
against 5 known ATS URL patterns, return `(ats_type, token)`). `tests/test_discovery.py`
— 12 tests, all green, red-before-green. Full suite: 47/47.

**Real verification, with an honest negative result.** `is_safe_url` tested live
against `stripe.com` (True) and `localhost` (False) — SSRF guard works correctly on
real hostnames, not just mocked ones. `detect_ats` tried against 3 real companies
(stripe.com, ashbyhq.com, ramp.com) — **all returned `None`.** This is a genuine,
consistent finding, not a bug: the unit tests prove the pattern-matching logic itself
is correct (12/12 green against mocked HTML), but modern career pages are mostly
JS-rendered SPAs, so a static HTML fetch with no JS execution won't see the board link
even when it's really there. This matches `SPEC.md` §3.4's own documented design (regex
over fetched HTML, explicitly not a headless browser — that's ruled out by ADR-002).
**Real-world hit rate for this approach is likely to be genuinely low against modern
sites** — worth flagging as a real limitation for whoever builds Phase 2's next slice
or reconsiders F5's approach, not something to discover by surprise later.

**Not done yet.** RQ/Redis wiring (B6) — still blocked on a Redis Cloud connection
string. Remaining connectors — same reasoning as slice 1, most need API keys not
available.

**Session note.** This entry was written in the *same* conversation as Phase 0/1 and
Phase 2 slice 1, despite two attempts to hand off to a fresh session — both "start
Phase 2" messages landed back in this conversation rather than a new one. If cost is a
concern, actually opening a new chat window (not just saying "start Phase 2" again in
this one) is what gets the savings.

---

### 2026-08-16 (later) — Phase 2 slice 1: dedupe fix, N+1 fix, verified live

**What changed.** First slice of Phase 2 (ATS discovery, connectors, dedupe,
background workers). This slice: the dedupe/query bugs from `CODE-REVIEW.md`
(H1 N+1 query, H3 narrow dedupe key). Approved and installed dependency group
`DEPENDENCIES.md` §1.3 (`rq`, `rq-scheduler`, `redis`, `tenacity`, `feedparser`,
`selectolax`) — not yet wired to a running Redis (Redis Cloud connection string
pending from the owner; decision already made and logged not to use Docker or
Upstash).

**Files created.** `connectors/normalize.py` (`canonical_hash`, `normalize_location`,
`SPEC.md` §3.1's algorithm), `connectors/pipeline.py` (`upsert_jobs` — 2 queries total
regardless of batch size, replacing the old 1-query-per-job loop). `tests/test_normalize.py`,
`tests/test_pipeline.py` — 12 new tests, all green, red-before-green throughout. One
test explicitly asserts query count stays flat as batch size grows (proves H1 is fixed,
not just "looks faster").

**Files changed.** `models.py` — `Job` gained `canonical_hash` (unique) and
`last_seen_at`. `main.py`'s `/discover/run` rewritten to use the new pipeline.
`alembic/versions/0003_job_canonical_hash.py` — **run for real against live Neon**
(confirmed `jobs` table had 0 rows first, so no backfill needed).

**Real verification, not simulated.** Booted the API, signed up, ran `/discover/run`
against the **live Remotive API** into **live Postgres**: `fetched: 48, inserted: 16,
skipped_duplicates: 32` — the 3 overlapping keyword searches (`REMOTIVE_KEYWORDS`)
genuinely collapsed to unique roles via `canonical_hash`, not just theoretically. Ran it
a second time: `inserted: 0, skipped_duplicates: 48` — proves idempotency, a second run
doesn't duplicate. Test jobs/users cleaned up afterward.

**Not done in this slice — deliberately, next up.**
- ATS discovery subsystem (F5) — the board-token sniffer for unknown company domains.
- RQ/Redis wiring (B6: move `/discover/run` off the request thread) — blocked on the
  Redis Cloud connection string, not on any code decision.
- Only 4 connectors exist (remotive/greenhouse/lever/ashby). The other ~8 from
  `PRD.md` Tier 2 (Adzuna, Reed, The Muse, Jooble, ZipRecruiter, Workday,
  SmartRecruiters...) mostly need API keys not yet available — building them now would
  produce unverifiable stub code, same reasoning as not building all 12 blind.

**Next.** Redis Cloud connection string unblocks RQ wiring + moving discovery off the
request thread. ATS discovery (F5) doesn't need Redis and could go first if preferred.

---

### 2026-08-16 — Phase 1 frontend: fact-review screen, Next.js App Router migration begun

**What changed.** Built the frontend half of Phase 1 — PRD.md calls the fact-review
screen "the product," and it didn't exist. Started the ADR-004 App Router+TypeScript
migration (old `pages/` router stays, coexists — not a rewrite). Approved dependency
group: `typescript`, `@types/react`/`node`/`react-dom`, `@tanstack/react-query`, `zod`
(minimal set — shadcn/Better Auth deferred, layering them in later needs no rework).

**Files created.** `apps/web/tsconfig.json`, `apps/web/lib/auth.ts` (token storage),
`apps/web/lib/api.ts` (typed client), `apps/web/app/{layout,providers}.tsx`,
`apps/web/app/login/page.tsx`, `apps/web/app/facts/page.tsx` (upload → review
→ edit/remove drafts → confirm → see persisted facts).

**Files changed.** `apps/web/lib/api.js` → renamed `legacy-api.js`, `pages/index.js`
import updated — see bug #1 below. `apps/web/package.json` — `next`/`react`/`react-dom`
bumped to 15/19/19 (see below).

**Four real bugs found, all by actually running the thing, not by reading code:**

1. **`next@14.2.5` had a real critical+high CVE.** `npm install` surfaced it
   unprompted. `ARCHITECTURE.md` §2 already specified Next.js 15 as the target, so
   upgraded now rather than migrating onto a known-vulnerable version. Separately,
   `npm audit` still flags 3 high-severity issues (postcss sourcemap/XSS, sharp/libvips)
   whose fix needs Next 16 — a bigger jump than this session's scope; not forced through
   silently, logged here for a future call.
2. **`typescript@^7.0.2` actually installed** — the new native Go-based TS compiler,
   incompatible with Next.js's config loader (`next build` failed with a cryptic
   `fileExists` TypeError). Pinned to stable `typescript@5.6.3`.
3. **`lib/api.js` (old) and `lib/api.ts` (new) coexisting broke the build** — the
   bundler silently resolved `@/lib/api` to the stale untyped file instead of the new
   one, so `ApiError` appeared "not exported" even though it clearly was. Renamed the
   old file to `legacy-api.js` to remove the ambiguity; `pages/index.js` updated to
   match.
4. **CORS + a header-precedence bug, found only in the browser, not in curl/pytest.**
   Running the frontend on port 3001 tripped the backend's CORS allowlist (only
   `localhost:3000` is permitted) — switched the dev server to port 3000. Separately,
   `lib/api.ts`'s `request()` wrapper unconditionally set `Content-Type: application/json`
   *after* spreading caller-provided headers, silently clobbering `login`'s intentional
   `application/x-www-form-urlencoded` header — every login attempt 422'd. Fixed by
   building the default header first and letting caller headers override it, not the
   reverse. Neither of these surfaced in any Python test — only visible by actually
   loading the page and trying to log in.

**A fifth, smaller bug fixed proactively:** FastAPI's `detail` field is a string for
`HTTPException`s but a *list* of `{loc, msg, type}` objects for 422 Pydantic validation
errors — rendering it directly produced `"[object Object],[object Object]"` on screen.
Added `formatErrorDetail()` to handle both shapes.

**Verification — real browser, real backend, real database, not simulated:**
Started both dev servers, drove the actual UI via Playwright: navigated to `/login`,
signed up, hit the header-precedence bug (fixed it), logged back in, landed on `/facts`,
confirmed the profile auto-created, uploaded a real `.docx` built with `python-docx`
through the actual file picker. The app extracted its text for real, made a real network
call to Anthropic, got a real `401` (placeholder key), and rendered the error message
clearly and readably — proving the whole pipeline (upload → parse → LLM call → error
handling → UI rendering) works end to end, under real failure conditions, in an actual
browser. Test users and the fixture file cleaned up afterward; confirmed zero
`%@example.com` rows remain in the live Neon database.

**Not done in this pass.** No shadcn/design-system polish (plain inline styles — this
proves the mechanism works, not final visual design). No Better Auth — JWT in
`localStorage` is a pragmatic placeholder, fine for dev, not for production (XSS
exposure — revisit before any real deployment). No signup email verification. Real LLM
extraction quality still unverified — needs a real `ANTHROPIC_API_KEY`.

**Next.** A real Anthropic key is now the single biggest thing blocking end-to-end
validation of the actual product value (does parsing produce good facts?), not
infrastructure. Everything infrastructure-shaped in Phase 1 is done and proven.

---

### 2026-08-15 (latest+2) — Phase 1 implementation: resume upload, parsing, facts KB

**What changed.** PRD.md Phase 1 exit criterion: "User can go from PDF to reviewed KB
in under 5 min." Built the full pipeline: `POST /profiles/{id}/resume` (upload) →
text extraction (pdfplumber/python-docx) → LLM structured extraction (Anthropic) →
draft facts returned → `POST /profiles/{id}/facts:bulk` (explicit user confirmation,
ADR-009: parsed output is never silently trusted). Approved dependency group
`DEPENDENCIES.md` §1.2 (`pdfplumber`, `python-docx`, `anthropic`) before installing.

**Files created.**
- `apps/api/parsing/extract.py` — `extract_text_from_pdf`, `extract_text_from_docx`.
- `apps/api/parsing/llm_extract.py` — `extract_facts_from_text`. Deliberately does NOT
  repeat `tailoring/engine.py`'s known bug (B5): JSON parsing is wrapped, malformed
  model output raises a clear `ValueError`, not an unhandled `JSONDecodeError`.
- `apps/api/alembic/versions/0002_resume_uploads.py` — new table, **run for real against
  the live Neon Postgres**, verified via schema inspection afterward.
- `apps/api/tests/test_extract.py`, `test_llm_extract.py`, `test_resume_upload.py`,
  `test_profiles.py` — 15 new tests, all green.

**Files changed.**
- `apps/api/models.py` — added `ResumeUpload` (tracks one parsing run; the raw file
  itself is never persisted, only draft facts, per ADR-009).
- `apps/api/schemas.py` — added `FactDraft`, `ResumeUploadOut`, `FactsBulkIn`.
- `apps/api/main.py` — added `POST/GET /profiles`, `POST /profiles/{id}/resume`,
  `GET /profiles/{id}/resume/{upload_id}`, `POST /profiles/{id}/facts:bulk`.

**Gap found and fixed mid-implementation.** There was no `POST /profiles` endpoint at
all — Phase 0 only built the tenancy *guard* for existing profiles, never profile
*creation*. Caught while trying to test the upload flow end-to-end over real HTTP (no
way to get a profile_id to test against). Added it; it's small, but genuinely
necessary, not scope creep — nothing in Phase 1 works without it.

**Real bug caught by testing, not just written.** The resume-upload integration test's
SQLite fixture initially failed with `no such table: users` — `sqlite:///:memory:`
gives each new connection its own fresh empty database by default, and the app's `get_db`
override was opening a new connection per request. Fixed with `StaticPool` so all
connections in a test share one in-memory database. Would not have been caught by
reading the code; only running it surfaced it.

**Verification beyond mocked tests.** Ran the full flow against the **live Neon
database**, not just SQLite: real signup → login → `POST /profiles` → uploaded a real
`.docx` built with `python-docx` → the app correctly extracted its text (no mocking —
real `pdfplumber`/`python-docx` parsing) → made a real network call to Anthropic's API
→ got a real `401 authentication_error` (the `.env` key is still a placeholder) → the
endpoint caught it and returned `status: "failed"` with a clear error message instead of
crashing. This proves the parsing pipeline and the error-handling path both work under
real conditions, not just mocked ones. Test data cleaned up afterward.

**Tests.** 23/23 green project-wide. Red-before-green on every new function
(`extract_text_from_pdf/docx`, `extract_facts_from_text`) — confirmed
`ModuleNotFoundError` before each implementation.

**Not done in this pass.**
- No real end-to-end LLM extraction test — blocked on a real `ANTHROPIC_API_KEY`
  (placeholder in `.env`). Unit tests mock the Anthropic client; the real network path
  was proven to fail gracefully (see above), not proven to succeed. Confirm this once a
  real key is available.
- No fact-review frontend UI — Phase 1 scope here was the API; `apps/web` untouched.
- No file storage (S3/R2) — deliberately unnecessary per ADR-009 (raw resume blob is
  never the generation source), so Phase 1 never needed it.

**Next.** A real `ANTHROPIC_API_KEY` unblocks testing the actual extraction quality.
Frontend fact-review screen (PRD.md J1 step 4 — "this screen is the product") is the
other missing piece before Phase 1 is user-usable end to end.

---

### 2026-08-15 (latest+1) — Docker abandoned in favor of Neon; Phase 0 verified against real Postgres

**What changed.** Owner approved Docker Desktop; the winget install got stuck at a UAC
elevation prompt (this tool runs non-interactively, can't click through GUI dialogs).
Rather than push through that, reconsidered the choice: ADR-013 already picked Neon for
Postgres hosting, and Redis (the other reason for Docker) isn't needed until Phase 2.
Owner agreed — killed the stuck installer processes, created a free Neon project instead.

**What was actually verified, against a real database, not SQLite:**
- `alembic upgrade head` run against the live Neon connection — all 5 tables +
  `alembic_version` created correctly, matching `models.py` exactly.
- Full app boot (`uvicorn main:app`) against real Postgres — `/health` responded.
- Real end-to-end flow exercised over HTTP: `POST /auth/signup` → `POST /auth/login`
  (real JWT issued) → `GET /auth/me` (token verified round-trip) →
  `POST /resume-facts?profile_id=<nonexistent>` correctly returned `404 Profile not
  found` — the tenancy guard rejecting a request against a real database, not a mock.
- Test user deleted afterward to keep the dev database clean.

**Bug found and fixed while re-running the suite.** `test_decode_rejects_tampered_token`
failed on this run after passing earlier — not flaky by chance, a real test-construction
bug: it flipped the *literal last character* of the JWT to simulate tampering, but
base64url's final encoding group has redundant padding bits, so flipping that specific
character doesn't always change the decoded signature bytes. Fixed by flipping a
character in the middle of the token instead, which reliably changes the payload.
Re-ran 5x to confirm it's deterministic now, not just lucky.

**Files changed.** `apps/api/.env` (real `DATABASE_URL`, gitignored, not committed) —
`REDIS_URL` still points at localhost as a placeholder, unused until Phase 2.
`apps/api/tests/test_security.py` (tampering test fixed).

**Next.** Docker Desktop is fully off the table for now — revisit only when Phase 2
(RQ/Redis) actually needs it, and even then, a hosted Redis alternative should get the
same honest reconsideration Postgres just got, not an automatic default to Docker.

---

### 2026-08-15 (latest) — Phase 0 implementation: auth, tenancy, migrations

**What changed.** First real feature code in the project. Implemented the fix order
from `docs/CODE-REVIEW.md` (B2, B3, B1) and the Phase 0 exit criterion from
`docs/PRD.md` §11: "every endpoint scoped to a user." Followed red-before-green
throughout — every new function had a failing test before it was implemented.

**Files created.**
- `apps/api/core/config.py` — `Settings` (pydantic-settings), validated at boot. Fixes H5.
- `apps/api/core/security.py` — argon2 password hashing, JWT create/decode.
- `apps/api/core/deps.py` — `get_current_user`, `get_owned_profile` (Depends-shaped),
  `resolve_profile_ownership` (plain function for body-based `profile_id`). The single
  tenancy enforcement point per `ARCHITECTURE.md` §5.
- `apps/api/auth/router.py` — `/auth/signup`, `/auth/login`, `/auth/me`.
- `apps/api/alembic/` — initialized, `env.py` wired to `Settings.database_url` and
  `models.Base.metadata`. `versions/0001_baseline.py` hand-written (no live Postgres to
  autogenerate against — Docker still pending approval) covering `users`, `profiles`,
  `jobs`, `applications`, `resume_facts`. **Verified by actually running
  `alembic upgrade head` against a throwaway SQLite file** — real functional validation,
  not just a syntax check. Re-run `--autogenerate` against real Postgres once available
  and diff against this file.
- `apps/api/tests/conftest.py`, `test_security.py`, `test_tenancy.py` — 8 tests, all
  green. `db_session` fixture uses in-memory SQLite (fast, no Postgres needed for
  ORM-level logic); full Postgres integration suite (pgvector, JSONB semantics) is
  still blocked on Docker.
- `apps/api/.env` (gitignored, dev placeholder values).

**Files changed.**
- `apps/api/database.py` — `DATABASE_URL` now comes from `Settings`, not `os.getenv`
  directly. Added `session_scope()` context manager; documented why
  `next(get_db())` (the old startup-seeding pattern, B3) leaks the connection.
- `apps/api/models.py` — added `User`, `Profile`, `Persona` enum. `ResumeFact` and
  `Application` now have `profile_id` FKs (were global/un-tenanted — B1).
  `Job` unchanged; full ATS-discovery schema is Phase 2 scope, not Phase 0.
- `apps/api/schemas.py` — added `UserCreate`/`UserOut`/`Token`/`ProfileCreate`/`ProfileOut`;
  `Application`/`ResumeFact` schemas gained `profile_id`.
- `apps/api/main.py` — every route now requires auth; `/applications`, `/resume-facts`,
  `/tailor` resolve their profile through the tenancy dependency, never a raw ID.
  `Base.metadata.create_all()` removed now that Alembic owns the schema (B2 closed).
  CORS origins now come from `Settings`.
- `.env.example` — added `JWT_SECRET`.
- `apps/api/requirements.txt` — added `email-validator`, `python-multipart` (both real
  missing sub-dependencies caught by actually running the app, not assumed).

**Bug caught before it shipped.** First draft of `main.py` called `get_owned_profile`
directly (as a plain function) for body-based `profile_id` fields — that dependency is
shaped for FastAPI's `Depends()` resolution, so calling it directly would have passed
the unresolved `Depends()` sentinel as `current_user` instead of a real user, silently
breaking tenancy on `create_application` and `tailor`. Caught by actually importing and
exercising the app, not just reading the code. Fixed by splitting `resolve_profile_ownership`
(plain function) out from `get_owned_profile` (the `Depends()`-shaped wrapper for
path/query-param routes).

**Tests.** 8/8 green: password hashing round-trips, JWT round-trips and rejects
tampering, tenancy dependency lets an owner through and 404s a different user
(both the intruder case and the nonexistent-profile case). Confirmed red before each
green — `ModuleNotFoundError` for `core.security` and `core.deps` before they existed.

**Verification beyond unit tests.** Imported the full FastAPI app with an ephemeral
SQLite `DATABASE_URL` and printed every registered route — confirms the whole
dependency graph (config → security → deps → auth router → main) actually wires
together, not just that each file parses. Ran the Alembic migration against a real
(throwaway) database file, not just `alembic history`.

**Not done in this pass (deliberately, in scope for later phases).**
- No real Postgres integration tests — blocked on Docker (`DEPENDENCIES.md` §5).
- No CI workflow file yet — GitHub Actions lane is `ARCHITECTURE.md` §8, not scoped
  into this Phase 0 slice.
- `tailoring/engine.py`'s stale model ID (H4) and unhandled `json.loads` (B5) — Phase 4
  scope, not touched here to avoid scope creep beyond auth/tenancy/migrations.
- Google OAuth login — email/password only for now; `User.password_hash` is nullable
  in anticipation of it, not wired up.

**Next.** Docker Desktop approval unblocks real Postgres testing and running the app
end-to-end. Phase 1 (facts & intake) is next per `PRD.md` §11.

---

### 2026-08-15 (later) — Phase 0 + eval-harness dependencies approved and installed

**What changed.** Owner approved the Phase 0 foundation group and the eval/feedback
harness group (ADR-014) from `docs/DEPENDENCIES.md` §6. Actually installed, not just
documented — first real dependency install of the project.

**What was installed.**
- `apps/api/.venv` created (Python 3.11.9). Phase 0 packages installed and verified
  importable: `alembic`, `pydantic-settings`, `python-jose[cryptography]`,
  `argon2-cffi`, `pytest`+`pytest-asyncio`+`pytest-cov`, `respx`, `ruff`, `mypy`,
  `factory_boy`, `Faker`.
- `scikit-learn==1.5.2` installed and verified (match-weight recalibration, ADR-014).
- `eval/` workspace created (`package.json`) with `promptfoo` installed via npm — got
  `0.100.6`, current is `0.122.0`, worth bumping the pin before real use.
- `apps/api/requirements.txt` updated to reflect all of the above.

**Problems hit.**
- `garak` (adversarial/injection red-team scan, ADR-014) **fails to install on this
  Windows machine**: a transitive dependency (`litellm`) needs a Rust/Cargo toolchain to
  compile from source, and another (`ecoji`) has no Windows wheel at all — no path
  forward without installing a Rust toolchain, which wasn't done without asking first.
  Also worth knowing: `garak` pulls in `torch` (multi-GB) for what is purely API-only
  usage against Claude, not local model inference.
- **Decision (owner, option "b" of three offered): skip local install, run garak in CI
  only.** Split it into `apps/api/requirements-ci.txt` (`-r requirements.txt` +
  `garak==0.10.3.1`), installed only by the Linux GitHub Actions runner. `requirements.txt`
  itself carries a comment explaining why garak isn't there, so a future session doesn't
  waste time re-attempting the same failed install.

**Files created.** `apps/api/.venv/` (gitignore this), `eval/package.json`,
`eval/node_modules/` (gitignore this), `apps/api/requirements-ci.txt`.

**Files changed.** `apps/api/requirements.txt` (Phase 0 + scikit-learn added, garak
explicitly excluded with reasoning); `docs/DEPENDENCIES.md` §1.1/§1.4b/§6 marked
installed.

**Tests.** None written yet — packages installed, no application code exists to test
against. First real test run happens when Phase 0 implementation (migrations, auth,
tenancy) actually starts.

**Next.** Add `.venv/`, `eval/node_modules/` to `.gitignore` if not already covered.
Bump `promptfoo` pin to `0.122.0`. Begin Phase 0 implementation: Alembic baseline
migration, session-handling fix (`CODE-REVIEW.md` B3), users/profiles/tenancy schema.

---

### 2026-08-15 — Documentation set created

**What changed.** Created `docs/` with seven documents: PRD, ARCHITECTURE, SPEC,
DECISIONS, DEPENDENCIES, CODE-REVIEW, and this WORKLOG.

**Why.** The prior session produced a working single-user MVP with no written product
definition. The owner's actual goal is a multi-tenant product covering three personas
(developer, product manager, marketing) with job aggregation, resume tailoring, automated
submission, and referral outreach. That is a different product from what the code is, and
building further without a written spec would compound the mismatch.

**Inputs to the design.**
- Read the entire existing codebase (`main.py`, `models.py`, `tailoring/engine.py`,
  `connectors/config.py`, `README.md`, `docker-compose.yml`, `.env.example`)
- Confirmed environment: Node v22.14.0, npm 10.9.2, Python 3.11.9, git 2.55.0, **no Docker**
- Fetched `github.com/Panniantong/agent-reach` — confirmed MIT licensed, Python 3.10+ CLI
  over web/YouTube/Twitter/Reddit/GitHub/RSS. Suitable for company research, invoked as a
  subprocess rather than vendored
- Four architecture decisions taken by the owner (listed above)

**Files created.**
- `docs/PRD.md` — problem, personas, 14 features, journeys, data model, metrics, risks, 8 phases
- `docs/ARCHITECTURE.md` — topology, module boundaries, connector contract, 5 critical data flows, tenancy, security posture
- `docs/SPEC.md` — authoritative DDL, full API surface, dedupe/scoring/tailoring algorithms, state machines, test requirements
- `docs/DECISIONS.md` — ADR-001 through ADR-010
- `docs/DEPENDENCIES.md` — approval gate. ~30 proposed packages, MCP server analysis, skill mapping
- `docs/CODE-REVIEW.md` — 6 blockers, 7 high, 10 medium findings against the existing MVP
- `docs/WORKLOG.md` — this file

**Files changed.** None. No existing code was modified.

**Dependencies added.** None. Per the standing rule, nothing was installed.
`docs/DEPENDENCIES.md` §6 is the checklist awaiting approval.

**Tests.** None written — no code was changed. The first Phase 0 task creates
`apps/api/tests/` and the CI lane, since the repo currently has zero tests.

**Problems hit.**
- The `GateGuard` fact-forcing hook blocked every `Write` on first attempt, requiring
  callers/schemas/instruction facts to be restated before each retry. Not a defect —
  worth noting so the next session expects it. `ECC_GATEGUARD=off` disables it if it
  becomes an obstacle during heavy implementation work.
- `docker -v` failed — Docker is not on this machine. Recorded as a Phase 0 blocker in
  `docs/DEPENDENCIES.md` §5 with three options and a recommendation.

**Open questions for the owner** (also in `docs/PRD.md` Appendix A):
1. Pricing model — affects the per-user model-spend cap design
2. Chrome Web Store from day one, or side-load for beta?
3. Which company seed list feeds ATS discovery?
4. One Facts KB shared across personas, or separate per persona? (current design: shared, tagged)
5. Hosted embeddings (voyageai) or local (sentence-transformers)? — blocks Phase 3

**Next.** Owner approves dependency groups in `docs/DEPENDENCIES.md` §6, then Phase 0
begins with the fix order in `docs/CODE-REVIEW.md`: Alembic + session handling, then
users/profiles/tenancy, then the first tests.

---

### Prior session (undated, reconstructed) — Initial MVP

**What was built.** Single-user job search dashboard: four ATS/board connectors, Postgres
schema via `create_all`, a resume-facts knowledge base seeded from `facts.json`, a
two-pass Claude tailoring engine with a truth-checker, an application tracker, and a
Next.js dashboard.

**Known limitations, as stated in the README at the time.** No Temporal, no pgvector
semantic search, no Playwright autofill, no auth. Explicitly single-user and local by
design.

**Reviewed on 2026-08-15.** See `docs/CODE-REVIEW.md`. The structure is sound; it is
missing boundaries — validation at the edges, tenancy at the top, migrations underneath,
and enforcement on the truth-check.

---

## Entry template

Copy this for each change.

```markdown
### YYYY-MM-DD — <short title>

**What changed.**
**Why.**
**Files created / changed / deleted.**
**Dependencies added.** (must already be approved in docs/DEPENDENCIES.md)
**Tests.** What was written; was red-before-green confirmed?
**Problems hit.** Including dead ends and approaches that failed.
**Next.**
```

---

## Related documents

`docs/PRD.md` · `docs/ARCHITECTURE.md` · `docs/SPEC.md` · `docs/DECISIONS.md` ·
`docs/DEPENDENCIES.md` · `docs/CODE-REVIEW.md`
