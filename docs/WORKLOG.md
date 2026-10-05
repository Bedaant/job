# Job Copilot — Worklog

**Purpose.** This is the context-recovery document. If a session loses context, or a new
person (or agent) picks up the work, **read this file first** — it says where the project
stands, what was decided, what is in flight, and what to do next.

**Rule.** Every change to this repo gets an entry here, appended at the top. An entry
records what changed, why, which files, and what broke. Errors and dead ends are recorded
too — a failed approach that is not written down gets retried by the next person.

---

## Current state — read this first

**As of 2026-10-03 (latest+69).** Product is **ApplyScout**, agent **Maggie** (ADR-015).
Autonomous multi-source auto-apply: the user approves a campaign once, then agents
discover → tailor → submit through the user's own browser.

- **Two plans run in parallel, and a bare "Phase N" is ambiguous — always use the prefix.**
  `docs/PLAN-JOB-COLLECTION.md` → stages `COLLECT-A…F` (getting jobs into the pool).
  `docs/PLAN-MULTI-ATS.md` → stages `ATS-0…3` (filling and submitting forms, ADR-016).
- **Collection:** COLLECT-A (freshness, ADR-017) and COLLECT-B (resilience) are **done**.
  COLLECT-C (reach) is next and **starts with an ADR, not code** — 19 of 22 Indian
  consumer-tech companies have no board on greenhouse/lever/ashby, measured live.
- **Forms:** plan routing is live for **Greenhouse only**; Lever and Ashby measured no gain
  on required fields (latest+59), so ATS-3's premise needs rethinking before it is executed.
- **LLM provider is NVIDIA NIM** (`LLM_PROVIDER=nvidia`, nemotron-3-super), not Anthropic —
  ADR, latest+34. `ANTHROPIC_API_KEY` is still a placeholder, which no longer blocks the
  product; it blocks only the ADR-014 eval harness, and that harness is pointed at the wrong
  provider. **Tailoring quality is currently unmeasured** (`GAPS.md` 6.1).
- 824 tests passing. Neon at migration 0022 — **0022 has never run against a real Postgres.**
- `apps/extension/` builds (the stray `D:\postcss.config.mjs` is handled by
  `css: { postcss: {} }` in its `vite.config.ts` — that blocker is **fixed**, despite what
  older entries say).

**👉 `docs/GAPS.md` is the open-items register** — 31 gaps across all phases, each marked
VERIFIED or DOC-CLAIM with its evidence. Read it before planning anything; it records five
places these docs were actively wrong, including an ADR-015 contradiction still live in the
extension code.

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

### 2026-10-05 (latest+81) — ADR-020: all four India job boards evaluated in parallel; every unlicensed India route is closed

**What changed.** Four parallel read-only feasibility probes, one per board, then ADR-020. Docs
only; 871 tests unchanged.

**Method.** One agent per board, each capped at ~15 requests ≥1s apart with a plain identifying
User-Agent, instructed to fetch `robots.txt` first and to **report** the posture rather than work
around it. **No UA spoofing, no login, no challenge solving** — the rails ADR-018 §9 and ADR-019
set.

| Board | robots.txt | Technical reality | Effort if licensed | Verdict |
|---|---|---|---|---|
| Instahyre | **wide open**, zero `Disallow` | public unauthenticated JSON API, 12,973 jobs, **753 PM-in-Bangalore**, company names present | **~half a day** | `legally-prohibited` |
| Cutshort | permissive + **44,320-URL** sitemap | anonymous `JobPosting` JSON-LD with **salary + datePosted + directApply** | **~1 day** | `legally-prohibited` |
| Hirist | permissive + **31,029-URL** daily sitemap | JS-only: SSR ships field names with values **blanked**, anti-bot slice armed | low | `legally-prohibited` |
| Naukri | **403 — cannot read it** | hard Akamai 403 on every path at request one | n/a | `blocked` |

**The finding that generalises: `robots.txt` was uncorrelated with permission, and pointed the
opposite way in three of four cases.** Instahyre's has zero `Disallow` lines while its ToS bans
"crawl or spider" and commercial use "whether or not for profit". Hirist and Cutshort publish
31k/44k-URL job sitemaps while their terms ban crawling and commercial derivative works.
**Technical ease ran inversely to permission** — the easiest source to ingest carries the most
explicit ban. Same lesson the SmartRecruiters brief drew, now confirmed four more times, and
ADR-020 makes it a rule: **quote the terms, not the robots file.**

**Two boards name this exact product.** Instahyre bars using the platform to build "a competitive
product or service"; Naukri's terms prohibit extraction "(by any process, whether automatic or
manual)" to offer products that "compete with the Company's services".

**Cutshort's terms foreclose ADR-015's legal shield.** Their automated-access provisions cover
"bots, scraping, **browser extensions**, data extraction". ADR-015's posture is execution "via the
user's own browser session, never a shared server bot"; for that source the argument is explicitly
named and rejected. ADR-020 §6 records that it does not generalise.

**Naukri is a different category** — access control, not terms. Its edge 403s a
plainly-identified client on every path, including `robots.txt` and the ToS page itself.
Extraction would need UA spoofing plus TLS-fingerprint matching, i.e. evasion, and no
degraded-but-legal fallback exists.

**Honesty note preserved from the probe:** the Naukri ToS quotes are from a search engine's
**index** of the page, not a response we received (it 403s). Labelled second-hand in both the
report and the ADR rather than presented as first-party.

**Decision (ADR-020).** No unlicensed ingestion from any of the four. Licensing is the only
sanctioned route and it is a business action — integration is half a day to a day *once
credentialed*, so the permission is the entire cost. Coverage is stated honestly rather than
quietly capped: global-remote roles, India roles at multinational GCCs via Workday, and Indian
companies that happen to use Greenhouse/Lever/Ashby — **23 live India product roles**.

**Files changed.** New `docs/harness-reports/india-job-boards-feasibility.md`,
`docs/DECISIONS.md` (ADR-020), `docs/GAPS.md` (3.1 closed), `docs/PLAN-JOB-COLLECTION.md`.

**Dependencies added.** None. **Tests.** 871, unchanged — no code in this entry.

**Problems hit.** A shell heredoc chain broke on quoting again and silently ran nothing (the
earlier doc edits had already landed, so the state was half-applied). That is the lesson from
latest+64 for the third time: **write prose and anything with quotes using the file tools, not
shell heredocs.**

**Next.** The remaining cheap lever is more board tokens on already-permitted platforms via
`tools/ats_token_probe.py` — paytm and mindtickle were both surfaced that way, and the slug list
is the limiting factor, not the method. SmartRecruiters (ADR-018 §7) is now relatively more
valuable as the only permitted-shaped route to a major Indian consumer company, still gated on
reading the SAP API Policy. SMTP and the first real submit remain with the owner.

### 2026-10-05 (latest+80) — GAPS 6.7 resolved: hard gate 1/30 -> 21/30, and the harness regression I had introduced

**What changed.** The owner ruled on GAPS 6.7 — the model checker's findings are **framing, not
fabrication** — and it is implemented, deployed and measured. 864 -> 871 tests. Migration 0024
applied to Neon the same session, not left pending.

**The split.** `truth_check` now returns its two halves separately instead of concatenating them
(concatenation was what made the gate un-splittable at the call site). New
`split_gate_findings()`: `deterministic_unsupported` is the **hard gate**, the model checker's
audit becomes **advisory**, duplicates across the halves reported once. `Application.advisory_claims`
(migration 0024) persists it, `batch_prep` writes it, three schemas expose it. `main.py:161` is
untouched and now does the right thing by construction, because it keys off
`flagged_unsupported_claims`, which is deterministic-only.

**Measured end to end on the 30-row golden set:**

| | before | after |
|---|---|---|
| hard gate | **1 / 30 (3%)** | **21 / 30 (70%)** |
| bullets grounded | 107 / 107 | **111 / 111** |
| advisory findings | n/a — all blocked | 136, mean 4.5/row, non-blocking |

**The 9 remaining blocks are the right ones.** The cover letter names the *job's* technology when
the candidate's facts do not contain it — flagged terms `iOS`, `Swift`, `Rust`, `React`, `SQL`,
`SRE`, `Machine Learning`, `SEO`, e.g. `"I am applying for the Staff iOS Engineer position at
Harborlight." [not in facts: iOS]`. That is the claim that gets an application binned, and it is
now what blocks instead of "Proven ability to…". Left deliberately imprecise: that sentence
arguably names the *role* rather than claiming the skill, and the gate cannot tell those apart,
so it blocks conservatively — a false block costs one application, a false pass costs credibility.

**A regression I had introduced, found by this run.** latest+77 removed the broken NIM grader on
the reasoning that "a configured-but-broken grader fails every row for the wrong reason". That
was wrong in effect: with an `llm-rubric` in `__expected` and **no** grader key, promptfoo does
not fail the soft gate — it **errors the whole test** before the python assertion runs, recording
no response and no component results. The first verification run returned `0 passed, 0 failed,
30 errors` and zero usable data, and it invalidated the instruction I had written into three
documents ("read the per-assertion results out of the JSON") — there were none to read. Removing
the grader had made the harness strictly worse than leaving it in.

Fixed by moving the rubric text from `__expected` into a `rubric_needs_grader` column, so
promptfoo stops treating it as an assertion. The rubric is preserved for whenever an independent
grader key exists; the hard gate now produces real numbers.

**The accepted cost, recorded in code.** `deterministic_unsupported` only sees names in
`matching/skills.py`'s vocabulary plus digits; its own docstring says an invented domain or
outcome in plain words is "left to the model checker". That path is now advisory, so such a claim
can reach an employer unless a human reads the advisory list — 136 of them on this set.
ADR-006's no-fabrication rail now **binds on concrete claims and advises on prose**. Stated in
`split_gate_findings`' docstring so it cannot later read as an oversight. Related: the
`nvidia_smoke` path has no deterministic half, so it now has **no hard fabrication gate at all**.

**Files changed.** `apps/api/tailoring/engine.py`, `apps/api/models.py`, `apps/api/batch_prep.py`,
`apps/api/schemas.py`, new `apps/api/alembic/versions/0024_application_advisory_claims.py`, new
`apps/api/tests/test_truthcheck_gate_split.py`, `apps/api/tests/test_tailoring_engine.py`;
`eval/golden.csv` (column rename), `eval/promptfooconfig.yaml`,
`docs/harness-reports/adr014-first-eval-run.md` (second correction), `docs/GAPS.md` (6.7 resolved,
6.8 updated), `.gitignore`.

**Problems hit.** Fifth wrong call of the same shape this week: I reasoned about what promptfoo
*should* do with a missing grader instead of checking what it *does*. Same as the NIM grader, the
`[not in facts:]` format, F5's premise and the migration state. The difference is that this one
was caught by the verification run I had deliberately gated the merge on, rather than by the
owner later.

**Next.** India coverage is the remaining product question (ADR for Indian job boards, or accept
the measured ceiling). SMTP still needs credentials; the first real submit still needs the owner.

### 2026-10-05 (latest+79) — Migrations 0022/0023 applied to Neon; F5 measured; the ATS coverage ceiling is now a measurement

**What changed.** Three things, the first of which was urgent.

**1. Neon was two migrations behind, and HEAD was incompatible with it.** Asked "is job
gathering resolved", I queried the real database and `delisted_at` **did not exist**: Neon was at
revision **0021**, so **0022 (delisted_at, indexes, dropping `uq_jobs_canonical_hash`) and 0023
(board_token) had never been applied.** Everything from COLLECT-A onward was merged, tested
against in-memory SQLite, and **not live** — and worse, `upsert_jobs` writes `board_token` and
`_sweep_delisted` filters on `delisted_at`, so a discovery run against Neon would have **errored
out**, not degraded. I had been repeating "0022 has never run against a real Postgres" as a risk
to watch; the accurate statement was that the feature was undeployed and HEAD was broken against
production.

Applied `alembic upgrade head` with no worker or scheduler running. Verified after: revision
**0023**, both columns present, `uq_jobs_canonical_hash` dropped as ADR-017 §5 requires, three
indexes built, **1,848 rows intact**. Then exercised the insert path that would have crashed —
`upsert_jobs` against real Neon inside a transaction, rolled back, 0 synthetic rows left.

**The pool, measured for the first time:** 1,848 live jobs; 266 live product roles; **23 live
product roles in India**; 1,827 embedded. By source, arbeitnow 1,051 / jobicy 154 / himalayas 131
/ reed 121 / remoteok 100 / wwr 97 / **greenhouse 90 / ashby 16 / lever 14**. Every one of the 23
India product roles comes from the ATS boards (zeta, meesho, mongodb, inmobi, okta). **The 1,588
aggregator-feed rows contribute essentially zero India product roles** — 86% of the pool, ~0% of
the value for this search.

**2. F5 measured: 1 correct of 9, and the cause is structural.** `detect_ats` regexes a careers
page for an ATS URL. On companies whose ATS we already knew, only supabase resolved. The reason
is not the regex: `okta.com/careers` is 290 KB with no ATS string anywhere, `meesho.com` returns
the same 47 KB SPA shell for every candidate path, `swiggy.com` 403s on all of them. The board
link appears only after JS, or on another host, or is blocked. Fixing that needs a headless
browser per company — declined twice already.

**3. The inversion, and the ceiling.** Instead of asking what ATS a company uses by crawling it,
ask whether a platform has a board for a slug. That is keyless, JS-free and definitive, and it is
now a committed tool — **`tools/ats_token_probe.py`** — rather than the scratch scripts
COLLECT-B/C used. Probing all 19 unreachable companies across greenhouse/lever/ashby/
smartrecruiters/workable:

- **paytm → lever: added.** 173 postings, 129 India-located, incl. an Associate Product Manager
  in Noida. **Found by F5**, and the reason matters: `paytm` was absent from COLLECT-B's 117-slug
  list. Platform probing is only as good as its slug list; F5 works from the domain side. The two
  are **complementary** — that is the real finding, not "F5 is bad".
- **swiggy → smartrecruiters**, still blocked on ADR-018 §7.
- **cars24** → an abandoned SmartRecruiters account, newest posting **2018-01-17**, caught by the
  recency check built into the tool.
- **The other 16 are on none of the five platforms at all.**

**So more ATS tokens and better ATS discovery cannot solve India coverage. That avenue is
exhausted, and it is now a measurement rather than a guess.** Only two honest paths remain: a
source with cross-company India search (Naukri/Instahyre/Hirist/Cutshort — no public API, so
scraping, needs an ADR), or accept the ceiling and state coverage honestly.

**Files changed.** New `tools/ats_token_probe.py`, new
`docs/harness-reports/f5-classifier-and-ats-coverage-ceiling.md`;
`apps/api/connectors/config.py` (paytm + its display name), `docs/GAPS.md` (3.1).

**Dependencies added.** None. **Tests.** 864, unchanged — plus the config guards in
`test_board_tokens.py` cover the new token.

**Problems hit.** My own framing of the migration risk was too soft for three consecutive
sessions. "Has never run against a real Postgres" reads like a caveat; "the feature is not
deployed and HEAD would crash against production" is what it actually meant. Worth remembering
that a schema caveat and a broken deployment are the same sentence until someone queries the
database.

**Next.** GAPS 6.7 (the truth-check blocking ~97% of applications) is still the decision that
gates everything downstream. For coverage, the remaining choice is the Indian-job-board ADR or
accepting the ceiling; the cheap middle step is running `ats_token_probe.py` over a much longer
Indian-startup slug list, since paytm shows the list is the limiting factor.

### 2026-10-04 (latest+78) — GAPS 6.7 re-measured: the cause was the opposite of what latest+77 said

**What changed.** Measurement and documentation only. No code. Tests unchanged at 864.

**latest+77 named the wrong half of the truth-check, and it was already merged.** It said every
flag came from `deterministic_unsupported`, "pass 2's model-free half". Measured properly, by
calling the two halves separately on 5 rows:

| half | flags |
|---|---|
| `deterministic_unsupported` (model-free) | **0** |
| model checker (`STRICT_CHECK_SYSTEM`) | **31** |

The deterministic half is clean; the model checker produces **100%** of the flags. The inference
error: both halves build their flag strings in the same `"<claim> [not in facts: …]"` format, so
the suffix proves nothing about origin. I read a format and called it a cause.

**And the model checker is not misbehaving — it is following its instructions exactly.**
`STRICT_CHECK_SYSTEM` tells it to flag "added outcomes or purposes", "scope or scale", and
"domains, tools, numbers, **titles**, durations and **praise adjectives**". So flagging
`"Senior Backend Engineer with expertise in Python, FastAPI…"` and `"Proven ability to design
high-performance backend systems"` is correct behaviour under its own spec.

**The real finding is a specification conflict between the two passes.** Pass 1 is asked for "a
2-sentence professional summary" and a cover letter — prose that inherently carries titles, scope
and evaluative framing — while pass 2 is instructed to flag precisely those. The gate is not
accidentally strict; **the two prompts disagree about what a résumé sentence may contain.**

**One option is now measured and eliminated.** A/B on the same 10 rows, augmenting only the
tailor prompt (the truth-check prompt untouched, or the test would be circular): adding an
explicit "do not name any tool or number not in the KB" rule for the summary and cover letter
changed **nothing** — 10/10 rows flagged in both arms, ~5.5 flags/row both arms, mean summary
length 200 → 206 chars. A one-line constraint does not move this.

Remaining options are recorded in `GAPS.md` 6.7 and the corrected report. The one I would look at
first is making the **deterministic half the hard gate** and the model half advisory: it had zero
false positives across these rows and is precise about the fabrication that actually gets
applications binned (unlisted tools and numbers). The cost is explicit in its own docstring — it
cannot see an invented outcome in plain words.

**Files changed.** `docs/harness-reports/adr014-first-eval-run.md` (correction block at the top of
the affected section, original text left intact beneath it), `docs/GAPS.md` (6.7 cause + options),
this entry.

**Problems hit.** This is the **fourth** wrong diagnosis I have put in writing on this project,
and the **second inside a document that was already merged and presented** — after 6.1, 4.4 and
§2. The pattern is identical every time: I read one signal (a file's presence, a placeholder key,
a flag's string format) and wrote a cause from it. The correction is kept visible rather than
silently edited, because the wrong version had already been acted on.

**Next.** 6.7 is still the owner's decision and still the highest-value open question — it decides
whether applications can be sent at all. It is now a precise decision rather than a vague one, and
one of its four options is eliminated by measurement.

### 2026-10-04 (latest+77) — ADR-014's harness completed a run for the first time, and it found something

**What changed.** The eval harness runs end to end and produced the project's first tailoring
quality measurement. Config-only; no engine change.

**A third blocker had to be cleared.** latest+75 fixed the golden-set fact ids; this run hit
another: **promptfoo spawns the Python provider with the system interpreter**, so `import
instructor` inside `tailoring/engine.py` failed, the worker crash-looped 3x and the run stalled
with no useful error. That was the 20-minute "hang" that looked like slow LLM calls. Pinned via
`config.pythonExecutable` in `promptfooconfig.yaml` (the key is read by the python provider
itself — confirmed by reading promptfoo 0.120.19's own bundle, not from docs). So ADR-014's
harness had never completed a run since it was built.

**The result — read per-assertion, not the headline.** promptfoo prints `0 passed, 30 failed`
and that number is meaningless, because a row fails if *any* assertion fails and the rubric gate
is broken (below). Per gate:

- **Pass 1 (drafting) is clean: 107 bullets across 30 rows, every one citing a real fact id,
  zero ungrounded.** `TailoredDraft`'s validation is doing its job.
- **Pass 2 (truth-check) flags 29 of 30 rows** — every one from `deterministic_unsupported`,
  the model-free half, firing on a technology name or number in the **summary or cover letter**.
  Never on a bullet. The bullets cite facts; the prose generalises past them ("…real-time event
  pipelines using Kafka and Py…").

**Why that is the most useful thing the harness has produced.** `main.py:161` filters the
ready/work queue to applications with **no** `flagged_unsupported_claims` — flagged means **not
sent**. So on this golden set **~97% of applications would never be sent, while every bullet is
correctly grounded.** Recorded as `GAPS.md` 6.7 and left as an **owner decision, not a quiet
patch**: constrain summary/cover-letter language to facts-only, scope the hard gate to bullets
and treat prose flags as warnings, or keep maximum safety and accept that almost nothing sends.
Three different products; ADR-006/009 are deliberately strict and this is their trade-off with a
number on it for the first time.

**The rubric grader is removed, not left broken.** Pointing `llm-rubric` at NIM's
OpenAI-compatible endpoint failed — 16x "No output", 4x "Could not extract JSON" — because
`nemotron-3-super` does not reliably return the JSON promptfoo parses; it would also have been
the same model grading its own output. A configured-but-broken grader fails every row for the
wrong reason and hides the gate that works, which is the same class of mistake as a
green-by-workaround pipeline. Removed with the reasoning in the config, and `GAPS.md` 6.8 records
that the CLI pass rate is unusable until an independent grader key exists.

**Files changed.** `eval/promptfooconfig.yaml`, new
`docs/harness-reports/adr014-first-eval-run.md`, `docs/GAPS.md` (6.1 updated, 6.7/6.8 added).
Eval output stays uncommitted (gitignored, as `eval/results.json` already was).

**Dependencies added.** None. **Tests.** Unchanged at 864 — this run measures the engine, it does
not alter it.

**Problems hit.**
1. The 20-minute "hang" diagnosed above. The lesson: a stalled run with no output is more likely
   a crash-loop than slow work — check CPU time and open connections before waiting longer.
2. promptfoo can sit on an interactive prompt with no stdin; `CI=true` and a closed stdin are
   needed for an unattended run.
3. The CLI's pass rate cannot express "one gate works, one is broken", so it reported 0% for a
   pipeline whose drafting half is flawless. Any future reader must pull per-assertion results
   out of `results-run.json`; that is now stated in the config, the report and GAPS.

**Next.** 6.7 is the owner's call and is the highest-value open question in the product right now
— it decides whether applications can be sent at all. SMTP (1.1) still needs credentials.

### 2026-10-04 (latest+76) — Known-name redaction; and the "ADR-015 contradiction" was my own error

**What changed.** 859 -> 864 tests. No behaviour removed.

**`redact_pii` no longer depends on NER guessing a name (GAPS 5.8).** It takes `known_names`
and matches them exactly via a presidio deny-list recognizer
(`PatternRecognizer(supported_entity="PERSON", deny_list=[...])` passed to
`analyze(ad_hoc_recognizers=...)` — signature read off the installed 2.2.358, not guessed).
Verified live: the name that previously survived is now `<PERSON>`. Blank and duplicate entries
are dropped, because a `deny_list` containing `""` would match everywhere — which a profile with
no `full_name` would otherwise produce.

**Found while doing it: PII redaction has no callers at all.** `redact_pii` appears only in its
own tests. The features it was built for — F7 cached dossiers, F8 generation history — have **no
storage in `models.py`**, and `research_company` is a pure function with no persistence. So
presidio was installed ahead of its consumers. Giving it a home means building F7/F8 storage,
which is scope nobody asked for; recorded rather than invented.

**The "ADR-015 contradiction" (GAPS §2) does not exist. That section was my diagnostic error** —
the third in that register, after 6.1 (eval provider) and 4.4 (remote-country filter). I inferred
a contradiction from the *presence* of `claim-submission` and `submitApprovedApplication` without
reading what they do or checking `campaigns.py`.

- **ADR-015 §2 is already implemented.** `campaigns.run_campaign` sets an application straight to
  `approved` when `campaign.auto_submit` is true, and leaves it `ready_for_review` otherwise —
  campaign-level approval, with the review queue already optional. Pinned both ways by
  `test_run_campaign_marks_approved_when_auto_submit_true` and its `auto_submit=False`
  counterpart. JobSpy's Google-only restriction was lifted too.
- **`claim-submission` is not a human-approval gate and must not be removed.** It is a
  `with_for_update()` row lock plus an `approved -> submitting` transition closed by
  `/submission-result`: the **at-most-once guarantee for an irreversible, outward-facing action**
  (a real application to a real employer), pinned by
  `test_claim_submission_still_cannot_fire_twice`. It is also the per-submission accounting that
  ADR-015's own non-negotiable "daily submission caps + a digest" rail depends on.
- **ADR-015's "Code to remove/change" bullet is dangerous as written** and is now amended in
  place. Following it literally would delete duplicate-submit protection and the caps accounting.
  Three different things were being conflated under "submit guard": ADR-001's per-item human
  precondition (gone, correctly), the at-most-once claim (stays), and the harness no-submit guard
  (`guard.py`, explicitly kept by ADR-016 §4 "no exceptions").
- The comments in `submitApprovedApplication.ts` and `main.py::claim_submission` still framed the
  mechanism in ADR-001 terms ("the human already approved once") — which is precisely what misled
  me — and are reworded, each with an explicit "do not remove this to finish the pivot" note.

**Files changed.** `apps/api/pii/redact.py`, `apps/api/main.py` (docstring),
`apps/extension/src/content/submitApprovedApplication.ts` (comment), new
`apps/api/tests/test_redact_known_names.py`, `apps/api/tests/test_redact.py`;
`docs/{DECISIONS,GAPS}.md`.

**Dependencies added.** None. **Tests.** 859 -> 864 API (red-before-green on all 5 new),
extension 132, typecheck clean.

**Problems hit.** My gap register has now been wrong three times, always the same way: I wrote a
plausible cause from reading a symptom, and the entry then reads like a finding. Twice the
register's implied action would have been actively harmful — repointing a harness that was
already correct, and here, deleting a safety guarantee. **A GAPS entry is a hypothesis; verify it
against the code before acting on it**, which is now stated at the top of each corrected entry.

**Next.** SMTP (GAPS 1.1) still needs the owner's credentials — unchanged and unblockable from
here. A full 30-row promptfoo scoring run remains the other open half of 6.1.

### 2026-10-04 (latest+75) — CI exists; and the eval harness was measuring the wrong code path

**What changed.** Two of `GAPS.md`'s headline items. 855 → 859 tests.

**CI (closes `GAPS.md` 5.2).** `.github/workflows/ci.yml`, three jobs on every PR and push to
main: **api** (pytest), **web** (vitest + `tsc --noEmit`), **extension** (node:test + typecheck).
All three were run locally first, green, before the workflow was written — a red-on-arrival
pipeline is worse than no pipeline. `Settings` has exactly three fields with no default
(`database_url`, `anthropic_api_key`, `jwt_secret`); CI supplies obvious placeholders, which is
safe because the suite runs on in-memory SQLite and `conftest.py` blocks real network. Not
included, and said so in the file: the garak lane (needs a real provider key in repo secrets and
a budget decision — a job that silently no-ops without one is worse than no job) and
`next build`.

**The eval harness (corrects `GAPS.md` 6.1, which I had diagnosed wrongly).**
- The register claimed the harness was "pointed at Anthropic with a placeholder key". **It never
  was.** `eval/providers/tailor_provider.py` calls the real engine, which reads
  `LLM_PROVIDER=nvidia` from `.env`. A live golden row tailored fine through NIM in 5.7s.
- **The real defect was worse.** `tailoring/engine.py:370` branches on
  `llm_provider == "nvidia_smoke" or not known_fact_ids`, and `known_fact_ids` comes from the
  `id` on each fact passed in. **All 30 golden rows' facts had no `id`**, so every eval row ran
  the **unvalidated smoke path**: no `TailoredDraft` validation, no `source_fact_ids`
  (min_length=1), no KB-existence check on cited ids. The harness has therefore never measured
  the path production takes for a real profile, whose `ResumeFact` rows always carry a PK.
- **Two visible symptoms, before the fix:** `source_fact_ids: []` on every bullet, and the
  model's own citation markers leaking into user-facing text — `"Led backend rewrite from Flask
  monolith to FastAPI microservices [0]"`. That bullet would have gone into a real application
  with a literal `[0]` in it.
- **Fix:** stable row-scoped ids (`r{row}f{n}`) on all 158 facts. The same two rows now return
  4/4 and 6/6 bullets grounded with real ids and **no markers in the text**. Guarded by
  `tests/test_eval_golden_set.py`, which is offline and calls no model.

**Files changed.** New `.github/workflows/ci.yml`, new `apps/api/tests/test_eval_golden_set.py`;
`eval/golden.csv` (158 fact ids added); `docs/{GAPS,WORKLOG}.md`.

**Dependencies added.** None. **Tests.** 855 → 859.

**Problems hit.**
1. **My own register entry was the obstacle.** GAPS 6.1 said "wrong provider", so the obvious
   action was to repoint the harness — which would have changed nothing. Running one real call
   and reading the output is what found the actual cause. A gap description is a hypothesis, not
   a finding.
2. This is exactly what an eval harness is for, and it was switched off by a missing field in a
   fixture rather than by anything in the product.

**CI's first run immediately earned its keep — and it is red.** `apps/api/requirements.txt`
**cannot be installed from scratch**: `presidio-analyzer==2.2.364` declares
`pydantic<3.0.0,>=2.12.5` while the file pins `pydantic==2.9.2`, so pip exits
`ResolutionImpossible` before a single test runs (PR #8, api job, 16s; web and extension pass).
It works locally only because this venv was built incrementally — presidio does import and run
fine against 2.9.2, so the pin's comment is right about *runtime* and silent about
*installability*. That means a new dev machine or any deploy would have hit the same wall.
Recorded as `GAPS.md` 5.7 and **blocked on the owner**, because both fixes change the dependency
set: pin presidio to **2.2.358** (newest release declaring no pydantic requirement) or bump
**pydantic to >=2.12.5** (bigger blast radius — fastapi, pydantic-settings, instructor, langfuse,
anthropic all sit on it). I did not pick one, and did not work around it in the workflow: a
green-by-workaround pipeline over a broken requirements file is worse than an honest red.

**Next.** A full 30-row promptfoo run has still not been scored, so tailoring quality is now
measured on a *sound* path but is not yet *quantified* — that is the remaining half of 6.1.
`GAPS.md`'s other headline items: the ADR-015 contradiction still live in the extension (§2,
per-item `claim-submission` machinery), and SMTP (§1.1, needs the owner's credentials).

### 2026-10-04 (latest+74) — COLLECT-E rejected on measurement; COLLECT-F done. Job collection is complete.

**What changed.** The last two collection stages. **COLLECT-E is a rejection, not a build**
(ADR-019); COLLECT-F is two small builds and two decisions. 850 → 855 API tests, web 140/140.

**COLLECT-E — liveness probing, REJECTED.** The idea was to probe each stored job's own
`apply_url` and treat 404/410 as removed, so the five feeds that cannot be paginated to
exhaustion could get real freshness. The plan's bar was *a false-positive rate of 0*. Measured
against jobs each feed is listing right now — live by construction, so any non-200 is a false
positive:

| Feed | Codes on 8 live jobs | False positives |
|---|---|---|
| remoteok | `{200: 8}` | 0% |
| arbeitnow | `{200: 8}` | 0% |
| workingnomads | `{200: 5, 403: 3}` | **37.5%** |
| himalayas | `{403: 8}` | **100%** |
| weworkremotely | `{403: 8}` | **100%** |

Not fixable by narrowing: the 100% failures are exactly the feeds with no pagination escape;
workingnomads is inconsistent on one host across eight sequential requests, which is noise rather
than a special-casable rule; and a 404/410-only rule reads 403 as "no signal", so those feeds
gain zero for several hundred requests a run. UA spoofing (would likely clear the 403s) and a
headless browser per job were both rejected — the first on ADR-018 §9's grounds, the second
because it destroys the cost argument the idea rested on. Evidence:
`docs/harness-reports/collect-e-liveness.md`.

**COLLECT-F — hygiene.**
- **`connector_runs` retention (built).** One bulk DELETE per discovery run, 30-day window.
  **F5's ATS-classifier rows are never pruned** — `models.ConnectorRun`'s own docstring calls
  them the owner's review surface for proposed ATS patterns, so blind age-pruning would have
  destroyed an un-reviewed decision queue. Caught while writing the test, not after.
- **JobSpy dropped from `/sources` (built).** It advertised a source `discover_jobs_task` has
  never fetched, with the note "Currently returns no results". The connector and its isolated
  venv stay; it is simply no longer offered. A new test pins the invariant **both ways**: every
  advertised source must be fetched, and every fetched source must be advertised.
- **Remote-country filtering — not built, and I had described the gap wrongly.** `_OPEN_WORDS`
  already filters "Remote - United States" correctly for any *known* country, so only the user's
  own country is needed, not a world list. The real hole is a profile with **`country_code`
  unset** (it is optional, parsed from the resume), which disables the filter entirely. A
  200-country table is YAGNI at one India-based user and needs a dependency none of which is
  installed (`pycountry`/`babel`) — and adding one needs the owner's approval. The fix is
  product-side: make country required at onboarding. `GAPS.md` 4.4 is corrected.
- **Duplicate `canonical_hash` — decided: permanently accepted.** Re-collapsing a pair means
  picking a winner and rewriting or tombstoning the loser: the destructive direction, for a
  cosmetic problem. Cost of leaving it is one duplicate card; risk of fixing it is deleting a row
  a user already applied through. If it ever becomes visibly annoying, de-duplicate at **read**
  time in the matches query, never by mutating rows.

**Files changed.** New `tests/test_connector_run_retention.py`,
new `docs/harness-reports/collect-e-liveness.md`; `workers/jobs.py`, `main.py`,
`tests/{test_source_isolation,test_onboarding_endpoints}.py`,
`apps/web/lib/onboarding.test.ts`; `docs/{DECISIONS,GAPS,PLAN-JOB-COLLECTION}.md`.

**Dependencies added.** None — and one deliberately *not* added (see the country-filter item).

**Tests.** 850 → 855 API, web 140/140. Red-before-green on all 5 new tests.

**Problems hit.**
1. **The retention trap.** `connector_runs` looks like a pure log but holds F5's proposed ATS
   patterns, which are a human review queue with no other copy. A 30-day age sweep would have
   silently deleted un-reviewed proposals. The test pins it.
2. **A recursive `grep` over the repo root walked `.venv` and `node_modules` and hit the command
   timeout.** Use the search tool, not shell `grep -r`, in this tree.
3. **I had mis-stated GAPS 4.4** when compiling the register, and only found it by reading
   `remote_open_to` properly rather than trusting my own earlier summary.
4. **I pushed this branch without a verified green suite.** The verify command ended in
   `pytest -q | tail -3`, so the pipeline's exit status came from `tail`, not pytest, and a
   failing run (`test_activity::test_today_counts`,
   `AttributeError: 'float' object has no attribute ...`) did not stop the commit. The test then
   passed in isolation and across four consecutive full 855-test runs, so it is an unreproduced
   flake rather than a regression — but the masking is the real defect. Never end a gating
   command in a pipe. Both observed flakes are now recorded as `GAPS.md` 6.6, with the note to
   capture a traceback next time instead of re-running until green.

**Collection is now complete: COLLECT-A…F are all closed** (C partly, see below). Sources with
real freshness: `greenhouse, lever, ashby, jobicy, workday`.

**Next.** One owner decision is still open and deliberately not taken: **the SmartRecruiters
`robots.txt: Disallow: /` ruling** (ADR-018 §7), which is the only route to Swiggy. Beyond
collection, `GAPS.md`'s remaining headline items are the ADR-015 contradiction still live in the
extension (§2), the eval harness pointing at the wrong provider (§6.1), no CI (§5.2) and no SMTP
(§1.1).

### 2026-10-04 (latest+73) — COLLECT-D: `Job.board_token`, so removing a board from config is no longer destructive

**What changed.** Migration **0023** adds `jobs.board_token` (indexed, nullable), and delisting
is now scoped per board instead of per source. 839 → 850 tests.

- `_sweep_delisted(db, source, token, jobs)` — `token=None` means a source with no per-board
  concept (the keyless feeds), and then only its NULL-token rows are in scope.
- `_fetch_ats_source` returns **one `(token, jobs)` batch per board that answered**, replacing
  the single all-or-nothing `trustworthy` flag. `_isolate` and `discover_jobs_task` carry batches
  through.
- greenhouse / lever / ashby / workday connectors stamp the token or tenant;
  `pipeline._UPDATE_FIELDS` includes it, so pre-migration rows pick it up when their board next
  lists them.

**Why.** Two consequences ADR-017 recorded and left open:
1. **Removing a token from `connectors/config.py` tombstoned that board's entire live
   inventory** on the next run. Editing config was a destructive data operation.
2. **One flaky board blocked delisting for the whole source** — if any token returned empty, the
   source was marked untrustworthy, because an empty board's rows would otherwise look absent
   from the combined id set.
Both are now fixed. `Job.company` could never do this job: Phase 1 made it a curated display
name whose formatting varies ("Rubrik Job Board", a trailing space).

**Files changed.** New `alembic/versions/0023_job_board_token.py`, new
`tests/test_board_token.py`; `models.py`, `workers/jobs.py`, `connectors/{greenhouse,lever,ashby,workday,pipeline,config}.py`,
`tests/test_delisting_sweep.py`; `docs/{DECISIONS,GAPS,PLAN-JOB-COLLECTION}.md`.

**Dependencies added.** None. **Tests.** 839 → 850, red-before-green on all 11 new ones.

**Problems hit.**
1. **I had to deliberately invert an assertion Phase 1 wrote.**
   `test_fetch_ats_source_is_untrustworthy_if_any_token_returns_empty` asserted that one dead
   board disables delisting for the whole source — correct while the sweep was source-wide, wrong
   now. It is renamed `test_an_empty_board_contributes_no_batch_and_the_others_still_sweep`, and
   the end-to-end counterpart likewise. Both carry a note saying the old behaviour was replaced
   on purpose, so a future reader doesn't "restore" it.
2. **I corrected a wrong claim in my own plan doc.** `PLAN-JOB-COLLECTION.md`'s COLLECT-D section
   said this would also remove the "editing `FEED_KEYWORDS` tombstones a swept source" hazard.
   **It does not** — narrowing `FEED_KEYWORDS` still drops stored jobs out of the filtered
   payload the sweep compares against. Independent of board identity, still open, now stated
   correctly in the plan, `config.py` and ADR-017.
3. A scripted splice of the test file left an orphaned test with one of its two decorators,
   which surfaced as `fixture 'mock_get_redis' not found`. Removed properly. Editing Python by
   index arithmetic is a bad trade; the file tools would have been faster.
4. Updating fixtures token-by-token, my bulk replacement only tokenized the *first* `_job` call
   in two tests, leaving siblings at NULL — which the new code then correctly skipped. The tests
   failed for the right reason and the fixtures were wrong, not the code.

**Accepted residue.** An ATS job that closed *before* migration 0023 keeps `board_token = NULL`,
is never re-seen, and so is never tombstoned. Stale beats tombstoning live jobs (ADR-017 §3); a
one-off script can clear those if the count ever matters. **Migration 0023 has not run against a
real Postgres** — same caveat as 0022, and its `create_index` is non-concurrent, so run the
upgrade outside an ingestion window.

**Next.** COLLECT-E (liveness probing) and COLLECT-F (hygiene) are the remaining collection
stages; both are described in the plan. The SmartRecruiters `robots.txt` ruling (ADR-018 §7) is
still the open owner decision.

### 2026-10-04 (latest+72) — COLLECT-C: Workday connector live; a pagination bug that would have tombstoned 486 live jobs

**What changed.** ADR-018 accepted ("do workday first") and the connector built.
`connectors/workday.py`, wired into discovery, in `SWEEPABLE_SOURCES`. 824 → 839 tests.

- **Two steps per board, and the split is the design.** List endpoint paginated to exhaustion
  (`limit` caps at 20 — 50+ is HTTP 400), then **only `FEED_KEYWORDS` matches are
  detail-fetched**. Hydrating a whole board would be 527 extra requests for Adobe alone.
  `searchText` can't carry the filter: it filters a single word ("engineer" cut adobe 527→343)
  but returns everything ranked for a phrase ("product manager" → all 527).
- **`locationsText` from the list payload is never stored** — it is frequently a count
  ("5 Locations", "3 Locations"), which would poison `canonical_hash` and silently defeat the
  India filter. Locations come from the detail endpoint.
- **`startDate` is `posted_at`.** It tracked `postedOn` with an exact, constant one-day offset
  across six jobs with six different `postedOn` values; a role start date wouldn't track it at
  all. `postedOn` prose is never parsed ("Posted 30+ Days Ago" is unbounded).
- **Tenants: adobe and cisco**, both verified live with an India-located product role.
  `target`/`micron`/`paypal`/`shell`/`qualcomm` excluded with their measurements in
  `config.py`.
- **Workday is fetched every 6th hour, not every run** (`WORKDAY_INTERVAL_HOURS`). Measured:
  adobe ~95s + cisco 165s = **~4.3 minutes**. Discovery is hourly on a single `SimpleWorker`,
  so fetching every run would park the only worker while campaign runs queue behind it.

**Why.** COLLECT-C's measurement (latest+71) found Workday is the only candidate that both
reaches India product roles and has a clean compliance position.

**Files changed.** New `apps/api/connectors/workday.py`, new `apps/api/tests/test_workday.py`;
`connectors/config.py`, `workers/jobs.py`, `main.py` (`/sources`), `tests/conftest.py`,
`tests/{test_discover_idempotency,test_source_isolation,test_board_tokens,test_delisting_sweep,test_feed_pagination}.py`;
`docs/DECISIONS.md` (ADR-018), `docs/PLAN-JOB-COLLECTION.md`.

**Dependencies added.** None. **Tests.** 824 → 839, red-before-green throughout.

**Problems hit — the first one is the serious one.**

1. **`total` is only reported on the FIRST page; later pages return `total: 0`.** The termination
   check `len(rows) >= total` was therefore trivially true at `40 >= 0`, so `_list_board`
   returned **40 of 526 rows** and called it a complete board. Because Workday is in
   `SWEEPABLE_SOURCES`, that short listing would have gone to the delisting sweep and
   **tombstoned the other 486 live jobs.** Caught only by comparing the live row count against
   the API's own `total` — the 3-vs-40 PM count looked plausible on its own. `total` is now read
   from page 0 only, and an empty page before the end raises instead of being read as
   "end of board" (ADR-017 §3's empty-fetch trap).
2. **My own test passed while the code was broken**, because every fixture page carried `total` —
   the "fixtures homogeneous, so the bound holds by construction" mistake from Phase 1's review,
   repeated. Fixtures now mirror reality (page 1 has `total`, later pages have `0`).
3. **The suite started making real network calls and blew a 10-minute timeout.** Workday went
   into `discover_jobs_task` without being added to the stub lists in
   `test_discover_idempotency._patch_connectors` and `test_source_isolation._offline`. This has
   now happened twice in this repo, so there is a guard: an autouse conftest fixture blocks
   `httpx.HTTPTransport.handle_request` and the async equivalent, failing fast with a message
   instead of hanging. `TestClient` uses `ASGITransport`, so API tests are unaffected.
4. **Site discovery attempt 1 was wasted (~30 min).** It fetched the career-site root and read
   the redirect; the root returns **HTTP 406** to a non-browser UA, so every tenant "failed",
   including adobe which demonstrably works. Spoofing a browser UA was rejected. The working
   method uses the CXS status codes: `404` = tenant+wd right and site wrong (keep guessing),
   `422` = wrong host, `200` = correct.
5. Even so, **7 tenants resolved to a `wd` host but no site matched a 15-candidate guess list**
   (mastercard, visa, autodesk, ebay, philips, unilever, lowes) — recorded in `config.py`.
6. A shell heredoc mangled backslashes in a test edit, which is the lesson already in latest+64.
   Use the file tools for anything with escapes.

**Next.** Owner still has to rule on the SmartRecruiters `robots.txt` (ADR-018 §7) — that is the
only route to Swiggy. Then COLLECT-D (`board_token` column), which now has a third consumer:
removing a Workday tenant tombstones that employer's inventory exactly like a board token.

### 2026-10-03 (latest+71) — COLLECT-C measurement: five platforms probed; the entry latest+70's PR owed

**What changed.** Docs only — `docs/harness-reports/collect-c-platforms.md`, plus
`PLAN-JOB-COLLECTION.md`'s COLLECT-C section and `GAPS.md` 6.5 closed. **This entry was missing
from the PR that added those files**, which is a break of this file's own "every change gets an
entry" rule; written up here after the fact.

**What it found.** Of the 19 Indian consumer-tech companies with no greenhouse/lever/ashby
board, **exactly one is reachable: Swiggy, on SmartRecruiters** (168 live postings). Workday
reaches India product roles at multinational GCCs. Workable has 17 of the 19 as accounts, every
one with `jobs: []`. Keka failed TLS (expired certificate) on every host. Darwinbox serves an
empty SPA shell.

**The reframing:** none of these platforms offers cross-company search — they are all
per-company-identifier APIs, so adding one adds no reach by itself. **Company→platform discovery
is the binding constraint**, which is why measuring `connectors/discovery.py`'s unmeasured F5
classifier may be worth more than another connector.

**Problems hit.** A control test changed the conclusion: 17 of 19 Workable slugs returned HTTP
200 with a plausible company name, which looked like Workable solved the gap. Nonsense slugs
return 404, so the accounts are real — but all have zero jobs. Separately, three of four
SmartRecruiters hits had the *correct* company name with postings from 2016/2018/2021: a new
trap where **existence is not liveness**, so new sources gate on posting recency.

### 2026-10-03 (latest+70) — Gap register; the job-collection plan gets a doc; stages are named, not numbered

**What changed.** Documentation only, no code.

- **`docs/GAPS.md` (new)** — every open item across all phases in one place. Compiled by
  sweeping this file (5,557 lines, latest+28 → latest+69), `DECISIONS.md` (ADR-001…017),
  `PLAN-MULTI-ATS.md` and the session memory, then **re-checking each claim against the code**
  rather than trusting the entry that recorded it. 31 gaps, 7 categories, each marked VERIFIED
  or DOC-CLAIM.
- **`docs/PLAN-JOB-COLLECTION.md` (new)** — the plan COLLECT-A and COLLECT-B were built from
  never had a document; it existed only as "Next" notes at the bottom of entries. Now written
  up with COLLECT-A/B recorded as done and COLLECT-C…F scoped.
- **Stage naming fixed.** `PLAN-MULTI-ATS.md`'s "Phase 0/1/2/3" are now `ATS-0…3`, collection
  stages are `COLLECT-A…F`, and both docs carry the convention. **A bare "Phase N" is ambiguous
  in this repo and must not be used.**
- **This file's "Current state" header was 7 weeks stale** (it said "Phase 3, in progress
  (2026-08-16)") and is rewritten.
- **`ATS-3` carries a warning now:** latest+59 measured no gain on Lever/Ashby, so "extend the
  planner to more platforms" has no evidence behind it.

**Why.** "Start phase 3" was genuinely ambiguous and stalled a session — two plans had a Phase
3, and one of the two plans had no document at all.

**Five places the docs were wrong, not merely incomplete** (all now corrected):
1. The `apps/extension` build blocker is **fixed**; `vite.config.ts` already has
   `css: { postcss: {} }`. The header still listed it as blocking.
2. `ANTHROPIC_API_KEY` is still the placeholder, but production is NIM — so it blocks only the
   eval harness, which is pointed at the wrong provider. The docs called it "the single
   remaining blocker for ADR-014", which now misleads: the real gap is that **tailoring quality
   is unmeasured on the model actually shipped**.
3. **ADR-015 and the code disagree about what the product is.** ADR-015 reversed
   per-application approval on 2026-09-26, but the extension still allows
   `POST /applications/{id}/claim-submission` (`apiProxyCore.mjs:16`) and still pins
   `submitApprovedApplication` as the single submit path (`architectureInvariants.test.mjs:32`).
4. The "Current state" header was 7 weeks stale.
5. Phase numbering collided across two plans.

**Files created / changed.** New `docs/GAPS.md`, new `docs/PLAN-JOB-COLLECTION.md`;
`docs/PLAN-MULTI-ATS.md` (stage names + the ATS-3 warning), `docs/WORKLOG.md` (header + this
entry).

**Dependencies added.** None. **Tests.** None — docs only; suite unchanged at 824.

**Next.** `GAPS.md` ends with a suggested order. The two that actually matter: an **ADR for
COLLECT-C** (India source class — measure candidate platforms first, don't guess), and
**repointing the eval harness at NIM** so tailoring quality stops being unknown.

### 2026-10-03 (latest+69) — Phase 2 item 4b: five board tokens added, three plausible slugs rejected as the wrong company

**What changed.** The owner chose "more ATS board tokens" over the three blocked portals
(YC WaaS / Wellfound / HN, see latest+68). 117 candidate slugs probed live across all three
platforms; **42 had a live board**; five were added, with their real names in
`TOKEN_COMPANY_NAMES`:

| Platform | Token | Company | Evidence |
|---|---|---|---|
| greenhouse | `groww` | Groww | Bengaluru-VTP / Mumbai / India, 7 postings |
| greenhouse | `fivetran` | Fivetran | Bengaluru PM role open; 181 postings, 17 match `FEED_KEYWORDS` |
| lever | `cred` | CRED | bengaluru, hyderabad, 8 postings |
| lever | `hevodata` | Hevo Data | Bangalore PM role open; 53 postings |
| ashby | `atlan` | Atlan | India + San Francisco, 6 postings |

**Why this is the cheap lever.** greenhouse/lever/ashby are already paginated per board,
already in `SWEEPABLE_SOURCES`, and already get real delisting. A token costs one request per
run and no code.

**Problems hit — the important one.**
**Three plausible slugs turned out to be a completely different company.** Verified by fetching
each board and reading its locations before adding:
- `slice` → payload company "Slice", locations Ohrid and Skopje (Macedonia), New Jersey,
  Connecticut — a US/Macedonia pizza business, **not** the Indian fintech.
- `porter` → "Porter Works" on Greenhouse (LA/SF/Seattle), and a *different* US Porter on Lever
  (Amherst MA, Boston, Michigan). Neither is the Indian logistics company.
- `navi` → San Francisco only, 3 postings. The Indian Navi is Bengaluru.

Had any been added, `TOKEN_COMPANY_NAMES` would have mapped a wrong real name onto a wrong
company's jobs and fed it into `canonical_hash`. **Never add a token because the slug matches a
company name.** `tests/test_board_tokens.py` records all three rejects.

**Second finding, and it reframes the coverage question: 19 of 22 Indian consumer-tech companies
have no board on Greenhouse/Lever/Ashby at all** — razorpay, swiggy, zomato, phonepe, flipkart,
zepto, zerodha, myntra, nykaa, delhivery, paytm, urbancompany, lenskart, cars24, blinkit, rapido,
licious, udaan, meesho (its Lever board was already configured). So "more ATS tokens" has a **low
ceiling for an India-focused PM search**: that market sits on other ATSs (Darwinbox, Keka,
SmartRecruiters, Workday) and on Indian job boards (Naukri, Instahyre, Hirist, Cutshort), none of
which is wired. That is the next real coverage decision, and it needs an ADR.

**Files changed.** `apps/api/connectors/config.py`, new `apps/api/tests/test_board_tokens.py`.

**Dependencies added.** None.

**Tests.** 820 → 824. New `test_board_tokens.py` pins four invariants, the load-bearing one being
that **every configured token has a `TOKEN_COMPANY_NAMES` entry** — an unmapped token falls back
to the raw slug as `company`, which feeds `canonical_hash`, so cross-source dedupe against a feed
listing the real name becomes impossible. Red-before-green confirmed: the five tokens were added
without names first and the guard named all five. Also verified live through the real connectors —
correct company on every row (the map strips the trailing space in Greenhouse's own `"Fivetran "`),
no missing `external_id`/`apply_url`, real `posted_at`.

**Next.** groww/cred/atlan have no PM opening today — they are standing subscriptions, and the
hourly sweep will catch openings as they appear. The India coverage question above is the decision
that actually matters next.

### 2026-10-03 (latest+68) — Phase 2: a failing source no longer aborts discovery; `connector_runs` gets written; jobicy paged to exhaustion

**What changed.** Phase 2 of the job-collection plan, items 1-3 in full plus item 4a.
Branch `phase2-source-isolation`. 807 → 820 tests passing.

- **Per-source error isolation (item 1).** `fetch_remotive_jobs` and `fetch_reed_jobs` call
  `raise_for_status()` and nothing in `discover_jobs_task` caught it, so a single Remotive 503
  threw away *every other source's* jobs, the delisting sweep and the embedding backfill for the
  whole run. Every source now goes through `workers/jobs.py::_isolate`, which catches, logs, and
  returns a row. A failed source is never `trustworthy`, so absence from it still delists nothing
  (ADR-017 §3).
- **`connector_runs` health rows (item 2).** One row per source per run:
  `fetched`/`failed`/`error`/`duration_ms`. The six keyless feeds reuse `fetch_enabled_feeds`'
  existing per-source report rather than a second reporting path. `inserted` stays 0 on purpose —
  dedupe is batch-wide in `upsert_jobs`, which returns totals, so there is no honest per-source
  insert count without attributing the batch. `GET /sources` now reports a source whose *latest*
  run failed as disabled, instead of inferring health from job counts (which cannot tell "fetched
  nothing this run" from "has never run").
- **Per-host pacing (item 3).** `HOST_PACING_SECONDS` (1s) between requests inside one source's
  loop — nine Greenhouse tokens were nine back-to-back requests to one host. Pacing sits at the
  loop rather than in a shared HTTP client because those loops are the only bursts that exist and
  no two share a host. An autouse conftest fixture zeroes it so the suite doesn't sleep ~15s per
  discovery test.
- **jobicy paged to exhaustion, and is now sweepable (item 4a).** `fetch_jobicy_jobs` follows
  `nextCursor`/`hasMore` to the end: **633 jobs in 7 requests, 12.9s**, verified live, 633 unique
  ids, `posted_at` on 100% of rows, 21 surviving `FEED_KEYWORDS`. It was fetching `count=50`
  before. Being a *complete* listing is what qualifies it for the delisting sweep under ADR-017 §2,
  so `SWEEPABLE_SOURCES` is now `{greenhouse, lever, ashby, jobicy}` — the first non-ATS source
  with real freshness. A mid-pagination failure raises and discards the partial listing
  deliberately: a partial payload would make every job on the pages that never arrived look
  absent from the board.

**Why.** Phase 1 made freshness *possible*; it did not make ingestion survivable. One source's bad
day cost the entire run, and nothing recorded which source had the bad day.

**Files changed.** `apps/api/workers/jobs.py`, `apps/api/connectors/feeds.py`, `apps/api/main.py`
(`/sources`), `apps/api/tests/conftest.py`, new `apps/api/tests/test_source_isolation.py` and
`apps/api/tests/test_feed_pagination.py`, `apps/api/tests/test_delisting_sweep.py` (pinned set).

**Dependencies added.** None.

**Tests.** 807 → 820. Red-before-green confirmed for all 13 new tests.

**Problems hit.**
1. **"Paginate those fetchers to exhaustion" turned out to be viable for exactly one of six.**
   Re-probed live, 1s pacing: jobicy exhausts in 7 requests/633 jobs. **himalayas reports
   `totalCount` 115,729 at a server-*forced* 20 per page — `limit=100` is ignored — so exhausting
   it is 5,786 requests per run.** arbeitnow returned HTTP **429 at page 21** (>2,450 jobs, and its
   own `meta.terms` says "please do not abuse"). remoteok/weworkremotely/workingnomads are
   structurally truncated with no knob at all. So five of six stay non-sweepable *by decision with
   a number behind it*, not by omission. The measurements are in
   `tests/test_feed_pagination.py`'s docstring and the `SWEEPABLE_SOURCES` comment — don't re-probe.
2. **A test patched a name that `FEED_FETCHERS` binds by reference.** `FEED_FETCHERS` captures
   function objects at import, so `patch("connectors.feeds.fetch_jobicy_jobs")` is invisible to
   `fetch_enabled_feeds` — the test silently made a real network call and passed a wrong
   assertion. Patch `_get` instead. Worth knowing for any future feed test.
3. **`/sources` nearly read the wrong row.** Taking "newest first, set the reason if the source
   has none yet" lets an *older* failed run override a newer successful one. Fixed by keeping only
   the first row per source (`setdefault`) before applying any of them.
4. A pre-existing order-dependent failure in
   `test_campaigns.py::test_run_campaign_does_not_rereport_jobs_it_already_looked_at` showed up in
   the baseline run (passes in isolation) and has not reappeared since. Not chased; noted so the
   next session doesn't think it's new.

**Not done — item 4b (new portals) is blocked on decisions, not on code.** None of the three
portals left on ADR-015's tier list is a keyless structured feed, checked live:
- **YC WaaS** — `workatastartup.com/jobs` returns **HTTP 406** to a non-browser client; the job
  list is behind a login. Would need authenticated scraping.
- **Wellfound** — serves a Cloudflare Turnstile challenge. Would need bot-challenge evasion.
- **HN "Who is hiring"** — the Algolia API (`hn.algolia.com/api/v1`) is keyless and works, but the
  postings are free-text comments with no company/title/apply_url fields. Structuring them needs
  an LLM call per comment, and a regex would put junk companies into `canonical_hash` and the
  match pool.
Each is a new decision (authenticated scraping / challenge evasion / per-comment LLM spend) that
needs the owner's approval and an ADR, same as ADR-016 got. **The cheap coverage win meanwhile is
more board tokens in `connectors/config.py`** — greenhouse/lever/ashby are already exhaustible,
already swept, and need no code at all; which companies is the owner's call.

**Next.** Owner decides on item 4b (the three portals above, or more ATS tokens instead). Then:
`ConnectorRun` rows are written but nothing prunes them (~14 rows/hour); migration 0022 still has
never run against a real Postgres — watch the first `alembic upgrade`.

### 2026-10-03 (latest+67) — Job freshness: re-seen jobs update, `posted_at` is a real date, real company names, absence-based delisting

**What changed.** Phase 1 of a job-collection plan, built as five tasks by one implementer each,
every task reviewed by a separate agent, then a whole-branch review. Branch
`phase1-ingestion-freshness`, 16 commits, 807 tests passing. ADR-017 records the decisions.

- **Freshness is now possible at all.** `upsert_jobs` was insert-only: a re-seen job was counted
  `skipped` and its row never touched, so `Job.last_seen_at` was written once at insert and never
  read — dead data. It now UPDATEs a re-seen row (matched on `(source, external_id)`, not
  `canonical_hash`), moving `last_seen_at`, clearing `delisted_at`, and filling fields only where
  the incoming value is non-empty. Budget: 3 queries per batch (SELECT, bulk INSERT, bulk UPDATE).
- **`posted_at` is a real datetime for every source.** Greenhouse was storing `updated_at` — a
  modification date — which recency scoring reads at 15% weight over a 30-day decay. It now reads
  `first_published` (present on 100% of jobs on all nine configured boards, surveyed per token) and
  stores NULL when absent. New `normalize.coerce_posted_at` handles ISO with `Z`, ISO with an
  offset converted to naive UTC, and garbage → NULL; it accepts strings only.
- **Real company names** for greenhouse/lever/ashby, which previously stored the board *token*
  (`grafanalabs`, `meesho`). That token fed `canonical_hash`, so cross-source dedupe could never
  match a feed listing the same role under the real name. A curated token→name map wins over the
  payload, because Greenhouse returns `"Rubrik Job Board"` for Rubrik and that suffix survives
  `canonical_hash` normalization.
- **Absence-based delisting.** `Job.delisted_at` (migration 0022) is set when a source was fetched
  successfully and a job was not in the payload. Never by age. Delisted jobs are excluded from
  `matching/filters.py`, `matching/service.py`'s candidate query, `campaigns._in_bounds`,
  `GET /jobs`, and the embedding backfill.
- **`canonical_hash` is no longer UNIQUE.** See "Problems hit" — this was a run-killer.

**Why.** "Find the latest jobs" was not implementable: nothing tracked whether a job was still
listed, and two sources' copies of one role could not dedupe. Adding more job portals on top of
that would have multiplied the breakage instead of adding coverage.

**Files changed.** `apps/api/connectors/{pipeline,normalize,greenhouse,lever,ashby,config,jobspy_connector}.py`,
`apps/api/{models,main,campaigns,formplans}.py`, `apps/api/matching/{filters,service}.py`,
`apps/api/workers/jobs.py`, `apps/api/alembic/versions/0022_job_delisted_at.py` (new), and tests
including new `tests/{test_job_freshness,test_greenhouse,test_ashby,test_delisting_sweep}.py`.

**Dependencies added.** None.

**Tests.** 742 → 807. Red-before-green confirmed per test; three exceptions are disclosed in the
fix report (two regression guards written after their fix, and the query-budget bound, proven to
bind by temporarily making the update loop data-dependent and watching `assert 4 <= 3` fire).

**Problems hit.** Reviews caught five things that implementers' green suites did not:
1. **The query-budget test asserted nothing.** It wrapped `Session.execute`, which
   `bulk_insert_mappings`/`bulk_update_mappings` bypass by calling `connection.execute` directly —
   it saw 1 statement where 3 ran. Rebuilt on an Engine-level `before_cursor_execute` listener.
   Its fixtures were also homogeneous, so the bound was held by construction rather than by the
   test; one heterogeneous fixture now makes it bind.
2. **`coerce_posted_at` took three rounds.** A magnitude floor, then a 1970-2100 calendar window,
   each still returning wrong-but-plausible dates (`"20260909120000"` → year 2612;
   `"20260230"` → 1970-08-23). The fix was deletion, not a fourth guard: epoch-as-a-string is a
   shape no connector sends, and it was the sole source of every wrong date.
3. **`canonical_hash` was UNIQUE while Task 4 rewrote it in place.** The first time a renamed ATS
   row's hash equalled a feed row's, `IntegrityError` escaped `session_scope` and rolled back the
   whole run — inserts, sweep, embeddings — recurring forever because the colliding pair stayed
   stored. Dropped the constraint; dedupe is enforced in `upsert_jobs` anyway. Tombstones are now
   excluded from that dedupe set, otherwise a tombstone permanently suppressed any live duplicate
   or re-post.
4. **The sweep would have expired by age.** Four of six feeds in the original sweepable set return
   truncated listings, and remoteok/workingnomads turned out to be fixed and rolling windows. The
   sweep is now ATS-only. Both this and (3) came from a brief naming a constant without the
   implementer reading the code behind it — the process note for next time.
5. **Two tasks collided invisibly.** Real company names broke the sweep's `Job.company == <token>`
   scoping: zero rows matched, nothing ever delisted, and its own tests still passed. Found by the
   other task's implementer, not by either review.

Also: `models.py` lacked `index=True` on the two columns migration 0022 indexes, so the next
`--autogenerate` would have dropped them and silently reverted the work.

**Next.** Phase 2 of the plan: per-source error isolation (one failing source currently aborts the
whole discovery run — remotive and reed `raise_for_status()`), `ConnectorRun` health rows (ingestion
writes none today, so `/sources` infers health from job counts), per-host pacing, then adding
portals from ADR-015's tier list. Before relying on feed freshness, paginate those fetchers to
exhaustion. Migration 0022 has never run against a real Postgres — watch the first `alembic upgrade`.

### 2026-09-30 (latest+66) — Multi-page forms (Workday first); optional fields that can't be set no longer block

**What changed.** One agent planned the work and two built it in parallel worktrees. ADR-016 amendment 3 records the decision.
- **Extension:** account walls stop the run with "Sign in…". It clicks entry buttons ("Apply Manually") by exact text,
  then runs a generic Next loop: it fills a page, clicks Next (picked by exact text, never a form-submitting button),
  waits for the page to change, and repeats. The driver bounds the loop at 8 pages (`jc:next-page`) and resets
  the item timer on each page. The final-submit path is unchanged.
- **Harness:** `auto_apply.py --fixture workday|workday-noconsent|wall` runs a local Workday-like SPA and a local
  account wall. `--url` runs guarded recon on real job pages. `mode_failures` checks the result, and the fixture server counts
  `/save` `/submitted` `/account` POSTs.
- **Brex:** a value the extension couldn't apply used to block the application even when the field was optional (Brex's
  phone "Country"). Now it blocks only a required field. Two older builds gave the same result, so the bug was already there.

**Results (guarded, synthetic identity, no submit).**
- Wall fixture: "Sign in…" in 14 s. Before the change it failed after a 190 s timeout. No password typed, 0 `/account`.
- Workday fixture: pass 1 filled and saved steps 1–3, then stopped on the questions only the user can answer. Pass 2, with those
  answers saved, reached step 4 and stopped at the consent checkbox. 5 saves, 0 submits, gender blank.
- No-consent fixture: it reached Review ("Submit") and handed it back. 0 submits.
- Greenhouse: Anthropic is unchanged (consent stop). Brex again reaches its guard-blocked submit.
- Real Workday: Salesforce stopped at sign-in in 40 s, as intended. Adobe (guest apply) reached "step 1 of 5", and NVIDIA
  went past Apply Manually. On both, the guard blocked Workday's POSTs (11 and 13), the page never rendered its fields, and the
  run timed out as failed. Live multi-page on real Workday can only be proven in the owner's own signed-in session.
- Tests: extension 132/132, typecheck and build clean; harness unit tests pass.

**Problems hit.**
- A merge conflict in `auto_apply.py` with the headed-mode merge was resolved, keeping both sides.
- The harness's canned answer matched "country" before "authorized" and answered a Yes/No with "United States". Fixed.
- Once, the machine's DNS didn't resolve the Neon host. The API returned 500 and the harness timed out, then it recovered on its own.

**Next.** An owner-watched run on the owner's own Workday account, to capture the step pages. After that, Workday
button-dropdowns. SMTP credentials. The first real submit.

### 2026-09-30 (latest+65) — Password reset; background-tab dropdown fix merged; worktrees cleaned

**What changed.**
- **Password reset.** `POST /auth/forgot-password` returns the same for any email and sends a one-hour link. `POST
  /auth/reset-password` checks the token's purpose and a fingerprint of the current password hash, so the link works once
  and a login token can't reset a password. No table. Web: "Forgot password?" on sign-in, `/forgot-password`, `/reset-password`.
  The API has 5 tests and web has 2. Live check with a throwaway account: link logged, new password works, old one refused,
  reused link refused. **Emails need SMTP:** with `SMTP_HOST` unset the link goes to the API log only (the same rule as the digest).
- **Background-tab dropdowns** (an agent's unverified WIP branch, now merged). Chrome runs a background tab's timers at most
  once a second, and only 5 of Anthropic's 8 dropdowns were read in budget. Waits now wake on DOM mutations. Merge conflicts
  were resolved. Extension tests pass (116). Headed `auto_apply.py` on Anthropic's embed reached all 23 fields in 32 s, with the
  guard on and no submit.
- 6 merged agent worktrees were removed. `worktree-agent-af607b1d421ec69ae` is left: an older onboarding-launch
  change that master's `launchCampaign` has superseded; delete it after a look.
- **Ops:** `uvicorn --reload` hung on Windows. It detected a change and never restarted, so the API served old code
  (the remote filter and the reset routes were missing live). The API now runs without `--reload`; restart it after API changes.

**Still open.** SMTP credentials (reset emails and the digest). The first real submit, which the owner watches. Multi-page and Workday forms.

### 2026-09-30 (latest+64) — Remote roles restricted to another country are left out

**What changed.** A user in India was offered "Remote - US", "Europe" and "Time zone: CET" roles. `matching.filters.remote_open_to`
treats a remote job as open if its location names no place (anywhere/worldwide/global/remote/blank), or names the user's country or
region (whole words, so "Indiana" doesn't count). `build_matches` uses it with `profile.country_code`, and so does campaign candidate
selection, because stored matches predate the filter. `LOCATION_ALIASES` moved from campaigns.py to matching/filters.py.
Only India is covered; an unknown country is not filtered. Live: 218 of 630 remote jobs are open to India. The API suite passes (737).

**Problem hit.** The `\b` regex escapes were written as literal backspace characters (heredoc → Python non-raw string).
The tests caught it. Write regex-bearing code with the file tools, not shell heredocs.

### 2026-09-30 (latest+63) — Audit of the owner's first real use: matching, worker, outages, free-tier embeddings

**What changed.** The owner asked for problems "like these" to be found and fixed. Each fix below has a test that failed before it and passes after. The API suite passes (733).
- **Matches:** `build_matches` took the global top 20, and the page filtered it to the campaign afterwards, so US/EU jobs crowded out India
  ones (3 shown). The top N is now taken inside the active campaigns' `_in_bounds`, and the page-level filter is deleted. The result is 20 India matches.
- **"India" matches Indian cities** (`campaigns._LOCATION_ALIASES`). Postings say "Bangalore, Karnataka" or "Gurugram".
- **No worker was running.** A campaign Run had sat in Redis since 17:04 UTC, reported as started. Run and Discover now return 503 with
  how to start the worker. The worker and scheduler were started; the run prepared Meesho Senior PM (ready_for_review).
- **LLM outage in map-fields** (NIM "overloaded") raised a 500 and the extension filled nothing. Rule and bank answers are now kept,
  and the rest are flagged.
- **Resume facts that a Voyage 429 left unembedded** were only re-embedded on an edit, so a new free-tier account could end up with no centroid and no
  matches. `build_matches` now refreshes them (`matching.service.refresh_fact_vectors`, moved from main.py).
- **Failed prep left applications `saved` forever**, and later runs skipped the job as "already applied". Each run now retries
  its own saved, untailored applications.
- **Free-tier embeddings:** a job's first 4,000 chars are embedded (about 6 jobs per request instead of 1), newest first. A new
  `embed_backlog_task` runs every 2 minutes and does the jobs an active campaign wants first. All 21 campaign jobs are embedded, and no
  Voyage payment is needed.

**Still open.** "Remote" includes US-only remote roles. There is no password reset. Services run locally: the API with `--reload`, the worker
and the scheduler (logs in `D:\tmp\job-copilot-logs`).

### 2026-09-29 (latest+62) — Matches page respects the campaign; the campaign was missing boards and Indian cities

**What happened.** The owner's campaign said India, but the Matches page showed US, UK and Europe roles. There were three causes:
- `GET /matches` listed every scored match. Only campaign runs applied `campaigns._in_bounds`. It now shows matches
  that fit any **active** campaign, using the same filter, and everything when no campaign is active. There is a test, and the suite has 724 passing.
- The API had been started before the ATS boards were configured and had no `--reload`, so `/sources` still said
  "No company boards added" and the campaign was created without greenhouse/lever/ashby. The API was restarted with `--reload`
  and the three sources were added to the campaign.
- Location "India" misses "Bangalore, Karnataka" and "Gurugram". The campaign's locations now also list the main Indian cities.
  Future users will hit the same problem: consider making "India" match Indian cities.

**Still blocked.** None of the India PM jobs has an embedding (Voyage 3 RPM limit), so 0 matches are in bounds until the owner adds a payment method.

### 2026-09-29 (latest+61) — Discovery set up for the owner: PM roles, remote or India

**What changed.** `connectors/config.py`: `FEED_KEYWORDS` = product manager, product owner, product lead and head of product.
The same filter now applies to the Greenhouse/Lever/Ashby boards (`workers/jobs.py`), because a board returns every opening.
15 board tokens were each checked live against the ATS's public API for PM roles in India or globally remote. Boards whose
remote PM roles were US-only were left out. The first live run fetched 274 and inserted 100, giving 199 PM jobs, 65 of them in India or remote.

**Blocked.** Voyage embeddings are rate-limited (3 RPM, no payment method on the account). Matching scores only jobs with an embedding,
and 196 of the 199 PM jobs have none yet. The owner adds a payment method, then discovery is re-run.

**Owner's campaign.** Roles `product manager` and `product owner`. **remote_only off**, because `campaigns._in_bounds` ANDs it with
locations. Locations are India, Bengaluru, Bangalore, Pune, Gurugram, Hyderabad, Mumbai and Remote. auto_submit is off. "Remote" also matches
US-only remote roles from feeds, so skip those in Review.

### 2026-09-29 (latest+60) — Planner report comes back on stdout, so there is no temp file to lose

**What changed.** The OpenAI plan in latest+59 failed with ENOENT: Python's temp dir for `plan.json` disappeared while
`plan.mjs` was running. Neither Stagehand nor chrome-launcher deletes it; they each remove only their own Chrome profile.
The cause wasn't proven; one candidate is the Chrome and supervisor processes orphaned by Linear's timeout just before. Instead of
guessing, the temp file is gone. `plan.mjs <url> -` prints the report as one JSON line on stdout, and
`formplans.plan_job` parses the last JSON line. `plan.mjs` exits only after stdout drains, because a piped write can be
cut off by `process.exit`. The human summary line moved to stderr. Harness use with a file path is unchanged.

**How tested.** Red → green in `tests/test_form_plans.py` (the stdout report, and a failed row when there's no report).
The API suite passes. Live: Cloudflare planned OK (12 fields). OpenAI returned its report and failed only because NIM was
overloaded.

### 2026-09-29 (latest+59) — Lever and Ashby re-measured with the plan: no gain on required fields; routing stays Greenhouse-only

**What changed.** `formplans.ROUTED_ATS` now reads `FORM_PLAN_ROUTED_ATS` (default `greenhouse`), so a measurement
can turn routing on without a code change. Lever and Ashby were re-run with it set to all three
(`docs/harness-reports/plan-vs-extension.md`, top section).
- Lever: required fields filled 16/36 in both runs. The plan added 2 optional fills, both correct. Last run's −4 was the flaky
  location typeahead.
- Ashby: identical on the 3 postings that ran both ways. Linear's plan timed out (300 s, NIM), and OpenAI's plan.mjs
  hit ENOENT writing into its temp dir (happened once). Both failed safe to today's filler.
- There were no wrong values, 0 demographic violations and 0 submits.

**Decision.** Keep Greenhouse-only. The ADR-016 "revisit" condition (routing beats today's filler) is not met on Lever or Ashby.
The API on :8000 is back on the default.

**Next.** Re-measure if the planner or the Lever location typeahead changes. Watch for the temp dir ENOENT in the worker logs.

### 2026-09-29 (latest+58) — "How did you hear about us?" is answered only from the answer bank

**What changed.** The Zoox risk from latest+57 is fixed. It was not a lone checkbox. The options share a name, so the
extension sent one group labelled "How did you hear about us?", and today's LLM path answered it "LinkedIn" in one
run. Only the user knows this answer. "hear about", "find out about", "referred you" and "referred by" joined
`ESSAY_LABEL_KEYWORDS` (API and the extension's mirror), so the question now goes to the answer bank or nothing, never the model.
A bank answer is now bound to the field's options on that path.

**How tested.** Red → green: 2 API tests, 1 extension test. API suite 721 passed, extension 113 passed, typecheck and
build clean. Live guarded fill of the Zoox posting: nothing ticked, flagged `essay_no_stored_answer`
("save the answer and we'll reuse it"), canary blocked, 0 submits.

### 2026-09-29 (latest+57) — ADR-016 built: form_plans, planner worker, plan routing; on for Greenhouse only

**What changed.** One agent planned and four agents built the parts in parallel worktrees. The pieces were then merged, and fixed when they met real planner output.
- `form_plans` table (migration 0021, applied on Neon, no RLS). `apps/api/formplans.py` runs `plan.mjs` as a subprocess,
  keeps only the plan fields that exist on the page, and stores one row per job. CLI: `python -m formplans`.
  An hourly `sweep_form_plans_task` plans jobs that have an Application ready_for_review or approved.
- `map_form_fields(..., plan=)`: after the consent/EEO rail and the deterministic matcher, the plan routes a field to a
  profile key or an answer-bank hit bound to the options. Everything else takes today's path. A stale plan
  (a key missing from the page) is dropped.
- The extension sends `job_id` to map-fields (work-queue items carry it). `check_form.py --job-id`, and the new
  `tools/stagehand-harness/measure.py`.
- Scorer: radio/checkbox groups are matched by their question. Lever recall went 65% → 84%, Ashby 74% → 96%.

**Result.** `docs/harness-reports/plan-vs-extension.md`, 13 postings with both runs: required fields filled
62 without a plan, 60 with one (Greenhouse +2, Lever −4, Ashby 0). There were 0 demographic violations and 0 submits.
Decision: routing is on for **Greenhouse only** (`formplans.ROUTED_ATS`). ADR-016 amendment 2.

**Problems hit.**
- Stagehand's `selector_hint` is an accessibility ref, not an id, so plans matched almost nothing on the page. `build_plan` now falls back to
  the label (or the radio group's question), never a radio/checkbox *option* label.
- NIM tagged Name, Email and Phone as `answer_bank_question`. `plan.mjs`'s `fill_from` is now an enum, and the instruction names the profile keys.
- The plan's "never" hit LinkedIn and website fields, and an answer-bank miss flagged fields today's path fills. Both now
  take today's path.
- The Lever connector passed `createdAt` (epoch ms) as `posted_at`, and Postgres rejected it. Discovery had the same bug,
  hidden because no Lever tokens are configured. Fixed, with a test.
- The Neon connection dropped while the planner ran for minutes. `plan_job` now commits before the subprocess.
  Robinhood re-planned OK (23 fields).
- The running API had no `--reload`, so it served old code. It was restarted before the measurement.
- **Risk, not caused by the plan (fixed in latest+58):** on Zoox, today's LLM path ticked a lone "LinkedIn" checkbox under "How did you
  hear?" in one run and not in the other. That is a made-up answer. Next: flag a lone checkbox whose label is
  an option of a group question, instead of asking the model.

**Next.** Fix the lone-checkbox risk. Re-measure Lever and Ashby when the planner or the typeahead changes.

### 2026-09-29 (latest+56) — Stagehand measured on Lever and Ashby; ADR-016 amended: Stagehand is the planner

**What changed.** The owner asked engineering to decide. The Stagehand harness was run on 5 live
Lever and 5 live Ashby postings, and ADR-016 now has an amendment: the server planner is Stagehand
`extract()`, not browser-use. The extension still fills and submits, and its own consent/EEO,
required and dropdown handling still decide.
- Lever: 65% recall/precision (understated: the scorer matches radio options, not their question), 92% required,
  median 23 s. Ashby: 74% recall, 82% precision, 95% required, median 11 s. Both use 2–3 calls per job.
- `docs/harness-reports/stagehand-{lever,ashby}.md` (new); `score.py` takes the ATS as an argument.
  `plan.mjs` takes its own DOM snapshot as ground truth, after `extract()`.

**Problems hit.**
- The guard blocked Ashby's GraphQL POST that loads the form, so every Ashby page had no form. `plan.mjs` now
  calls `guard.is_readonly_ashby_query` (the tested Python check, fail-closed) instead of copying it into JS.
  Also, `execFileSync` needs a string path, not a URL; it threw, and fail-closed hid that.
- While Ashby was blank, `extract()` **made up 11–21 fields** on pages with no inputs. The ADR amendment
  says a plan whose fields don't match the live DOM is discarded.
- Lever Outreach and Ro fired one submit event each on load, with no click from Stagehand. The DOM guard
  cancelled both. Worth knowing for the extension on Lever.
- NIM returned 503s ("temporarily overloaded"), which the retry handled.

**Next.** Build the planner worker and `form_plans` store (PLAN-MULTI-ATS). First test: whether a plan
improves the extension's fill rate on the same 15 postings. Scorer: match radio/checkbox groups by their question.

### 2026-09-29 (latest+55) — Phase 0 (ADR-016): browser-use planner fails; Stagehand extract() works

**What changed.** Phase 0 was measured on 5 live Greenhouse postings. The run was stopped
before Lever/Ashby because the result was already clear. Full numbers:
`docs/harness-reports/phase0-greenhouse.md` (browser-use) and
`docs/harness-reports/stagehand-greenhouse.md` (Stagehand).
- browser-use planner: 7% field recall, 0% dropdown options, ~8 min, 30 LLM calls, ~417k tokens
  per job. It loops re-clicking comboboxes until the 30-step cap.
- Stagehand 3.7.3 `extract()` (one read-only call, same NIM model): 85% recall, 99% precision,
  median 17 s, 2 calls, ~9k tokens. Gaps: dropdown options 13% (react-select options are hidden
  until opened), consent/EEO tagged "never" only 59%.
- Recommendation: Stagehand replaces browser-use as ADR-016's server planner. The extension
  still fills and submits, and keeps its own consent/EEO and required checks. ADR-016 is not
  yet edited.

**Why.** Owner: test Stagehand/Browserbase (real sites) vs the extension. Local Chrome for now,
Browserbase later. Rule: filling real forms with the synthetic identity is fine; a real submit
never is.

**Files.** New `tools/stagehand-harness/` (`plan.mjs`, `score.py`, `package.json`, `out/`).
Both new reports. Phase 0 harness (`phase0.py`, `plan_form.py`, `test_phase0.py`) merged
from the agent worktree.

**Dependencies added.** `@browserbasehq/stagehand@3.7.3`, `@ai-sdk/openai-compatible@1.0.57`,
`zod@4.4.3`, isolated in `tools/stagehand-harness` (owner-approved). Pinned to 3.7.3 because
Stagehand 4.x needs Node >= 22.18 and this machine has 22.14.

**Problems hit.**
- Stagehand's `openai/<model>` route uses OpenAI's Responses API, which NIM lacks. Fixed by
  using `AISdkClient` + `createOpenAICompatible` (chat completions). A custom `fetch` injects
  `chat_template_kwargs.enable_thinking=false` and counts calls.
- Without `supportsStructuredOutputs: true`, NIM's JSON didn't match the schema ("No object
  generated"). With it, it works.
- The guard is CDP `Fetch` (non-GET requests failed) plus a DOM init script; a canary POST is
  checked before the real page loads.
- NIM returned a 504 on Robinhood, and the retry made it 328 s.

**Next.** Owner decision: edit ADR-016 to use Stagehand as the planner. Run Lever and Ashby with
the Stagehand harness. Test whether a plan improves the extension's fill rate.

### 2026-09-28 (latest+54) — Auto-apply driven live on embedded Greenhouse: five fixes; Redis password rotated

**How tested.** New `tools/browser-use-harness/auto_apply.py`: a harness job (local
careers page with a 2-field talent form + the Greenhouse embed) → batch-approve →
`jc:run-queue` → watch the driver's tab under the full guard (`guard.py` unchanged).
Re-run: `python auto_apply.py --ext-dist ..\..\apps\extension\dist --job brex/8795500002`.
**Result.** The iframe is chosen and the talent form is untouched. On brex/8795500002
the fill completed (resume, names, email, country, phone, LinkedIn), the guard cancelled
the submit event, and the driver reported `unconfirmed` (no application POST left the
browser). Anthropic's posting stops at `needs_human` on its arbitration consent (never
auto-given): correct.
**Bugs (agent, red first each).**
1. The embed hydrates after load and swaps every control, so dropdown options were read
   from dead nodes (0 options → every combobox low_confidence). Fix: `relink.readLive`
   re-reads, at most 3 tries.
2. The phone country shows "+1" for "United States +1" and was flagged every pass. Fix:
   accept the option's trailing words, only after our own click.
3. Optional unmapped fields (Website) blocked the run. Now `optional_left_blank`.
4. `ITEM_TIMEOUT` 60 s was less than load + reads + /map-fields. Now 180 s (driverCore).
5. Added on review: a label ending in "*" counts as required, so an asterisk-only
   required field still blocks instead of being submitted blank.
**Tests.** Extension 106/106, `tsc` clean; api 672; web 137; guard 12/12.
**Redis.** The owner rotated the password (the old one was pasted in chat). The new one
is verified and the old one is rejected; API, worker and scheduler restarted on it.
**Open.** Required Location (City) typeaheads (Robinhood, GitLab) always end
`needs_human`. Consent/unfittable questions never reach the review queue, so the user
sees "needs input" with nothing to answer. The needs_human note lists reason codes, not
field labels. Background-tab timer throttling is untested in a headed browser.

---

### 2026-09-28 (latest+53) — Names from a two-word full_name, Voyage free-tier backfill, digest email

Three parallel worktree agents, each reviewed and merged. Suite **672/672**.
- **First/Last Name.** `formfill/map_fields.build_profile_summary` only copied
  `given_name`/`family_name`, so a profile with just `full_name` left Greenhouse's two
  required name fields flagged. Now a **two-word** full_name fills the missing parts at
  mapping time. It is never written back, and parts the user typed win. The agent's
  version split any name (first/last token); narrowed on review to exactly two words,
  because the earlier "a split is a guess" call (entries around lines 713/1582) is right
  for "Mary Jane Watson" / "Juan Carlos García López" / "Cher". Those stay flagged; the
  Profile page sets the parts.
- **Voyage backfill** (`connectors/pipeline.py`). All 50 pending jobs went in ONE request
  (far over the 10K TPM free tier; the client has `max_retries=0`), so every pass got a
  429 and embedded nothing. Now requests are ≤24K chars (~6K tokens, ponytail-marked
  estimate), each committed as it lands, and the first failure ends the pass. No sleeping
  in the SimpleWorker. `upsert_jobs`' one-shot embed is unchanged.
- **Digest email** (`digest.smtp_sender`, stdlib smtplib). Set `SMTP_HOST/PORT/USER/
  PASSWORD/FROM` (repo-root `.env.example`) to send; port 465 = SSL, else STARTTLS. Unset
  = log-only as before. A failed send → Notification `failed`, only the exception type
  is logged. A failed day is not retried (the per-day idempotency check sees the row).
  Gmail needs an App Password.

---

### 2026-09-28 (latest+52) — Embedded Greenhouse, tested live: two bugs found and fixed

**How tested.** A local careers page (127.0.0.1) with its own one-field "talent
community" form and Greenhouse's official embed iframe
(`job-boards.greenhouse.io/embed/job_app?for=anthropic&token=4461450008`), run through
the no-submit harness with a freshly built extension. `check_form.py` now snapshots
the frame holding the most fields (`form_frame`), not always the top frame.

**Bug 1: the wrong frame answered the popup.** `jc:fill-form` reaches every frame and
the first answer wins. The top frame always filled, so it answered first and filled
the careers page's talent-community email box; the Greenhouse form got nothing, and
the harness still said PASS. Fix: `driverCore.fillsOnPopup`, where a frame fills only
if it holds an application form (≥4 fields). The top frame still fills a small form,
but only on a page without iframes. The popup now says "No application form found on
this page." when no frame answers (before, `sendMessage` threw and nothing was shown).

**Bug 2: writes to detached elements.** Greenhouse's embed re-renders its whole form
(an in-page navigation, window state kept) as the fill starts. Proven by tagging every
input first: 0 tagged inputs left live. `fillForm` held the old elements through the
~20 s `/map-fields` call, then wrote into detached nodes, so it reported `filled: 4`
with nothing on screen. Fix: after mapping, any detached control is swapped for its
live twin (`content/relink.mjs`: same index if the form has the same shape, else the
same id, else left alone and never guessed).

**Result.** Embedded and direct runs are now identical: Email, Country +1, Phone and
LinkedIn filled; demographics blank; 0 submits. The harness now also fails when the
extension reports fields filled but none are visible.

**Tests.** Red first for `fillsOnPopup` and `relink`. Extension 98/98, `tsc` clean,
guard 12/12.

**Notes.** First/Last Name come back `low_confidence` on both direct and embedded
pages. The harness profile sets only `full_name`, not `given_name`/`family_name`;
this is a mapping gap and not specific to the embed. Only the popup fill was tested
live; the auto-apply frame claim (`jc:claim-frame`) was not driven (that needs an
approved queue item).

---

### 2026-09-28 (latest+51) — Redis back; worker socket leak fixed

**What changed.** New Redis Cloud DB (`REDIS_URL` in `apps/api/.env`). The first
connect failed with `max number of clients reached`: the local RQ worker held 29
sockets and the scheduler 1, which is the free tier's cap of 30. Root cause:
`workers/jobs.get_redis_connection()` built a new `Redis` client (and pool) on every
call, and jobs running inside the long-lived SimpleWorker call it repeatedly. It now
has `@lru_cache(maxsize=1)`: one client per process. `events/sse.py` closes its own
client, and `run_relay.py` is one client per process, so both are fine.

**Verified.** Red test first (`test_redis_connection_is_one_shared_client_per_process`),
api **660/660**. After a restart: PING ok, the scheduler's startup discover + sweep
ran, and a `len([1,2,3])` job went queue → worker → `3`. 3 sockets open, not 30.

**Notes.** Voyage is on its no-billing tier (3 RPM): the embedding backfill in
discover hits `RateLimitError`. The job still completes, but embeddings lag until a
payment method is added at dashboard.voyageai.com.

---

### 2026-09-28 (latest+50) — Four stranded worktrees reviewed and merged

The four worktrees left at f21a331 held finished-but-uncommitted work. Each one was
reviewed, its own tests run in place, then committed and merged `--no-ff`. There were
no conflicts.
- **browser-use guard** (`tools/browser-use-harness`): one allowed remote POST,
  Ashby's read-only GraphQL job-posting query. It must be exactly that https
  host+path, a JSON object body, and query operations only; any `mutation`/
  `subscription` in the body is refused, and the checked bytes are what gets
  forwarded. 12/12.
- **Truth check** (`tailoring/engine.py`, `eval/truth_check_bench.py` + cases): pass 2
  is a per-claim audit (`ClaimAudit`: each claim → fact ids + unsupported phrases),
  plus `deterministic_unsupported`, which flags vocabulary tools/numbers that no fact
  contains, with no model call. Also a no-padding rule in the tailor prompt.
  **Review fix:** "one"/"zero" were read as numbers, so "one of the roles I want most"
  was flagged and would block ready-to-send. Now number words start at "two". Red test
  first.
- **Age is demographic + iframes** (`answer_bank.py`, extension): DOB/age questions
  and age-bracket option sets are never filled or stored; 18/21 eligibility checks
  still are. Server and extension share one spec and the same test cases. Content
  scripts now run `all_frames`, and the driver gives the tab to the one claiming
  frame with the most fields (≥4), so captcha/ad frames stay silent. **Not
  live-browser-tested.**
- **Daily digest** (`digest.py`, `GET /digest/preview`, scheduler at 00:05 UTC):
  sent/unconfirmed/ready/needs-you/skips/replies per user. Idempotent per day. It only
  logs (Notification `skipped`) until email credentials exist.

**Tests (merged master).** api **659/659**, web 137/137, extension 94/94 + tsc,
harness 12/12.

**Next.** Load the extension and try an embedded Greenhouse board. Needs email
credentials for the digest and a new REDIS_URL.

---

### 2026-09-28 (latest+49) — Rejected resume files say why; 0020 applied to Neon

**What changed.** Onboarding's resume Dropzone showed nothing when a file was too big,
the wrong type, or more than one. `rejectedFileMessage()` (`lib/onboarding.ts`) turns
react-dropzone's raw text into plain words; `StepResume` shows it in a `role=alert`, and
the next good drop clears it. Migration **0020 applied to Neon** (0018 → 0020 head). Its
docstring no longer asks for a 0019 rebase, because no 0019 exists. Removed the merged
applications worktree.

**Uncommitted work sitting in 4 old worktrees (all at f21a331, never merged):**
`agent-a83ee6bd…` browser-use harness guard edits, `agent-a979c3d5…` tailoring engine +
`eval/truth_check_bench.py`, `agent-aa64bf67…` answer_bank + extension driver/manifest,
`agent-ab786fcd…` `digest.py` + scheduler. Left untouched until the owner decides.

**Tests.** Red first (`rejectedFileMessage` missing) → web **137/137**, `tsc` clean.

**Next.** New REDIS_URL. Decide on the 4 worktrees. Push.

---

### 2026-09-28 (latest+48) — Post-merge check; match links skip the redirect

**What changed.** Merged master (profile + onboarding + applications branches) verified
together: api **604/604**, web **136/136**, `tsc` + `next build` clean. Migration chain is
linear (0020 → 0018; no 0019 landed, so no second head). Today tile, Today activity rows
(`activityHref`), StepDone and the empty Review state now link `/applications/matches`
directly instead of bouncing through the `/matches` redirect.

**Files.** web: `lib/today.ts` + test, `app/today/page.tsx`, `app/review/page.tsx`,
`components/onboarding/StepDone.tsx`.

**Tests.** Red first (`activityHref` expected the new path), then green.

**Next.** Apply 0020 to Neon before deploying. Redis Cloud DB still gone (new REDIS_URL
needed). Dropzone rejects too-big/wrong-type files silently. 6 local commits not pushed.

---

### 2026-09-28 (latest+47) — Onboarding: no duplicates, survives refresh, real sources; 404/error pages

**What changed.**
- *Duplicate facts (API).* `POST /profiles/{id}/facts:bulk` is idempotent: a fact equal
  after normalisation (category/achievement/metric/proof; case + whitespace folded) to one
  the profile already has, or to an earlier one in the same payload, is skipped. Body is
  still the list of *newly created* facts (back-compatible with /facts and the harness);
  `X-Skipped-Facts` lists the skipped payload indices. Nothing new → no commit, no embed call.
- *Duplicate facts (web).* `factsToPost(drafts, saved)` (same rule) — the wizard posts only
  facts the server doesn't have; nothing new → no facts:bulk call at all.
- *Refresh / second campaign.* The wizard draft (step, facts, basics, prefs, campaign draft —
  never the token or the file) is kept in sessionStorage per profile
  (`applyscout.onboarding.<profileId>`, every access try/catch), cleared on launch.
  `startingStep()` decides where to open from the server: a non-archived campaign exists →
  "You're already set up" with Go to Today / Change your campaign / Add more facts (re-running
  onboarding used to create a second campaign); saved facts → Preferences (facts and basics
  preloaded from the server, so leaving the facts step can't wipe saved basics); a saved draft
  further along wins; "done" is never restored.
- *Sources.* New `GET /sources` (auth): every source the discovery worker knows, with label,
  note, `enabled` + plain `reason`, and `job_count` from the jobs pool as the cheap health
  signal (`connector_runs` has no rows for these — only F5's classifier writes it). Enabled
  from `connectors/config.py`: remotive + the six keyless feeds (remoteok, himalayas,
  workingnomads, jobicy, arbeitnow, weworkremotely); Greenhouse/Lever/Ashby off until board
  tokens exist, Reed off without a key, Google Jobs off ("Currently returns no results" —
  JobSpy isn't even in discovery). `AVAILABLE_SOURCES` deleted; the campaign step renders the
  server list, disabled ones stay visible with their reason; default = every enabled source;
  launch drops any source the server says is off (a restored draft may hold one).
- *A11y.* Continue/Back use `aria-disabled` (not `disabled`) while a step saves, stay
  focusable, and read "Saving…". A blocked Continue focuses the first `aria-invalid` field
  (panel only for form-level errors); one polite summary region ("Can't continue: N problems…
  <first>") replaces the per-field `role=alert`s — via an `ErrorsAnnounced` context in
  `fields.tsx`, so /campaign keeps its alerts. Chip × is a 44px target (negative margins keep
  the chip small; rows spaced so targets don't overlap); "Remove fact" is 44px tall. Dropzone
  caption "PDF or Word (.docx), up to 5 MB", `multiple={false}`. Per-fact inputs are
  "Metric (fact 2)" / "Proof (fact 2)". Facts copy: "You can edit or remove facts later on your
  Profile page" (edit/delete endpoints land from another branch).
- *404 / error.* `app/not-found.tsx` (Go to Today / Sign in) and `app/error.tsx` (Try again =
  `reset()`, Go to Today; heading takes focus; the raw error only goes to the console).
  No `global-error.tsx`: the root layout has nothing that throws.

**Files.** api: `main.py` (one block: `_fact_key`, facts:bulk, `GET /sources`), `schemas.py`
(`SourceOut`), `tests/test_onboarding_endpoints.py` (new). web: `lib/onboarding.ts` + test,
`lib/api.ts` (`Source`, `listSources` only), `lib/campaigns.test.ts`, `app/onboarding/page.tsx`,
`components/onboarding/{fields,StepFacts,StepResume,StepCampaign}.tsx`,
`app/{not-found,error}.tsx` (new).

**Dependencies added.** None. No migration.

**Tests.** Red first: api 5 failing (duplicates appended, no header, /sources 404) → api
578 → **583**. web 8 failing (`factsToPost`/`saveDraft`/`startingStep`/`defaultSources`/
`api.listSources` missing) → web 105 → **113**. `tsc` clean, `next build` clean
(/onboarding 19.5 kB). Not driven in a browser this time.

**Not done / notes.** The Kibo Dropzone drops a rejected file (too big / wrong type) silently
— `StepResume` passes no `onError`; worth a visible message. Deleting a preloaded (already
saved) fact inside the wizard doesn't delete it server-side; the Profile page does.

---

### 2026-09-28 (latest+45) — Profile: edit facts, identity and saved answers

**What changed.**
- **API.** `PATCH /resume-facts/{id}` (only the fields sent change; `achievement`/
  `category` can't be null or blank) and `DELETE /resume-facts/{id}` (204). Both are
  owner-scoped by joining the fact to a profile of the current user — another user's
  fact is a 404. An edit that changes `achievement` clears the fact's vector, then
  `_refresh_fact_vectors` embeds every fact of the profile still missing one and
  recomputes `fact_centroid` from the embedded facts (None when there are none).
  Voyage failing or unconfigured never blocks the edit: the fact stays unembedded and
  out of the centroid, and is picked up on the next edit/delete. A delete recomputes
  the centroid the same way. No migration.
- **Web.** `/facts` is now "Profile" with three sections and an in-page nav:
  *Facts* (upload as before; edit inline — kind, words, number, where; delete hides the
  row with a 5-second Undo, then sends the DELETE, flushed if you leave the page; add
  one by hand through `facts:bulk` so it gets embedded), *About you* (full/first/last
  name, phone, address, country code, website, links, work authorisation — GET/PUT
  basics, validated with onboarding's `validateBasics`), *Saved answers* (question,
  answer, times used; edit re-saves via `PUT answers`, delete via `DELETE`). Copy
  says changes apply to future applications.
- `lib/profile.ts`: `factChanges` (only changed fields, so an untouched achievement
  never costs a re-embed) and `undoableDeletes` (timer-based; no restore endpoint).
  `lib/api.ts`: `updateFact`, `deleteFact`, `listAnswers`, `deleteAnswer`, `SavedAnswer`.

**Why.** After onboarding, what Maggie knows could only grow: a wrong fact, an old
phone number or an outdated saved answer stayed forever. User-edited facts are still
the user's own words, so the no-fabrication rail holds.

**Already-tailored applications.** Their bullet text lives in
`tailored_resume_json`, so an edit doesn't change them. A *deleted* fact does drop
the bullets citing it from a prepared resume downloaded later
(`download_tailored_resume_docx` only keeps bullets whose fact ids resolve) — the
UI says so rather than keeping a retracted claim alive.

**Files.** `apps/api/{main.py,schemas.py,tests/test_resume_fact_edit.py (new)}`,
`apps/web/app/facts/page.tsx`, `apps/web/lib/{api.ts,profile.ts (new),profile.test.ts (new)}`.

**Dependencies added:** none.

**Tests.** Red first. api 578 → 587 (9 new: re-embed on edit, Voyage failure clears
and still saves, catch-up embedding, no Voyage call without a text change, blank/null
rejected, delete recomputes/clears the centroid, cross-user 404, 401). web 105 → 115
(factChanges, undo timing/undo/flush with fake timers, msw PATCH/DELETE 204/answers).
`tsc` clean, `next build` clean.

**Next.** Onboarding's "once saved, facts can't be edited yet" copy
(`components/onboarding/StepFacts.tsx`) is now false — owned elsewhere, needs a
one-line change. `POST /resume-facts` still doesn't embed (the page uses `facts:bulk`).
Not verified in a browser this pass.

---

### 2026-09-28 (latest+46) — Applications: tracker, detail page, match actions

**What changed.**
- *API (one block at the end of `main.py`, after review-queue/ready-to-send so
  `/applications/{id}` can't swallow those paths).* `GET /applications` rows gain `job
  {id, title, company, location, apply_url}` + `created_at`/`updated_at`
  (`ApplicationListOut`). New `GET /applications/{id}` (owner-scoped 404): job, status,
  match score, timestamps, tailored summary, bullets each with `sources: [{id,
  achievement}]` (the user's own fact text; ids that don't resolve are left out), cover
  letter, flags, pending questions (bank-answered ones dropped, same as review), stored
  `keyword_gap`, `keywords {matched, reworded, missing}` (live `compute_keyword_gap` —
  deterministic, no model call; `reworded` = its `reword` suggestions), `needs_input`,
  `last_attempt`, `history` (every `[outcome] reason` stamp, new
  `needs_input.attempt_history`). `PATCH /matches/{id}` `{state: new|saved|dismissed}`
  (422 otherwise). `GET /matches` hides dismissed and adds `application_id` /
  `application_status`. `POST /matches/{id}/prepare`: get-or-create the Application
  (`saved`), mark the match saved, enqueue the existing `prepare_applications_task([id])`
  (batch_prep path, not duplicated); already-prepared → `queued: false`, no re-tailor;
  enqueue failure → 503 with the application kept (retry reuses it).
- *API, new status `withdrawn`* (migration **`0020_application_status_withdrawn.py`**,
  `ALTER TYPE … ADD VALUE`, **not applied to Neon**). Numbered 0020 because 0019 is the
  profile agent's; `down_revision = "0018"` — **if 0019 merges, change it to "0019"** or
  Alembic has two heads. Not `dismissed`: that means declined-before-sending and its undo
  clears `applied_at`; a withdrawal keeps the sent date.
- *Web NAV:* Today, Review, Applications, Campaign, Profile (→ /facts). 5 items on the
  phone tab bar; `aria-current` also on sub-paths (`/applications/…`).
- *Web /applications (Pipeline):* columns Applied (applied, submitted_unconfirmed,
  submitting) / Heard back (recruiter, oa) / Interviewing / Offer, plus a collapsed
  `<details>` Closed (rejected, withdrawn). Not-yet-sent rows are a one-line count linking
  to Review. Moving a card = a native labelled `<select>` "Move to" (44px, keyboard/screen
  reader for free, no drag, no new deps) → PATCH status, optimistic with rollback; one live
  region announces "Moved X to Y" or the failure (`role=alert`). `submitted_unconfirmed`
  shows as a warning-toned "Couldn't confirm" pill; its menu offers "I've confirmed it was sent".
- *Web /applications/matches (Matches):* Prepare this one / Save (aria-pressed) / Not for
  me / View listing; a match with an application links to its detail instead. `/matches`
  now redirects there (Today's links keep working). Pipeline/Matches are two real links
  (`aria-current`), not JS tabs.
- *Web /applications/[id]:* status + Move menu, match %, sent/found times, "Couldn't
  confirm" note, why Maggie stopped (only while not yet sent), Open the job, Download
  tailored resume, keyword coverage before → after + Already in your facts / Reworded /
  "Not in your facts — left out", tailored bullets next to the fact each came from, truth-
  check flags, cover letter, "What happened" history.

**Files.** api: `main.py`, `schemas.py`, `models.py`, `needs_input.py`,
`alembic/versions/0020_application_status_withdrawn.py`, `tests/test_applications_tracker.py`
(new). web: `lib/applications.ts` + `.test.ts` (new), `lib/api.ts`,
`components/AppShell.tsx`, `app/applications/{page,parts}.tsx`,
`app/applications/matches/page.tsx`, `app/applications/[id]/page.tsx` (new),
`app/matches/page.tsx` (now a redirect).

**Dependencies added.** None.

**Tests.** Red first. api 578 → **590** (11 red: missing job on list rows, 404/405 routes,
`withdrawn` 422). web 105 → **118** (module-not-found red). `tsc` clean, `next build`
clean. Browser (scratch SQLite API :8100, `next start` :3100, never Neon): /matches →
/applications/matches, "Not for me" hides the card, 390px no horizontal scroll, Move
SRE (Couldn't confirm) → "I've confirmed it was sent" announced and moved, select 44px
tall, detail page renders keywords/bullets-with-facts/cover letter/history; desktop 1280
four columns + collapsed Closed. Found in the browser and fixed: the "Maggie stopped"
callout showed on an application already sent.

**Not done / notes.** "Prepare this one" not clicked in the browser (would enqueue on the
real Redis); covered by pytest. No undo for a move (the menu can move it back). Today's
tiles still link `/matches` (redirects; `lib/today.ts` not mine). Apply 0020 before
deploying (a `withdrawn` write fails on 0018).

---

### 2026-09-27 (latest+42) — Legal consent is never automated; country codes bind to option names

**What changed.** `answer_bank.is_consent_field(label, options)` — arbitration
agreements, terms/privacy consent, "I agree/accept/certify/attest/acknowledge",
signatures — joins the demographic rail: never mapped (map_fields' never-fillable set,
checked on the question AND its options), never saved to or served from the answer bank
(agreeing once is not agreeing for every employer). Also `deterministic._country_option`:
an ISO `country_code` binds to an option naming that country ("US" → "United States +1")
via the already-installed phonenumbers (private `_region_display_name`, wrapped so any
failure means "not filled", never a wrong value); ambiguous/no match stays unfilled.

**Why.** The combobox harness run (latest+40) showed the model accepting Greenhouse's
"Agreement to Arbitrate" (single option "I understand and agree…") at high confidence and
the extension clicking it — legal consent must be the user's own act. Country stayed empty
because the options are names, the profile a code.

**Tests.** Consent recognised on 6 real phrasings incl. option-only; NOT on work
authorization / visa / relocation / "how did you hear"; LLM never called and value None
for the arbitration field even when the bank would answer; consent refused on save.
Country: US/IN bind, DE (no option) stays None. Red before green; api 578/578.

**Next.** Re-run the harness on Greenhouse to confirm the arbitration fields now stay
blank for the user and Country fills.

---

### 2026-09-27 (latest+41) — Assisted apply: Maggie prepares, you send

**What changed.** Owner decision: the proven pattern (the agent finds, ranks and tailors;
the human clicks Submit) is the default; auto-submit stays opt-in while the extension hardens.
- *API.* `GET /applications/{id}/resume.docx` — the **tailored** resume: only bullets whose
  every `source_fact_id` resolves to the profile's facts (ADR-009; the LLM summary is not
  used), grouped by the first cited fact's category, dates only when all cited facts share
  one period. Same ATS linter + parse-back as the base resume (shared
  `_verified_resume_response`); 409 when nothing grounded; owner-scoped 404. Both resumes now
  open with a name + contact line (full_name or given+family; email, phone, city/region,
  website, profile links) as body paragraphs — not a Word header (rule 3) nor a heading (rule 5).
- *API.* `PATCH /applications/{id}` `status` is now `ApplicationStatus` (422 on anything
  else). Moving to `applied` stamps `applied_at` and writes `application.submitted` with
  `manual: true` → `/activity` titles it "You sent it". Leaving `applied` for a pre-send
  status clears `applied_at`.
- *API.* `GET /applications/ready-to-send?profile_id=` = `ready_for_review`/`approved` with ≥1
  tailored bullet, no truth-check flags, no unanswered question. Captcha/account stops don't
  block it — the human is the one sending. Review rows (both endpoints, one builder) gain
  `prepared_answers` (bank answers to questions the form asked) and `keyword_gap`.
  `/today` gains `ready_to_send`; `needs_you` no longer counts those (one list each).
- *Web /review.* "Ready to send" section on top (not a new route: nav stays 5 on phone and
  Review is already where prepared applications wait). Per card: role, company, match %,
  keyword coverage before → after, then 3 steps — Download tailored resume (blob with auth),
  Copy cover letter + each prepared answer (visible "Copied" in `role=status`; clipboard
  refused → readonly textarea to copy by hand), Open application form (new tab, sr-only
  hint, http(s) only) — then "I've sent it" / "Not for me". Both hide the card at once and
  wait 6s with Undo (focused, announced) before the PATCH; leaving the page sends it
  (`pagehide` + unmount flush, `keepalive`). The extension note ("Fill this form", you press
  Submit) is said once in the section intro. Below: "Needs you first" = the old cards minus
  anything ready.
- *Web copy.* `auto_submit` is a two-option radio (`SubmitModeChoice`, used by onboarding
  StepCampaign and /campaign): "Assisted — Maggie prepares, you send (recommended)" /
  "Automatic — Maggie sends within your daily limit". /campaign status line and StepDone use
  the same `submitModeLine`; StepDone says the extension is optional in Assisted mode.
- *Web /today.* "Ready to send" tile → `/review#ready-to-send`; summary line counts it.
- *Web, pre-existing bug.* `components/ui/card.tsx` used v4-only `px-(--card-spacing)` /
  `--spacing(4)`; under Tailwind 3.4 every Card had zero padding. Now `px-5`/`py-5`/`gap-5`.

**Files.** api: `main.py`, `schemas.py`, `documents/generate_docx.py`,
`tests/test_assisted_apply.py` (new), `tests/test_activity.py` (new key in two exact-dict
asserts). web: `lib/assisted.ts` + `.test.ts` (new), `lib/today.ts` + `.test.ts`, `lib/api.ts`,
`components/review/SendCard.tsx` (new), `components/SubmitModeChoice.tsx` (new),
`components/review/ApplicationCard.tsx` (export `saveBlob`), `components/ui/card.tsx`,
`components/onboarding/{StepCampaign,StepDone}.tsx`, `app/{review,today,campaign}/page.tsx`.

**Dependencies added.** None. No migration.

**Tests.** Red first. api 554 → **565** (10 red: 404/405 routes, 422 not raised, missing
`ready_to_send`), then `test_activity` exact dict updated. web 91 → **105** (module-not-found
red; summaryLine red). `tsc` clean, `next build` clean (/review 11.3 kB).
Browser (scratch SQLite API on :8100, `next start` :3100, never Neon): Today tile + summary,
/review at 390px (no horizontal scroll), tailored docx 200 via fetch with auth, Copy →
"Copied", I've sent it → Undo → count restored, second press → after 6s `/today`
sent_today 1 and one "You sent it" activity row; /campaign radio pair.

**Not done / notes.** Undo after the 6s window isn't offered (the API supports it). An
`approved` row in ready-to-send can still be claimed by a running extension; if the user
then marks it applied, the extension's report 409s (nothing double-sends). Extension
untouched (another agent owns it).

---

### 2026-09-27 (latest+40) — Comboboxes: read options, pick the exact one, verify

**What changed.** The extension now fills custom "combobox" dropdowns (react-select on Greenhouse, ARIA
listbox typeaheads elsewhere). Before, it sent them with no options and could never fill them.
1. *Detection.* `comboboxKind()` works from an attribute snapshot: `<input role=combobox>`, visible, and
   either inside a react-select control or with popup semantics (`aria-autocomplete=list|both`,
   `aria-haspopup=listbox|true`, `aria-controls`/`aria-owns`). intl-tel-input's hidden "Search" combobox
   is not a widget.
2. *Options at extraction.* Each widget's menu is opened, its option labels are read from ITS OWN listbox
   (`aria-controls` / `react-select-<id>-listbox` / the container's `[role=listbox]`), and it is closed
   again. It goes to map-fields as `input_type: "select"` with the options (capped at 50), so
   `bind_to_options` applies. Budget: 300 ms per menu, at most 40 widgets, 8 s in all; anything unread is
   sent with no options, so it gets flagged rather than guessed. A question whose label is demographic is
   never opened at all.
3. *Filling.* Open the menu, find the option whose text equals the mapped value exactly, and click it (the
   widget's own handler, not a value write). If it isn't rendered and the input is searchable, type the
   text and wait up to 1 s. Then close and check that the control now SHOWS the option. Anything else is
   `low_confidence`, and search text we typed is cleared. The fill glue is also a demographic
   belt-and-braces: the glue refuses to open a combobox that `isDemographicField` matches.

**Found live, on Greenhouse (guarded probes, nothing submitted).**
- A dispatched `keydown` alone does NOT open the menu: Greenhouse opens it on key/mouse UP. `keydown`+`keyup`
  ArrowDown does.
- **Escape on a closed Greenhouse select CLEARS its value**, and on an open one it doesn't even close the
  menu. The first harness run clicked "Yes" correctly, then the closing Escape wiped it. Menus now close
  by blur only.
- A `mousedown`/`mouseup` on an option makes Greenhouse's wrapper toggle the menu shut, which detaches the
  option before its click lands. Options get `.click()` only.
- The page keeps intl-tel-input's 244 phone-country `[role=option]`s in the DOM at all times, so options
  are never read page-wide.
- `inReactSelect` (from latest+37) marks the react-select siblings AROUND a control, not the combobox input
  inside it. Kind detection uses the enclosing control instead.

**Harness.** Two changes:
- `check_form.py --ext-dist <dir>` loads a worktree's build. The default is unchanged.
- **Harness snapshot bug fixed.** It read a combobox's display via `el.closest('[class*="select"]')`,
  which matched Greenhouse's own `select__input`. Every react-select therefore looked empty, even after it
  was filled. It now reads the single-value inside the enclosing control. `guard.py` is untouched.

**Real run, Greenhouse (anthropic/4461450008), guards on, same fixed snapshot both runs.** PASS both.
- Before (main's dist): filled 4, **11 required empty**. latest+39 reported 17 with the buggy snapshot.
- After (this build): filled 7, **8 required empty**.
- Filled through the widget and verified: relocation = "Yes"; "Please read the arbitration agreement" =
  "I will read the arbitration agreement below."; "Agreement to Arbitrate" = "I understand and agree to
  the terms…".
- Gender, Hispanic/Latino and Veteran: left blank, never opened.
- Guard: 0 submit attempts, canary 2/2, 2 non-GET requests blocked (Snowplow, S3 resume).
- Fill 16.8 s. Reports: `docs/harness-reports/20260927T162724Z-greenhouse-baseline.md` (before) and
  `20260927T162830Z-greenhouse.md` (after).

**Tests.** `combobox.test.mjs` (14, red first) covers kind, option cleanup, exact match, read sequencing
(always closed, even on a throw), budget/cap, fill sequencing (typed text cleared, a typeahead showing our
own text is not a selection, closed on a throw). `fieldDecision.test.mjs` +2 (a read combobox goes out as a
select; planFill picks the exact label). Extension tests 70 → 86. tsc and build clean.

**Files.** `apps/extension/src/content/{combobox.mjs,combobox.d.mts,combobox.test.mjs,formFill.content.ts,
fieldDecision.mjs,fieldDecision.d.mts,fieldDecision.test.mjs}`, `apps/extension/package.json` (test list),
`tools/browser-use-harness/check_form.py`.

**Still failing / next.**
- **The LLM agreed to the Agreement to Arbitrate for the user.** It was a required single-option consent
  and the backend mapped it confidently. Whether ApplyScout may ever accept legal terms on a user's behalf
  is an owner decision for the backend (`map_fields` prompt/rules). The extension just fills what it's told.
- **Country**: options are "United States +1"… and the profile has "US", so `bind_to_options` flags it
  (backend: needs a code→name binding). The page defaults it to "+1" when the phone is filled anyway.
- Office-4-days, AI Policy, interviewed-before and visa come back unknown/low-confidence. That is correct:
  there is no profile data for them, and the user answers them once into the bank.
- First/Last Name: flagged by the backend (latest+38; no given/family name on the harness profile).
- Ashby could not be probed under the guard: it loads the form itself through a GraphQL **POST**, which
  the no-submit route aborts, so the page never renders. Its location typeahead (async, "Start typing…")
  goes through the typing path, unverified live. Lever's saved form has no comboboxes.
- A widget whose shown text differs from its option label (Greenhouse shows "+1" for "United States +1")
  is flagged `low_confidence` after a successful pick. This is the safe direction.

---

### 2026-09-27 (latest+39) — browser-use harness: automated fill-never-submit checks on real forms

**What changed.** New `tools/browser-use-harness/` automates `docs/LIVE-FORM-TEST.md` against the REAL
built extension. `check_form.py --url <form>` runs this sequence:
1. Guards the browser context.
2. Creates a throwaway account over the API: signup, profile, basics ("Morgan Ellery", example.com), 3 facts.
3. Launches Playwright Chromium with `apps/extension/dist` loaded and puts `jc_token`/`jc_profile_id` into
   `chrome.storage.local` through the extension's service worker.
4. Opens the form and proves the guard is live.
5. Sends the popup's `jc:fill-form` (the interactive path; never `jc:run-queue`).
6. Takes a deterministic DOM snapshot before and after the fill.
7. Runs a browser-use auditor (NIM) that can only call `done`.
8. Writes `reports/<stamp>-<ats>.{json,md,png}` (gitignored).
9. Deletes the account (`cleanup_accounts.py` under `apps/api/.venv`, owner role, cascade from `users`).

`run_suite.py` runs the three LIVE-FORM-TEST URLs (all still open 2026-09-27) and prints a table.

**Safety (the point of this).** Four layers, all always on:
- a context-wide route aborts every non-GET/HEAD/OPTIONS request to a non-localhost host, closes remote
  WebSockets and blocks page service workers;
- an init script makes `form.submit`/`requestSubmit` throw and cancels `submit` events in the capture phase;
- the auditor's browser-use tools are an allowlist of `{done}`, and it refuses to start otherwise;
- canary proof on the live page before the fill and after the audit; exit 1 on a missing guard, any submit
  attempt, or a demographic value.

`test_guard.py`: 7 offline tests (localhost only), red first.

**Real bug found by the harness in itself.** The first real run failed loud: the canary POST to a foreign
`.invalid` host never reached the route, because Greenhouse's CSP `connect-src` killed it first. The canary
on remote pages is now a same-origin path; a strict-CSP test was added red first.

**Real run, Greenhouse (anthropic/4461450008), guards on.** PASS.
- Extension `ok:true`, filled 6. The `jc:api` proxy (d53ba5c) works: no CORS failure.
- 5 text values survived the React re-render (1 of 6 in LIVE-FORM-TEST).
- **Bug: First Name AND Last Name both = "Morgan Ellery".**
- Gender, Hispanic/Latino and Veteran all left empty.
- 17 required fields still empty (Country combobox, Yes/No comboboxes, "Why Anthropic?", arbitration).
- Guard: 2 non-GET blocked (a Snowplow beacon, and the **Greenhouse S3 resume upload**, as intended),
  0 submit attempts, canary 2/2.
- Timings: fill 37 s, audit 158 s (one 150 s LLM timeout, then success), total 226 s.

**LLM.** Model is `nvidia/nemotron-3-super-120b-a12b`, the default. browser-use's `ChatOpenAI` has no
`extra_body`, so a subclass wraps the client's `create` with `chat_template_kwargs.enable_thinking=false`.
Tried on a local form:
- kimi-k3: every call 400 (`frequency_penalty` is immutable for this model).
- nemotron-3.5-lightning-30b: works, but 213 s.
- nemotron-3-super: 10 s on the local form.

With extract/scroll/read_file available, both nemotrons looped for all 10 steps (scroll `index` = garbage
digits), hence `{done}` only plus a 4000 px viewport.

**Dependencies added.** `browser-use==0.13.10` (owner-approved) + `playwright==1.63.0` (drives the guarded
browser; browser-use 0.13 is CDP-only), in the ISOLATED venv `tools/.venv-browser-use` (391 MB; Chromium
1243 432 MB + headless shell 270 MB in ms-playwright). Nothing added to apps/**.

**Files.** `tools/browser-use-harness/{check_form,run_suite,guard,test_guard,cleanup_accounts}.py`,
`requirements.txt`, `README.md`; `.gitignore` (reports/).

**Not done / limits.**
- Lever and Ashby were not run (the brief asked for one real form); `run_suite.py` covers them.
- The auditor is slow and shallow (it read 10 of 31 fields and missed the first/last-name bug); the DOM
  snapshot is the ground truth.
- The resume never reaches the ATS (the upload is blocked by design).

---

### 2026-09-27 (latest+38) — Form mapping on real forms: EEO rule, option-bound answers, name fields

**What changed.** Backend fixes for the findings in `docs/LIVE-FORM-TEST.md`. The
extension side (CORS proxy, native value setter, radio/checkbox grouping, submit
confirmation) belongs to the extension agent and is not in this entry.
- *EEO rule, one place (#2, P0).* `answer_bank.is_demographic_field(label, options)` is
  the whole rule. `is_demographic_label` is now its label half. `save_answer`,
  `find_answer`/`serve_answer`, the needs_human question filter and `map_form_fields`
  all go through it, and `map_form_fields` checks it before anything else. All text is
  normalized first (lowercase, punctuation → space).
  - Question rule: whole-word keywords race, ethnicity, ethnic, hispanic,
    latino/a/x, gender, sex, sexual orientation, transgender, pronoun, veteran,
    disability, disabled.
  - Option rule: a decline phrase plus any demographic option, or ≥2 *distinct*
    demographic terms. An option has a term only if it equals it or starts with it
    followed by a space. So "White (Not Hispanic or Latino)" counts, and a university
    list with "Asian Institute of Technology" does not.
  - Same spec as the extension's `fieldDecision.mjs`. One server-only extra: an
    optional plural "s" ("Pronouns"), which can only make the server stricter.
  - Per-radio descriptors that share a `name` are checked as one group, because
    today's extension sends Ashby's "Man"/"Woman" one radio at a time.
  - Existing bank rows that match the new rule stay in the table and are never served.
    `find_answer` filters them, so no data migration was needed; the live
    "Are you Hispanic/Latino?" row is now unreachable.
- *Deterministic false hits (#6, P1).*
  - name/id are split into tokens (camelCase, `_`, brackets). `tel` must be a whole
    token, so `hotel_preference` no longer matches.
  - Label rules match whole words. They have no bare "tel", so "Telugu (TEL)" is out.
  - Label rules only run on labels of ≤6 words that don't mention
    sponsor/authoriz/visa/eligib/citizen/permit/relocat/willing. That rules out the
    Greenhouse visa question.
  - A checkbox, radio, hidden or file input never gets a profile value.
  - autocomplete uses its last token, so `section-x tel` works.
- *Option-bound answers (#9, P1).* `deterministic.bind_to_options` checks every value
  from the rules, the bank or the LLM against the field's options.
  - Matching is case-insensitive and trimmed. yes/y/true (or no/n/false) picks the
    single option that starts with that word.
  - No match means the field is flagged; it is never filled with a nearby value.
  - The system prompt now says: pick exactly one listed option, or return "unknown".
- *Latency and payload (#10, #15, P2).*
  - These fields are flagged without being sent to the model: g-recaptcha,
    h-captcha and cf-turnstile, hidden and search inputs, fields with no
    label/name/id/options, and lone radios or checkboxes with no options (their label
    is an option, not a question: "White", the 26 Lever language boxes).
  - The prompt keeps only field_id/label/input_type/options, with options capped at 50
    plus `options_total`, and uses compact JSON.
  - Still exactly one LLM call per form (tested).
  - Prompt size measured by replaying the live `*-extract.json` descriptors through
    `map_form_fields`:

    | Form | Before | After |
    |---|---|---|
    | Greenhouse | 7.8 KB | 2.1 KB |
    | Lever | 144 KB | 3.5 KB |
    | Ashby | 12.1 KB | 1.1 KB |

- *Empty resume (#12, P2).* `GET /profiles/{id}/resume.docx` now returns 409 "This
  profile has no resume facts yet…" instead of a 200 empty document. The existing
  endpoint test had been passing on an empty document: its fact POST lacked
  `profile_id` and 422'd without anyone noticing. It is fixed and now asserts the
  POST succeeds.
- *First/last name (#11, P2).*
  - New optional `given_name`/`family_name` columns (migration `0018`) are added to
    `schemas.ApplicantBasics` and GET/PUT `/profiles/{id}/basics`.
  - They fill deterministically from: autocomplete `given-name`/`family-name`; id
    tokens first/given/last/family name and surname; the labels "First name"/"Last
    name"; Greenhouse `first_name`/`last_name` in `ats_schemas.py`.
  - They are still never split from `full_name`. Without the user's own values these
    fields fall through, as before.
  - The onboarding "You" section has two new inputs (`StepFacts.tsx`, `lib/api.ts`).
    No new logic, so no vitest was added.

**Findings closed.** #2 (EEO leak), #6 (Telugu/visa), #9 (San Francisco into Yes/No
when options are sent), #10 (server side), #11 (backend + onboarding), #12 (409), #15
(payload).

**Files.** api: `answer_bank.py`, `formfill/deterministic.py`, `formfill/map_fields.py`,
`formfill/ats_schemas.py`, `main.py`, `models.py`, `schemas.py`,
`alembic/versions/0018_profile_given_family_name.py` (new),
`tests/test_live_form_fixes.py` (new), `tests/test_resume_docx_endpoint.py`. web:
`components/onboarding/StepFacts.tsx`, `lib/api.ts`. `docs/SPEC.md` schema regenerated.

**Dependencies added.** None.

**Tests.** Every new test failed first: a collection error, then 3 reds on the
mirrored option rule, then 1 red on the lone checkbox. api 469 → **547** passed. web
`tsc --noEmit` clean, vitest 87/87.

**Not done / notes.**
- Migration `0018` is written but NOT applied. It declares `down_revision = "0017"`
  (the Verify agent's migration, not on this branch), so the chain resolves only
  after both are merged.
- The Greenhouse relocation question arrived as `input_type: "text"` with no options
  (react-select). Server-side binding can't catch it until the extension sends the
  options; the prompt rule is the only guard for now.
- Greenhouse "Country" is a react-select typeahead but still matches `country_code`
  by id, so "US" is typed into it and ignored. It needs a role/combobox hint from
  the extension.
- Age brackets ("Under 30"…) are not in the shared EEO spec.
- `extract_basics` may now propose given/family name from a resume. It is only a
  draft the user reviews in onboarding.

---

### 2026-09-27 (latest+37) — Extension on real forms: proxy, React-safe fills, groups, EEO options

**What changed.** Closes the extension-side findings of `docs/LIVE-FORM-TEST.md` (the live
no-submit run on Greenhouse/Lever/Ashby).
- *#1 P0 backend unreachable (CORS).* Content scripts no longer fetch the API. They
  message the worker (`{type: "jc:api", method, path, body}`); `background/apiProxy.ts`
  (registered by ONE import line in `driver.ts`) does the fetch from the extension origin.
  Not a generic fetch: `apiProxyCore.mjs` allow-lists exactly `POST /extension/map-fields`
  and `GET /profiles/<uuid>/resume.docx` (anchored regexes, strings only, fixed host
  `API_BASE_URL`), refuses messages whose `sender.id` isn't this extension, and attaches
  the bearer token itself — content scripts no longer read `jc_token`. JSON comes back
  as-is; the docx crosses the (JSON) message boundary as chunked base64. CORS stays narrow.
- *#3 P0 React values didn't stick.* Text and `<select>` values go through the prototype's
  native `value` setter (`setNativeValue`, walks past React's instance-level value
  tracker) then bubbling `input` + `change`. Files are attached FIRST, then text (Ashby's
  upload re-render wiped earlier text; Lever parses the resume into its own fields).
- *#7 P1 radio/checkbox/select.* `.value` is never written into a radio/checkbox.
  `planFill` (pure): radio / checkbox-group → click the member whose label or value equals
  the mapped value (case-insensitive, trimmed); lone checkbox → checked only for
  yes/true, left unchecked for no/false, anything else (the phone number in "Telugu")
  flagged; select → the `<option>` whose text or value matches, set via the native
  setter. No exact match → not filled, flagged `low_confidence` (the relocation Yes/No
  = "San Francisco" case).
- *#8 P1 group questions lost.* `buildDescriptors` (pure) emits ONE descriptor per
  radio group / same-name checkbox group: `label_text` = the question, `options` = the
  option labels. The glue finds the question in `fieldset > legend`, the
  `role=radiogroup|group` container's `aria-labelledby`/`aria-label`, else the nearest
  preceding text (`pickQuestionText`, pure: skips option labels and `*`/`✱` markers; the
  glue skips labels belonging to other controls). Unlabeled text fields (Lever `cards[…]`
  textareas) fall back to the same question text, then the placeholder.
- *#10/#15 P2 junk fields, option cap.* Skipped: `type=hidden|submit|button|reset|image`,
  invisible (zero rect / `display:none`, `visibility:hidden`, `aria-hidden` ancestor),
  `g-recaptcha|h-captcha|cf-turnstile` names/ids, `honeypot` names/ids, and react-select
  internals (only its `role=combobox` input is mapped). Radios/checkboxes count as
  visible if their label is (styled controls hide the native input); file inputs are
  never skipped for visibility (they sit behind buttons). `options` sent are capped at
  `MAX_OPTIONS` = 50; matching still uses every option.
- *#2 P0 EEO options (shared spec, the backend agent implements the same rule).*
  `isDemographicField` in `fieldDecision.mjs`: demographic if (a) the question text
  contains race, ethnicity, ethnic, hispanic, latino, latina, latinx, gender, sexual
  orientation, transgender, pronoun, veteran, disability, disabled (substring) or the
  whole word "sex"; or (b) the options contain a decline option ("decline to
  self-identify" / "i don't wish to answer" / "prefer not to say") plus ≥1 demographic
  option, or ≥2 distinct demographic options (man, woman, male, female, non-binary, white,
  black or african american, asian, hispanic or latino, native hawaiian, american indian,
  two or more races, protected veteran, i am a veteran, not a veteran, i have a
  disability, no disability). Matching precision the backend must mirror: normalise
  (lowercase, non-alphanumeric runs → one space, trim); a decline phrase matches
  whole-word anywhere in the option; a demographic term matches when the option equals it
  or starts with it + space ("White (Not Hispanic or Latino)"), and terms are counted
  distinct — so a university `<select>` with "Asian Institute of Technology", "Asian
  University for Women" and "Texas Woman's University" is not EEO. `decideFieldActions`
  and `unansweredQuestions` use it; the latest+31 optional→left blank / required→stop
  rule is unchanged. Eligibility ("18 or older", work authorisation, sponsorship,
  relocation) is tested NOT demographic.
- *#17 P2 iframes — deliberately NOT done.* `all_frames: true` would inject
  `autoApply.content.ts` into every frame, including the reCAPTCHA/hCaptcha iframes every
  tested ATS has. Each frame asks `jc:what-am-i-doing` keyed only by tab, gets the same
  assignment, runs, and reports; the driver takes the FIRST `jc:apply-result` from the
  tab, so a captcha frame's "no form found" can win the race. Gating to the frame that
  holds the form needs `autoApply.content.ts` / the driver to key by `frameId` (e.g. each
  frame reports its field count, the driver assigns the richest) — the Verify agent's
  files. Direct `job-boards.greenhouse.io` URLs are unaffected.

**Files.** extension: `src/background/apiProxy.ts` (new), `apiProxyCore.mjs/.d.mts/.test.mjs`
(new), `driver.ts` (one import line), `src/content/fieldDecision.mjs/.d.mts/.test.mjs`,
`formFill.content.ts`, `package.json` (test script lists the new test file).

**Dependencies added.** None.

**Tests.** Red first (module failed to load on the missing exports), then green.
Extension 37 → **53** (`npm test`): 13 in `fieldDecision.test.mjs` (EEO keywords, "sex"
whole-word, eligibility not caught, option-only EEO groups incl. the university
false-positive, demographic group never filled nor a question, radio/checkbox grouping,
unlabeled fallback, junk skipping, option cap, question-text picking, `planFill` for
select/radio/checkbox/combobox, native setter past a React-style tracker) + 3 in
`apiProxyCore.test.mjs` (allow-list, 15 refused method/path shapes, base64 round trip).
`architectureInvariants` still green. `tsc --noEmit` clean, `npm run build` clean; the
proxy code lands only in the worker bundle and the content bundle no longer contains
the API URL.

**Not verified / notes.**
- DOM glue not live-browser-tested (standing limitation): the proxy round trip inside a
  loaded extension, `click()` on styled radios, react-select detection, question-text
  walking on real Lever/Ashby markup, and whether the upload re-render still wipes text.
- The live test's `el.value` failure ran in the PAGE world. A real content script runs in
  an isolated world, where React's per-node tracker isn't visible, so plain assignment
  may already have worked there; the native setter is correct in both worlds.
- react-select comboboxes (Greenhouse Country, Yes/No questions) are never filled — their
  options aren't in the DOM until opened — so a required one stops the run every pass,
  and a bank answer can't clear it. Upgrade: open the menu, type, click the exact
  `[role=option]`.
- `submitApprovedApplication.ts` still fetches `claim-submission` from the content script
  — the same CORS failure as #1. It's the Verify agent's file; the fix is one more
  allow-listed route in `apiProxyCore.mjs` plus a `callApi` there.
- Still open from the report (other owners): #4/#5 confirmation and Ashby's missing
  `<form>`, #6/#9/#11/#12/#18 backend, #13 attach only in the final pass, #16 visible "✱"
  as required.

---

### 2026-09-27 (latest+36) — Scheduled runs: Maggie works without anyone pressing a button

**What changed.** The IA audit's gap: nothing ran by itself. The scheduler only ran
discovery; campaigns ran only on Launch/Start; and `Match` rows were only built when
someone opened `GET /matches`, so even a scheduled run would have found nothing new.
- *`workers.jobs.sweep_campaigns_task`* (new). For every `active` campaign: rebuild that
  profile's matches with the existing `build_matches`, then enqueue `run_campaign_task`
  with job id `campaign-<id>-sweep-<hour bucket>` + `unique=True` (layer 1) and the same
  Redis claim inside the task (layer 2). `sweep` keeps these ids apart from the manual
  per-minute ids; `[A-Za-z0-9_-]` only (rq 2.x, latest+27). No facts (no
  `fact_centroid`) or no job embeddings (no `VOYAGE_API_KEY`) → `build_matches` returns
  `[]` and the run uses existing matches — no special casing needed. Each campaign gets
  its own `session_scope` + try/except + `logger.exception`; one failure is reported in
  `failed` and the rest carry on.
- *Cadence* (`workers/run_scheduler.py`, rq-scheduler — croniter is not used). Discovery
  stays at `DISCOVERY_INTERVAL_SECONDS` = 4h (ARCHITECTURE §4.1); the sweep runs every
  `CAMPAIGN_SWEEP_INTERVAL_SECONDS` = 1h (`workers/jobs.py`, also the job-id bucket). Both
  are cancelled and re-registered on scheduler restart (was: discovery only).
- *Cap.* The scheduled path is `run_campaign_task → run_campaign → remaining_quota`, the
  same server-side rail as the manual run; nothing new computes quota.
- *Tenancy.* The sweep runs on the owner role (`session_scope` → `SessionLocal`), no RLS
  tenant. Every query is scoped by `campaign.id` / `profile_id` (`build_matches` by
  profile, `run_campaign` by campaign); events go to `campaign.profile.user_id`.
- *Observability.* `run_campaign_task(..., scheduled=True)` writes ONE
  `campaign.scheduled_run` event per run: `{campaign_id, created, reason}` ("Started 2
  applications." / "Nothing new to apply to."). `GET /activity` maps it to "Ran on
  schedule" (one-line hunk in `_ACTIVITY`). Web needs no change: unknown row types
  already fall back to a muted icon and link to /campaign.

**Run it locally on Windows** (two terminals, from `apps/api`, venv active, `.env` with
`REDIS_URL`/`DATABASE_URL`):
1. `python -m workers.run_worker` — `WindowsSafeWorker` (SimpleWorker +
   TimerDeathPenalty; the default forking worker crashes on Windows).
2. `python -m workers.run_scheduler` — registers discovery (4h) + sweep (1h), both fire
   immediately, then on interval. Enqueues only; the worker runs them.
One-off sweep without the scheduler:
`python -c "from workers.jobs import get_queue, sweep_campaigns_task; get_queue().enqueue(sweep_campaigns_task)"`.

**Files.** `apps/api/workers/jobs.py`, `apps/api/workers/run_scheduler.py`,
`apps/api/main.py` (one `_ACTIVITY` line), `apps/api/tests/test_scheduled_runs.py` (new).

**Dependencies added.** None. No migration.

**Tests.** 456 → **466**, all 10 new red first: sweep builds matches + enqueues only the
active campaign with an rq-valid id and `scheduled=True`; same id within a window,
new id next window; no facts / no embeddings → still enqueued, no error; one campaign's
`build_matches` raising doesn't stop the next; 5 sweeps in 5 windows (claim always
succeeds) → still exactly `daily_cap` applications; two users matching the same job →
each gets their own match/application, every event goes to the campaign owner;
`scheduled=True` writes exactly one event, a manual run none; `/activity` mapping;
scheduler registers both intervals and cancels both on restart.

**Not verified / notes.** Not run against live Redis/Postgres (the main checkout's worker
is live; tests only). Sweep and discovery are independent intervals, not chained, so a
sweep may run on jobs up to 4h old. Hourly "Nothing new to apply to." rows = up to 24
activity rows/day per campaign; if that's noise, write the event only when `created > 0`.
`build_matches` still scans every embedded job per profile (existing ponytail note).

---

### 2026-09-27 (latest+35) — Verify: 'submitted' only when the employer's page confirms it

**What changed.**
- *Extension, pure (`src/content/submitVerification.mjs`, new).* `decideVerification`
  takes `{urlBefore, urlAfter, pageText, formStillPresent, visibleErrorTexts,
  captchaVisible, elapsedMs}` → `confirmed | rejected (captcha | required_field |
  validation_errors) | unconfirmed | pending`. Confirmed: URL changed to a
  `/thanks`, `/confirmation`, `/thank-you`, `/success`… path, or confirmation text
  ("thank you for applying", "application (has been|was) (successfully) submitted|received",
  "we('ve| have) received your application") **once the page moved on** (new URL or
  form gone — a careers header can say "thank you for applying" above the form).
  Rejected: a visible captcha challenge frame (reCAPTCHA `bframe`, hCaptcha
  `frame=challenge`, Cloudflare), or the form still there with errors after 1.5s.
  Unconfirmed: nothing by 20s. `verificationReport` maps confirmed→`submitted`,
  rejected→`needs_human`, unconfirmed→`unconfirmed`.
- *Extension, glue.* `autoApply.content.ts` polls the page every 500ms after submit
  (errors read inside the form only: `role=alert`, error classes, `aria-invalid` +
  its described-by text, native `:invalid` — `requestSubmit()` silently refuses an
  invalid form). **Navigation handoff:** right before the native submit
  (`submitApprovedApplication`'s new `beforeSubmit` hook, after the claim) the page
  sends `jc:submit-sent {urlBefore, sentAt}` and waits for the driver's ack; no ack →
  throw → nothing is submitted. The driver stores `verify` on the tab's in-memory
  assignment and swaps its 60s timer for 20s+10s → `unconfirmed`. The page the submit
  navigates to gets a fresh content script; `jc:what-am-i-doing` now returns the item
  with `verify`, so it only watches, never fills or submits again. First report wins.
  Not `chrome.storage.session`: the state is only useful while the driver's `runItem`
  loop is alive to take the report, and that loop is in-memory too. Once sent, any
  error reports `unconfirmed`, never `failed` (a retry could apply twice).
- *Ashby has no `<form>`* (docs/LIVE-FORM-TEST.md #5): now `needs_human` with a plain
  reason instead of `failed`. Clicking Ashby's own button was not built: it needs the
  React value fix (#3) first, or it would submit empty fields.
- *API.* `SubmissionResultIn.outcome` gains `unconfirmed` →
  `ApplicationStatus.submitted_unconfirmed` (migration **`0017`**, `ALTER TYPE ... ADD
  VALUE IF NOT EXISTS ... BEFORE 'applied'`, same as 0013; **not applied to Neon**).
  Stamps `applied_at` (= when it was sent), never re-enters the work queue or the
  review queue; the user PATCHes it to `applied` (applied_at kept). `/today` gains
  `unconfirmed_today` (of `sent_today`). `/activity` maps `application.unconfirmed` to
  "Sent to {company} — couldn't confirm it went through" plus `apply_url`. Daily cap
  unchanged: it counts rows created, whatever their status. `needs_input.py` reads
  `[unconfirmed]` stamps so an older needs_human line isn't taken as the last attempt.
- *API, pre-existing bug fixed.* `failed`/`needs_human` reported **before** a claim
  (blocking field, no form, captcha on load) hit a row still `approved` and 409'd, so
  those cards never reached the review queue live. They now close from `approved`
  too; `submitted`/`unconfirmed` still require the claim.
- *Web.* Today row: mail-question icon in warning tone, "Check your email for a
  confirmation from {company}, or open the form."; the row opens the form (new tab,
  http(s) only). Summary: "3 applications sent today, 1 not confirmed yet."

**Why rejected → needs_human, not failed.** A retry refills the same data and hits
the same error, up to 3 times; the review card ("other" kind) shows the employer's
error text and "open the form". A captcha reason keeps the word "captcha" so the card
says so.

**Files.** extension: `src/content/submitVerification.mjs/.d.mts/.test.mjs` (new),
`autoApply.content.ts`, `submitApprovedApplication.ts`, `background/driver.ts`,
`package.json` (test list). api: `models.py`, `schemas.py`, `main.py`,
`needs_input.py`, `alembic/versions/0017_application_status_submitted_unconfirmed.py`,
`tests/test_submission_unconfirmed.py` (new), `tests/test_activity.py` (new key in two
exact-dict asserts). web: `lib/today.ts`, `lib/today.test.ts`, `lib/api.ts`,
`app/today/page.tsx`.

**Dependencies added.** None.

**Tests.** Red first on every layer. api 456 → **462** (5 red on `submitted_unconfirmed`
missing, then 1 red on the pre-claim 409). extension 36 → **51** (module-not-found
red). web 87 → **91** (4 red). `architectureInvariants` still green: the native
submit stays only in `submitApprovedApplication.ts`. Extension `tsc` + build, web
`tsc` + `next build` clean.

**Confirmation wording — what is verified.** Lever: fetched a live
`jobs.lever.co/<co>/<id>/thanks` page, "Application submitted!". Greenhouse: the
`/confirmation` route (LIVE-FORM-TEST.md page source; search-index titles "Thank you
for applying…"; direct fetches 404'd). Ashby: "Your application was successfully
submitted." (LIVE-FORM-TEST.md page source); companies can customise it.

**Not verified.** No live submit (by design) and no loaded-extension run: the
navigation handoff, the polling glue and the error/captcha DOM reads are verified by
reading only. A service-worker restart mid-verify loses the driver loop (pre-existing,
same as `attempts`); the row stays `submitting`.

**Next.** Apply `0017` to Neon before deploying this API (a `submitted_unconfirmed`
write fails on 0016). Ashby submit via its button once the React value fix lands. A
web control to mark an unconfirmed application applied (the API PATCH exists).

---

### 2026-09-27 (latest+34) — NVIDIA NIM is the production LLM provider (owner decision)

**What changed.** New `LLM_PROVIDER=nvidia` (the old `nvidia_smoke` stays as the dev-only,
unvalidated path). `nvidia` runs through the SAME validated paths as Claude: tailoring
uses instructor (`from_openai`, JSON mode) with fact-id grounding + bounded retry +
truth-check; resume facts, identity and form mapping all route to NIM.
`core/config.py`: `nvidia_model` (default `nvidia/nemotron-3-super-120b-a12b`),
`nvidia_enable_thinking` (default off) and `nvidia_extra_body()`. `tests/conftest.py`
pins `LLM_PROVIDER=anthropic` so a developer's `.env` can never route a test to a live
model (found live: switching `.env` sent 4 tests to NVIDIA and took 3 minutes).

**Model choice — live bake-off** (fabrication-trap task: 3 true facts, JD demanding
Kafka): nemotron-3-super 4.8s, valid JSON, only real fact ids, no Kafka ✓ (chosen).
kimi-k3 passed but 31s and embellished ("distributed"). glm-5.3-flash 259s.
deepseek-v4.1-flash, glm-5.3, gemma-4-31b timed out; mistral-large, kimi-k2.6 → 404 on this key.

**Problems hit.** Tailoring hit `IncompleteOutputException` at max_tokens 1500, then
intermittently at 4096: the model reasons by default. Measured: thinking off answered
in 0.7s vs 4.4s with ~¼ the tokens. Now off via `chat_template_kwargs.enable_thinking`;
two consecutive live runs all four paths OK (tailoring 5–11s).
**Quality caveat (measured, not fixed):** with thinking off the truth-check is weaker —
run 1 bullets added unsupported padding ("on-time delivery", "across microservices")
and nothing was flagged; run 2 flagged a line that was supported. Needs the ADR-014
eval run on `nvidia` before trusting auto-submit; options: thinking on for the
truth-check pass only, or a stricter "no added claims" rewrite prompt.

**Tests.** 456/456 (new: nvidia uses validated path + model + OpenAI message shape +
max_tokens + thinking-off body; extract routes to NVIDIA and finds JSON inside prose;
`nvidia_extra_body` only for the real provider). Red before green each time.

---

### 2026-09-27 (latest+33) — tzdata pinned; Redis replaced; worker loop verified live

**What changed.** `tzdata==2026.3` added to `apps/api/requirements.txt` — it was only
present transitively (pandas), but `GET /today` depends on it directly (zoneinfo local
day); without IANA data on a slim Linux image every user silently counts on the UTC day.
Same version already installed (`pip install --dry-run`: nothing to install). New Redis
Cloud instance in `apps/api/.env` (`REDIS_URL`, gitignored; the old DB's host no longer
resolved). Verified live: PING ok; `POST /campaigns/{id}/run` and `POST /discover/run`
return queued; `workers/run_worker.py` processed a campaign run to "Job OK".

**Dependencies added.** tzdata (pin of an already-installed transitive dep, owner-approved).

**Next.** Rotate the Redis password (it was pasted in chat). Real `ANTHROPIC_API_KEY`.

---

### 2026-09-27 (latest+32) — Skipped jobs show in Today; one meaning of "today"

**What changed.**
- *Skip events (API).* `run_campaign` now writes `campaign.skipped` events (existing
  outbox `write_event`, same commit as the applications) with payload
  `{campaign_id, job_id?, reason_code, reason}`. Only matches **new since
  `last_run_at`** are "looked at", so a job is reported once, not every run. Per-job rows
  only for jobs inside the campaign's filters (role/location/source/remote) that were
  passed on: `already_applied`, `below_score` ("Score 61%, below your 70% minimum"),
  `daily_cap`. At most `SKIP_EVENT_LIMIT` (20) per run. Everything else is one summary
  row per run: `checked` — "Checked 214 new jobs; 12 fit your campaign." (+ "N more
  skipped, not listed." past the limit). Run-level rows: `not_active` (paused/draft run)
  and `daily_cap` when the cap was already used and nothing new arrived. The campaign
  filters were pulled out of `select_candidates` into `_in_bounds` so the skip report and
  the picker use the same bounds. `last_run_at` is now stamped on every active run
  (cap-reached too, with the run's start time) so the "new since" window is right.
- *`GET /activity`.* Maps `campaign.skipped`: with a job → title "Skipped" + job + reason
  (row reads "Skipped · Staff Engineer at Acme / Score 61%…"); without one → "Checked new
  jobs" / "Daily limit reached" / "Didn't run" by `reason_code`.
- *One "today".* `GET /today?tz=<IANA>`: `campaigns.local_day_start(tz)` (zoneinfo;
  unknown/invalid → UTC; `max_length=64`) is the day start for `sent_today` and
  `new_matches_today`, so the counters match the activity list's local day. The daily
  cap stays on `utc_day_start` (server-side rail). Web `api.getToday()` sends
  `Intl.DateTimeFormat().resolvedOptions().timeZone`; the "Sent today" tile caption is
  now `dailyLimitCaption` — "Daily limit 10 · resets 5:30 AM your time" (next UTC
  midnight in the viewer's clock). Activity rows for skips: skip-forward icon, muted,
  link to /campaign (where score/limit/roles are changed).

**Files.** API: `campaigns.py`, `main.py`, `tests/test_campaigns.py`,
`tests/test_activity.py`. Web: `lib/today.ts`, `lib/today.test.ts`, `lib/api.ts`,
`app/today/page.tsx`.

**Dependencies added.** None. No migration.

**Tests.** Red first on both layers. API 446 → **452** (6 new, all red: no skip events,
unmapped type, no `local_day_start`): per-job reasons + summary + off-role jobs only
counted; second run doesn't re-report (one run-level cap row); 25 low-score → 20 rows +
"5 more"; paused run → one `not_active`; activity mapping; `/today` Kolkata vs
UTC/invalid tz. Web 85 → **86** (red: `dailyLimitCaption` missing, `tz` not sent; the
`/today` contract test now checks the `tz` param; `activityHref("campaign.skipped")`).
`tsc` caught `queryFn: api.getToday` passing react-query's context as `tz` → wrapped.
`tsc` clean, `next build` clean (`/today` 6.46 kB).

**Not done / notes.** Not verified against a live API/browser. Discovery (`match.new`)
itself doesn't write skip rows — jobs the matcher's hard filters drop never become
matches, so "Checked N" counts matches, not raw scraped jobs. `tzdata` isn't in
requirements; zoneinfo works here (Windows) and on Linux via system tz — pin `tzdata` if
a slim image lacks `/usr/share/zoneinfo` (it would silently fall back to UTC).

---

### 2026-09-27 (latest+31) — EEO fields: optional ones are left blank and no longer stall auto-apply; required ones still stop

**What changed.**
- *Pure layer (`fieldDecision.mjs`).* A demographic field is still never filled, by
  anything. `decideFieldActions` now splits the old `demographic` flag by required-ness:
  `demographic_required` (blocks) vs `demographic_left_blank` (does not). A radio group is
  required if any member with the same `name` is. Optional ones are left untouched — not
  even "Decline to self-identify", since picking an option is answering.
  `NEEDS_USER_REASONS` and the needs_human message (`needsHumanReason`) moved here from
  `autoApply.content.ts` so the blocking rule is unit-tested. The message spells the reason
  as "required demographic self-identification question": `needs_input.py` keys
  `demographic_left_blank` on `\bdemographic\b`, and `_` is a word char, so the raw code
  `demographic_required` would not have matched.
- *DOM glue (`formFill.content.ts`).* `required` also reads `aria-required="true"` on the
  element or any wrapper (ARIA puts it on the radiogroup, not the radios). Optional EEO
  fields get a grey dashed outline + "Left blank for you — ApplyScout never answers
  these."; required ones keep the red outline with a "required self-identification" note.

**Why.** latest+28's Problems hit: every form with an EEO section (most Greenhouse/Lever
forms, where it is optional voluntary self-identification) stopped at `needs_human` on
every pass, so approving again could never send it.

**Files.** extension: `src/content/fieldDecision.mjs`, `fieldDecision.d.mts`,
`fieldDecision.test.mjs`, `autoApply.content.ts`, `formFill.content.ts`.

**Dependencies added.** None.

**Tests.** Red first: missing exports, then with stubs 5 failing (old `demographic`
assertions, optional-vs-required, radio group, message word-boundary) → green. Extension
33 → **36** (`npm test`). `tsc --noEmit` clean, `npm run build` clean.
`unansweredQuestions` still never returns a demographic label (both reasons covered).

**Not done / notes.** DOM glue not live-browser-tested (standing limitation). A radio's
own label is usually the option ("Male"), not the question, so a radio EEO group is only
recognised when its label text carries the keyword — pre-existing gap, unchanged. On a
successful submit with blank optional EEO fields nothing is reported (fine: nothing was
answered). Web copy for `demographic_left_blank` now only appears for required ones.

---

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
