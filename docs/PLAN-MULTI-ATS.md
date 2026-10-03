# Plan: auto-apply beyond Greenhouse

> **Stage naming.** This plan's stages are `ATS-0`…`ATS-3` (the "Phase 0/1/2/3" headings below
> map one-to-one). A bare "Phase N" is ambiguous in this repo — `PLAN-JOB-COLLECTION.md` runs in
> parallel with its own `COLLECT-*` stages, and that collision stalled a session on 2026-10-03.
> Always write the prefix. See that doc's naming section.

**Status:** accepted 2026-09-29 (ADR-016, amended after Phase 0: the planner is Stagehand `extract()`, not browser-use): **a read-only planner plans each job on the server (read-only, synthetic profile); the extension executes the plan and submits in the user's browser; the extension's own filler is the fallback.**
**Context:** WORKLOG latest+50…55. One Greenhouse posting produced ~12 bugs. Most were
in the shared engine, not Greenhouse: frames, re-rendered forms, timeouts, optional
fields, Review gaps. The question is how to reach Lever, Ashby, Workable,
SmartRecruiters, Workday… without a new bug hunt per platform.

---

## 1. What the bugs actually tell us

| Layer | Where the bugs were | Generic or per-ATS |
|---|---|---|
| Finding the form | iframe choice, form re-rendered after load | Generic |
| Reading fields | dropdowns with no options until opened/typed | Generic (widget types) |
| Deciding values | names, city, consent, demographics, optional vs required | Generic (profile + rules) |
| Writing values | React inputs, react-select, typeahead, "+1" display | Widget-level, reused across ATSs |
| Flow | time limits, background tabs, multi-page "Next" | Generic |
| Truly per-ATS | Greenhouse phone-country display, field-name schemas | Small |

**Conclusion:** the per-ATS part is small. The cost is in **widget types** (text,
select, react-select, async typeahead, radio group, checkbox, date, file) and **flow**
(multi-page, "add another", account walls). Build those once, well, and every ATS
benefits.

## 2. Decided: plan on the server, submit in the user's browser

| Step | Where | What |
|---|---|---|
| Plan | Server, browser-use, behind the no-submit guard, synthetic profile | Walk the form; save per field: widget, how to fill/verify, which profile key / bank question. No values. |
| Validate | Server, harness | A guarded test fill of the plan must pass before it's trusted |
| Execute | User's browser, extension | Real values in, verify each field; user presses Send (Assisted) or extension sends within cap (Automatic) |
| Fallback | User's browser, extension | Today's filler when there's no plan or the form's fingerprint changed (re-plan queued) |

One plan per job, shared by all users, built at discovery time.

## 3. Stages

### ATS-0 (was "Phase 0"): measure first
Answer three questions on ~10 real postings each on Greenhouse, Lever and Ashby, guard on:
1. **Can browser-use produce an accurate plan?** Compare its field list (type, required,
   options, multi-page) with the DOM ground truth the harness already snapshots.
2. **What does a plan cost?** Time and LLM calls per job, on NIM.
3. **Baseline:** the extension's own fill rate on the same postings (`check_form.py`).
Output: `docs/harness-reports/phase0-*.md`, per ATS.

### ATS-1 (was "Phase 1"): planner worker + `form_plans`
- RQ job `plan_form(job_id)` → subprocess into an isolated browser-use venv (the
  JobSpy/agent-reach pattern). Guard on, synthetic profile, allowlisted actions, allowed
  domains = the ATS host. `ANONYMIZED_TELEMETRY=false`.
- `form_plans` table: job_id, ats, fingerprint, plan JSON, validated_at, status.
- Triggered after discovery for jobs that pass hard filters; re-plan on mismatch.

### ATS-2 (was "Phase 2"): plan executor in the extension
- Fetch the job's plan; compare fingerprints; fill each field through the widget
  executors (write → re-read → verify); plan steps like "Next" are allowed clicks,
  never Submit.
- Mismatch or missing plan → today's filler (fallback). Unresolved fields → Review.

### ATS-3 (was "Phase 3"): platforms by data
Greenhouse, Lever, Ashby first; Workable and SmartRecruiters next. Workday/iCIMS/Taleo:
plans are possible when the page loads without login; otherwise extension only.
Account creation is never automated.

> ⚠ **This stage's premise was undercut by its own measurement — revisit before executing.**
> WORKLOG latest+59 re-measured the plan on Lever and Ashby and found **no gain on required
> fields**, which is why plan routing is still Greenhouse-only (latest+57). "Extend the planner
> to more platforms" therefore has no evidence behind it yet. Decide first *why* the plan helped
> on Greenhouse and not elsewhere; extending it without that answer buys nothing. Related:
> `docs/GAPS.md` 6.3 and 6.4 — none of §5's success metrics has been measured on a real platform,
> so no platform can honestly be called "supported" today.

## 4. Rails that do not change
- Assisted mode stays the default; auto-submit is opt-in within daily caps (ADR-015).
- Legal consent and demographic questions are never answered by software.
- No fabricated facts or numbers (ADR-006/009).
- Every harness run has the full no-submit guard (`guard.py`), no exceptions.
- browser-use: `ANONYMIZED_TELEMETRY=false`, no cloud features. Application data is PII.
- No AGPL code vendored (rules out Skyvern and AIHawk). Licences are checked before
  any new dependency, and each needs the owner's approval.

## 5. How we'll know it works
| Metric | Target before calling a platform "supported" |
|---|---|
| Wrong values written | **0** (any wrong value fails the platform) |
| Required fields filled or correctly routed to Review | ≥ 95% |
| Postings reaching the (blocked) submit with nothing left | ≥ 70% of consent-free postings |
| Median time to fill | < 60 s |
| `needs_human` cards with nothing actionable in Review | 0 |
