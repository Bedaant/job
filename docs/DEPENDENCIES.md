# Job Copilot — Dependencies, MCP Servers, and Skills

> **This file is an approval gate (ADR-010).** Nothing in it is installed. Each line item
> is a proposal with a justification and a "what if we don't" column. Approve per-line,
> per-group, or reject.
>
> **Current status: NOTHING INSTALLED. Awaiting approval.**

- **Last updated:** 2026-08-15
- **Machine state:** Node v22.14.0, npm 10.9.2, Python 3.11.9, git 2.55.0. **Docker is
  not installed** — `docker-compose.yml` cannot run as written. See §5.

---

## 1. Python — API and workers

Already declared in `apps/api/requirements.txt`: fastapi, uvicorn, sqlalchemy,
psycopg2-binary, httpx, pydantic.

### 1.1 Phase 0 — Foundation (request approval to add)

| Package | Why | If we skip it |
|---|---|---|
| `alembic` | Schema migrations. Currently `Base.metadata.create_all()` — any column change in production loses data | We cannot change the schema after launch without manual SQL |
| `pydantic-settings` | Typed env config validated at boot | Missing `ANTHROPIC_API_KEY` becomes a 401 at runtime instead of a boot failure |
| `python-jose[cryptography]` | Verify Better Auth JWTs in FastAPI | No auth on the API |
| `argon2-cffi` | Password hashing | — (only if we hash server-side rather than in Better Auth) |
| `pytest`, `pytest-asyncio`, `pytest-cov` | Test suite. There are currently **zero tests** | No red-before-green, which violates the standing quality rule |
| `respx` | Mock httpx in connector tests | Connector tests would hit live APIs in CI |
| `ruff` | Lint + format, replaces black/flake8/isort | Style drift |
| `mypy` | Type checking | Type hints become decoration |
| `factory_boy` + `Faker` | Realistic seed/fixture data for connectors, matching, and tailoring tests during development | Hand-written fixture dicts that drift from the real schema |

### 1.2 Phase 1 — Facts and intake

| Package | Why | If we skip it |
|---|---|---|
| `pdfplumber` | Extract text from uploaded PDF resumes | No resume upload — users hand-enter every fact |
| `python-docx` | Read `.docx` resumes **and** generate ATS-safe output | Same, plus no DOCX export |
| `anthropic` | Official SDK. Replaces the hand-rolled `httpx.post` in `tailoring/engine.py` | We keep maintaining our own retry, streaming, and error handling |
| `clamd` + official `clamav` Docker container | Virus-scan resume uploads before they reach `pdfplumber`/`python-docx` — closes a security gap flagged earlier with no concrete pick until now | Arbitrary PDF/DOCX from the public internet processed unscanned |

### 1.3 Phase 2 — Ingestion

| Package | Why | If we skip it |
|---|---|---|
| `rq`, `rq-scheduler` | Background workers and cron. `/discover/run` currently does all network I/O inline in a request | Discovery times out as soon as we exceed ~20 boards |
| `croniter` (validation only, separate from `rq-scheduler`'s own internal `crontab` dependency) | Validate any user- or config-supplied cron string at the API boundary via `croniter.is_valid()` before scheduling | A malformed schedule string fails silently or crashes the scheduler instead of rejecting at input |
| `redis` | RQ client (Redis server already in compose) | — |
| `tenacity` | Retry/backoff for flaky ATS APIs | One 503 loses a whole board's listings for that run |
| `feedparser` | RSS sources (WeWorkRemotely, Personio XML, Uplers) | Lose the RSS tier |
| `selectolax` | Fast HTML → text for JD bodies and ATS detection | Regex over HTML, which is how you get bad data |

No new package needed for Adzuna, Reed, The Muse, or Jooble — all four are plain REST +
JSON, fetched with the already-approved `httpx`. Each becomes one connector module under
`ingest/connectors/`, same contract as the existing four (`docs/ARCHITECTURE.md` §3).
ZipRecruiter needs no new package either, but its publisher-agreement requirement means
it should be built last, after the `apiKey`-only sources are live.

### 1.4 Phase 3 — Matching and research

| Package | Why | If we skip it |
|---|---|---|
| `pgvector` (Python binding) | SQLAlchemy `Vector` column type | Hand-written SQL for every embedding query |
| `voyageai` **or** `sentence-transformers` | Embeddings. Hosted (voyage) vs local (sentence-transformers, no API cost but needs ~500MB model + CPU) | No semantic matching — keyword only, which is materially worse |

> **Decision needed:** hosted embeddings (per-token cost, zero ops) or local
> (zero marginal cost, slower, bigger image). Recommendation: hosted for v1, local if
> embedding spend becomes a visible line item.

### 1.4b Eval/feedback harness (ADR-014)

| Package | License | Why | If we skip it |
|---|---|---|---|
| `promptfoo` | MIT | Golden-dataset prompt regression testing, CI-gated. The one piece of infrastructure that makes "did this prompt change help or hurt" a measured fact instead of a guess | Every tailoring-prompt edit is an unvalidated change on the core differentiator |
| `garak` | Apache-2.0 | Offline adversarial/injection red-teaming — closes the dossier-injection gap (ADR-014). Needs a ~30-50 line custom Generator wrapper around the JD-field and dossier-field call sites, not zero-config. **CI-only (Linux) — fails to install on Windows: `litellm` needs a Rust/Cargo toolchain to compile, `ecoji` has no Windows wheel at all, and it pulls in `torch` (multi-GB) for what's API-only usage. Pinned in `apps/api/requirements-ci.txt`, not `requirements.txt`** | The dossier stays an unguarded second injection surface, unlike the JD path which already has fixtures |
| `scikit-learn` | BSD-3 | Scheduled `LogisticRegression` refit of the match-score weights against real outcome data (`match_weight_history`, `SPEC.md`) | Match-score weights (0.55/0.30/0.15) stay hand-picked constants forever, never checked against whether they predict anything |

**Not adopted:** `Vowpal Wabbit` — evaluated and rejected in ADR-014. Contextual
bandits solve real-time exploration-exploitation under high-frequency, non-stationary
reward; this system has low-frequency outcome data (days/weeks) and three fixed
coefficients to refit monthly. A bandit library would be solving a problem this product
doesn't have. `DeepEval` and `Ragas` — evaluated against `promptfoo` for the eval-harness
slot; DeepEval is a viable second choice but more code for the same job, Ragas is wrong
domain (RAG-retrieval grading, this pipeline has no retrieval step to grade).

### 1.5 Phase 4 — Documents

| Package | Why | If we skip it |
|---|---|---|
| `rapidfuzz` | Parse-back check: fuzzy-match extracted bullets against source facts | The ATS-safety guarantee is unverified |
| LibreOffice (system binary, not pip) | DOCX → PDF with a real text layer | PDF export either doesn't exist or is a screenshot ATS parsers can't read |

### 1.6 Phase 6 — Outreach

| Package | Why | If we skip it |
|---|---|---|
| `google-api-python-client`, `google-auth-oauthlib` | Gmail send-as-user | No referral sending |
| `dnspython` | MX verification when inferring `first.last@company.com` | We send to addresses that bounce, which damages the user's sender reputation |

### 1.8 Observability, structured output, and data quality (pass 4)

| Package | Why | If we skip it |
|---|---|---|
| `instructor` | Maps Pydantic models onto Claude tool-calling with automatic retry-on-`ValidationError`. Fixes CODE-REVIEW.md B5 — `tailoring/engine.py` currently does an unhandled `json.loads` on model output | The tailoring pipeline keeps failing opaquely on malformed JSON, with no retry |
| `langfuse` (SDK) + self-hosted Langfuse service (docker-compose) | Traces every Claude call across the 3-pass pipeline — tokens, cost, latency, prompt version. MIT core; the `ee/` folder (SSO/RBAC) is proprietary but irrelevant to a single-tenant-ops self-host | Zero visibility into what tailoring actually costs or where it's slow — currently the case |
| `sse-starlette` | Thin `EventSourceResponse` wrapper over Starlette (already under FastAPI) — powers real-time push for the review queue (F10) and resume-parsing status (F2) instead of polling | Frontend keeps polling `@tanstack/react-query` on an interval; works, just wastes requests and adds latency to "job finished" |
| `rq-dashboard-fast` | FastAPI-based dashboard for the RQ queues chosen in ADR-008 — token-auth, mountable as a sub-app behind our existing auth, supports `rq-scheduler`'s recurring jobs | We're flying blind on ingestion/tailoring/outreach queue health in production |
| `cleanco` | Strips company-suffix noise ("Inc.", "GmbH", "Ltd") before computing `canonical_hash` (SPEC.md §3.1) | Dedupe misses "Acme Inc" vs "Acme" as the same company |
| `price-parser` | Extracts amount + currency from messy salary strings ("$120k–$150k", "€80.000"), handles locale separators | Salary fields stay unparsed or need a hand-rolled regex that breaks on locale variants |
| `iso4217` | Canonical currency-code enum for the `currency` field | Hand-rolled currency-code validation |

**Not proposed as a package — build in-house instead:**
- **Semantic LLM response cache.** The obvious library (`GPTCache`, MIT) is confirmed stalled — no meaningful commits in 13+ months, README still says "under heavy development." A `llm_cache` table (`embedding vector`, `prompt_hash`, `response_json`) with an ivfflat cosine lookup at a ~0.97 threshold is ~40 lines on the pgvector setup we already have (ADR-005) and avoids a dead dependency.
- **Job-title / seniority normalization.** No maintained, properly-licensed library found (the one comprehensive dataset, `jneidel/job-titles`, has no LICENSE file — reject per ADR-010). A small synonym/level-stripping table is a few hours of work, not a dependency.

### 1.9 Explicitly NOT proposed

- `celery` — RQ covers it (ADR-008)
- `langchain` / `llamaindex` — three prompt calls do not need a framework
- `beautifulsoup4` — `selectolax` is faster and sufficient
- `pandas` — nothing here is a dataframe problem
- Any scraping/anti-bot library — ruled out by ADR-002
- `GPTCache` — stalled upstream (13+ months no meaningful commits); build the cache in-house on pgvector instead (§1.8)
- `Helicone` — Apache-2.0 and fully self-hostable, but proxy-based (adds a network hop) and in maintenance mode since its Mintlify acquisition; Langfuse's SDK-based, purpose-built pipeline UI is the better fit
- `Socket.io` / `fastapi-socketio` — F10/F2 are pure server→client notifications; WebSockets solve a bidirectional-state problem we don't have. `sse-starlette` covers the actual need

---

## 2. JavaScript — web and extension

Currently in `apps/web/package.json`: next, react, react-dom, tailwindcss.

### 2.1 Web

| Package | Why | If we skip it |
|---|---|---|
| `typescript` + `@types/*` | The dashboard is currently untyped `.js` | Runtime errors we could have caught |
| `better-auth` | Self-hosted auth, Google OAuth included, no per-MAU cost | No signup. Alternative is Clerk (faster, costs per MAU) |
| `@tanstack/react-query` | Server-state, polling for async tailoring jobs | Hand-rolled `useEffect` fetch + loading state in every component |
| `zod` | Runtime validation of API responses at the client boundary | Trust the server blindly; a schema change breaks silently |
| `shadcn/ui` + `radix-ui` | ✅ **installed 2026-08-16.** Accessible primitives (dialog, combobox, toast). Copy-in components, not a runtime dependency | Build a design system by hand, badly, with a11y bugs |
| `openapi-typescript` | Generate the API client from FastAPI's OpenAPI | Hand-written fetch wrappers that drift from the API |
| `diff` (jsdiff) | ✅ **installed 2026-08-16.** Underlying diff algorithm for the review queue's tailored-vs-base resume comparison. **Not** `react-diff-viewer` — see §2.4, no adoptable prose-diff component exists; build the UI on this with custom shadcn styling | The core review UX has no diff |
| `vitest` + `@testing-library/react` | Frontend tests | None |
| `msw` (Mock Service Worker) | Mocks the API at the network layer for frontend dev/tests, derived from the same OpenAPI spec driving `openapi-typescript` so mocks and the real client don't drift independently | Frontend built ahead of backend (the phased plan implies this) has nothing to run against but hand-rolled stubs |
| `style-dictionary` | Single design-token source of truth (colors/spacing/typography), transformed three ways: Tailwind theme values for the web app, a CSS-variable bundle for the extension's shadow-root UI, and inlined styles for `react-email` output | Three UI surfaces (dashboard, extension, email) drift out of visual sync with no shared source |

### 2.2 Extension

| Package | Why |
|---|---|
| `@types/chrome` | MV3 typings |
| `vite` + `@crxjs/vite-plugin` | MV3 build with HMR |

### 2.4 UI, design, and icons (pass 6)

| Package | License | Why | If we skip it |
|---|---|---|---|
| `lucide-react` | ISC | Icon set — shadcn's own default, tree-shakable, matches shadcn's icon-prop conventions | Hand-picking icons from mismatched sets, inconsistent stroke weights |
| `@dnd-kit/core` (+ `@dnd-kit/sortable`) | MIT | Drag-and-drop for the application tracker's kanban board (F13) | `react-beautiful-dnd` — **confirmed archived August 2025, no React 19 support, do not use** |
| `motion` (Framer Motion) | MIT | Drag feedback/transitions on the kanban board and card interactions | Static, unpolished drag interactions |
| `sonner` | MIT | Toast notifications — already shadcn's own recommended default | Hand-rolled toast component |
| `diff` (jsdiff) | MIT | See §2.1 — underlying algorithm for the resume-comparison diff UI, custom-styled, not a packaged diff component | — |

**Not packages — copy-in references, MIT unless noted:**
- **shadcn official blocks** (ui.shadcn.com/blocks) — canonical source for dashboard/data-table layout patterns, zero lock-in since shadcn components are copy-in by design (already established in §2.1)
- **Kibo UI** (MIT) — ✅ **installed 2026-08-16** (kanban, dropzone, combobox, status, relative-time via the shadcn CLI's `@kibo-ui` registry). Kanban is the direct starting point for F13's tracker UI, pairs with `@dnd-kit` (not yet installed — needed for drag interactions on top of the static Kanban component)
- **react-email template gallery** (MIT) — real designed email templates (Stripe/Vercel-style) as the starting point for the weekly digest (F13/notifications), not a blank page
- **Origin UI** (MIT) — study for filter/facet UI patterns on the matches dashboard (the new search/filter params from ADR-012)

**Confirmed whitespace — no adoptable prose-diff component exists, build in-house:** every
diff-view library found (`react-diff-viewer` and its forks) is code-diff-styled, not
suited to comparing two versions of resume prose; the one prose-specific match found
(`prose-diff`) has no license and 1 star. The review queue's tailored-vs-base comparison
is built directly on `jsdiff`'s diff algorithm with custom shadcn styling — a UI
component, not a missing library, and not worth re-searching for.

**Explicitly avoided:**

| Item | Reason |
|---|---|
| `react-beautiful-dnd` | Archived August 2025, no React 19 support — was the obvious kanban pick, now dead |
| Shadcnblocks.com, Aceternity UI (paid tiers) | Both mostly paywalled; free tiers skew toward marketing pages, not dashboard/kanban components Job Copilot needs |
| `prose-diff` | No LICENSE file, 1 star — reject per ADR-010 regardless of topical fit |
| unDraw illustrations | Usable for in-app empty states but under a custom free-commercial license with no resale/redistribution — read the actual terms before using, don't assume MIT-equivalent freedom |

### 2.5 Explicitly NOT proposed

- A component library beyond shadcn (MUI, Chakra) — shadcn is copy-in, zero runtime lock-in
- Redux/Zustand — react-query plus URL state covers it
- `moment` — `Intl.DateTimeFormat` is native

---

## 3. Third-party repos

| Repo | License | How we use it | Vendored? |
|---|---|---|---|
| [Panniantong/agent-reach](https://github.com/Panniantong/agent-reach) | MIT | ✅ **installed 2026-08-16**, own venv (`tools/.venv-agent-reach/`). Company research: `research/company_research.py` wraps 2 of its channels that work with zero extra credentials (GitHub via `gh`, arbitrary web via Jina Reader) — live-verified. Twitter/Reddit/etc. need real per-service tokens not available, not wired | **No** — installed as a tool, not copied into our tree. Keeps the license obligation to attribution only |
| [public-apis/public-apis](https://github.com/public-apis/public-apis) | MIT | Reference list only, for finding additional job/company data sources | **No** — it is a directory, not code |
| [jsonresume/jsonresume.org](https://github.com/jsonresume/jsonresume.org) | MIT | ✅ **installed 2026-08-16.** `parsing/jsonresume_export.py` + `GET /resume-facts:jsonresume`. Adopted as our canonical resume/facts interchange format — mature, widely-tooled standard, no reason to invent our own shape | **No** — schema/spec adopted, not code vendored |
| [speedyapply/JobSpy](https://github.com/speedyapply/JobSpy) | MIT | ✅ **installed 2026-08-16, isolated** (`tools/.venv-jobspy/`, not the main app venv — hard-pins `numpy==1.26.3`, conflicts with pgvector/scikit-learn's numpy 2.x and broke a real test when tried in-venv). `connectors/jobspy_connector.py` subprocess-wraps it. **Upgraded 1.1.82 -> 1.3.0 and wired into ingestion 2026-10-09 (GAPS 3.2).** The 0-yield was only partly upstream: on 1.1.82 **ZipRecruiter and Glassdoor were both answering HTTP 403** and the connector swallowed the exit code, so a block looked identical to an empty board. On 1.3.0 **Glassdoor works** (`google`, `zip_recruiter`, `indeed` still return 0, so `JOBSPY_SITES` is `["glassdoor"]` alone). Queried **per city, never per country** — `location="India"` returns Indianapolis, because Glassdoor prefix-matches the string. Measured: **147 unique India PM jobs across 101 companies** from six cities, against the 23 that were GAPS 3.1's ceiling. Keep the isolated venv pinned at >=1.3.0; re-probe the dead sites before re-adding one | **No** — installed as a package (isolated venv), used only against the non-excluded sources |
| [srbhr/Resume-Matcher](https://github.com/srbhr/Resume-Matcher) | Apache-2.0 | **Study only, not adopted as a dependency.** Reference for keyword-gap/ATS-scoring logic (F6 matching, F9 export). License permits full adoption later if scope grows | **No** — read for technique; any reused logic is reimplemented under our own license, not copied |
| [microsoft/presidio](https://github.com/microsoft/presidio) | MIT | ✅ **installed 2026-08-16.** `pii/redact.py`. PII redaction for cached company dossiers (F7) and generation history (F8) — 13+ entity types, Microsoft-maintained, industry standard. Live-verified (real name/email/phone redacted) | **No** — installed as a package |
| [seomoz/simhash-py](https://github.com/seomoz/simhash-py) | MIT | ✅ **2026-08-16: algorithm reimplemented, not vendored.** Upstream is a Cython/C++ extension (185KB `simhash.cpp`) needing a compiler toolchain — same class of problem already declined for garak (Rust). `matching/near_duplicate.py` reimplements Charikar's simhash in pure Python instead, wired into `connectors/pipeline.py`'s dedupe | **Reimplemented**, not vendored — see `matching/near_duplicate.py`'s module docstring |
| [KonstantinosPetrakis/esco-skill-extractor](https://github.com/KonstantinosPetrakis/esco-skill-extractor) | MIT | **Study only, not adopted as a dependency.** Reference for JD → structured skills extraction (F6 matching) against the ESCO/ISCO taxonomy | **No** — read for approach; our own extractor is reimplemented, not copied |
| [MaxMLang/pytector](https://github.com/MaxMLang/pytector) | Apache-2.0 | **Study only, not adopted as a dependency.** Pluggable prompt-injection detector — candidate to complement, not replace, the structural defence in ADR-006 (truth-check never sees the JD). Best-in-class alternative (`llm-guard`) is archived, this is the live option | **No** — evaluate against our adversarial fixtures (SPEC.md §5) before any adoption decision |
| [kalil0321/ats-scrapers](https://github.com/kalil0321/ats-scrapers) | MIT (**LICENSE file read and verified 2026-09-27**, not trusted from GitHub's sidebar label — "MIT License / Copyright (c) 2026 Kalil Bouzigues", standard unmodified MIT text) | ⬆️ **Verdict changed 2026-09-27: "study only" → partial adoption of its URL→ATS host mapping (data, not code).** "Study only" was the correct call under ADR-002, which forbade scraping and therefore left nothing here worth taking. **ADR-015 lifted that constraint**, and resolving an aggregator `apply_url` to the real ATS became a product requirement — this repo is the best-maintained public catalogue of ATS tenant URL shapes. **Adopted:** the host→ATS mapping in `src/ats_scrapers/resolve.py` (`_PATH_HOSTS`, `_SUBDOMAIN_SUFFIXES`, `_WORKDAY_HOST_RE`, `_ICIMS_HOST_RE`) — used to extend `connectors/discovery.py`'s existing `ATS_PATTERNS` from 5 to 17 ATS types, and its reserved-segment idea (`_KEKA_RESERVED_SEGMENTS`, `_JOBVITE_RESERVED_SEGMENTS`) generalised into one `_RESERVED_SUBDOMAINS` guard. **Not adopted:** its scrapers, registry, exceptions, models, per-ATS API clients, and its 6.7 MB / 47-file `ats-companies/` slug directory — see note below | **Facts only, no files copied.** The regexes are written for our table's one-capture-group contract; `connectors/discovery.py` carries the origin + license + copyright line in a comment above `ATS_PATTERNS`, which is the MIT attribution obligation discharged. `connectors/apply_target.py` is our own code |
| [nanobrowser/nanobrowser](https://github.com/nanobrowser/nanobrowser) | Apache-2.0 | **Study only, not adopted as a dependency.** The one credible prior art for an LLM agent loop running *inside* an MV3 extension (vs. server-side) — reference architecture for F11's bounded form-filling agent per ADR-011 | **No** — read for the content-script/DOM-interaction pattern; our own loop is raw Anthropic tool-use with a hard iteration cap, not this framework |
| [pydantic/pydantic-ai](https://github.com/pydantic/pydantic-ai) | MIT | **Noted, not adopted.** Not used today — raw Anthropic SDK + hard iteration cap still stands for F11/F5 per ADR-011. Recorded as the pre-selected *next* option (ahead of LangGraph) if F11's loop ever crosses the ADR-011 revisit trigger — it's Pydantic-native, first-class Anthropic support, and we already depend on Pydantic everywhere | **No** — evaluation-only until the revisit trigger fires |
| [Pickle-Pixel/ApplyPilot](https://github.com/Pickle-Pixel/ApplyPilot) | Unverified | **Study only, not adopted.** 6-stage pipeline (discover → score → tailor → cover letter → submit) using Claude Code to drive the final submit step itself. Its stage decomposition is already mirrored in this project's own pipeline, but the last stage — autonomous form-fill-and-submit — conflicts with ADR-001 (human approves, machine executes) at the architecture level, not a config toggle. Not adopted | **No** |
| [career-ops-hq/career-ops](https://github.com/career-ops-hq/career-ops) | MIT | **Study only, not adopted.** Assist-mode CLI (scan → score 1-5 → tailor → track, human decides, runs inside Claude Code/Codex) — philosophically validates this project's own ADR-001 stance, but is a single-user local tool with no persistence layer. This project's Postgres/FastAPI + real connectors + eval harness (ADR-014) + Langfuse tracing is already more mature in the areas that matter here | **No** |

**Note on jobhive:** the owner separately flagged "jobhive (ats-scrapers)" — this appears to be the same repo already evaluated above as [kalil0321/ats-scrapers](https://github.com/kalil0321/ats-scrapers) (Greenhouse/Lever/Ashby/Workday + more, no API key required), not a new candidate. Verdict superseded 2026-09-27 by the row above: its URL→ATS host mapping is now adopted (facts, no files), its scraper code still is not.

**Note on `ats-companies/` (the ~63k-company slug directory), decided 2026-09-27 rather than done silently.** **Not vendored.** It is data and the repo's MIT licence covers it, so licence is not the blocker — size and staleness are. 47 CSVs totalling **~6.7 MB** (`join_com.csv` 1.79 MB, `paycom.csv` 785 KB, `greenhouse.csv` 427 KB, `workable.csv` 322 KB, `workday.csv` 316 KB), committed into git, to answer a question we do not currently ask: nothing in this project needs "list companies on Greenhouse". `resolve_apply_target` works from the URL in front of it, and `discover_ats_for_domain` works from a company domain — neither needs a directory. A vendored copy would also silently rot, since tenants come and go. **Revisit if** we ever want company→ATS lookup without a network call, and then fetch it at build time from the upstream repo instead of committing it.

**Explicitly rejected, recorded so they aren't re-proposed:**

| Repo | Reason |
|---|---|
| [feder-cr/Jobs_Applier_AI_Agent_AIHawk](https://github.com/feder-cr/Jobs_Applier_AI_Agent_AIHawk) | AGPL-3.0 (copyleft), archived/dead May 2026, and architecturally a fully-autonomous apply bot — conflicts with ADR-001 (human approves, machine executes) |
| [xitanggg/open-resume](https://github.com/xitanggg/open-resume) | AGPL-3.0 — cannot wrap in commercial SaaS without releasing our source. Parsing approach may be studied, not copied |
| [louisgregg/ats-resume-generator](https://github.com/louisgregg/ats-resume-generator) | No LICENSE file — "all rights reserved" per our standing rule |
| Any LinkedIn/Indeed scraper (including JobSpy's LinkedIn/Indeed modes) | Server-side scraping of these platforms is ruled out by ADR-002 regardless of the scraper's own license |
| [GodsScion/Auto_job_applier_linkedIn](https://github.com/GodsScion/Auto_job_applier_linkedIn) | LinkedIn Easy-Apply automation bot — hits ADR-002's explicit revisit trigger ("Never for LinkedIn") directly |
| [feder-cr/... AIHawk-style forks (e.g. Intusar/Auto_Jobs_Applier_AI_Agent)](https://github.com/Intusar/Auto_Jobs_Applier_AI_Agent) | Same AGPL-3.0 + fully-autonomous-apply issue as the original AIHawk entry above — rejected for the same reasons, not re-evaluated per-fork |
| [protectai/llm-guard](https://github.com/protectai/llm-guard) | Was best-in-class for prompt-injection scanning, but the repo is archived — no hard dependency on unmaintained security tooling |
| [roksela/smartrecruiters-python-client](https://github.com/roksela/smartrecruiters-python-client) | Dead since 2017, stale Swagger-codegen wrapper |
| [Francis1998/agentic-career-search](https://github.com/Francis1998/agentic-career-search) | No LICENSE file — its Workday `wday/cxs` pagination guide is useful reading but the repo itself is not adoptable |
| [NVIDIA-NeMo/Guardrails](https://github.com/NVIDIA-NeMo/Guardrails) | License unclear (NOASSERTION, no resolvable SPDX) — needs a manual LICENSE check before it is even reconsidered, not a straight adopt or reject |
| [PaulleDemon/Email-automation](https://github.com/PaulleDemon/Email-automation) | License ambiguous, no suppression-list/opt-out mechanism found despite outreach use case — doesn't meet our compliance bar (ADR-003) |
| [omers/pii-anonymizer-api](https://github.com/omers/pii-anonymizer-api) | No LICENSE file; also just a thin wrapper around Presidio, which we're adopting directly |

**Confirmed whitespace — no adoptable prior art found, build in-house:** DOCX XML
structural linter for the F9 parse-back check (existing tools score text-extraction
quality, none walk the raw XML for tables/textboxes/headers the way our spec requires);
Workday multi-page client-side apply-flow automation; MV3 install-token/pairing-code
auth (extension boilerplates use OAuth-popup or `chrome.identity`, not device-pairing —
worth looking at OAuth Device Authorization Grant implementations instead); Gmail
outreach tooling with a real suppression-list compliance layer; JD seniority/
years-of-experience extraction (every repo found stops at skill-span extraction).

**Standing rule (ADR-010):** before copying any code from a third-party repo, check the
LICENSE file. MIT/Apache-2.0/BSD is fine with attribution. No LICENSE file means "all
rights reserved" — do not copy. "For educational purposes only" means it cannot be
commercialized. Record every vendored file's origin and license in this table.

---

## 4. MCP servers

Already connected in this environment (no install needed): **Playwright**,
**Chrome DevTools**, **Repomix**, **Gmail**, **Google Calendar**, **Google Drive**, **IDE**.

### 4.1 Which ones this project actually needs

| MCP | Status | Use in this project |
|---|---|---|
| **Playwright** | ✅ connected | E2E tests of the signup → upload → review → approve flow. Prototyping and validating the extension's ATS field maps against real Greenhouse/Lever/Ashby forms. This is the highest-value MCP here |
| **Chrome DevTools** | ✅ connected | Lighthouse audits and performance traces on the dashboard; the matches list will get long and needs to stay fast. Also a11y auditing |
| **Repomix** | ✅ connected | Pack and grep `agent-reach` and any candidate third-party repo before we depend on it — read the whole thing, check the license, understand the CLI surface, without cloning |
| **Gmail** | ✅ connected | Development and testing of the outreach templates end-to-end before wiring the production Gmail OAuth path. **Not** the production send path — that is the user's own OAuth token |
| **Context7** | ✅ **installed this session** (`claude mcp add context7 -- npx -y @upstash/context7-mcp@latest`, project-local config) | Standing rule is "never guess APIs, use Context7." We are about to write against FastAPI, Alembic, pgvector, Better Auth, Chrome MV3, and the Gmail API. First health check timed out on the cold `npx` download — expected on first run, not a failure; re-check on next actual use |
| **GitHub** | ⚠️ **configured but broken** — found already present in user-global MCP config pointed at `https://api.github.com` as an SSE transport, which is not a valid MCP endpoint (fails with `HTTP 415`) | The "ship it" workflow depends on it. Not fixed automatically — repointing it to the correct endpoint (`https://api.githubcopilot.com/mcp/`, OAuth or PAT) is a change to **user-global** config (affects every project, not just this one), so it needs your go-ahead and a token before I touch it |
| **Postgres MCP Pro** ([crystaldba/postgres-mcp](https://github.com/crystaldba/postgres-mcp), MIT, ~2,400★, active) | Not installed — needs a live Postgres connection string, which doesn't exist yet (no DB running, Docker not installed per §5) | Schema inspection, `EXPLAIN ANALYZE` during pgvector ivfflat tuning. Confirmed current best pick, replacing the earlier generic "a Postgres MCP" placeholder. Install once a dev database exists |
| **GlitchTip MCP** | Not installed — needs a self-hosted GlitchTip instance first (`GLITCHTIP_ENABLE_MCP=true`, no separate API key beyond that) | Ships with GlitchTip itself (pass 5's self-hosted-Sentry-alternative pick, still pending — see §1.8's build-in-house observability note). Trivial add once GlitchTip is running: one env var |
| **Figma** | Not needed | This project's design system is code-first (Tailwind tokens via `style-dictionary`, shadcn) — no Figma-first workflow exists. Needs a paid Figma Dev/Full seat regardless; revisit only if that changes |

**Status: Context7 installed. GitHub needs your decision** — provide a PAT (or confirm
OAuth) and approve editing user-global config, or leave it broken/unused. Postgres MCP
Pro and GlitchTip MCP are correctly-identified but blocked on infrastructure that
doesn't exist yet (a running Postgres, a running GlitchTip) — not blocked on approval.

### 4.2 Skills to use during the build

Available in this environment, no installation required. Listed so the plan is explicit
about which ones govern which phase:

| Phase | Skills |
|---|---|
| All phases | `superpowers:brainstorming` before each feature, `superpowers:test-driven-development` (matches the red-before-green rule), `superpowers:verification-before-completion`, `ponytail` (active) |
| Phase 0 | `ecc:database-migrations`, `ecc:security-review`, `ecc:postgres-patterns` |
| Phase 1–2 | `ecc:fastapi-patterns`, `ecc:python-testing`, `ecc:api-connector-builder`, `pdf` (github.com/anthropics/skills — F2 resume parsing), `docx` (same repo — F9 ATS-safe DOCX generation) |
| Phase 3 | `ecc:postgres-patterns` (pgvector indexing) |
| Phase 4 | `zero-hallucination-coder` — the tailoring engine is exactly the "high-stakes, spans existing code" case it exists for |
| Phase 5 | `ecc:react-patterns`, `ecc:frontend-design-direction`, `frontend-design` (anthropics/skills — avoiding generic-AI-dashboard aesthetics on the matches dashboard/review queue), `ecc:accessibility`, `ecc:e2e-testing`, `ecc:browser-qa` |
| Phase 6 | `ecc:security-review` again — outreach touches PII, OAuth, and email reputation |
| Phase 7 | `dataviz` for the analytics dashboard |

**Checked and correctly not adopted:** `webapp-testing` (anthropics/skills) is redundant
with the already-connected Playwright MCP for this project — same ground, no added
value. `theme-factory` (anthropics/skills) is scoped to artifact/slide/document theming,
not app design-token pipelines — wrong tool for `style-dictionary`'s job. Broader
community Claude Code skill repos searched for FastAPI/SQLAlchemy/Next.js/MV3-specific
skills found nothing that beats the `ecc:*` skills already available in this environment
— single-maintainer, unverified provenance, duplicate coverage. Not worth the trust
diligence for something already covered.
| Continuous | `ecc:code-review` after each change, `ecc:silent-failure-hunter` on the connector layer |

---

## 5. Infrastructure gap: Docker is not installed

`docker-compose.yml` declares Postgres 16 and Redis 7, but `docker` is not on this
machine. Three options:

| Option | Trade-off |
|---|---|
| **Install Docker Desktop** | Matches the compose file exactly, closest to production. Heavy on Windows, needs WSL2 |
| **Install Postgres + Redis natively on Windows** | Lighter, but the compose file becomes dead documentation and local/prod drift starts on day one |
| **Use hosted dev instances (Neon + Upstash)** | Zero local install, free tiers, and it exercises the real connection path. Slower local iteration, needs network |

**Recommendation: Docker Desktop.** Also note the compose file will need
`pgvector/pgvector:pg16` rather than `postgres:16-alpine` once we add embeddings, plus
removal of the obsolete `version:` key (Compose v2 ignores it and warns).

---

## 6. Approval checklist

Reply with which groups to proceed on. Nothing is installed until then.

- [x] §1.1 Python foundation — installed, `apps/api/.venv`
- [x] §1.2 Resume intake (pdfplumber, python-docx) — installed. `anthropic` SDK installed AND now actually used (2026-08-16, swapped in for `tailoring/engine.py`'s hand-rolled `httpx.post`)
- [x] §1.3 Ingestion (rq, redis, tenacity, feedparser, selectolax) — installed and live (Phase 2)
- [x] §1.4 Matching — hosted embeddings (Voyage AI) chosen and live (Phase 3)
- [x] §1.4b Eval/feedback harness — `scikit-learn` installed (not yet used — needs real outcome data); `promptfoo` in `eval/`, bumped to `0.120.19` (Node-version-compatible, fixes a real SQLite bug in `0.100.6`) 2026-08-16; `garak` pinned to `apps/api/requirements-ci.txt` (CI/Linux only, does not install on Windows — see §1.4b table)
- [ ] §1.5 Documents (rapidfuzz + LibreOffice system install) — not started
- [ ] §1.6 Outreach (google-api-python-client, dnspython) — not started, blocked on a real Google Cloud OAuth client from the owner
- [x] §2.1 Web — typescript, react-query, zod, shadcn/ui, Kibo UI, jsdiff **installed and building** (2026-08-15/16). Still open: better-auth, openapi-typescript, vitest
- [ ] §2.2 Extension (vite, crxjs, chrome types) — not started, its own sub-project
- [x] §1.8 Observability — `langfuse` **installed, connected to Langfuse Cloud, real traces confirmed** 2026-08-16 (the main piece). Still open: `instructor`, `sse-starlette`, `rq-dashboard-fast`, `cleanco`, `price-parser`, `iso4217`
- [x] §3 agent-reach — **installed 2026-08-16**, own venv (`tools/.venv-agent-reach/`), GitHub+web channels wired and live-verified; Twitter/Reddit need real credentials, not wired
- [x] §3 jsonresume schema, presidio, simhash-py — **installed/adopted 2026-08-16** (simhash reimplemented in pure Python, not vendored — see §3 table). JobSpy **installed, isolated** (`tools/.venv-jobspy/` — hard-conflicts with the main venv's numpy pin) — **wired into ingestion 2026-10-09 at 1.3.0, Glassdoor only, per-city** (GAPS 3.2). The earlier 0-yield was a 403 the connector was swallowing, not only a Google-side issue
- [x] §4 Context7 MCP — **installed** this session
- [x] §4 GitHub MCP — **fixed and connected** this session. Was pointed at an invalid endpoint (`https://api.github.com` as SSE); repointed to `https://api.githubcopilot.com/mcp/` (HTTP transport) with a Bearer PAT header, user-scope config. **Action item: rotate the PAT** — it was shared in-conversation, which is not a secure channel; regenerate on GitHub and update this MCP entry with the new value when done. Verify the token's scope includes `contents: write` (and `pull_requests: write` if PR creation is wanted) on target repos
- [ ] §4 Postgres MCP Pro, GlitchTip MCP — blocked on infra (no DB/GlitchTip running yet), install when available
- [x] §5 **Docker Desktop abandoned** — got stuck at a UAC prompt this tool can't answer non-interactively. Reconsidered instead of pushing through: ADR-013 already picked Neon for Postgres, so a free Neon dev project replaces local Postgres entirely (connection string wired into `.env`, migration + full auth/tenancy flow verified against it live). Redis/Docker deferred to Phase 2 — revisit with the same honest "do we actually need this" question, not an automatic default
- [ ] §1.8/§2.4 pass 7 additions: `factory_boy`+`Faker`, `clamd`+ClamAV container, `croniter`, `msw`, `style-dictionary`

---

## Related documents

`docs/PRD.md` · `docs/ARCHITECTURE.md` · `docs/SPEC.md` · `docs/DECISIONS.md` ·
`docs/CODE-REVIEW.md` · `docs/WORKLOG.md`
