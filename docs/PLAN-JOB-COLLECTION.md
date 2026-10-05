# Plan: job collection

**Status:** in progress. Stages COLLECT-A and COLLECT-B are done; COLLECT-C is next and
starts with a decision, not with code.

**Why this doc exists.** This plan had no document. Stages A and B were built from "Next" notes
at the bottom of `docs/WORKLOG.md` entries, and both were called "Phase 1" and "Phase 2" — the
same numbers `PLAN-MULTI-ATS.md` uses for entirely different work. On 2026-10-03 "start phase 3"
was genuinely ambiguous and stalled a session (`docs/GAPS.md` 7.3).

---

## Naming convention — read this before writing "Phase N" anywhere

**A bare phase number is ambiguous in this repo and must not be used.** Two plans run in
parallel, so every stage carries its plan's prefix:

| Plan | Prefix | What it covers |
|---|---|---|
| `PLAN-JOB-COLLECTION.md` (this doc) | `COLLECT-A`, `COLLECT-B`, … | Getting jobs into the pool: sources, freshness, ingestion health |
| `PLAN-MULTI-ATS.md` | `ATS-0`, `ATS-1`, … | Filling and submitting application forms (ADR-016) |

Letters, not numbers, so a stage can be inserted without renumbering the rest. Say
"COLLECT-C", never "Phase 3". `PLAN-MULTI-ATS.md`'s existing "Phase 0/1/2/3" map to
`ATS-0/1/2/3`.

---

## Where this plan sits

Collection ends when a job is in the pool, still listed, embedded and matchable. What happens
to it afterwards — tailoring, form plans, submission — is `PLAN-MULTI-ATS.md` and ADR-015.

The rails from ADR-015 and ADR-017 apply to every stage below and are not re-litigated:
expiry is by source absence and never by age; only a source returning a complete listing may
be swept; a failed or empty fetch delists nothing; no AGPL vendoring; every new dependency
needs the owner's approval.

---

## COLLECT-A — Freshness · **DONE** (2026-10-03, WORKLOG latest+67, ADR-017)

A job could not stop being current. `upsert_jobs` was insert-only, `last_seen_at` was written
once and never read, Greenhouse stored a modification date in `posted_at`, and greenhouse/
lever/ashby stored the board *token* in `company`, defeating the cross-source dedupe that
`canonical_hash` exists for.

Delivered: re-seen rows UPDATE, `posted_at` is a real date per source, real company names,
absence-based delisting via `Job.delisted_at` (migration 0022), `canonical_hash` no longer
UNIQUE. 742 → 807 tests.

## COLLECT-B — Resilience · **DONE** (2026-10-03, WORKLOG latest+68/+69)

Freshness was possible but ingestion was not survivable: one source's bad day cost the whole
run, and nothing recorded which source had the bad day.

Delivered: per-source error isolation (`_isolate`), one `connector_runs` row per source per run
with `/sources` reading it, per-host pacing, jobicy paged to exhaustion and added to
`SWEEPABLE_SOURCES`, five verified board tokens. 807 → 824 tests.

Measured and closed out: five of six keyless feeds **cannot** be paginated to exhaustion
(himalayas 5,786 requests/run, arbeitnow 429s at page 21, three have no knob). Don't re-probe —
the numbers are in `tests/test_feed_pagination.py`.

---

## COLLECT-C — Reach · **DONE for Workday** (2026-10-04, ADR-018, WORKLOG latest+72)

`connectors/workday.py` is live, wired into discovery and in `SWEEPABLE_SOURCES`, with two
verified tenants (adobe, cisco — both with an India-located product role). Fetched every 6th
hour, not every run: two boards measured ~4.3 minutes and discovery shares a single worker.

**Still open in this stage:** the owner's ruling on SmartRecruiters' `robots.txt: Disallow: /`
(ADR-018 §7), which is the only route to Swiggy. Workable is implemented-not-worth-it, Keka
needs a re-probe (expired TLS certs), Darwinbox stays out.

The measurement that drove all of it is below, unchanged.

**The problem, measured.** 117 candidate slugs were probed live across Greenhouse, Lever and
Ashby. 42 had a live board. **19 of 22 Indian consumer-tech companies had none at all** —
razorpay, swiggy, zomato, phonepe, flipkart, zepto, zerodha, myntra, nykaa, delhivery, paytm,
urbancompany, lenskart, cars24, blinkit, rapido, licious, udaan.

The owner's search is India PM roles. **Adding more tokens to the three ATSs we support has a
low ceiling for that search**, because the target companies are not on those ATSs.

**This stage cannot start as code.** It needs an ADR choosing a source class. The options, with
what each actually costs:

| Option | What it needs | Risk |
|---|---|---|
| **Other ATSs** — Darwinbox, Keka, SmartRecruiters, Workable | A public per-company endpoint per platform, found by reading live responses. SmartRecruiters and Workable have documented public APIs; Darwinbox and Keka need checking and may not. | Low if a public API exists; the connector contract already fits. Highest chance of clean structured data. |
| **Indian job boards** — Naukri, Instahyre, Hirist, Cutshort | None has a public API. Means scraping, and checking each one's ToS and bot defences. | Account-safety and legal exposure. ADR-015 reversed no-scraping, but its rails still stand. |
| **Company career pages directly** | Per-company work; the ATS-discovery classifier (F5, `connectors/discovery.py`) already proposes patterns. | Doesn't scale without the classifier being good, and that is unmeasured. |
| **Accept the ceiling** | Nothing. Be explicit that coverage is global-remote plus a few India offices. | Honest, and leaves the owner's actual search underserved. |

**First task — DONE 2026-10-03: `docs/harness-reports/collect-c-platforms.md`.** All five
platforms probed live. Headline: **only 1 of the 19 unreachable companies is reachable at all
(Swiggy, on SmartRecruiters)**, and the measurement reframes the stage —

- **No platform here offers cross-company search.** SmartRecruiters, Workday and Workable are
  all per-company-identifier APIs, structurally identical to greenhouse/lever/ashby. Adding one
  does not add reach by itself; **company→platform discovery is the actual work**, and it
  inherits COLLECT-D's token problem.
- **Workday reaches India PM roles at multinational GCCs** (verified: Adobe, Principal PM,
  Bangalore) — a large currently-unserved slice — and its `robots.txt` explicitly allows the
  career path. Cleanest option. `postedOn` is prose ("Posted 30+ Days Ago"), so `posted_at`
  needs a detail fetch or stays NULL.
- **SmartRecruiters has the best data contract** (real `releasedDate`, ISO country code) **but
  its API host serves `robots.txt: Disallow: /`** — an owner decision, deliberately not resolved
  in the report.
- **New trap: dead accounts.** Three of four SmartRecruiters hits had the right company name and
  postings from 2016/2018/2021. Existence is not liveness — **gate on posting recency**. Same
  class of error as COLLECT-B's `slice`/`porter`/`navi` slugs.
- Workable: 17 of 19 accounts exist, **all with `jobs: []`**. Caught only by a nonsense-slug
  control; without it this stage would have "solved" the gap on a false positive.
- Keka: every `*.kekahire.com` host failed TLS (expired certificate). Darwinbox: empty SPA shell.

**Recommended next step (not yet decided):** ADR taking **Workday first** on compliance grounds,
SmartRecruiters second gated on the robots call — **and seriously consider that measuring
`connectors/discovery.py`'s unmeasured F5 ATS classifier may be worth more than either
connector**, since discovery is the binding constraint.

**Done when:** an ADR is accepted, one new source class is live behind the same connector
contract, and it is either in `SWEEPABLE_SOURCES` with evidence or explicitly excluded with a
measured reason.

> **India coverage CLOSED 2026-10-05 (ADR-020).** All four cross-company India boards were
> evaluated in parallel and all four are unusable unlicensed — Instahyre, Cutshort and Hirist
> `legally-prohibited`, Naukri `blocked` by Akamai at request one. `robots.txt` turned out to be
> uncorrelated with permission (the easiest source had the most explicit ban), and two boards
> name a *competing product* specifically. Licensing is the only sanctioned route and it is a
> business action, not an engineering one. See `docs/harness-reports/india-job-boards-feasibility.md`.

## COLLECT-D — Board identity · **DONE** (2026-10-04, migration 0023, WORKLOG latest+73)

`Job.board_token` ships, stamped by the greenhouse/lever/ashby/workday connectors and refreshed
on re-seen rows. `_sweep_delisted(db, source, token, jobs)` scopes per board, and
`_fetch_ats_source` now returns one batch per board that answered instead of an all-or-nothing
trust flag. Removing a token or tenant from config is no longer destructive, and one silent
board no longer blocks delisting for the rest of its source. 839 → 850 tests.

**Correction to what this section originally claimed:** it said this "also removes the
'editing `FEED_KEYWORDS` would tombstone a swept source' hazard". **It does not.** Narrowing
`FEED_KEYWORDS` still drops stored jobs out of the keyword-filtered payload the sweep compares
against, so they get tombstoned. That is independent of board identity and remains open.

**Residue:** an ATS job that closed *before* migration 0023 keeps `board_token = NULL`, is never
re-seen, and so is never tombstoned. Stale beats tombstoning live jobs; a one-off script can
clear those if the count matters.

The original scope, for the record:

**Why it's coupled to C.** `Job` has no `board_token` column, so the delisting sweep is
source-wide. **Removing a token from `connectors/config.py` tombstones that board's entire
inventory on the next run, even though every job is still live** (ADR-017 consequences; the
trap is documented at the token lists). Editing config is currently a destructive data
operation.

That is survivable with 20 tokens. COLLECT-C plausibly multiplies the token count, and with it
the chance of someone pruning a token and silently killing live jobs.

**Work:** add `Job.board_token`, write it in the greenhouse/lever/ashby connectors, scope
`_sweep_delisted` per token instead of per source, and replace `_fetch_ats_source`'s
all-or-nothing trust flag with per-token trust — one flaky board then blocks delisting only for
itself. This also removes the "editing `FEED_KEYWORDS` would tombstone a swept source" hazard.

**Done when:** a token can be removed from config without tombstoning anything, proven by a
test, and one flaky board no longer suppresses the whole source's sweep.

## COLLECT-E — Liveness · **REJECTED** (2026-10-04, ADR-019, WORKLOG latest+74)

Probing a stored job's own `apply_url` for 404/410 was measured and rejected
(`docs/harness-reports/collect-e-liveness.md`). The bar was a false-positive rate of 0 on a
sample of jobs that are live by construction. Measured instead:

| Feed | Codes on 8 live jobs | False positives |
|---|---|---|
| remoteok | `{200: 8}` | 0% |
| arbeitnow | `{200: 8}` | 0% |
| workingnomads | `{200: 5, 403: 3}` | **37.5%** |
| himalayas | `{403: 8}` | **100%** |
| weworkremotely | `{403: 8}` | **100%** |

The 100% failures are exactly the feeds with no pagination escape, so the mechanism yields
nothing where there is no alternative; workingnomads is inconsistent on a single host, which is
noise rather than a special-casable rule; and a 404/410-only rule reads 403 as "no signal", so
those feeds gain zero for several hundred requests a run. UA spoofing and a headless browser per
job were both rejected (ADR-019).

**The five truncated feeds stay stale by decision, with a number behind it.** The productive
path is more complete-listing sources (ADR-018's Workday), not cleverer expiry — a sweepable
source needs no probe.

## COLLECT-F — Hygiene · **DONE** (2026-10-04, WORKLOG latest+74)

Two items built, two decided and documented.

- **`connector_runs` retention — DONE.** One bulk DELETE per discovery run, 30-day window (`RUN_RETENTION_DAYS`). **F5's ATS-classifier rows are never pruned:** `models.ConnectorRun`'s docstring calls them the owner's review surface for proposed ATS patterns, so age-pruning them would destroy an un-reviewed decision queue. Pinned by a test.
- **Remote-country filtering — NOT BUILT, and the gap was described wrongly.** `_OPEN_WORDS` already filters "Remote - United States" correctly for *any* known country; `_COUNTRY_NAMES` only needs the user's own country, not a world list. The real hole is a profile with **`country_code` unset** (it is optional, parsed from the resume), which disables the filter entirely. A 200-country table is YAGNI with one India-based user and would need a new dependency (`pycountry`/`babel` — none installed, and adding one needs the owner's approval). **The product fix is making country required at onboarding**, which is the owner's call.
- **JobSpy — DONE, dropped from the UI.** `jobspy_google` is gone from `/sources`: it was advertising a source that `discover_jobs_task` has never fetched. The connector and its isolated venv stay (reviving it is a separate decision), it is just no longer offered to users. A new test pins the invariant **both ways** — every advertised source must be fetched, and every fetched source must be advertised.
- **Duplicate `canonical_hash` — DECIDED: permanently accepted.** Two live rows can share a hash (ADR-017 §5) and nothing re-collapses the pair. Re-collapsing means picking a winner and rewriting or tombstoning the loser, which is the destructive direction for a cosmetic problem: the cost is one duplicate card in a list, the risk is deleting the row a user already applied through. Not worth it. If duplicates ever become visibly annoying, de-duplicate at **read** time in the matches query, never by mutating rows.

---

## How we'll know collection works

| Metric | Target |
|---|---|
| Live jobs wrongly tombstoned | **0** — any false delisting fails the stage |
| Jobs in the pool matching the owner's campaign bounds | grows stage over stage; was 20 India matches at latest+63 |
| Sources with real freshness (in `SWEEPABLE_SOURCES`) | 4 today; every new source either qualifies with evidence or is excluded with a measured reason |
| A failing source's blast radius | confined to that source — held by COLLECT-B |
| Stale rows from non-sweepable sources | known and stated, never silently presented as fresh |

## Related

`docs/GAPS.md` (every open item, with evidence) · `docs/DECISIONS.md` ADR-015 and ADR-017 ·
`docs/PLAN-MULTI-ATS.md` (the `ATS-*` stages) · `docs/WORKLOG.md` latest+67/+68/+69
