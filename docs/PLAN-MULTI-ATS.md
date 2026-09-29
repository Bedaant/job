# Plan: auto-apply beyond Greenhouse

**Status:** accepted 2026-09-29 (ADR-016): **browser-use on our server first, the extension as fallback.**
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

## 2. Decided: browser-use on our server first, the extension as fallback

Owner's decision (ADR-016). browser-use 0.13.10 (installed, MIT) runs in a server worker
with its own Chromium and fills the form. The extension, in the user's own browser, takes
over when the server run stops (captcha, login/account wall, a form it couldn't finish).
Assisted mode (default): the server fills and stops before Submit, and the user sends it
through the extension. Automatic mode: the server submits within daily caps.

## 3. Phases

### Phase 0: measure first (1–2 days)
- Run the harness with browser-use **filling** (not only grading) over ~10 real postings
  each on Greenhouse, Lever and Ashby (5 each on Workable/SmartRecruiters), guard on.
- Per posting: required fields filled correctly, wrong values (must be 0), stops and why,
  captcha hits, time and LLM cost per form, submit blocked.
- Same postings through the extension, for a side-by-side comparison. **This decides,
  per ATS, whether server-first actually beats the extension.**

### Phase 1: the server apply worker
- New RQ job `apply_via_browser_use(application_id)` in an isolated venv (browser-use pins
  its own starlette/openai/anthropic, like `tools/.venv-browser-use`), invoked as a
  subprocess the same way as JobSpy/agent-reach.
- Agent restricted to fill actions: `input`, `select_dropdown`, `dropdown_options`,
  `click`, `upload_file` (the tailored resume only), `scroll`, `done`. No `navigate`
  off the job's domain (`allowed_domains`), no `evaluate`.
- **Submit guard in code**: in Assisted mode the network layer blocks the final submit,
  as `guard.py` does; in Automatic mode it is lifted only within the daily cap.
- Values come only from a server-built answer sheet (profile, facts, answer bank,
  tailored resume). The agent may choose where to put them, never what they are.
  Consent/demographic fields are left blank.
- `ANONYMIZED_TELEMETRY=false`, no cloud features, no screenshots kept beyond the run.

### Phase 2: hand-off to the extension
- A server stop becomes `needs_human` with its reason (captcha / login / field list) and
  queues the application for the extension (the existing driver path, frame choice and
  Review flow).
- Assisted mode: the extension does the final fill in the user's browser and the user
  presses Send.

### Phase 3: add platforms by data
- Greenhouse, Lever and Ashby first (no login needed). Workable and SmartRecruiters next.
- **Workday / iCIMS / Taleo:** extension only (they need an account per employer;
  account creation is never automated).

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
