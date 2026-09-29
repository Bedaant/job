# Plan: auto-apply beyond Greenhouse

**Status:** accepted 2026-09-29: option C (ADR-016). Fallback = agent loop inside the extension.
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

## 2. The one decision: where browser-use runs

browser-use 0.13.10 (installed, MIT) is a generic "look at page → pick action →
act → re-look" agent. It attaches to Chrome over CDP (`cdp_url`), handles
cross-origin iframes, can be restricted by domain and by action, and uploads files.
Today we use it only as the harness's **read-only grader** (its only action is `done`).

| Option | How | Verdict |
|---|---|---|
| A. browser-use on our server | Our own Chromium applies for the user | **No.** Breaks ADR-015 (the user's own browser session). Datacenter IPs get captchas. Not the user's logged-in state. |
| B. browser-use on the user's machine | A desktop companion attaches to the user's Chrome over CDP | **Later, maybe.** Chrome must be started with `--remote-debugging-port`; a Python install per user. Heavy for consumers. |
| **C. The same loop, inside the extension** | The extension does observe → act → verify; the LLM picks from a small safe action set via our API | **Recommended.** Runs where the user is logged in, on their IP, with the guards we already have. No new runtime. |

**Recommendation: C for the product, and browser-use as the test and discovery
tool.** browser-use's value to us is the loop design and a generic grader, not its
runtime. We copy the loop into the extension (≈ one new endpoint + one executor),
and keep browser-use for:
- grading every harness run (already done);
- the pass-rate benchmark (§3, Phase 0);
- exploring a new ATS's flow before we write anything for it.

If you prefer B (browser-use itself driving your real Chrome), it's a separate
opt-in "desktop mode" after Phase 2. It isn't a replacement.

## 3. Phases

### Phase 0: measure first (1–2 days)
- `run_suite.py` over **~10 real postings each** on Greenhouse, Lever and Ashby (5
  each on Workable/SmartRecruiters as a probe), popup fill and `auto_apply.py`,
  guard on.
- Per posting: required fields filled correctly, wrong values (must be 0), blocked
  by `needs_human` and why, time, submit blocked. The browser-use grader reads every
  filled form.
- Output: a table in `docs/harness-reports/` plus the top failure causes. **This
  decides Phase 1's order.** No more fixing from single postings.

### Phase 1: harden the shared engine (from Phase 0's list)
- Verify and merge the stopped background-tab fix (branch
  `worktree-agent-aaffc64663cda2efa`, WIP `c1cbafc`, unverified).
- One **widget executor** per widget type, each with write → re-read → verify:
  text, native select, react-select / listbox, async typeahead, radio group,
  checkbox, date, file. Detect by behaviour, never by ATS name.
- Required detection: attribute, `aria-required`, trailing `*`, and the form's own
  "required" text.

### Phase 2: the generic fallback loop in the extension (option C)
When fields are still unresolved after deterministic + map-fields:
1. The extension sends a compact snapshot of **only the unresolved fields** (label,
   type, options if any, nearby text) plus the page's buttons, excluding submit.
2. New `POST /extension/next-action` returns **one** action from an allowlist:
   `type(field, value)`, `choose(field, option)`, `check(field)`,
   `upload_resume(field)`, `click(button)` (e.g. "Next", "Add another"), or `stop`.
3. The extension executes it with the widget executors, re-reads, and verifies.
   At most N steps (e.g. 15) per page.
4. **Rails stay in the executor, not the prompt:** no submit click (same classifier
   as today), consent/demographic never, values only from profile/facts/answer bank
   (ADR-006/009: no fabrication), and every value is re-checked server-side.
5. Multi-page flows ("Next") come for free: it's just another allowed click.

### Phase 3: add platforms by data, not by hope
- Lever and Ashby already have `ats_schemas.py` entries and harness targets. Fix
  what Phase 0 shows.
- Workable and SmartRecruiters: add schemas only if the Phase 2 loop falls short.
- **Workday / iCIMS / Taleo:** assisted only (they need an account per employer;
  account creation is never automated). The extension fills page by page while the
  user is present.

### Phase 4 (optional): desktop mode with browser-use (option B)
Only if Phase 2 plateaus: an opt-in local companion runs browser-use against the
user's Chrome over CDP, with the same guards and allowlist. **Must set
`ANONYMIZED_TELEMETRY=false`** (browser-use sends telemetry by default;
`config.py:59`) and never use its cloud features. Application data is PII.

## 4. Rails that do not change
- Assisted mode stays the default; auto-submit is opt-in within daily caps (ADR-015).
- Legal consent and demographic questions are never answered by software.
- No fabricated facts or numbers (ADR-006/009).
- Every harness run has the full no-submit guard (`guard.py`), no exceptions.
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
