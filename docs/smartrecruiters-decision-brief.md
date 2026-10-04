# Decision brief: adopt SmartRecruiters as a source, or not?

**For:** the product owner · **Prepared:** 2026-10-04 · **Status:** awaiting decision
(ADR-018 §7 deferred it; this is the evidence, not a recommendation)

COLLECT-C found SmartRecruiters is the **only** route to any of the 19 Indian consumer-tech
companies that have no Greenhouse/Lever/Ashby board. One decision blocks it, and it is a
judgement call rather than a technical one.

---

## 1. The facts, measured or quoted

| Evidence | Source |
|---|---|
| `GET api.smartrecruiters.com/v1/companies/{id}/postings` returns clean JSON, no auth, with a real `releasedDate` and ISO country code | measured live 2026-10-03 |
| **Swiggy: 168 live postings**, including a PM in Bengaluru | measured live |
| **`api.smartrecruiters.com/robots.txt` = `User-agent: * / Disallow: /`** | fetched live |
| Vendor docs call it "available only to specific endpoints which contain publicly available data", usable "Without Authentication", for "customers to build fully customizable career sites and **partners to build widgets**", at **10 requests/second** | `developers.smartrecruiters.com/docs/customer-overview` |
| Use of SmartRecruiters APIs is **governed by the SAP API Policy** (SmartRecruiters is SAP-owned) | vendor developer docs |
| The public Postings feed is **tier-dependent** — customers on lower plans do not have it enabled, and no endpoint enumerates who does | vendor docs + consistent with our measurement |

## 2. The tension

The vendor **publishes this endpoint for third-party reading without authentication**, and
describes partner widgets as an intended use. The same host's `robots.txt` tells all crawlers to
read nothing.

These are not actually contradictory: `robots.txt` governs *crawlers* indexing a site's URLs,
while the developer docs govern *API clients* calling a documented endpoint. Reading a published
JSON API for one company you already identified is the second thing, not the first.

**That is the standard reading, and it is still a reading.** A conservative position — treat any
`Disallow: /` on a host as declining automated access — is defensible and would rule this out.

## 3. What I have NOT verified

**I have not read the SAP API Policy itself.** The chain "SmartRecruiters APIs → governed by the
SAP API Policy" comes from the vendor's own docs, and there is recent trade reporting that SAP
tightened that policy specifically around AI/third-party access. **Whether it permits this use is
the one question that actually decides this, and it needs reading before anyone relies on it.**
Do not treat §2's reasoning as settling it.

## 4. The yield, which matters to the decision

Even granted permission, the upside is **narrow and does not scale**:

- **1 of 19** target companies has a live feed (Swiggy). The other 18 are not on SmartRecruiters
  with an enabled public feed.
- The feed is tier-dependent and **per-company**: there is no directory, so every company must be
  identified by hand — the same company→platform discovery constraint COLLECT-C identified as the
  real binding limit on reach.
- Three of the four hits we found were **abandoned accounts** with postings from 2016/2018/2021
  (`Zomato1`, `Meesho1`, `Cars24`), so any adoption must gate on posting recency, not existence.

So the realistic framing is: **this buys Swiggy**, plus a mechanism that needs a curated company
list forever.

## 5. The options

| | Option | Consequence |
|---|---|---|
| A | **Adopt**, treating `robots.txt` as crawler-directed and the documented API as intended for this | Gains Swiggy. Requires reading the SAP API Policy first (§3), a recency gate (§4), and accepting the position knowingly |
| B | **Decline**, treating `Disallow: /` as binding | Swiggy stays unreachable. Costs one company; costs nothing else |
| C | **Defer** until the SAP API Policy is read | The honest default if §3 is unresolved — the question is cheap to answer and expensive to get wrong |

## 6. Why this is not mine to decide

ADR-016 §4 makes licence and ToS checks a precondition for any new source, and ADR-015 explicitly
records that the owner accepts the ToS/ban risk for end users — i.e. that this class of risk is an
owner-level call. The measurement is done; the judgement is not a measurement.

**Related:** `docs/harness-reports/collect-c-platforms.md` (the full platform measurement),
`DECISIONS.md` ADR-018 §7 (where this was deferred), `GAPS.md` 3.1.
