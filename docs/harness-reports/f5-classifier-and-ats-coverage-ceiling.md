# F5 measured, and the ATS coverage ceiling found

**Date:** 2026-10-05 · **Asked:** COLLECT-C said measuring F5
(`connectors/discovery.py`) might be worth more than another connector. Measured.
**Answer: F5 is structurally limited (1/9), but the exercise closed the coverage question
definitively — and found one real company.**

---

## 1. F5 accuracy: 1 correct of 9

`detect_ats(domain)` fetches `/careers`, `/jobs`, `/join-us`, `/work-with-us` and regexes the
HTML for any of 17 ATS URL shapes. Run against companies whose ATS we already knew from this
session's live measurements:

| domain | expected | F5 said |
|---|---|---|
| supabase.com | ashby | **ashby / `supabase`** ✅ |
| mongodb.com | greenhouse | no match |
| okta.com | greenhouse | no match |
| gitlab.com | greenhouse | no match |
| adobe.com | workday | no match |
| cisco.com | workday | no match |
| zeta.tech | lever | no match |
| meesho.com | lever | no match |
| swiggy.com | smartrecruiters | no match |

**1 correct, 0 wrong, 8 no-match.**

## 2. Why — and it is not a regex bug

The ATS URL is simply **not in the raw HTML** of a modern careers page:

```
okta.com/careers     200, 290 KB   no ATS string anywhere in the body
meesho.com/careers   200,  47 KB   and /jobs, /join-us, /work-with-us all return
                                   the SAME 47 KB shell — it is an SPA
swiggy.com/careers   403           on every candidate path (bot-blocked)
```

The board link appears only after JS runs, or lives on another host behind a button, or the
site blocks us outright. **F5's premise — "the careers page names its ATS" — is false for this
class of site.** Fixing it needs a headless browser per company, which this project has already
declined twice (ADR-019; COLLECT-C's Darwinbox finding).

So F5 should not be invested in as the route to coverage. It is not useless (see §4), it just
cannot be the primary mechanism.

## 3. The inversion that does work

Don't ask *"what ATS does company X use?"* by crawling X. Ask **"does platform P have a board
for slug S?"** by calling P's public API. Those APIs are keyless, JS-free, unblocked and
definitive — they return the token *and* the postings in one call. That is what actually found
coverage during COLLECT-B/C, and it is now a committed tool rather than scratch scripts:
**`tools/ats_token_probe.py`** (greenhouse, lever, ashby, smartrecruiters, workable; labels
which are ingestible; prints product-role counts and SmartRecruiters recency).

## 4. F5's one hit was genuinely complementary

**paytm → lever.** Verified live: **173 postings, 129 India-located**, including
*"Product Management - Associate Product Manager"* in Noida. Added to
`LEVER_COMPANY_TOKENS`.

It matters *why* this was a miss for the other method: **`paytm` was absent from COLLECT-B's
117-slug candidate list.** Platform probing is only as good as the slug list; F5 works from the
domain side and can surface a company the list forgot. **The two are complementary**, which is
the real lesson — not "F5 is bad".

## 5. The coverage ceiling, now evidence-backed

The 19 Indian consumer-tech companies COLLECT-B found unreachable, after probing all five major
platforms with `ats_token_probe.py`:

| outcome | companies |
|---|---|
| **Reachable and added** | **paytm** (lever, 173 postings) |
| Reachable but blocked on a decision | **swiggy** (smartrecruiters, 168 postings — ADR-018 §7 / the robots+SAP brief) |
| Abandoned account only | cars24 (smartrecruiters, newest posting **2018-01-17**) |
| **On none of the five platforms at all** | razorpay, zomato, phonepe, flipkart, zepto, myntra, nykaa, delhivery, urbancompany, lenskart, blinkit, rapido, licious, udaan, zerodha, meesho* |

\* meesho is already configured on lever separately; its own slug probe found it there.

**So: more ATS tokens, and better ATS discovery, cannot solve this.** That avenue is exhausted,
and it is now a measurement rather than a guess. These companies run Indian HRMS stacks
(Darwinbox, Keka, Zoho Recruit, SuccessFactors) or their own — and COLLECT-C already measured
Darwinbox as an empty SPA shell and Keka as unreachable (expired TLS on every host tried).

## 6. What that leaves

Only two honest paths to India coverage beyond today's 23 live product roles:

1. **A source with cross-company India search** — Naukri, Instahyre, Hirist, Cutshort. The only
   option that escapes the curated-slug ceiling. None has a public API, so it means scraping,
   with the ToS/bot-defence exposure the SmartRecruiters brief already frames. **Needs an ADR.**
2. **Accept the ceiling** and state coverage honestly: global-remote roles, multinational India
   GCCs (Workday), and the handful of Indian companies that happen to use Greenhouse/Lever/Ashby.

The cheap middle step, if wanted: run `ats_token_probe.py` over a much longer list of Indian
startups. It costs nothing but requests, and paytm shows the list itself is the limiting factor.

**Related:** `docs/harness-reports/collect-c-platforms.md`,
`docs/smartrecruiters-decision-brief.md`, `GAPS.md` 3.1.
