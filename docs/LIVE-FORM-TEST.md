# Live form-fill test: real ATS pages, 2026-09-27

**Scope.** I ran ApplyScout's form-fill pipeline against three real, open public application forms. The MV3 extension can't be loaded into the Playwright MCP browser, so I replicated its content script instead:
- a verbatim copy of `extractFields()` / `extractLabel()` from `formFill.content.ts`
- the real backend `POST /extension/map-fields` on localhost:8000, with LLM provider NVIDIA NIM
- `fieldDecision.mjs` itself (the module text injected unchanged, with only `export` stripped)
- `fillForm`'s own mutation: `el.value = v` followed by bubbling `input` and `change` events

Resume inputs got the real `/profiles/{id}/resume.docx` bytes, attached via `setInputFiles` (equivalent to the extension's `DataTransfer` attach).

**Nothing was submitted.** No submit button was clicked and no Enter was pressed in any field. The harness also installed its own capture-phase `submit` blocker and replaced `form.submit` and `requestSubmit` with throwing stubs. The blocked-submit counter stayed at 0 on all three pages, and every tab was closed afterwards.

**Test identity.** Throwaway account `livetest-1598029356@example.com`, profile `f89e912b-…`. Basics: "Priya Raman", +1 415 867 2931, San Francisco CA US, plus LinkedIn and GitHub URLs. One answer-bank entry: "Why do you want to work at Anthropic?". The account now also holds one EEO answer ("Are you Hispanic/Latino?" → "No"), stored deliberately to prove bug #2. Delete the account.

## Findings table

| | Greenhouse | Lever | Ashby |
|---|---|---|---|
| URL | job-boards.greenhouse.io/anthropic/jobs/4461450008 | jobs.lever.co/palantir/6ed76ce8-…/apply | jobs.ashbyhq.com/ashby/7458d4e9-…/application |
| Rendering | React (Remix); react-select comboboxes; intl-tel-input | server-rendered plain `<form method=post>`; hCaptcha | React; **no `<form>` element at all** (`document.forms.length === 0`) |
| Form iframe / shadow DOM | none on job-boards (only reCAPTCHA iframes); no shadow DOM | none (hCaptcha iframes only) | none (reCAPTCHA iframes only) |
| Descriptors sent / file inputs | 32 / 1 | 58 / 1 | 36 / 2 |
| map-fields latency | **25.8 s** (1 LLM call) | **50.5 s** (122 KB payload: one 3,302-option university `<select>`) | **22.0 s** |
| Fill decided: ATS schema | 2 (email, phone) | 4 (name, email, phone, urls[Portfolio]) | 2 (_systemfield_name, _systemfield_email) |
| Fill decided: deterministic | 3 (LinkedIn ✓; Country "US" ✗; **visa-sponsorship question "US" ✗**) | 3 (LinkedIn ✓, GitHub ✓; **"Telugu (TEL)" checkbox = phone number ✗**) | 1 (LinkedIn ✓) |
| Fill decided: answer bank | 0 ("Why Anthropic?" did not match the stored "Why do you want to work at Anthropic?", a conservative miss) | 0 | 0 |
| Fill decided: LLM | 1 (**relocation Yes/No combobox = "San Francisco"** at 0.8 ✗) | 0 | 0 (it put an answer in `maps_to: "literal:No, I am in Pacific Time…"` with `value: null`, so nothing was filled) |
| **Values that actually survived** | **1 of 6** (phone only). React reset email, LinkedIn, country and both combobox texts to `""` | 7 of 7 (plain DOM; one of them is wrong) | **0 of 3**. React state stayed `""`; the DOM text was wiped on the next re-render (the resume upload) |
| Flagged: demographic_left_blank | 2 (Gender, Veteran Status) | 0 (no EEO section on this post) | 1 ("Another Gender Identity" option only) |
| Flagged: demographic_required | 0 | 0 | 0 |
| Flagged: essay_no_stored_answer | 0 ("Why Anthropic?" doesn't match the essay keywords) | 0 | 0 |
| Flagged: low_confidence | 24 (includes **"Are you Hispanic/Latino?"**, First/Last Name, 7 react-select shadow inputs, the hidden reCAPTCHA textarea, the hidden iti "Search" box) | 51 (26 language checkboxes, 10 radios labelled only "Yes"/"No", unlabeled selects and textareas) | 32 (includes **25 EEO/age radios and checkboxes**: "Man", "Woman", "White", "Veteran", "Person with disability"…) |
| Flagged: file_upload | 0 | 0 | 0 |
| Resume input | ✓ `id=resume` (label is only "Attach", so the id saved it). Attached; Greenhouse **immediately POSTs the file to S3** | ✓ `name=resume`, but it extracted as `required:false` although the page shows ✱. Attached; Lever **immediately POSTs /parseResume** ("Couldn't auto-read resume" because the docx was empty) | ✓ `_systemfield_resume`; the unlabeled "autofill from resume" input was correctly skipped. Attached; Ashby immediately runs `ApiCreateFileUploadHandle` → S3 → `ApiSetFormValueToFile` |
| EEO field filled? | No, but only by luck (the LLM said unknown). The Hispanic/Latino question passed both demographic rails | No EEO present | No, but only by luck. Every EEO option passed both rails |
| Auto-apply outcome today | `needs_human` (First/Last Name etc.) | `needs_human` | `failed: no form found on page` (findForm returns null), and only after `needs_human` clears |
| Confirmation after submit (from page source, not submitted) | Client route `/:url_token/jobs/:job_post_id/confirmation` (Remix manifest) | Form POSTs to `/apply`; Lever normally redirects to `…/thanks` (not verified) | Toast/text: "Your application was successfully submitted. We'll contact you if there are next steps." |

## Screenshots (`D:\job-copilot\.playwright-mcp\`)

- `livetest-greenhouse-anthropic-asis.png`: the fill exactly as the extension does it. Green outlines sit on **empty** email and LinkedIn boxes.
- `livetest-greenhouse-anthropic-nativesetter.png`: the same page after re-filling with the native value setter (the proposed fix). Values persist in React state; the resume chip "livetest-resume.docx" is visible.
- `livetest-lever-palantir.png`: Lever after the fill and resume attach (includes the phone number sitting in the Telugu checkbox's value).
- `livetest-ashby-asis.png`: Ashby after the as-is fill plus the resume upload. The text fields were wiped by the re-render.
- `livetest-ashby-nativesetter.png`: Ashby after the native-setter re-fill (name and email persist).
- Raw data: `gh-extract.json` / `gh-map.json`, `lever-extract.json` / `lever-map.json`, `ashby-extract.json` / `ashby-map.json`, plus the generated `livetest-resume.docx`.

## Bugs, by severity

### P0: the pipeline cannot work on real ATS pages

1. **The content script can't reach the backend (CORS).**
   - Where: `formFill.content.ts:141`, `:179` (fetch from the content script); `apps/api/core/config.py:55` (`cors_origins = ["http://localhost:3000"]`).
   - Evidence: an `OPTIONS /extension/map-fields` preflight with `Origin: https://job-boards.greenhouse.io` returns **400 with no `Access-Control-Allow-Origin`**. Since Chrome 85, MV3 content-script fetches carry the page's origin and are CORS-checked; `host_permissions` only exempt the service worker and extension pages. Every fill therefore throws "Failed to fetch" before anything else happens.
   - Confirmed by preflight only, not inside a loaded extension. A page-world fetch was also blocked, but by Greenhouse's CSP, which doesn't apply to isolated-world content scripts.
   - Fix: proxy both calls through the background service worker (`background/driver.ts`, `chrome.runtime.sendMessage`). Don't widen CORS to `*`.
2. **The EEO rail leaks, and the answer bank will then fill EEO questions.**
   - Where: `fieldDecision.mjs:14` and `apps/api/answer_bank.py:44`.
   - The substring list misses "Are you Hispanic/Latino?" (Greenhouse's standard EEO question). It also misses every option-labelled EEO control: Ashby's "Man", "Woman", "White", "Veteran", "Person with disability", and age brackets.
   - These become `low_confidence` → `unansweredQuestions()` sends them to the review card as questions → the user answers → the bank serves the answer.
   - **Proved live:** `PUT /answers {"Are you Hispanic/Latino?": "No"}` → 200, then `map-fields` returns `{"maps_to":"answer_bank","confidence":1.0,"value":"No"}` for `dom_id=hispanic_ethnicity`.
   - Fix, one shared predicate in both places:
     - add `hispanic`, `latin`, `veteran`, `disability`, `sexual`, `pronoun`, `age range`;
     - check the **group/question label**, not just the option label (see #5);
     - also check `dom_id` / `name` (`gender`, `hispanic_ethnicity`, `veteran_status`, `disability_status` on Greenhouse);
     - `answer_bank.py` should also refuse the write (`PUT /answers`) for these.
3. **Values don't stick on React forms (Greenhouse, Ashby).**
   - Where: `formFill.content.ts:195`, `el.value = value`.
   - React's value tracker swallows the input event, so React state stays `""`. Greenhouse reset the DOM immediately; Ashby kept stale DOM text until the next re-render (the resume upload wiped it). A submit would send empty fields.
   - Fix (verified live on both ATSes): `Object.getOwnPropertyDescriptor(HTMLInputElement.prototype /* or HTMLTextAreaElement / HTMLSelectElement */, "value").set.call(el, value)`, then dispatch `input` and `change`. Attach files **before** filling text, or re-verify values after the upload.
4. **`report("submitted")` isn't gated on anything real.**
   - Where: `autoApply.content.ts:93`, right after `submitApprovedApplication.ts:39`.
   - `requestSubmit()` returning is not success. On React ATSes the submit handler does its own validation and XHR (and with #3 unfixed, validation fails), and reCAPTCHA or hCaptcha can intercept it. The backend claim has already flipped the row to `applied`, so this is a silent lie.
   - Fix: wait for the confirmation signal (Greenhouse URL `/confirmation`; Ashby text "Your application was successfully submitted"; Lever `/thanks`) before reporting `submitted`, else report `failed` or `needs_human`.
5. **Ashby has no `<form>`.**
   - Where: `autoApply.content.ts:47` `findForm()` returns null, so it reports "no form found on page" on every Ashby job, even a perfectly filled one.
   - Fix: submitting needs a per-ATS submit-button strategy, not `form.requestSubmit()`. That is an ADR-001 allowlist change, so it's the owner's decision.

### P1: wrong values written

6. **The deterministic regexes match inside question text and words.**
   - Where: `apps/api/formfill/deterministic.py:45` and `:51`.
   - `tel(?:ephone)?` matched "**Tel**ugu (TEL)", so the phone number was written into a language checkbox's value.
   - `\bcountry\b` matched Greenhouse's visa question ("…to work in the **country** in which the job…"), so "US" was filled at confidence 1.0 into a Yes/No combobox. It also sent "US" into the react-select Country combobox, which ignores typed text.
   - Fix:
     - only apply label regexes to short labels (for example ≤ 4 words), or anchor them;
     - skip `checkbox` / `radio` / `role=combobox` inputs in the deterministic text rules;
     - use `\btel\b` or `telephone`.
7. **Radio, checkbox and select are "filled" by writing `.value`.**
   - Where: `formFill.content.ts:195`.
   - On a checkbox or radio this rewrites the value that gets submitted and never sets `.checked` (seen live on Lever's Telugu checkbox).
   - On a `<select>`, the backend was given option **text** (`formFill.content.ts:~88`), but `.value` needs the option **value**.
   - Fix: branch on `input_type`. Radio/checkbox: `.checked = true` on the option whose label matches. Select: pick the option by text. Never write `.value` on these.
8. **Choice questions lose their question text.**
   - Where: `extractLabel` in `formFill.content.ts:52-65`.
   - Lever and Ashby radios and checkboxes get only the option label ("Yes"/"No", "Man"). Greenhouse react-select shadow inputs, Lever `cards[…]` selects and textareas get `null`.
   - Consequences: the LLM can't answer them, the EEO rail can't see them (#2), and the review card asks the user "Yes", "No", "English (ENG)", "Start typing…" as questions. A "Yes" answer saved into the bank would then match every "Yes" option.
   - Fix: when the element is a radio or checkbox, or has no label, walk up to the nearest `fieldset > legend`, `[role=radiogroup|group][aria-labelledby]`, or the ATS question container (Lever `.application-question .application-label`, Ashby `label` of the field container). Send one descriptor per group, not per option.
9. **The LLM fills a Yes/No combobox with a profile attribute.**
   - The relocation question on Greenhouse got "San Francisco" at 0.8 confidence, which passes the 0.75 threshold.
   - Where: `apps/api/formfill/map_fields.py:81` `SYSTEM_PROMPT`. Tell it that `combobox`/`select` fields must use a listed option or `unknown`, and send react-select options (they aren't in the DOM until opened, so treat them as unknown).

### P2: noise, cost, correctness gaps

10. **Hidden and anti-bot fields are sent to the LLM and block the run.**
    - Where: `formFill.content.ts:81`.
    - `g-recaptcha-response` (hidden textarea), the hidden iti "Search" input, and 7 invisible react-select `requiredInput`s are sent. They flag `low_confidence`, stop auto-apply, and show up as questions.
    - Nothing prevents a model from filling one.
    - Fix: skip `offsetParent === null` / zero-rect / `aria-hidden` elements, and names matching `g-recaptcha|h-captcha|cf-turnstile`.
11. **Greenhouse First/Last Name is never filled.**
    - The fields carry `autocomplete=given-name/family-name`; the LLM returns `full_name` at 0.5 confidence, so they are flagged. This alone forces `needs_human` on **every** Greenhouse application.
    - Where: `deterministic.py` `_AUTOCOMPLETE_MAP` / `schemas.ApplicantBasics`. Add user-confirmed `given_name` / `family_name` columns, as latest+21 already proposed.
12. **The resume docx is empty and has no identity.**
    - Where: `main.py:932` → `documents/generate_docx.py:34`.
    - `generate_resume_docx(headline, facts)` has no name, email or phone parameters. A profile with zero facts returns **200 with an empty document** (zero paragraphs), which got attached as the candidate's resume on all three sites and is already uploaded to Greenhouse's and Ashby's S3.
    - Fix: 409 when there are no facts, and put the basics header (name and contact) into the docx.
13. **Resume attach is not reversible.** On all three ATSes, attaching the file uploads it to the employer's storage immediately (Greenhouse S3 and Ashby S3 + `ApiSetFormValueToFile`, before submit; Lever `/parseResume`). An aborted `needs_human` run still hands the employer a file. Attach only in the final pass, once no blocking flags remain (`formFill.content.ts:203-205`).
14. **Lever's parseResume may overwrite filled values.** Lever auto-fills name, email and phone from a parsed resume. Because `fillForm` fills text first and attaches afterwards, a parseable resume could overwrite ApplyScout's values. This wasn't observed because the docx was empty. The fix is the same ordering change as #3.
15. **Latency.**
    - map-fields took 22-51 s per form on NVIDIA NIM.
    - Lever's 3,302-option select put 122 KB into the prompt. Truncate `options` (for example first 50 plus a count) in `formFill.content.ts:~88`, or drop options server-side before the LLM call.
    - The driver's per-item timeout must be above this.
16. **The Lever resume was extracted as `required:false`.** Lever marks it with ✱ and the `required` attribute is absent, so a non-matching label would be "skip" instead of "flag". Consider treating a visible "✱" or "*" in the field label as required.
17. **Embedded boards aren't reached.** `manifest.json:15-21` has no `"all_frames": true`, so company careers pages that embed Greenhouse via `#grnhse_iframe` (`boards.greenhouse.io/embed/job_app`) never get the content script. Not an issue on direct `job-boards.greenhouse.io` URLs like the one tested.
18. **Model output drifts from the schema.** On Ashby the model put its answer inside `maps_to` ("literal:No, I am in Pacific Time…") with `value: null`; the Pacific Time part is inferred from region=CA, not given data. It was harmless here because `value` was null, but the response isn't validated beyond field ids (`map_fields.py` loop around `validate_ids_against_known_set`).

## What worked

- The resume classifier chose the right input on all three ATSes and skipped Ashby's unlabeled autofill input.
- ATS-schema and network rules produced the right values for name, email, phone and LinkedIn/GitHub/Portfolio wherever those fields existed. They only failed to stick because of #3.
- The Greenhouse "Gender" and "Veteran Status" and Ashby "Another Gender Identity" fields were correctly left blank.
- The answer bank correctly did *not* stretch "Why do you want to work at Anthropic?" to "Why Anthropic?".
