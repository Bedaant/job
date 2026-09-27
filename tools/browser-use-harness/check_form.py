"""Fill-never-submit check of ApplyScout's extension on ONE real application form.

  ..\\.venv-browser-use\\Scripts\\python check_form.py --url <application URL> [--ats greenhouse|lever|ashby]

Flow: guard the browser context (guard.py) -> throwaway ApplyScout account -> load the built
extension -> open the form -> verify the guard on the live page -> send the popup's
`jc:fill-form` -> DOM snapshot -> browser-use auditor (read-only tools) -> report -> delete
the account. Exit 1 on a demographic value, any submit attempt, or a missing guard.
"""

import argparse
import asyncio
import json
import os
import re
import secrets
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

os.environ.setdefault("ANONYMIZED_TELEMETRY", "false")  # browser-use: no posthog
os.environ.setdefault("BROWSER_USE_CLOUD_SYNC", "false")

import httpx  # noqa: E402
from dotenv import dotenv_values  # noqa: E402
from playwright.async_api import async_playwright  # noqa: E402
from pydantic import BaseModel  # noqa: E402

from cleanup_accounts import EMAIL_PREFIX  # noqa: E402
from guard import GuardMissing, install_guard, verify_guard  # noqa: E402

HERE = Path(__file__).resolve().parent
MAIN = Path(os.environ.get("APPLYSCOUT_MAIN", r"D:\job-copilot"))  # shared checkout: .env, dist, api venv
EXT_DIST = MAIN / "apps" / "extension" / "dist"
API_ENV = MAIN / "apps" / "api" / ".env"
API_PY = MAIN / "apps" / "api" / ".venv" / "Scripts" / "python.exe"
API = os.environ.get("APPLYSCOUT_API", "http://localhost:8000")
REPORTS = HERE / "reports"
FILL_TIMEOUT_S = 240  # map-fields took 22-51 s live (LIVE-FORM-TEST.md)

# Letter-bounded so `hispanic_ethnicity` / `veteran_status` ids match too.
DEMOGRAPHIC = re.compile(
    r"(?<![a-z])(gender|sex|sexual|race|racial|ethnicity|ethnic|hispanic|latin[oax]?|veteran|"
    r"disabilit\w*|disabled|pronouns?|transgender|lgbtq?|age range)(?![a-z])",
    re.I,
)

# Allowlist, not denylist: the auditor gets `done` only. Every other browser-use action (click,
# input, select_dropdown, send_keys, upload_file, navigate, evaluate, scroll, ...) is excluded, and
# run_auditor refuses to start if anything else is registered. Tried and dropped: extract/read_file
# (both models looped on them for all 10 steps) and scroll (nemotron sent garbage `index` values).
# Instead the harness scrolls the form into view and makes the viewport tall before the audit.
AUDITOR_ALLOWED = {"done"}
AUDIT_VIEWPORT = {"width": 1280, "height": 4000}

AUDIT_TASK = """You are a READ-ONLY auditor of a job application form that software has just pre-filled.
The page is already open. HARD RULES: do not click anything, do not type, do not select, do not
upload, do not press keys, do not navigate, and NEVER submit, apply or send the application.
The browser state you are given already lists the form fields with their current values. Call
done with the report right away.
Report EVERY visible form field (text inputs, textareas, dropdowns/comboboxes, radio groups,
checkbox groups, file uploads) as one item: label, value_now (exactly what is shown; "" if empty),
required (the page marks it required, e.g. with *), looks_correct (false if the value is empty on a
required field, wrong for the question, or ANY value is present on a gender/race/ethnicity/
veteran/disability/sexual-orientation question), problem ("" if none). An EMPTY demographic
field is correct. You cannot see attached file names: for a file upload write value_now
"(file input)" and looks_correct true (the harness checks files itself).
Applicant the software used: {identity}."""


class AuditField(BaseModel):
    label: str
    value_now: str
    required: bool
    looks_correct: bool
    problem: str


class AuditReport(BaseModel):
    fields: list[AuditField]


SNAPSHOT_JS = r"""() => {
  const txt = (n) => ((n && n.textContent) || '').replace(/\s+/g, ' ').trim();
  const labelOf = (el) => {
    const al = el.getAttribute('aria-label'); if (al) return al.trim();
    const lb = el.getAttribute('aria-labelledby');
    if (lb) { const t = lb.split(/\s+/).map((i) => txt(document.getElementById(i))).join(' ').trim(); if (t) return t; }
    if (el.id) { const l = document.querySelector(`label[for="${CSS.escape(el.id)}"]`); if (txt(l)) return txt(l); }
    const cl = el.closest('label'); if (txt(cl)) return txt(cl);
    return el.getAttribute('placeholder') || '';
  };
  const groupOf = (el) => {
    const fs = el.closest('fieldset'); const lg = fs && fs.querySelector('legend'); if (txt(lg)) return txt(lg);
    const g = el.closest('[role=radiogroup],[role=group]');
    if (g) { const id = g.getAttribute('aria-labelledby'); if (id) return txt(document.getElementById(id)); if (g.getAttribute('aria-label')) return g.getAttribute('aria-label'); }
    const q = el.closest('.application-question, [class*="field"], [class*="question"]');
    const ql = q && q.querySelector('label, .application-label, legend');
    return ql ? txt(ql) : '';
  };
  const visible = (el) => { const r = el.getBoundingClientRect(); const s = getComputedStyle(el);
    return r.width > 0 && r.height > 0 && s.visibility !== 'hidden' && s.display !== 'none'; };
  const out = [];
  document.querySelectorAll('input, select, textarea').forEach((el, i) => {
    const type = el.tagName === 'SELECT' ? 'select' : el.tagName === 'TEXTAREA' ? 'textarea' : (el.type || 'text');
    if (['hidden', 'submit', 'button', 'image', 'reset'].includes(type)) return;
    let value = '';
    if (type === 'checkbox' || type === 'radio') value = el.checked ? (el.value || 'on') : '';
    else if (type === 'file') value = Array.from(el.files || []).map((f) => f.name).join(', ');
    else if (type === 'select') { const o = el.selectedOptions[0]; value = o && o.value !== '' ? txt(o) : ''; }
    else value = el.value || '';
    let display = '';
    if (el.getAttribute('role') === 'combobox') {
      const c = el.closest('[class*="container"], [class*="select__control"], [class*="select"]');
      const sv = c && c.querySelectorAll('[class*="single-value"], [class*="singleValue"], [class*="multi-value__label"]');
      display = sv ? Array.from(sv).map(txt).join(', ') : '';
    }
    const label = labelOf(el); const group = groupOf(el);
    out.push({
      index: i, type, role: el.getAttribute('role') || '', id: el.id || '', name: el.getAttribute('name') || '',
      label: label.slice(0, 200), group: group === label ? '' : group.slice(0, 200),
      required: el.required || el.getAttribute('aria-required') === 'true' || !!el.closest('[aria-required="true"]') || /[*\u2731]\s*$/.test(label),
      value: String(value).slice(0, 300), display: display.slice(0, 300), visible: visible(el),
      mark: el.title && el.title.includes('ApplyScout') ? el.title : '',
    });
  });
  return out;
}"""


def _key(f: dict) -> str:
    return f["id"] or f["name"] or f"#{f['index']}"


def _shown(f: dict) -> str:
    return f["display"] or f["value"]


def analyse(before: list[dict], after: list[dict]) -> dict:
    base = {_key(f): _shown(f) for f in before}
    filled, demographic, empty_required, groups = [], [], [], {}
    for f in after:
        text = " ".join([f["label"], f["group"], f["name"], f["id"]])
        changed = _shown(f) and _shown(f) != base.get(_key(f), "")
        if f["mark"].startswith(("Auto-filled", "Resume attached")) or changed:
            filled.append({"label": f["label"] or f["group"] or _key(f), "value": _shown(f),
                           "marked_by_extension": bool(f["mark"]), "value_present": bool(_shown(f))})
        if DEMOGRAPHIC.search(text):
            demographic.append({"label": f["label"], "group": f["group"], "key": _key(f),
                                "value": _shown(f), "got_value": bool(changed)})
        if f["type"] in ("radio", "checkbox") and f["name"]:
            g = groups.setdefault(f["name"], {"f": f, "any": False, "required": False})
            g["any"] |= bool(f["value"])
            g["required"] |= f["required"]
        elif f["required"] and f["visible"] and not _shown(f):
            empty_required.append(f["label"] or f["group"] or _key(f))
    empty_required += [g["f"]["group"] or g["f"]["label"] or n for n, g in groups.items()
                       if g["required"] and not g["any"]]
    return {
        "fields_total": len(after),
        "filled": filled,
        "filled_marked_but_empty": [x["label"] for x in filled if x["marked_by_extension"] and not x["value_present"]],
        "empty_required": list(dict.fromkeys(empty_required)),  # react-select pairs repeat a label
        "demographic_fields": demographic,
        "demographic_violations": [d for d in demographic if d["got_value"]],
    }


def nim_llm():
    """browser-use ChatOpenAI pointed at NVIDIA NIM. ChatOpenAI has no extra_body knob, so the
    AsyncOpenAI client's create() is wrapped to add NIM's thinking-off body (WORKLOG latest+34)."""
    import functools

    from browser_use import ChatOpenAI

    env = dotenv_values(API_ENV)
    key = env.get("NVIDIA_API_KEY") or os.environ.get("NVIDIA_API_KEY")
    if not key:
        sys.exit(f"NVIDIA_API_KEY missing in {API_ENV}")
    extra = {"chat_template_kwargs": {"enable_thinking": False}}

    class NimChat(ChatOpenAI):
        def get_client(self):
            client = super().get_client()
            client.chat.completions.create = functools.partial(client.chat.completions.create, extra_body=extra)
            return client

    model = os.environ.get("HARNESS_MODEL") or env.get("NVIDIA_MODEL") or "nvidia/nemotron-3-super-120b-a12b"
    base = env.get("NVIDIA_BASE_URL") or "https://integrate.api.nvidia.com/v1"
    return NimChat(model=model, base_url=base, api_key=key, timeout=180, max_completion_tokens=8192), model


def provision(stamp: str) -> dict:
    email = f"{EMAIL_PREFIX}{stamp}-{secrets.token_hex(3)}@example.com"
    password = secrets.token_urlsafe(18)
    basics = {
        "full_name": "Morgan Ellery", "phone": "+1 415 867 2931", "city": "San Francisco",
        "region": "CA", "country_code": "US",
        "network_profiles": [
            {"network": "LinkedIn", "url": "https://www.linkedin.com/in/morgan-ellery-example"},
            {"network": "GitHub", "url": "https://github.com/morgan-ellery-example"},
        ],
    }
    facts = [
        {"category": "experience", "achievement": "Built a Python/FastAPI service handling 2M requests/day",
         "tags": ["python", "fastapi"], "period_from": "2021-03-01"},
        {"category": "experience", "achievement": "Led migration of a React front end to TypeScript",
         "tags": ["react", "typescript"], "period_from": "2019-06-01", "period_to": "2021-02-28"},
        {"category": "education", "achievement": "B.S. Computer Science, State University", "tags": ["cs"]},
    ]
    with httpx.Client(base_url=API, timeout=60) as c:
        c.post("/auth/signup", json={"email": email, "password": password}).raise_for_status()
        tok = c.post("/auth/login", data={"username": email, "password": password}).raise_for_status().json()
        h = {"Authorization": f"Bearer {tok['access_token']}"}
        profile = c.post("/profiles", headers=h, json={"persona": "developer", "headline": "Software Engineer",
                                                       "location": "San Francisco, CA"}).raise_for_status().json()
        c.put(f"/profiles/{profile['id']}/basics", headers=h, json=basics).raise_for_status()
        c.post(f"/profiles/{profile['id']}/facts:bulk", headers=h, json={"facts": facts}).raise_for_status()
    return {"email": email, "token": tok["access_token"], "profile_id": profile["id"], "basics": basics}


def cleanup(email: str) -> str:
    if not API_PY.exists():
        return f"NOT CLEANED: {API_PY} missing; run cleanup_accounts.py --email {email}"
    r = subprocess.run([str(API_PY), str(HERE / "cleanup_accounts.py"), "--email", email],
                       capture_output=True, encoding="utf-8", errors="replace", timeout=120)
    return (r.stdout.strip() or r.stderr.strip()[-300:]) if r.returncode == 0 else \
        f"CLEANUP FAILED ({r.returncode}): {r.stderr.strip()[-300:]}"


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


async def run_auditor(cdp_url: str, host: str, identity: dict, timings: dict) -> dict:
    from browser_use import Agent, Browser, Tools

    llm, model = nim_llm()
    browser = Browser(cdp_url=cdp_url, keep_alive=True, allowed_domains=[host, f"*.{host}"],
                      highlight_elements=False, accept_downloads=False, auto_download_pdfs=False)
    excluded = sorted(set(Tools().registry.registry.actions) - AUDITOR_ALLOWED)
    agent = Agent(
        task=AUDIT_TASK.format(identity=json.dumps(identity)), llm=llm, page_extraction_llm=llm,
        browser=browser, tools=Tools(exclude_actions=excluded), output_model_schema=AuditReport,
        use_vision=False, flash_mode=True, directly_open_url=False, max_actions_per_step=2, llm_timeout=150,
        use_judge=False,
    )
    actions = set(agent.tools.registry.registry.actions)
    if not actions <= AUDITOR_ALLOWED:  # layer 3: refuse to run an auditor that could click
        raise GuardMissing(f"auditor has mutating actions: {sorted(actions - AUDITOR_ALLOWED)}")
    t = time.monotonic()
    try:
        history = await agent.run(max_steps=6)
    finally:
        timings["audit_s"] = round(time.monotonic() - t, 1)
        await browser.stop()
    try:
        out = history.structured_output
    except ValueError:  # model's final text did not match AuditReport; keep the raw text below
        out = None
    return {
        "model": model,
        "actions_available": sorted(actions),
        "actions_used": [k for step in history.model_actions() for k in step if k != "interacted_element"],
        "fields": [f.model_dump() for f in out.fields] if out else [],
        "flagged": [f.model_dump() for f in out.fields if not f.looks_correct] if out else [],
        "errors": [e for e in history.errors() if e],
        "final_result": None if out else (history.final_result() or "")[:1000],
    }


async def check(url: str, ats: str, headed: bool, audit: bool) -> dict:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    timings: dict = {}
    report: dict = {"url": url, "ats": ats, "started_at": stamp, "timings_s": timings, "dialogs": []}
    if not (EXT_DIST / "manifest.json").exists():
        sys.exit(f"{EXT_DIST} missing - build it: cd {MAIN / 'apps/extension'} && npm run build")

    t0 = time.monotonic()
    acct = provision(stamp)
    timings["provision_s"] = round(time.monotonic() - t0, 1)
    report["account"] = {"email": acct["email"], "profile_id": acct["profile_id"]}
    user_dir = tempfile.mkdtemp(prefix="bu-harness-profile-")
    port = free_port()
    guard = None
    try:
        async with async_playwright() as pw:
            t = time.monotonic()
            context = await pw.chromium.launch_persistent_context(
                user_dir, channel="chromium", headless=not headed, service_workers="block",
                viewport={"width": 1280, "height": 900},
                args=[f"--disable-extensions-except={EXT_DIST}", f"--load-extension={EXT_DIST}",
                      f"--remote-debugging-port={port}"],
            )
            guard = await install_guard(context)  # layers 1+2, before ANY navigation
            page = await context.new_page()
            for p in context.pages:
                if p is not page:
                    await p.close()
            page.on("dialog", lambda d: (report["dialogs"].append(d.message), asyncio.ensure_future(d.dismiss())))
            sw = context.service_workers[0] if context.service_workers else \
                await context.wait_for_event("serviceworker", timeout=20000)
            await sw.evaluate("(v) => chrome.storage.local.set(v)",
                              {"jc_token": acct["token"], "jc_profile_id": acct["profile_id"]})
            timings["launch_s"] = round(time.monotonic() - t, 1)

            t = time.monotonic()
            await page.goto(url, wait_until="load", timeout=60000)
            await page.wait_for_timeout(2500)
            await verify_guard(page, guard)  # loud failure if either layer is not live here
            timings["navigate_s"] = round(time.monotonic() - t, 1)
            before = await page.evaluate(SNAPSHOT_JS)

            t = time.monotonic()
            try:
                report["extension_response"] = await asyncio.wait_for(sw.evaluate(
                    """async ({url, profileId}) => {
                      const tabs = await chrome.tabs.query({});
                      const tab = tabs.find((t) => t.url === url) || tabs.find((t) => (t.url || '').startsWith('http'));
                      if (!tab) return {ok: false, error: 'tab not found'};
                      try { return await chrome.tabs.sendMessage(tab.id, {type: 'jc:fill-form', profileId}); }
                      catch (e) { return {ok: false, error: String(e)}; }
                    }""", {"url": page.url, "profileId": acct["profile_id"]}), FILL_TIMEOUT_S)
            except asyncio.TimeoutError:
                report["extension_response"] = {"ok": False, "error": f"no answer in {FILL_TIMEOUT_S}s"}
            await page.wait_for_timeout(1500)  # let React settle / re-render after the fill
            timings["fill_s"] = round(time.monotonic() - t, 1)
            after = await page.evaluate(SNAPSHOT_JS)
            report["dom"] = analyse(before, after)
            report["dom_snapshot"] = after
            REPORTS.mkdir(exist_ok=True)
            await page.screenshot(path=str(REPORTS / f"{stamp}-{ats}.png"), full_page=True)

            if audit:
                await page.set_viewport_size(AUDIT_VIEWPORT)
                await page.evaluate("() => { const f = document.querySelector('form') || "
                                    "document.querySelector('input:not([type=hidden]), textarea, select');"
                                    " if (f) f.scrollIntoView({block: 'start'}); }")
                try:
                    report["auditor"] = await run_auditor(f"http://127.0.0.1:{port}", urlsplit(url).hostname,
                                                          acct["basics"], timings)
                except GuardMissing:
                    raise
                except Exception as e:  # the auditor is advisory; the DOM snapshot is the ground truth
                    report["auditor"] = {"error": f"{type(e).__name__}: {e}"[:1000]}
            await verify_guard(page, guard)  # still live after the auditor
            report["final_url"] = page.url
            await context.close()
    except GuardMissing as e:
        report["guard_error"] = str(e)
    finally:
        report["guard"] = guard.summary() if guard else {"installed": False}
        report["cleanup"] = cleanup(acct["email"])
        timings["total_s"] = round(time.monotonic() - t0, 1)
        shutil.rmtree(user_dir, ignore_errors=True)

    failures = []
    if report.get("guard_error") or not report["guard"]["installed"]:
        failures.append(f"guard missing: {report.get('guard_error', 'not installed')}")
    if report["guard"].get("submit_attempts_blocked"):
        failures.append(f"{report['guard']['submit_attempts_blocked']} submit attempt(s)")
    for d in report.get("dom", {}).get("demographic_violations", []):
        failures.append(f"demographic field got a value: {d['label'] or d['group'] or d['key']} = {d['value']!r}")
    report["failures"] = failures
    report["passed"] = not failures
    write_report(report, stamp, ats)
    return report


def write_report(r: dict, stamp: str, ats: str) -> None:
    REPORTS.mkdir(exist_ok=True)
    base = REPORTS / f"{stamp}-{ats}"
    base.with_suffix(".json").write_text(json.dumps(r, indent=2, ensure_ascii=False), encoding="utf-8")
    dom, g, aud = r.get("dom", {}), r["guard"], r.get("auditor", {})
    lines = [
        f"# {ats} - {'PASS' if r['passed'] else 'FAIL'}", "", f"URL: {r['url']}", "",
        f"- Guard: installed={g.get('installed')}, canary blocked={g.get('canary_blocked', 0)}, "
        f"blocked non-GET requests={g.get('blocked_non_get_requests', 0)}, blocked websockets="
        f"{g.get('blocked_websockets', 0)}, submit attempts blocked={g.get('submit_attempts_blocked', 0)}",
        f"- Extension response: `{json.dumps(r.get('extension_response'))[:400]}`",
        f"- Dialogs: {r['dialogs'] or 'none'}",
        f"- Fields: {dom.get('fields_total', '?')}, filled: {len(dom.get('filled', []))}, "
        f"marked-but-empty: {dom.get('filled_marked_but_empty', [])}",
        f"- Empty required: {dom.get('empty_required', [])}",
        f"- Demographic fields: {len(dom.get('demographic_fields', []))}, with a value: "
        f"{[d['label'] or d['key'] for d in dom.get('demographic_violations', [])]}",
        f"- Auditor ({aud.get('model', '-')}): {len(aud.get('fields', []))} fields read, "
        f"{len(aud.get('flagged', []))} flagged, actions used {aud.get('actions_used', [])}"
        + (f", error: {aud['error']}" if aud.get("error") else ""),
        f"- Timings (s): {r['timings_s']}", f"- Cleanup: {r['cleanup']}",
        f"- Failures: {r['failures'] or 'none'}", "", "## Filled", "",
    ]
    lines += [f"- {f['label']}: `{f['value']}`" for f in dom.get("filled", [])] or ["- none"]
    lines += ["", "## Auditor-flagged", ""]
    lines += [f"- {f['label']}: `{f['value_now']}` - {f['problem']}" for f in aud.get("flagged", [])] or ["- none"]
    base.with_suffix(".md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"report: {base}.json / .md")


def detect_ats(url: str) -> str:
    host = urlsplit(url).hostname or ""
    return next((a for a, h in (("greenhouse", "greenhouse.io"), ("lever", "lever.co"), ("ashby", "ashbyhq.com"))
                 if host.endswith(h)), "other")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--url", required=True)
    ap.add_argument("--ats", choices=["greenhouse", "lever", "ashby", "other"])
    ap.add_argument("--headed", action="store_true")
    ap.add_argument("--no-audit", action="store_true", help="skip the browser-use LLM auditor")
    a = ap.parse_args()
    r = asyncio.run(check(a.url, a.ats or detect_ats(a.url), a.headed, not a.no_audit))
    print("PASS" if r["passed"] else "FAIL: " + "; ".join(r["failures"]))
    return 0 if r["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
