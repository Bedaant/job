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
