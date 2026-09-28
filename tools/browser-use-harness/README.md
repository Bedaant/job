# browser-use harness: fill, never submit

This harness loads the built ApplyScout extension into a guarded Chromium and opens a real job application form. It runs the popup's interactive fill (`jc:fill-form`), then checks the result two ways: a deterministic DOM snapshot, and a read-only browser-use auditor (an LLM on NVIDIA NIM). It writes a report.

It automates the manual test in `docs/LIVE-FORM-TEST.md`.

**It cannot submit an application.** Sending a fabricated application to a real employer is harmful. Every layer below is always on, and there is no flag to turn any of them off.

## Safety model

1. **Network.** `guard.py` puts a Playwright route on the whole browser context. It aborts every request that is not GET, HEAD or OPTIONS, unless the host is localhost or 127.0.0.1.
   - This kills native form POSTs, fetch/XHR submits, `sendBeacon`, and employer S3 resume uploads (intended).
   - WebSockets to non-local hosts are closed.
   - One exception, because Ashby's form page loads its posting through a GraphQL POST: `is_readonly_ashby_query` lets through a POST to exactly `https://jobs.ashbyhq.com/api/non-user-graphql` whose body is a JSON object with a `query` document made only of `query` operations (plus fragments). The words `mutation`/`subscription` anywhere in the body refuse it; so do non-JSON, batched arrays and any other host, port, path or method. Ashby's submit and resume upload are mutations to that same URL, so they stay blocked. Allowed ones are counted in the report (`allowed_readonly_graphql_queries`).
   - Page service workers are blocked (`service_workers="block"`), so none can bypass the route.
2. **DOM.** An init script runs in every frame, before page JS:
   - `HTMLFormElement.prototype.submit` and `requestSubmit` throw.
   - A capture-phase `submit` listener on `window` calls `preventDefault()` and `stopImmediatePropagation()`.
   - Every hit is recorded.
3. **Auditor.** The browser-use agent gets an allowlist of exactly one action: `done`.
   - Everything else is excluded: click, input, select_dropdown, send_keys, upload_file, navigate, evaluate, scroll, and the rest.
   - `run_auditor` refuses to start if any other action is registered.
   - The task text also forbids clicking, typing and submitting.
4. **Proof and fail-loud.** The guard is installed before the first navigation. `verify_guard()` runs on the live page after load and again after the audit:
   - The init-script flag must be present.
   - A canary POST must be aborted by the route. On remote pages the canary goes to a same-origin path, because ATS pages set CSP `connect-src`. Real finding: the first real run failed loudly on exactly this.
   - If either check fails, the run stops before the fill and the report says `guard missing`.
   - The report counts blocked non-GET requests, blocked websockets, blocked submit attempts and canary hits. The run exits 1 on any submit attempt, a missing guard, or a demographic field that got a value.

`test_guard.py` proves all four layers offline, against a page served on 127.0.0.1:
- `submit()` and `requestSubmit()` throw;
- a submit-button click is prevented and the server gets no POST;
- a POST to a remote host is aborted, while a POST to localhost passes;
- the Ashby exception: a job-posting query is allowed; a mutation to the same URL, a query to another host, and the other shapes above are aborted;
- the canary works under a strict CSP;
- `verify_guard` raises on an unguarded context.

## Setup (once)

```
D:\Python311\python.exe -m venv D:\job-copilot\tools\.venv-browser-use
D:\job-copilot\tools\.venv-browser-use\Scripts\python -m pip install -r requirements.txt
D:\job-copilot\tools\.venv-browser-use\Scripts\python -m playwright install chromium
```

The venv is isolated on purpose, like `.venv-jobspy`: browser-use pins its own starlette, openai and anthropic, which would clash with `apps/api`.

## Run

Prerequisites:
- The backend is running on `http://localhost:8000`.
- `D:\job-copilot\apps\extension\dist` exists. If it doesn't, run `npm run build` in `apps/extension`.
- `apps/api/.env` has `NVIDIA_API_KEY`. The key is read at runtime and never printed.

```
cd tools\browser-use-harness
..\.venv-browser-use\Scripts\python -m unittest test_guard -v          # offline, ~8 s
..\.venv-browser-use\Scripts\python check_form.py --url <application URL> [--ats greenhouse] [--headed] [--no-audit]
..\.venv-browser-use\Scripts\python run_suite.py [--only greenhouse] [--no-audit]
```

Options:
- `HARNESS_MODEL=<nim model id>` overrides the auditor model. The default is `NVIDIA_MODEL` from `.env`, which is `nvidia/nemotron-3-super-120b-a12b`.
- `APPLYSCOUT_MAIN` overrides the checkout that provides `.env`, `dist` and the API venv. The default is `D:\job-copilot`.

Each run creates a throwaway account (`bu-harness-<stamp>-<hex>@example.com`) with a fictional identity and 3 facts, and deletes it at the end. The delete runs `cleanup_accounts.py --email ...` under `apps/api/.venv` (owner role; everything cascades from `users`). If a run dies before the delete, remove all leftovers with:

```
D:\job-copilot\apps\api\.venv\Scripts\python.exe cleanup_accounts.py
```

### Auto-apply mode

`auto_apply.py` drives the driver path instead of the popup: a harness job (`cleanup_accounts.py --add-job`; the API has no job-create route) whose `apply_url` is a local careers page with its own 2-field "talent community" form and a Greenhouse embed iframe. The application is approved through `batch-approve`, then `jc:run-queue` is sent from an extension page. The harness watches the tab the driver opens: it proves the guard on that tab, and it records every ApplyScout mark as it lands. A `needs_human` pass answers the returned questions in the answer bank (like the user in review) and re-approves. The run fails on a missing guard, any talent-community value, a demographic value, no fill in the iframe, or a reported send the guard didn't see.

```
..\.venv-browser-use\Scripts\python auto_apply.py [--job anthropic/4461450008] [--passes 2] [--ext-dist <dist>] [--headed]
```

The default Anthropic posting stops at `needs_human` on its required arbitration consent, which ApplyScout never gives. `--job brex/8795500002` has no consent and no required location, so it reaches the submit. The guard cancels the submit, and the driver reports `unconfirmed`. The harness job is deleted along with the account.

## Reading the report

Each run writes `reports/<UTC stamp>-<ats>.json`, `.md` and a full-page `.png`. The directory is gitignored.

| Key | Meaning |
|---|---|
| `guard` | Counters. `canary_blocked` should be 2 (before the fill and after the audit). `blocked_request_samples` shows what was stopped: analytics beacons, S3 uploads. |
| `extension_response` | The content script's own answer: `ok`, `filled`, `flagged[]`, `questions[]`. `ok:false` plus a `dialogs` entry means the fill threw. |
| `dom.filled` | Fields the extension marked, or whose value changed after the fill. `filled_marked_but_empty` is the "green outline on an empty box" React bug. |
| `dom.empty_required` | Required fields still empty. This is what would stop a submit. |
| `dom.demographic_fields` / `demographic_violations` | EEO fields, found by label, group, name or id. Any violation fails the run. |
| `auditor` | browser-use's reading of the page. `flagged` holds the fields it thinks are wrong. It is advisory: the DOM snapshot is the ground truth. |
| `timings_s` | Per phase: provision, launch, navigate, fill, audit, total. |

## Known limits

- The auditor is slow and shallow on nemotron-3-super. It took 10-160 s and sometimes hit a timeout and retried. It sees only the top part of long forms (browser-use's DOM window is about the viewport plus 1000 px, so the viewport is set to 4000 px tall). It cannot see file names.
- Resume uploads never reach the employer (the S3 POST is blocked), so the ATS may show the file field as empty.
- A same-origin canary POST reaches the employer's origin (a 404 path) only if the route layer were missing while the init script was present. The init-script check runs first.
- Report names collide if two runs of the same ATS start in the same second.
