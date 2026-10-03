# COLLECT-C platform measurement — can a new ATS reach Indian companies?

**Date:** 2026-10-03 · **Stage:** COLLECT-C, the measurement task that must precede the ADR
(`docs/PLAN-JOB-COLLECTION.md`) · **Method:** live probes, 0.5–0.6s pacing, every field name
read off a real response. `robots.txt` fetched per host *before* any job path.

**The question.** COLLECT-B measured that **19 of 22 Indian consumer-tech companies have no
board on Greenhouse/Lever/Ashby**. Does adding Darwinbox, Keka, SmartRecruiters, Workable or
Workday reach them?

**The answer: one of the 19. Swiggy.** Everything else is either a dead account, an
unreachable platform, or a compliance decision.

---

## 1. Verdict per platform

| Platform | Public keyless JSON? | `robots.txt` | Reaches the 19? | Verdict |
|---|---|---|---|---|
| **SmartRecruiters** | **Yes** — `GET api.smartrecruiters.com/v1/companies/{id}/postings` | ⚠ **`Disallow: /`** on the API host | **1 of 19 — Swiggy, live** | Technically the best fit; **blocked on a robots/ToS decision** |
| **Workday** | **Yes** — `POST {tenant}.wd{N}.myworkdayjobs.com/wday/cxs/{tenant}/{site}/jobs` | Allows the career-site path explicitly | 0 of 19, but **reaches India PM roles at multinational GCCs** | Viable. Tenant+site discovery is the cost |
| **Workable** | **Yes** — `GET apply.workable.com/api/v1/widget/accounts/{slug}?details=true` | `Disallow:` (empty — allows all) | 17 of 19 have an account; **all have `jobs: []`** | Contract fine, yields nothing today |
| **Keka** | Unknown | n/a | n/a | **Blocked: expired TLS certificate on every `*.kekahire.com` host tried** |
| **Darwinbox** | **No** | no rules served | n/a | Career page is an empty SPA shell (561–951 bytes). Needs JS rendering |

## 2. SmartRecruiters — the only real hit, and a trap

`GET https://api.smartrecruiters.com/v1/companies/{identifier}/postings?limit=100`

Keyless, 200 JSON, rich fields read off a live Swiggy posting:

```
id, name, uuid, refNumber, company{identifier,name}, releasedDate,
location{city, country, fullLocation, remote, hybrid},
industry, department, function, typeOfEmployment, experienceLevel
```

`releasedDate` is a real ISO timestamp and `location.country` is an ISO code (`in`) — both map
onto `Job` without inference. This is a **better** contract than Greenhouse's.

### The dead-account trap — new, and it will bite again

Four of the 19 returned a non-zero `totalFound` with the right company name. **Three are
abandoned accounts:**

| Identifier | `totalFound` | Newest posting | Real? |
|---|---|---|---|
| `Swiggy` | **168** | **2026-10-03 (today)** | ✅ live |
| `Zomato1` | 3 | **2016-12-20** | ❌ dead ~10 years |
| `Meesho1` | 3 | 2021-12-28 | ❌ dead; Meesho's live board is on Lever |
| `Cars24` | 1 | 2018-01-17 | ❌ dead ~9 years |

This is the **same class of mistake as the board-token slugs in COLLECT-B** (`slice`, `porter`,
`navi`) but with a different tell: the company name is *correct*, the postings are just years
stale. Existence is not liveness.

**Rule for any new source: gate on `releasedDate` recency, not on the account existing.** Note
the trailing `1` in `Zomato1`/`Meesho1` — a hint the real company reserved another account, but
not a reliable one; `Cars24` has no suffix and is equally dead.

### ⚠ The compliance decision — owner's call, not mine

`https://api.smartrecruiters.com/robots.txt` serves:

```
User-agent: *
Disallow: /
```

The endpoint is unauthenticated and is what SmartRecruiters' own career pages call, and
third-party scrapers of it are widely published — **but the API host asks crawlers not to read
anything.** Our rails require a ToS check before a new source (ADR-016 §4, DEPENDENCIES
approval). This is a decision, with no technically correct answer:

- Treating `robots.txt` as binding ⇒ **SmartRecruiters is out**, and with it the only route to Swiggy.
- Treating it as crawler-directed and not applicable to a per-company API read ⇒ it is in, and the owner accepts that position knowingly.

I have **not** resolved this. Everything above was a handful of read-only requests at 0.5s
pacing; a production connector polling hourly is a different posture.

## 3. Workday — reaches India, but via GCCs, not Indian startups

`POST https://{tenant}.wd{N}.myworkdayjobs.com/wday/cxs/{tenant}/{site}/jobs`
body `{"appliedFacets":{}, "limit":20, "offset":0, "searchText":"product manager"}`

Fields are thin: `title, externalPath, locationsText, postedOn, bulletFields`. `postedOn` is
**"Posted 30+ Days Ago"** — prose, not a date, so `posted_at` would need a per-job detail fetch
(`GET` the `externalPath` endpoint) or be left NULL.

Measured:

| Tenant/site | Result |
|---|---|
| `nvidia / NVIDIAExternalCareerSite` | total 1208, 0 India in first 20 |
| `adobe / external_experienced` | total 527, **1 India PM in first 20 — "Principal Product Manager (DSP Advertising), Bangalore"** |
| `salesforce / External_Career_Site` | total 406, 0 India in first 20 |
| `dell/External`, `cisco/at-cisco`, `qualcomm/External`, `tesco/TescoCareers` | **HTTP 422** — wrong site name |

**Two findings.** (1) India PM roles *are* reachable here — multinational GCCs in
Bengaluru/Hyderabad are a large and currently-unserved slice of India PM hiring, arguably bigger
than the startup slice. (2) **3 of 6 guessed tenant/site pairs 422'd.** The `site` segment is
arbitrary per employer, so discovery is manual per company.

`robots.txt` on the nvidia host explicitly **allows** `/NVIDIAExternalCareerSite/` and disallows
only `/talentcommunity/` and `/refreshFacet/` — a much cleaner compliance position than
SmartRecruiters.

## 4. Workable — works, yields nothing

Control test first, because 17 of 19 looked like hits: **nonsense slugs return HTTP 404**
(`zzqqxxnotacompany123`, `asdkjhasdkjh`), so the accounts are real. But **every one returns
`{"name": ..., "description": null, "jobs": []}`** — razorpay, swiggy, zomato, phonepe,
flipkart, zepto, myntra, nykaa, delhivery, paytm, lenskart, cars24, blinkit, rapido, licious,
udaan, meesho. Dormant or reserved slugs.

Had I not run the control, this report would have claimed Workable solves the gap. It doesn't.

## 5. Keka and Darwinbox — not reachable

- **Keka:** every `*.kekahire.com` host tried (`zluri`, `darwinbox`, `plumhq`, `sprinto`) failed TLS: `CERTIFICATE_VERIFY_FAILED — certificate has expired`. Not worked around; disabling verification is not acceptable for a production connector. Published scrapers claim this works, so either those subdomains don't exist behind a stale wildcard cert, or Keka's certs are currently expired. **Re-check before ruling it out permanently** — the platform matters for Indian SMBs.
- **Darwinbox:** `{tenant}.darwinbox.in/ms/candidate/careers` returns a 561–951 byte SPA shell with only `<title>` and OG tags. No job data, no API hint. Would need a headless browser per company.

## 6. What this means for the ADR

**The reframing: no platform here offers cross-company search.** SmartRecruiters, Workday and
Workable are all **per-company identifier** APIs — structurally identical to
Greenhouse/Lever/Ashby. Adding them does not add reach by itself; it adds reach only for
companies we already know to look up, and it inherits COLLECT-B's token problem (plus the new
dead-account trap, plus COLLECT-D's "removing an identifier tombstones its inventory").

So the real choice is between two *kinds* of source:

1. **More per-company APIs** (SmartRecruiters + Workday). Clean structured data, keyless, and genuinely reaches Swiggy and the GCC market. Cost: a curated identifier list per platform, forever, and the SmartRecruiters robots decision. **Discovery of which companies use which platform is the actual work — not the connector.**
2. **A source with cross-company search for India** — Naukri, Instahyre, Hirist, Cutshort. The only option that answers "all India PM roles" rather than "PM roles at companies on my list". None has a public API, so it means scraping, with ToS and bot-defence exposure that `robots.txt` questions above are a mild preview of.

**Recommendation for the ADR:** take **Workday first**. It has the cleanest compliance position
(robots explicitly allows the career path), reaches the India GCC market that is currently
entirely unserved, and needs no new decision about robots. Treat SmartRecruiters as a second
step gated on the owner's robots/ToS call — the Swiggy-shaped prize is real but singular. Leave
Workable unimplemented (nothing to fetch), re-probe Keka later, and keep Darwinbox out until
something cheaper than a headless browser per company exists.

**Do not write the ADR as "add platform X".** The binding constraint is company→platform
discovery; `connectors/discovery.py`'s F5 classifier already proposes ATS patterns per domain
and is **unmeasured** (`GAPS.md` 6.3-adjacent). Measuring that classifier may be worth more than
either connector.

## 7. Reproducing this

Probe scripts were scratch, not committed (one-shot measurement, ~60 requests total). The
contracts, exact URLs and request bodies above are sufficient to re-run. Key controls worth
repeating in any follow-up:

- a nonsense identifier, to prove a 200 means something,
- `releasedDate`/`postedOn` recency, to tell a live account from an abandoned one,
- `robots.txt` per host, fetched before any job path.
