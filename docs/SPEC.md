# Job Copilot — Technical Specification

- **Status:** Draft v1.0
- **Last updated:** 2026-08-15
- **Companion to:** `docs/PRD.md`, `docs/ARCHITECTURE.md`

This document is the contract. Where the PRD says *what* and the architecture says
*shaped how*, this says *exactly what the interfaces are*. If an implementation
disagrees with this file, one of the two is a bug — resolve it here first.

---

## 1. Schema (DDL, authoritative)

All IDs are `uuid` with `gen_random_uuid()` default (pgcrypto). All timestamps are
`timestamptz`, stored UTC, serialized ISO-8601. Money is integer minor units with an
explicit currency column — never float.

<!-- BEGIN GENERATED SCHEMA (apps/api/scripts/generate_spec_schema.py) -->

This block is generated from `apps/api/models.py` by `apps/api/scripts/generate_spec_schema.py` — do not hand-edit it, run the script instead (`--check` verifies it's current, no args regenerates).
Types are compiled against the real Postgres dialect (Neon). Enum columns (`persona`, `applicationstatus`) become native Postgres ENUM types, not VARCHAR+CHECK. Comments after `--` describe app-level (ORM) defaults honestly instead of inventing a SQL DEFAULT that doesn't exist.

```text
users:
  id  UUID  NOT NULL  PRIMARY KEY  -- default: app-level callable gen_uuid() — not a DB DEFAULT, set by the ORM on insert
  email  VARCHAR  NOT NULL  UNIQUE
  password_hash  VARCHAR  NULL
  created_at  TIMESTAMP WITHOUT TIME ZONE  NULL  -- default: app-level callable utcnow() — not a DB DEFAULT, set by the ORM on insert
  deleted_at  TIMESTAMP WITHOUT TIME ZONE  NULL

profiles:
  id  UUID  NOT NULL  PRIMARY KEY  -- default: app-level callable gen_uuid() — not a DB DEFAULT, set by the ORM on insert
  user_id  UUID  NOT NULL  -- FK -> users.id ON DELETE CASCADE
  persona  persona  NOT NULL  -- default <Persona.developer: 'developer'> (app-level, not a DB DEFAULT)
  headline  VARCHAR  NULL
  location  VARCHAR  NULL
  prefs  JSON  NULL  -- default: app-level callable dict() — not a DB DEFAULT, set by the ORM on insert
  full_name  VARCHAR  NULL
  phone  VARCHAR  NULL
  website_url  VARCHAR  NULL
  street_address  VARCHAR  NULL
  city  VARCHAR  NULL
  region  VARCHAR  NULL
  country_code  VARCHAR(2)  NULL
  postal_code  VARCHAR  NULL
  network_profiles  JSON  NULL  -- default: app-level callable list() — not a DB DEFAULT, set by the ORM on insert
  work_auth  JSON  NULL  -- default: app-level callable list() — not a DB DEFAULT, set by the ORM on insert
  fact_centroid  VECTOR(512)  NULL
  created_at  TIMESTAMP WITHOUT TIME ZONE  NULL  -- default: app-level callable utcnow() — not a DB DEFAULT, set by the ORM on insert
  UNIQUE (user_id, persona)

jobs:
  id  UUID  NOT NULL  PRIMARY KEY  -- default: app-level callable gen_uuid() — not a DB DEFAULT, set by the ORM on insert
  source  VARCHAR  NOT NULL
  external_id  VARCHAR  NOT NULL
  canonical_hash  VARCHAR  NOT NULL  UNIQUE
  title  VARCHAR  NOT NULL
  company  VARCHAR  NOT NULL
  location  VARCHAR  NULL
  remote  BOOLEAN  NULL  -- default True (app-level, not a DB DEFAULT)
  salary  VARCHAR  NULL
  description  TEXT  NULL
  apply_url  VARCHAR  NOT NULL
  tags  JSON  NULL  -- default: app-level callable list() — not a DB DEFAULT, set by the ORM on insert
  skills  JSON  NULL  -- default: app-level callable list() — not a DB DEFAULT, set by the ORM on insert
  seniority  VARCHAR  NULL
  embedding  VECTOR(512)  NULL
  posted_at  TIMESTAMP WITHOUT TIME ZONE  NULL
  fetched_at  TIMESTAMP WITHOUT TIME ZONE  NULL  -- default: app-level callable utcnow() — not a DB DEFAULT, set by the ORM on insert
  last_seen_at  TIMESTAMP WITHOUT TIME ZONE  NULL  -- default: app-level callable utcnow() — not a DB DEFAULT, set by the ORM on insert
  UNIQUE (source, external_id)

applications:
  id  UUID  NOT NULL  PRIMARY KEY  -- default: app-level callable gen_uuid() — not a DB DEFAULT, set by the ORM on insert
  profile_id  UUID  NOT NULL  -- FK -> profiles.id ON DELETE CASCADE
  job_id  UUID  NOT NULL  -- FK -> jobs.id
  status  applicationstatus  NULL  -- default <ApplicationStatus.saved: 'saved'> (app-level, not a DB DEFAULT)
  portal  VARCHAR  NULL
  notes  TEXT  NULL
  tailored_resume_json  JSON  NULL
  tailored_cover_letter  TEXT  NULL
  applied_at  TIMESTAMP WITHOUT TIME ZONE  NULL
  next_follow_up_at  TIMESTAMP WITHOUT TIME ZONE  NULL
  created_at  TIMESTAMP WITHOUT TIME ZONE  NULL  -- default: app-level callable utcnow() — not a DB DEFAULT, set by the ORM on insert
  updated_at  TIMESTAMP WITHOUT TIME ZONE  NULL  -- default: app-level callable utcnow() — not a DB DEFAULT, set by the ORM on insert
  UNIQUE (profile_id, job_id)

resume_facts:
  id  UUID  NOT NULL  PRIMARY KEY  -- default: app-level callable gen_uuid() — not a DB DEFAULT, set by the ORM on insert
  profile_id  UUID  NOT NULL  -- FK -> profiles.id ON DELETE CASCADE
  category  VARCHAR  NOT NULL
  achievement  TEXT  NOT NULL
  proof  TEXT  NULL
  metric  VARCHAR  NULL
  tags  JSON  NULL  -- default: app-level callable list() — not a DB DEFAULT, set by the ORM on insert
  period_from  DATE  NULL
  period_to  DATE  NULL
  embedding  VECTOR(512)  NULL
  created_at  TIMESTAMP WITHOUT TIME ZONE  NULL  -- default: app-level callable utcnow() — not a DB DEFAULT, set by the ORM on insert

matches:
  id  UUID  NOT NULL  PRIMARY KEY  -- default: app-level callable gen_uuid() — not a DB DEFAULT, set by the ORM on insert
  profile_id  UUID  NOT NULL  -- FK -> profiles.id ON DELETE CASCADE
  job_id  UUID  NOT NULL  -- FK -> jobs.id ON DELETE CASCADE
  score  NUMERIC(5, 2)  NOT NULL
  breakdown  JSON  NOT NULL
  state  VARCHAR  NOT NULL  -- default 'new' (app-level, not a DB DEFAULT)
  created_at  TIMESTAMP WITHOUT TIME ZONE  NULL  -- default: app-level callable utcnow() — not a DB DEFAULT, set by the ORM on insert
  UNIQUE (profile_id, job_id)

events:
  id  BIGINT  NOT NULL  PRIMARY KEY
  user_id  UUID  NOT NULL  -- FK -> users.id ON DELETE CASCADE
  type  VARCHAR  NOT NULL
  payload  JSON  NOT NULL
  created_at  TIMESTAMP WITHOUT TIME ZONE  NULL  -- default: app-level callable utcnow() — not a DB DEFAULT, set by the ORM on insert
  published_at  TIMESTAMP WITHOUT TIME ZONE  NULL

notifications:
  id  UUID  NOT NULL  PRIMARY KEY  -- default: app-level callable gen_uuid() — not a DB DEFAULT, set by the ORM on insert
  user_id  UUID  NOT NULL  -- FK -> users.id ON DELETE CASCADE
  trigger  VARCHAR  NOT NULL
  channel  VARCHAR  NOT NULL
  template  VARCHAR  NOT NULL
  payload  JSON  NULL  -- default: app-level callable dict() — not a DB DEFAULT, set by the ORM on insert
  status  VARCHAR  NOT NULL  -- default 'pending' (app-level, not a DB DEFAULT)
  sent_at  TIMESTAMP WITHOUT TIME ZONE  NULL
  error  TEXT  NULL
  created_at  TIMESTAMP WITHOUT TIME ZONE  NULL  -- default: app-level callable utcnow() — not a DB DEFAULT, set by the ORM on insert

connector_runs:
  id  UUID  NOT NULL  PRIMARY KEY  -- default: app-level callable gen_uuid() — not a DB DEFAULT, set by the ORM on insert
  source  VARCHAR  NOT NULL
  token  VARCHAR  NULL
  fetched  INTEGER  NOT NULL  -- default 0 (app-level, not a DB DEFAULT)
  inserted  INTEGER  NOT NULL  -- default 0 (app-level, not a DB DEFAULT)
  failed  INTEGER  NOT NULL  -- default 0 (app-level, not a DB DEFAULT)
  error  TEXT  NULL
  notes  JSON  NULL
  duration_ms  INTEGER  NULL
  ran_at  TIMESTAMP WITHOUT TIME ZONE  NULL  -- default: app-level callable utcnow() — not a DB DEFAULT, set by the ORM on insert

resume_uploads:
  id  UUID  NOT NULL  PRIMARY KEY  -- default: app-level callable gen_uuid() — not a DB DEFAULT, set by the ORM on insert
  profile_id  UUID  NOT NULL  -- FK -> profiles.id ON DELETE CASCADE
  status  VARCHAR  NOT NULL  -- default 'parsing' (app-level, not a DB DEFAULT)
  draft_facts  JSON  NULL
  error  TEXT  NULL
  created_at  TIMESTAMP WITHOUT TIME ZONE  NULL  -- default: app-level callable utcnow() — not a DB DEFAULT, set by the ORM on insert
```

<!-- END GENERATED SCHEMA -->

### 1.1 `profiles.prefs` shape

```json
{
  "locations": ["Remote", "Bengaluru", "Berlin"],
  "remote_types": ["remote", "hybrid"],
  "salary_min": 1800000,
  "currency": "INR",
  "seniority": ["mid", "senior"],
  "company_size": ["seed", "series_a", "series_b"],
  "exclude_companies": ["example-corp"],
  "max_age_days": 21,
  "daily_application_cap": 20
}
```

## 2. API surface

Base: `/api/v1`. All endpoints except `/health` and `/auth/*` require
`Authorization: Bearer <jwt>`. All list endpoints are cursor-paginated
(`?cursor=&limit=`, max limit 100). Errors are RFC 7807 problem+json.

### 2.1 Profiles & facts

| Method | Path | Body / Query | Returns |
|---|---|---|---|
| `GET` | `/profiles` | — | `Profile[]` for current user |
| `POST` | `/profiles` | `{persona, headline, location, work_auth, prefs}` | `Profile` |
| `PATCH` | `/profiles/{id}` | partial | `Profile` |
| `POST` | `/profiles/{id}/resume` | multipart `file` (pdf/docx, ≤5MB) | `{upload_id, status:"parsing"}` |
| `GET` | `/profiles/{id}/resume/{upload_id}` | — | `{status, facts: FactDraft[]}` |
| `POST` | `/profiles/{id}/facts:bulk` | `{facts: FactIn[]}` | `Fact[]` — confirms parsed drafts |
| `GET` | `/profiles/{id}/facts` | `?category=` | `Fact[]` |
| `PATCH` | `/facts/{id}` | partial | `Fact` |
| `DELETE` | `/facts/{id}` | — | `204` |

Resume parsing is async. `POST /resume` returns immediately; the client polls the GET
until `status == "ready"`, then renders the fact-review screen. Facts are **not**
persisted until the user confirms via `facts:bulk` — parsed output is never silently
trusted.

### 2.2 Jobs & matches

| Method | Path | Body / Query | Returns |
|---|---|---|---|
| `GET` | `/matches` | `?profile_id=&min_score=&state=&q=&location=&remote_type=&salary_min=` | `Match[]` with embedded job |
| `PATCH` | `/matches/{id}` | `{state}` | `Match` |
| `GET` | `/jobs/{id}` | — | `Job` incl. `sources[]` and company dossier summary |
| `POST` | `/jobs:capture` | `CapturedJob` (from extension) | `{job_id, deduped: bool}` |

`POST /jobs:capture` is the extension's ingestion endpoint. It accepts a job scraped
from a page the user is viewing, normalizes it through the same pipeline as API
connectors, and returns the canonical job — deduping against Tier-1 records so a
LinkedIn capture of a role we already have from Greenhouse does not create a second row.

**`q`, `location`, `remote_type`, `salary_min` are a distinct concern from F6's semantic
score.** F6 already factors location/salary/skills into ranking at match-creation time;
these params let the user re-search and re-filter their *already-scored* matches list
after the fact ("show me only Berlin, remote, $150k+ from what already matched"). `q`
runs `plainto_tsquery('english', :q) @@ jobs.search_vector`, ranked with `ts_rank`, with
a `similarity(title, :q) > 0.3` fallback via `pg_trgm` for typo tolerance. No dedicated
search engine (Meilisearch/Elasticsearch) — `tsvector` + `pg_trgm` on Postgres is the
adopted pattern, following the live precedent in `docs/DEPENDENCIES.md` §3
(PeelJobs/opensource-job-portal).

### 2.3 Applications

| Method | Path | Body | Returns |
|---|---|---|---|
| `POST` | `/applications` | `{job_id, profile_id}` | `Application` (status `draft`) |
| `POST` | `/applications/{id}/prepare` | — | `202 {task_id}` — enqueues tailoring |
| `GET` | `/applications/{id}` | — | `Application` incl. `generations[]`, `flags[]`, artifact URLs |
| `POST` | `/applications:approve` | `{ids: uuid[]}` | `{approved: n, blocked: [{id, reason}]}` |
| `PATCH` | `/applications/{id}` | `{status?, notes?, next_follow_up_at?}` | `Application` |
| `GET` | `/applications` | `?status=&profile_id=` | `Application[]` |

**Approval invariant:** `POST /applications:approve` MUST reject any application whose
latest pass-2 generation contains a flag with `severity == "high"`. The response lists
it under `blocked` with the flag text. There is no override parameter. This is the
enforcement point for PRD Principle 1 and must be covered by a test.

### 2.4 Extension

| Method | Path | Body | Returns |
|---|---|---|---|
| `POST` | `/extension/pair` | `{pairing_code}` | `{install_token}` |
| `GET` | `/extension/queue` | — | `SubmissionManifest[]` for approved applications |
| `POST` | `/extension/result` | `{application_id, outcome, screenshot}` | `204` |

`SubmissionManifest` carries the ATS type, the apply URL, a field map, and 15-minute
signed URLs for the resume/PDF. It never carries the user's password or OAuth tokens.

### 2.5 Outreach

| Method | Path | Body | Returns |
|---|---|---|---|
| `GET` | `/outreach/candidates` | `?application_id=` | `Candidate[]` ranked by hook |
| `POST` | `/outreach/draft` | `{application_id, candidate_id}` | `{subject, body}` |
| `POST` | `/outreach/send` | `{application_id, to_email, subject, body}` | `Outreach` |
| `POST` | `/outreach/unsubscribe` | `{token}` (public, unauthenticated) | `204` |

**Send preconditions, checked in this order, all mandatory:**
1. Google OAuth connected and scope `gmail.send` granted
2. `to_email` not in `suppressions`
3. User's sends in trailing 24h < 10
4. Application status is `applied` (you may not ask for a referral for a job you
   haven't applied to)
5. Body contains the generated unsubscribe line

Any failure returns `422` with the specific unmet precondition. No partial sends.

### 2.6 Real-time events and notifications

| Method | Path | Body / Query | Returns |
|---|---|---|---|
| `GET` | `/events` | header `Last-Event-ID` (optional) | `text/event-stream` — SSE |
| `GET` | `/notifications` | `?status=` | `Notification[]` |
| `PATCH` | `/notifications/{id}` | `{status: "seen"}` | `Notification` — in-app read receipt |

`GET /events` is the single push channel for match updates (F6), application status
changes (F13), resume-parsing completion (F2), and new-notification signals — one
connection per session, not one per feature. On connect, if `Last-Event-ID` is present,
the server first replays every `events` row for that user with `id > Last-Event-ID`
(bounded to the last 500, oldest first) before subscribing live. This is what makes a
page refresh or a laptop waking from sleep not silently drop a status change — see
ARCHITECTURE.md §4.6 for the write path that feeds this table.

Notifications (`weekly_digest`, `follow_up_nudge`, `application_status`) are produced by
a dedicated RQ job per trigger, rendered from the `template` registry key, and delivered
over `email` (Gmail send-as-user, same path as outreach) or `in_app` (a `notification.created`
event pushed over `/events`). A notification's `status` tracks delivery
(`pending → sent | failed | skipped`), separate from whether the user has seen it in the
UI — read receipts are a client-side concern via `PATCH /notifications/{id}`.

## 3. Algorithms

### 3.1 Canonical hash / dedupe

```python
def canonical_hash(company_name: str, title: str, location: str | None) -> str:
    c = re.sub(r"\b(inc|llc|ltd|gmbh|pvt|private|limited)\b", "", company_name.lower())
    c = re.sub(r"[^a-z0-9]", "", c)
    t = re.sub(r"[^a-z0-9 ]", "", title.lower())
    t = re.sub(r"\b(sr|jr|i{1,3}|iv|v)\b", "", t).strip()
    t = re.sub(r"\s+", " ", t)
    loc = normalize_location(location)          # → "remote" | "city,country" | ""
    return hashlib.sha256(f"{c}|{t}|{loc}".encode()).hexdigest()
```

Collision policy: on conflict, keep the existing row, update `last_seen_at`, prefer the
Tier-1 `apply_url` over an aggregator's. Record the new source in `job_sources`.

### 3.2 Match score and its breakdown

```
semantic       = 1 - cosine_distance(profile.fact_centroid, job.embedding)   # 0..1
skill_coverage = |job.skills ∩ profile.skills| / max(1, |job.skills|)        # 0..1
recency        = clamp(1 - days_since_posted / 30, 0, 1)                     # 0..1

score = round(100 * (0.55*semantic + 0.30*skill_coverage + 0.15*recency), 2)
```

`breakdown` persisted as:

```json
{
  "semantic": 0.81,
  "skill_coverage": 0.78,
  "recency": 0.93,
  "matched_skills": ["python", "postgres", "fastapi", "docker", "aws", "redis", "ci"],
  "missing_skills": ["kubernetes", "terraform"],
  "hard_filters_passed": ["work_auth", "location", "salary", "seniority"]
}
```

The UI renders `missing_skills` verbatim. A score with no breakdown is a bug.

### 3.3 Tailoring passes — contracts

**Pass 1 output schema (strict, validated with Pydantic before persisting):**

```json
{
  "summary": "string, 2 sentences",
  "bullets": [{"text": "string", "source_fact_ids": ["uuid"]}],
  "cover_letter": "string, 150-200 words",
  "keywords_targeted": ["string"]
}
```

`source_fact_ids` is mandatory per bullet. A bullet that cites no fact is rejected at
validation, before the truth-checker even runs — that is a cheap, deterministic first
line of defence.

**Pass 2 output schema:**

```json
{
  "flags": [
    {"claim": "string", "severity": "high|medium|low", "reason": "string",
     "location": "summary|bullet:{n}|cover_letter"}
  ]
}
```

Severity rubric, stated in the prompt so it is consistent:
- `high` — a specific achievement, metric, employer, title, or credential not in the KB
- `medium` — a plausible generalization the KB partly supports
- `low` — tone or emphasis, no factual content

**Pass 3** takes pass-1 text plus a 300-word register sample from the user's original
resume and returns the same schema as pass 1, with `source_fact_ids` preserved
unchanged. If pass 3 alters `source_fact_ids`, the output is discarded and pass 1's text
is used.

**Model routing** (see `docs/DEPENDENCIES.md` for versions): pass 1 and pass 3 use the
strong model; pass 2 and all extraction/classification use the cheap model. Model IDs
live in config, never hardcoded in the engine.

### 3.4 ATS detection

```
for path in ["/careers", "/jobs", "/join-us", "/work-with-us"]:
    resp = safe_fetch(domain + path, follow_redirects=True)   # SSRF-guarded
    for pattern in ATS_PATTERNS:
        if m := pattern.regex.search(resp.final_url + resp.text[:200_000]):
            return pattern.ats_type, m.group("token")
return None
```

`ATS_PATTERNS` includes the boards listed in PRD §6/F4. The detector runs against a
company seed list nightly and is idempotent — re-detection updates
`companies.ats_type/ats_token` only when it finds a different, verified board.

**Unknown-ATS classification (added Phase 4, F5).** `discover_ats_for_domain(db,
domain)` is the real call site: it tries `detect_ats()` first, and only when that
returns `None` does it spend a bounded, single Claude/nvidia_smoke call (ADR-011 —
one pass, not F11's multi-pass budget) via `classify_unknown_ats(domain)`. That
function reuses the same `is_safe_url()` SSRF guard and `CANDIDATE_PATHS` fetch as
`detect_ats()` — no new fetch surface — and asks the model to identify the ATS vendor
from page evidence (JS bundle URLs, iframe `src`, vendor branding) and propose a
single-capture-group regex for the board token, grounded in concrete evidence, never
inventing a pattern with none.

The proposal is **never auto-promoted** into `ATS_PATTERNS` — every attempt (whether
a candidate was found or not) is logged as a `connector_runs` row (`source =
"ats_discovery_classify"`, `token = domain`, `notes` = the parsed proposal JSON or
`null`, `failed = 1` when no candidate was found). This row *is* the review surface —
decided against a new table or admin UI; the owner reads `connector_runs` directly
and manually adds a verified pattern to `ATS_PATTERNS` in code.

### 3.5 ATS-safe document rules (enforced, not advisory)

The renderer must satisfy all of these, and `tests/test_ats_safety.py` asserts each by
inspecting the generated DOCX XML:

1. Zero `<w:tbl>` elements (no tables)
2. Zero `<w:txbxContent>` elements (no text boxes)
3. Empty header and footer parts
4. Zero embedded images
5. Section headings drawn only from `{Summary, Experience, Skills, Education, Projects}`
6. Single section, single column (`<w:cols w:num="1"/>`)
7. Fonts limited to a safe list, embedded
8. Dates matching `^[A-Z][a-z]{2} \d{4} – ([A-Z][a-z]{2} \d{4}|Present)$`

**Parse-back check:** render → extract text with `pdfplumber`/`python-docx` → fuzzy-match
each bullet against its source fact at ≥0.9 similarity. Any bullet that fails to survive
the round trip fails the build.

### 3.6 Idempotency for retried background jobs

RQ retries a job on worker crash or timeout (ADR-008). Without an idempotency guard, a
retried `prepare` job re-runs all three tailoring passes, double-calling the Anthropic
API and — before the fix below — creating duplicate `generations` rows. This is a
correctness bug and a live cost bug: it silently defeats
`MAX_MODEL_SPEND_USD_PER_USER_PER_MONTH` (§6), which has no other enforcement mechanism.

Two layers, both required — the first prevents a duplicate *enqueue*, the second
prevents a duplicate *execution* of an already-running job:

1. **Enqueue dedupe.** The RQ job ID for a tailoring run is derived deterministically:
   `job_id = f"prepare:{application_id}:{attempt_epoch}"`, enqueued with `at_front=False,
   job_id=job_id` — RQ's own `job_id` uniqueness means a second `POST .../prepare` call
   for a job already queued or running returns the existing `task_id` instead of
   enqueuing a duplicate.
2. **Execution claim.** Before calling Claude for pass *N*, the worker attempts
   `SETNX idempotency:{application_id}:{pass}:{attempt} <worker_id> EX 300` against
   Redis. If the claim fails (another worker already holds it — e.g. a retry that races
   a still-running original), the worker skips the call and polls `generations` for the
   row the original run will produce, rather than re-calling the API.
3. **Database backstop.** The `UNIQUE (application_id, pass, attempt)` constraint on
   `generations` (§1) makes a duplicate insert impossible even if both of the above
   somehow fail — the second `INSERT` errors, the worker catches it, and treats it as
   "already done" rather than a hard failure.

This pattern generalizes to any RQ job with an external side effect (Anthropic calls,
Gmail sends, ATS submissions) — derive the job ID from the business key, claim before
the paid/irreversible action, and back it with a DB constraint. Outreach sending already
has an equivalent guard via its send-precondition checks (§2.5); this section makes the
pattern explicit so new job types don't have to rediscover it.

### 3.7 F11 — bounded form-fill agent

No section for F11 existed anywhere in this document before Phase 4 (plan item 4) —
only ADR-011/PRD §"F11 — Submission" narrative-level description. This is the real
engineering-detail authoring that closes that gap.

**Flow, end to end.** The user clicks "Fill this form" in the extension popup on an
ATS application page. The already-injected content script (matches every page except
`linkedin.com`, per ADR-002) extracts a `FieldDescriptor[]` from every `<input>`,
`<select>`, and `<textarea>` on the page — `field_id` (a stable per-page index),
`label_text` (nearest `<label for>`, else `aria-label`, else `placeholder`),
`input_type`, `options` (for select/radio), `required`. This is POSTed, with the
user's JWT (extension stores it in `chrome.storage.local` after the same
`/auth/login` the web app uses — no separate extension auth flow), to a new backend
endpoint, never to Anthropic/NVIDIA directly from the content script (a raw API key
must never ship in extension code, ADR-011's own framing plus basic key-exposure
hygiene).

```
POST /extension/map-fields
  body: {url, fields: FieldDescriptor[]}
  auth: same Bearer JWT as every other endpoint
  → one bounded Claude/nvidia_smoke call (ADR-011: single pass; F11's own design per
    DECISIONS.md is literally "one Claude call returns field mappings", not a
    multi-round loop — the 2-3 pass ADR-011 ceiling covers a defensive retry on a
    malformed/unparseable response, not a reasoning loop)
  → FieldMapping[]: {field_id, maps_to, confidence, value}
      maps_to  = "profile.<attr>" | "resume_fact:<category>" | "literal:<short-string>" | "unknown"
      confidence = 0.0-1.0
      value    = the string to fill, present when maps_to != "unknown"
```

The backend call is grounded in the profile's own data (name, email, phone, location,
resume-fact categories/tags — never the raw resume blob, ADR-009) — the model may only
select from what's given, the same "never invent" constraint tailoring's pass 1 uses.

**Confidence threshold: 0.75.** A field with `confidence >= 0.75` and a resolvable
`maps_to` is auto-filled. Below that, or `maps_to == "unknown"`, the field is flagged
for the user instead — never guessed into a wrong answer.

**Hard-coded exclusions, enforced client-side, independent of model confidence.**
Regardless of what the model returns, any field whose `label_text` matches a
demographic/EEO/essay keyword list (race, ethnicity, gender, veteran status,
disability status, sexual orientation, "why do you want to work here" and
equivalents) is always flagged, never auto-filled — PRD §"F11 — Submission"'s
"never auto-answers demographic/EEO questions" and "never auto-answers 'why do you
want to work here'" are non-negotiable product rules, not something a confidence
score should be able to override. This check runs in the extension before any field
is written, not only in the backend prompt — a defense-in-depth pair, not a single
point of failure.

**Human-fallback UI (MVP scope this pass).** Auto-filled fields get a visible
highlight (border + a small "auto-filled by Job Copilot" marker) so the user can see
what changed before they hit the ATS's own Submit button — nothing here submits
anything (ADR-001's approval gate is untouched, F11 only fills). Flagged fields get a
highlighted border and a title-attribute note naming why (`low_confidence` or
`demographic_or_essay`). **Deferred, not built this pass:** the richer
`ShadowRoot`-mounted, Constructable-StyleSheet Tailwind banner ARCHITECTURE.md's
"Extension UI isolation" section specifies — this pass uses plain inline-style DOM
attributes on the actual form fields, which needs no shadow-root/portal work at all
and is visually correct on any host page without CSS isolation concerns, but doesn't
give a single consolidated summary view. Upgrade trigger: once a real ATS page is
tested and the inline-highlight approach turns out to be hard to spot amid the host
page's own styling.

**Validation against real forms — explicitly scoped as fixture-based, not live.**
PRD's exit criterion ("validate against 15-20 real Greenhouse/Lever/Workday forms")
cannot be met by server-side scraping of those forms even for test fixtures — ADR-002
forbids that regardless of purpose. Fixtures must be user-side HTML captures the owner
provides (save-page-as from a real, logged-out application form), consistent with
SPEC §5's connector fixture-testing pattern. **None exist yet as of this pass** — not
fabricated here; the field-decision logic below is unit-tested against small synthetic
DOM shapes, which is real coverage of the logic but is NOT the PRD's 15-20-real-form
accuracy claim. That claim stays open until the owner supplies real captures.

## 4. State machines

### Application

```
draft ──prepare──▶ ready_for_review ──approve──▶ approved ──submit──▶ applied
                          │                          │                   │
                          └──── prepare (retry) ──────┘                   ├─▶ oa
                                                                          ├─▶ recruiter ─▶ interview ─▶ offer
                                                                          ├─▶ rejected
                                                                          └─▶ withdrawn
```

Illegal transitions return `409`. `approved → applied` may only be set by
`POST /extension/result` or an explicit manual override with `submitted_via="manual"`.

### Outreach

```
drafted ──send──▶ sent ──(no reply, +6d)──▶ followed_up ──▶ closed
                    └──reply detected──▶ replied (terminal)
```

At most one follow-up. Ever.

## 5. Testing requirements

| Layer | Requirement |
|---|---|
| Connectors | Each has a recorded-fixture test (VCR-style). No live network in CI |
| Dedupe | Property test: same job from 3 sources → exactly 1 `jobs` row, 3 `job_sources` |
| Tenancy | Generated test over the route table: every `{id}` endpoint 404s cross-user |
| Tailoring | Golden-file tests on a fixed KB + JD with a stubbed model client |
| Truth-check | Adversarial fixtures: JDs containing prompt injection must produce `high` flags. **Extended (ADR-014): the same fixture set applies to company-dossier content, not just JDs** — a poisoned dossier is the same attack surface, unguarded until this is added |
| Approval gate | Application with a `high` flag cannot be approved — direct API test |
| Documents | ATS-safety assertions (§3.5) + parse-back check |
| Prompt regression (ADR-014) | Promptfoo golden-set eval (≥30 JD/facts pairs) runs in CI on any `tailoring/` prompt change; a new prompt version must not regress the LLM-judge quality score or the truth-check flag rate vs. the version it replaces. Golden set + run history persisted in Langfuse Datasets |
| Injection red-team (ADR-014) | `garak` scan against custom Generator wrappers for both the JD-field and dossier-field injection points, using the adversarial fixtures above as probe payloads. Runs pre-release, not on every commit (slower scan) |
| E2E | Playwright: signup → upload → review facts → match → prepare → approve |

Coverage floor 80% on `apps/api`. The approval gate, suppression check, and tenancy
guard require 100% branch coverage — these are the three places a bug is not recoverable.

## 6. Configuration

```
DATABASE_URL, REDIS_URL
ANTHROPIC_API_KEY
MODEL_STRONG, MODEL_CHEAP          # ids in config, never in code
S3_ENDPOINT, S3_BUCKET, S3_KEY, S3_SECRET
GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET
JWT_SECRET, ENCRYPTION_KEY
SENTRY_DSN
OUTREACH_DAILY_CAP=10
MAX_MODEL_SPEND_USD_PER_USER_PER_MONTH=15
```

All are validated at startup by a Pydantic `Settings` object. A missing required var
fails the boot — never `None` propagating to a 401 at 3am.

---

## Related documents

`docs/PRD.md` · `docs/ARCHITECTURE.md` · `docs/DECISIONS.md` · `docs/DEPENDENCIES.md` ·
`docs/CODE-REVIEW.md` · `docs/WORKLOG.md`
