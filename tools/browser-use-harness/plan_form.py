"""Read-only FORM PLAN of one application form by browser-use (ADR-016, PLAN-MULTI-ATS Phase 0).

  ..\\.venv-browser-use\\Scripts\\python plan_form.py --url <apply url> [--allow host ...] [--out plan.json] [--headed]

Guarded Chromium exactly like check_form (install_guard before any navigation, verify_guard after
load and at the end), no extension, a synthetic identity only. A browser-use agent walks the form
(opens dropdowns, tries typeaheads, clicks non-submit Next steps) with an allowlist of exploring
actions and returns a structured plan: per field the widget, required flag, options, and WHERE the
value comes from (profile key / answer-bank question / resume / never), never the value itself.
The DOM snapshot (check_form.SNAPSHOT_JS) before and after the walk is saved as ground truth.
"""

import os

os.environ["ANONYMIZED_TELEMETRY"] = "false"  # before browser_use is imported (via check_form too)
os.environ["BROWSER_USE_CLOUD_SYNC"] = "false"

import argparse  # noqa: E402
import asyncio  # noqa: E402
import hashlib  # noqa: E402
import json  # noqa: E402
import shutil  # noqa: E402
import sys  # noqa: E402
import tempfile  # noqa: E402
import time  # noqa: E402
from datetime import datetime, timezone  # noqa: E402
from urllib.parse import urlsplit  # noqa: E402

from playwright.async_api import async_playwright  # noqa: E402
from pydantic import BaseModel, Field  # noqa: E402

import check_form as cf  # noqa: E402
from guard import GuardMissing, install_guard, verify_guard  # noqa: E402

# Exploring actions only. No navigate/go_back/search/switch/close (stay on the page), no evaluate
# (arbitrary JS), no upload_file/write_file/read_file/replace_file/save_as_pdf/screenshot, no
# send_keys (Enter can submit), no extract (models looped on it, see check_form).
# dropdown_options/select_dropdown dropped after two trials: nemotron called dropdown_options on every
# react-select input (it only works on native <select>), hit max_failures and returned an empty plan.
PLANNER_ALLOWED = {"done", "click", "input", "scroll", "find_elements", "search_page", "find_text", "wait"}
VIEWPORT = {"width": 1280, "height": 4000}  # browser-use sees ~viewport+1000px of DOM; make it the form
PROFILE_KEYS = ["full_name", "given_name", "family_name", "email", "phone", "city", "region", "country_code",
                "location", "linkedin", "github", "website", "current_company", "current_title", "cover_letter"]
IDENTITY = {"full_name": "Morgan Ellery", "email": "morgan.ellery@example.com", "phone": "+1 415 867 2931",
            "city": "San Francisco", "region": "CA", "country": "United States",
            "linkedin": "https://www.linkedin.com/in/morgan-ellery-example"}  # fictional, check_form's basics

TASK = """You are MAPPING a job application form to build a fill plan. The form is already open.
HARD RULES: NEVER click a Submit / Apply / Send / Finish button. Do not navigate to another page or
open links. Do not upload files. Stay on this page.

Your job: walk the WHOLE form, top to bottom (scroll down until you have seen its end), and
report every field a candidate would fill. To learn each field:
- native <select>: its first options are listed in the browser state; record those.
- custom dropdown / combobox (an <input role=combobox>, "Select..."): CLICK the input to open it,
  read the listed options from the next browser state, then move on to the next field (at most 20
  options per field; for long standard lists such as countries or US states record the first 5
  and then "... (list of countries)").
- If an action fails, do not repeat it on the same element: record what you know and move on.
- location / city fields that suggest as you type: input "San Francisco" and read the suggestions.
- If there is a "Next" / "Continue" step button that is NOT the final submit, click it and map the
  next step too; list each such click in `steps` (e.g. "click Next").
You MAY type this fictional applicant's data only to reveal options: {identity}.
Work fast (several actions per step), but call done ONLY after you have opened every dropdown /
combobox once, read its options, and scrolled to the end of the form (demographic / EEO questions
are usually at the bottom). Every field in the plan must have a non-empty label. `done` ENDS the task for good: it must carry
the COMPLETE plan with EVERY field of the form (fields you did not open still go in, with the
options you could see), never just the field you worked on last. Keep the running field list in
your memory as you go.

For each field report:
- label: the question text as shown.
- selector_hint: the element's id attribute, else its name attribute ("" if neither).
- widget: one of text, textarea, select (native), react_select (custom dropdown), typeahead
  (suggests as you type), radio, checkbox, date, file, other.
- required: true if marked required (asterisk, "required", aria-required).
- options: the choices for select / react_select / typeahead / radio / checkbox groups ([] otherwise).
- fill_from: where the value would come from: one of the profile keys {keys}; or "resume" (resume/CV
  upload); or "answer_bank_question" (a job-specific question: sponsorship, work authorization, how
  did you hear, salary, why us, free-text questions, yes/no questions); or "never" for EVERY consent,
  acknowledgement, agreement, privacy/terms, certification-of-truth, arbitration, and EVERY
  demographic / EEO question (gender, race, ethnicity, veteran, disability, sexual orientation,
  pronouns, age); or "unknown".
- verify: how to confirm the value shows after filling (e.g. "input value", "selected chip text",
  "radio checked").
Never put the applicant's values into the plan."""


# --mode list: no exploring at all. The browser state already lists every field (tall viewport), so
# the agent gets `done` only (like check_form's auditor) and reads the plan off the page in one call.
LIST_ALLOWED = {"done"}
LIST_VIEWPORT = {"width": 1280, "height": 8000}
LIST_TASK = """You are MAPPING a job application form to build a fill plan. The form is already open and
the browser state you are given lists EVERY field of it. HARD RULES: do not click, type, select,
scroll, navigate or submit. Call done right away with the COMPLETE plan: every field a candidate
would fill, top to bottom, including the demographic / EEO questions at the bottom. Options: the
choices you can see (native select options, radio / checkbox labels; at most 20; [] if hidden).
Every field must have a non-empty label. The fictional applicant is only context: {identity}.

""" + TASK[TASK.index("For each field report:"):]


class PlanField(BaseModel):
    label: str
    selector_hint: str = ""
    widget: str = "other"
    required: bool = False
    options: list[str] = Field(default_factory=list)
    fill_from: str = "unknown"
    verify: str = ""


class FormPlan(BaseModel):
    fields: list[PlanField]
    steps: list[str] = Field(default_factory=list)


def fingerprint(snapshot: list[dict]) -> str:
    """Stable id of the form's field set: sorted, deduped ids/names of the non-hidden controls."""
    keys = sorted({f["id"] or f["name"] for f in snapshot if f["id"] or f["name"]})
    return hashlib.sha256("\n".join(keys).encode()).hexdigest()[:16]


async def run_planner(cdp_url: str, allowed: list[str], max_steps: int, mode: str = "explore") -> dict:
    from browser_use import Agent, Browser, Tools
    from browser_use.dom.views import DEFAULT_INCLUDE_ATTRIBUTES

    llm, model = cf.nim_llm()
    browser = Browser(cdp_url=cdp_url, keep_alive=True, allowed_domains=allowed,
                      highlight_elements=False, accept_downloads=False, auto_download_pdfs=False)
    permitted = LIST_ALLOWED if mode == "list" else PLANNER_ALLOWED
    excluded = sorted(set(Tools().registry.registry.actions) - permitted)
    agent = Agent(
        task=(LIST_TASK if mode == "list" else TASK).format(identity=json.dumps(IDENTITY), keys=", ".join(PROFILE_KEYS)), llm=llm,
        page_extraction_llm=llm, browser=browser, tools=Tools(exclude_actions=excluded),
        output_model_schema=FormPlan, use_vision=False, flash_mode=False, use_thinking=False, directly_open_url=False,
        max_actions_per_step=5, llm_timeout=170, use_judge=False, max_failures=8,
        include_attributes=DEFAULT_INCLUDE_ATTRIBUTES + ["required", "aria-required"],
    )
    actions = set(agent.tools.registry.registry.actions)
    if not actions <= permitted:  # never run a planner that could navigate / upload / eval
        raise GuardMissing(f"planner has disallowed actions: {sorted(actions - permitted)}")
    t = time.monotonic()
    try:
        history = await agent.run(max_steps=max_steps)
    finally:
        await browser.stop()
    try:
        out = history.structured_output
    except ValueError:
        out = None
    usage = history.usage
    return {
        "model": model,
        "plan": out.model_dump() if out else None,
        "final_result": None if out else (history.final_result() or "")[:2000],
        "agent_s": round(time.monotonic() - t, 1),
        "steps": history.number_of_steps(),
        "llm_calls": usage.entry_count if usage else None,
        "prompt_tokens": usage.total_prompt_tokens if usage else None,
        "completion_tokens": usage.total_completion_tokens if usage else None,
        "actions_used": [k for step in history.model_actions() for k in step if k != "interacted_element"],
        "errors": [e[:300] for e in history.errors() if e],
        "done": history.is_done(),
    }


async def plan(url: str, allow: list[str], headed: bool, max_steps: int, mode: str = "explore") -> dict:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    t0 = time.monotonic()
    report: dict = {"url": url, "started_at": stamp}
    host = urlsplit(url).hostname
    allowed = sorted({d for h in [host, *allow] for d in (h, f"*.{h}")})
    user_dir = tempfile.mkdtemp(prefix="bu-plan-profile-")
    port = cf.free_port()
    guard = None
    try:
        async with async_playwright() as pw:
            context = await pw.chromium.launch_persistent_context(
                user_dir, channel="chromium", headless=not headed, service_workers="block", viewport=LIST_VIEWPORT if mode == "list" else VIEWPORT,
                args=[f"--remote-debugging-port={port}"],
            )
            guard = await install_guard(context)  # layers 1+2, before ANY navigation
            page = await context.new_page()
            for p in context.pages:
                if p is not page:
                    await p.close()
            page.on("dialog", lambda d: asyncio.ensure_future(d.dismiss()))
            t = time.monotonic()
            await page.goto(url, wait_until="load", timeout=60000)
            await page.wait_for_timeout(2500)
            await verify_guard(page, guard)
            report["load_s"] = round(time.monotonic() - t, 1)
            form = await cf.form_frame(page)
            report["form_frame_url"] = form.url
            report["snapshot_before"] = await form.evaluate(cf.SNAPSHOT_JS)
            await page.evaluate("() => { const f = document.querySelector('form, iframe, input:not([type=hidden])');"
                                " if (f) f.scrollIntoView({block: 'start'}); }")
            try:
                report["planner"] = await run_planner(f"http://127.0.0.1:{port}", allowed, max_steps, mode)
            except GuardMissing:
                raise
            except Exception as e:
                report["planner"] = {"error": f"{type(e).__name__}: {e}"[:1000]}
            for p in context.pages:  # the planner must not have escaped the guard on any web tab
                if p.url.startswith("http"):
                    await verify_guard(p, guard)
            form = await cf.form_frame(page)
            report["snapshot_after"] = await form.evaluate(cf.SNAPSHOT_JS)
            report["final_url"] = page.url
            report["pages_open"] = len(context.pages)
            await context.close()
    except GuardMissing as e:
        report["guard_error"] = str(e)
    finally:
        report["guard"] = guard.summary() if guard else {"installed": False}
        report["total_s"] = round(time.monotonic() - t0, 1)
        shutil.rmtree(user_dir, ignore_errors=True)
    if report.get("snapshot_before"):
        report["fingerprint"] = fingerprint(report["snapshot_before"])
    return report


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--url", required=True)
    ap.add_argument("--allow", nargs="*", default=[], help="extra hosts the agent may be on (embed iframes)")
    ap.add_argument("--out", help="write the JSON report here (default reports/<stamp>-plan.json)")
    ap.add_argument("--max-steps", type=int, default=30)
    ap.add_argument("--mode", choices=["explore", "list"], default="explore",
                    help="explore: walk the form with clicks/typing; list: done-only, read the plan off the page")
    ap.add_argument("--headed", action="store_true")
    a = ap.parse_args()
    r = asyncio.run(plan(a.url, a.allow, a.headed, 3 if a.mode == "list" else a.max_steps, a.mode))
    r["mode"] = a.mode
    out = a.out or str(cf.REPORTS / f"{r['started_at']}-plan.json")
    cf.REPORTS.mkdir(exist_ok=True)
    with open(out, "w", encoding="utf-8") as fh:
        json.dump(r, fh, indent=2, ensure_ascii=False)
    p, g = r.get("planner", {}), r["guard"]
    print(f"plan: {out}\nfields={len((p.get('plan') or {}).get('fields', []))} steps={p.get('steps')} "
          f"llm_calls={p.get('llm_calls')} agent_s={p.get('agent_s')} error={p.get('error') or r.get('guard_error')}"
          f"\nguard: canary={g.get('canary_blocked')} blocked={g.get('blocked_non_get_requests')} "
          f"submits={g.get('submit_attempts_blocked')}")
    bad = r.get("guard_error") or not g.get("installed")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
