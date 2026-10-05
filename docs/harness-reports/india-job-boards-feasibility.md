# India job boards: all four candidates evaluated, all four unusable unlicensed

**Date:** 2026-10-05 · **Method:** four parallel read-only probes, one per board, each capped at
~15 requests ≥1s apart, plain identifying User-Agent, **no UA spoofing, no login, no challenge
solving**. Each agent was instructed to fetch `robots.txt` first and to *report* the posture
rather than work around it.

**Why this was the last option:** COLLECT-C and the F5 measurement established that 16 of the 19
Indian consumer-tech companies the owner targets are on **none** of
greenhouse/lever/ashby/smartrecruiters/workable, and that company→ATS discovery cannot fix it. A
source with **cross-company India search** was the only remaining path.

---

## 1. Verdicts

| Board | robots.txt | Technical reality | Effort if licensed | Verdict |
|---|---|---|---|---|
| **Instahyre** | **wide open** — zero `Disallow` | **public unauthenticated JSON API**, 12,973 jobs, 753 PM-in-Bangalore, company names present | **~half a day** | `legally-prohibited` |
| **Cutshort** | permissive for `/job/`,`/jobs/` + **44,320-URL** sitemap | anonymous `JobPosting` JSON-LD with **salary + datePosted + directApply** | **~1 day** | `legally-prohibited` |
| **Hirist** | permissive + **31,029-URL** daily sitemap | JS-only: SSR payload ships field names with **values blanked**; `botDetection` slice armed | low (sitemap) | `legally-prohibited` |
| **Naukri** | **403 — cannot even read it** | hard Akamai 403 on every path, request one | n/a | `blocked` |

## 2. The finding that generalises

**`robots.txt` permissiveness was uncorrelated with permission — and in three of four cases it
pointed the opposite way from the contract.**

- Instahyre's `robots.txt` has **zero** `Disallow` lines, and its ToS bans *"crawl or spider"*,
  *"search, copy, monitor, download, harvest or scrape or otherwise extract in any manner"*, and
  commercial use *"whether or not for profit"*.
- Hirist publishes a 31k-URL job sitemap, and its ToS bans crawling, commercial derivative works
  and deep-linking past the home page.
- Cutshort publishes a 44k-URL job sitemap, and its ToS bans *"systematic or automated data
  collection"* three separate ways.

**Worse, technical ease ran inversely to permission:** the easiest source to ingest (Instahyre,
half a day, no auth) carries the most explicit prohibition. "It's an open API" is the weakest
possible argument for permission.

This is the same lesson `docs/smartrecruiters-decision-brief.md` already drew — that `robots.txt`
is not the deciding signal and the contract is — now confirmed four more times.

## 3. Two boards name this exact product

- **Instahyre** separately bars using the platform to build *"a competitive product or service"*.
- **Naukri**'s ToS prohibits extraction *"(by any process, whether automatic or manual)"* in order
  *"to offer any products or services which may compete with the Company's services"* — note that
  covers **manual** extraction too.

An India-focused job-search product is not in a grey area with respect to those clauses; it is
the named target.

> **Provenance caveat, preserved deliberately:** the Naukri quotes above came from a search
> engine's index of `naukri.com/termsconditions`, **not** from a response we received — the page
> itself 403s. The direction is unambiguous, but it is second-hand and labelled as such rather
> than presented as a first-party quote.

## 4. Cutshort's ToS forecloses ADR-015's legal shield

Cutshort's terms were recently updated to say that the provisions on automated access

> "…bots, scraping, **browser extensions**, data extraction, misuse of the platform … apply
> equally to Freedom Plans."

ADR-015's posture is *"autonomous submission via the user's own browser session, never a shared
server bot — keeps ban/legal exposure off shared infra."* **For this source, that distinction is
explicitly closed.** The "it's the user's own browser, not our crawler" argument is named and
rejected. Worth knowing before leaning on it for any future source.

## 5. Naukri is a different category: access control, not terms

Every path returns **HTTP 403 from AkamaiGHost** to a plainly-identified client — `robots.txt`,
`sitemap.xml`, the search page, `jobapi/v3/search`, and the ToS page itself. Not rate limiting,
not a solvable challenge: a hard deny on the first request, path-independent.

Getting data out would require UA spoofing plus TLS-fingerprint matching — **deliberate evasion
of an access control**, which is a different thing from a ToS disagreement, and it is exactly what
this project's rails forbid (ADR-018 §9 and ADR-019 both already rejected UA spoofing). There is
no degraded-but-legal fallback: no sitemap, no RSS, no robots-sanctioned path.

## 6. What every probe independently recommended

All four reports converged on the same action: **this is a business conversation, not an
engineering ticket.**

- Info Edge (Hirist/Naukri's parent) runs commercial data partnerships.
- Cutshort advertises a partner/dev entry point (`/a/devdocs`).
- Instahyre's path is written permission or a data agreement.

In each case the integration is ~half a day to a day **once credentialed** — the technical work
is trivial and the permission is the entire cost. That asymmetry is the argument for sending an
email rather than writing a crawler.

## 7. What this closes

Combined with the ATS ceiling measurement, **every non-licensed route to broad India coverage is
now evaluated and closed.** The honest statement of coverage is:

- global-remote roles (the keyless feeds),
- India roles at multinational GCCs (Workday),
- and the Indian companies that happen to use Greenhouse/Lever/Ashby — currently 23 live product
  roles in India.

That is a real product with a stated limit, which is better than an unstated one. See **ADR-020**
for the decision.

**Related:** `docs/harness-reports/collect-c-platforms.md`,
`docs/harness-reports/f5-classifier-and-ats-coverage-ceiling.md`,
`docs/smartrecruiters-decision-brief.md`, `GAPS.md` 3.1.
