# COLLECT-E measurement — can we delist a feed job by probing its own `apply_url`?

**Date:** 2026-10-04 · **Stage:** COLLECT-E, the measurement the plan requires before the ADR ·
**Verdict: NO. Rejected.** Recorded as ADR-019.

## The idea

Five of the six keyless feeds cannot be paginated to exhaustion (COLLECT-B measured why:
himalayas needs 5,786 requests/run, arbeitnow 429s at page 21, three have no pagination knob at
all), so they can never be swept for delistings and their rows go stale forever.

The proposal was to probe each **stored** job's own `apply_url` and treat 404/410 as gone. That
is *direct evidence a posting is removed*, which is stronger than inferring from absence, and it
costs one request per job we hold (hundreds) rather than per job the feed has (115,729 for
himalayas alone).

## The test

The dangerous failure mode is a **false positive**: tombstoning a job that is still open. So the
sample was jobs each feed is listing **right now** — every one live by construction — and the
measurement is simply what their `apply_url` returns. 8 jobs per feed, 0.8s pacing, our normal
User-Agent.

## Result

| Feed | Live jobs probed | Status codes | False-positive rate |
|---|---|---|---|
| remoteok | 8 | `{200: 8}` (all redirected) | 0% |
| arbeitnow | 8 | `{200: 8}` | 0% |
| **workingnomads** | 8 | `{200: 5, 403: 3}` | **37.5%** |
| **himalayas** | 8 | `{403: 8}` | **100%** |
| **weworkremotely** | 8 | `{403: 8}` | **100%** |

The plan's bar was *"a measured false-positive rate of 0 on a sample"*. Three of the five feeds
this stage exists to help fail it outright.

## Why this is fatal, not fixable

1. **The three worst offenders are exactly the feeds that need it.** himalayas and
   weworkremotely 403 every request; they are also two of the three feeds with no pagination
   escape. The mechanism yields nothing precisely where there is no alternative.
2. **workingnomads is inconsistent on the same host** — 5× 200 and 3× 403 across eight
   sequential requests. That is the worst possible shape: not a clean "this host blocks us" rule
   you can special-case, but noise. Any threshold drawn through it is arbitrary.
3. **Restricting the rule to 404/410 only does not rescue it.** These are 403s, so a
   404/410-only probe reads them as "no signal" and the three feeds get *zero* delisting signal —
   the status quo, for the cost of several hundred requests per run.
4. **Even for remoteok and arbeitnow the expected yield is unverified and probably near zero.**
   Aggregators keep job pages up for SEO long after a role closes, so a closed posting most
   likely still answers 200. Proving otherwise needs a set of known-dead URLs, which we do not
   have — those two feeds have never been sweepable, so nothing has ever been tombstoned to
   calibrate against.

Softening the rule in any direction makes it worse: widen past 404/410 and the 403s start
tombstoning live jobs at a measured 100% rate on two feeds; keep it narrow and it buys nothing.

## Not pursued, and why

- **Spoofing a browser User-Agent** would likely clear the 403s. Rejected on the same grounds as
  in COLLECT-C: these rails exist so the product does not depend on looking like something it
  isn't, and a 403 is the host declining automated access.
- **A headless browser per job** inverts the cost argument the idea rested on (cheap, one request
  per stored job) and is a much larger dependency than the problem justifies.

## What to do instead

Nothing, for now. The honest position is the one ADR-017 already takes: **the five truncated
feeds accumulate stale rows, and that is stated rather than hidden.** Freshness is real for
`greenhouse, lever, ashby, jobicy, workday` — the five sources that return a complete listing.

The cheaper paths to better freshness, in order of value:
1. More sources that return a **complete listing**, which is what COLLECT-C/ADR-018 did with
   Workday. A sweepable source needs no liveness probe.
2. If a feed ever ships a cursor API (jobicy did, which is why it qualifies), it becomes
   sweepable for free.

## Reproducing

Scratch script, ~40 requests. The shape is: fetch the feed, take jobs it is listing now, GET
each `apply_url` with our UA, record status codes. The control that matters is that the sample is
**live by construction** — any non-200 is a false positive, no interpretation needed.
