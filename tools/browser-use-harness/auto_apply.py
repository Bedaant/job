"""Drive the extension's AUTO-APPLY path (driver + frame claims + submit + verify) on an embedded
Greenhouse board, under the same no-submit guard as check_form.

  ..\\.venv-browser-use\\Scripts\\python auto_apply.py [--ext-dist <dist>] [--headed] [--passes 2]

Flow: throwaway account -> a harness job whose apply_url is a local careers page (its own 2-field
"talent community" form + the Greenhouse embed iframe) -> application ready_for_review ->
batch-approve (the real approval) -> guarded Chromium with the extension -> `jc:run-queue` from an
extension page -> watch the tab the driver opens (guard proof, per-frame snapshots) -> report.
A `needs_human` pass answers the questions it returned in the answer bank (the review-queue loop)
and re-approves, up to --passes. Account and job are deleted at the end.
Exit 1 on: guard missing, the submit NOT blocked, a talent-community value, a demographic value,
or no fields filled in the iframe.

  --fixture workday|workday-noconsent|wall   local Workday-like multi-page SPA / account wall
  --url <job URL>                            recon on a real posting (guarded, outcome not judged)
Those modes are judged by mode_failures(): a password filled, a POST to /account or /submitted,
a demographic value, and per mode the expected final status / notes / pages reached.
"""

import argparse
import asyncio
import http.server
import json
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

import httpx
from playwright.async_api import async_playwright

import check_form as cf
from guard import GuardMissing, install_guard, verify_guard

# Anthropic's form ends in a required arbitration consent, which ApplyScout never gives, so it
# stops at needs_human. `--job robinhood/8202874` has no consent: it reaches the (blocked) submit.
DEFAULT_JOB = "anthropic/4461450008"
EMBED = "https://job-boards.greenhouse.io/embed/job_app?for={board}&token={token}"
HOST_PAGE = """<!doctype html><html><head><meta charset="utf-8"><title>Careers - Harness Co</title></head>
<body><h1>Careers at Harness Co</h1>
<form id="talent-community" action="/talent" method="post"><h2>Join our talent community</h2>
<label>Email <input id="tc-email" name="tc_email" type="email"></label>
<label>Name <input id="tc-name" name="tc_name" type="text"></label>
<button type="submit">Join</button></form>
<iframe id="grnhse_iframe" src="{embed}" width="100%" height="3000" title="Greenhouse Job Board"></iframe>
</body></html>"""
# Observation only (not a guard layer): every ApplyScout mark (fill / flag title) is reported the
# moment it lands, since the driver closes the tab right after the frame reports.
MARKS_BINDING = "__applyscoutHarnessMark"
MARKS_SCRIPT = """(() => {
  const label = (el) => ((el.labels && el.labels[0] && el.labels[0].innerText) || el.getAttribute('aria-label')
    || el.id || el.name || el.tagName).trim().slice(0, 150);
  new MutationObserver((ms) => { for (const m of ms) {
    const el = m.target; if (!el.title || !el.title.includes('ApplyScout')) continue;
    try { window.%s(label(el), el.title, String(el.value || '').slice(0, 100), el.type || ''); } catch (_) {}
  } }).observe(document, {subtree: true, attributes: true, attributeFilter: ['title']});
})();""" % MARKS_BINDING
# Observation only: a chained 25 ms timer in every frame, to measure background-tab throttling
# (Chrome aligns hidden-tab timers to 1 s), plus when menus opened (option reads) and the first
# ApplyScout mark landed, in ms since the frame loaded. Read by the Watcher with each snapshot.
TIMER_PROBE = """(() => {
  const p = window.__jcTimerProbe = {n: 0, hidden_n: 0, max_ms: 0, hidden_max_ms: 0, over_500: 0, hidden_seen: false,
    menus_opened: 0, first_menu_ms: null, last_menu_before_mark_ms: null, first_mark_ms: null, read_ids: []};
  new MutationObserver((ms) => { for (const m of ms) {
    const now = Math.round(performance.now());
    if (m.attributeName === 'title' && (m.target.title || '').includes('ApplyScout')) p.first_mark_ms ??= now;
    if (m.attributeName === 'aria-expanded' && p.first_mark_ms === null) { (p.ev ??= []).push([m.target.id.slice(-6), m.target.getAttribute('aria-expanded'), now]); (window.__refs ??= []).push(m.target); }
    if (m.attributeName === 'aria-expanded' && m.target.getAttribute('aria-expanded') === 'true') {
      p.menus_opened++; p.first_menu_ms ??= now;
      if (p.first_mark_ms === null) { p.last_menu_before_mark_ms = now; p.read_ids.push(m.target.id); } }
  } }).observe(document, {subtree: true, attributes: true, attributeFilter: ['title', 'aria-expanded']});
new MutationObserver((ms) => { if (p.first_mark_ms !== null) return; const now = Math.round(performance.now()); for (const m of ms) { const has = (n) => n.nodeType === 1 && (n.matches('[role=listbox]') || n.querySelector('[role=listbox]')); for (const n of m.addedNodes) if (has(n)) (p.ev ??= []).push(['+lb', now]); for (const n of m.removedNodes) if (has(n)) (p.ev ??= []).push(['-lb', now]); } }).observe(document, {subtree: true, childList: true});  document.addEventListener('focusin', (e) => { if (p.first_mark_ms === null) (p.ev ??= []).push(['focus', (e.target.id||'').slice(-6), Math.round(performance.now())]); }, true);  document.addEventListener('keyup', (e) => { if (p.first_mark_ms === null) (p.ev ??= []).push(['keyup', Math.round(performance.now())]); }, true);  document.addEventListener('mouseup', (e) => { if (p.first_mark_ms === null) (p.ev ??= []).push(['mouseup', Math.round(performance.now())]); }, true);
  let t = performance.now();
  const tick = () => { const d = performance.now() - t; p.n++; p.max_ms = Math.max(p.max_ms, Math.round(d));
    if (document.hidden) { p.hidden_seen = true; p.hidden_n++; p.hidden_max_ms = Math.max(p.hidden_max_ms, Math.round(d)); }
    if (d > 500) p.over_500++; t = performance.now(); setTimeout(tick, 25); };
  setTimeout(tick, 25);
})();"""
# = Playwright's service_workers="block", which a CDP-joined context doesn't take (guard layer 1)
BLOCK_SW = "if (navigator.serviceWorker) navigator.serviceWorker.register = async () => {};"
RUN_TIMEOUT_S = 300  # ITEM_TIMEOUT 60 s + verify 20+10 s per item, plus slack
LONG_RUN_TIMEOUT_S = 900  # fixture / url modes: several pages per item
FIXTURES = cf.HERE / "fixtures"
FIXTURE = {"workday": ("workday_like.html", ""), "workday-noconsent": ("workday_like.html", "?consent=0"),
           "wall": ("account_wall.html", "")}
# Where a multi-page flow is, per snapshot: URL, which Workday automation ids are on the page, the
# active step and the next button's text.
WORKDAY_IDS = ["adventureButton", "applyManually", "signInContent", "password", "bottom-navigation-next-button",
               "progressBarActiveStep", "errorMessage"]
TRAIL_JS = """(ids) => {
  const q = (i) => document.querySelector(`[data-automation-id="${i}"]`);
  const txt = (i) => ((q(i) || {}).innerText || '').replace(/\\s+/g, ' ').trim().slice(0, 120);
  return {href: location.href, ids: ids.filter(q), step: txt('progressBarActiveStep'),
          next: txt('bottom-navigation-next-button')};
}"""
# Fictional answers for questions a needs_human pass returns (the user would type these in review).
# First match wins: "authorized" before "country" ("Are you legally authorized to work in this country?" is a Yes/No).
CANNED = [("notified", "Yes"), ("name of your current manager", "Alex Example"), ("sponsor", "No"), ("interviewed", "No"), ("deadline", "No"), ("authorized", "Yes"), ("country", "United States"), ("visa", "No"), ("relocat", "Yes"), ("remote", "Yes"),
          ("in-person", "Yes"), ("office", "Yes"), ("salary", "Open to discussing"), ("start", "In two weeks"),
          ("hear about", "Company website"), ("website", "https://example.com"), ("ai policy", "Yes")]


def canned(q: str) -> str:
    low = q.lower()
    return next((a for k, a in CANNED if k in low),
                "I build reliable backend services and would like to work on safe AI systems.")


def serve_host_page(page: str) -> tuple[http.server.ThreadingHTTPServer, str]:
    """Serves `page` on every GET; counts POSTs per path in srv.hits (/save, /submitted, /account)."""
    body = page.encode()
    hits: Counter = Counter()

    class H(http.server.BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_POST(self):  # noqa: N802
            self.rfile.read(int(self.headers.get("Content-Length") or 0))
            hits[urlsplit(self.path).path] += 1
            self.send_response(204)
            self.end_headers()

        def log_message(self, *_):
            pass

    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H)
    srv.hits = hits
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, f"http://127.0.0.1:{srv.server_address[1]}/careers"


async def launch_like_a_user(pw, user_dir: str):
    """--headed: Chromium started by us and joined over CDP with no_defaults. Playwright's own launch
    passes --disable-background-timer-throttling & co and turns on focus emulation for every page it
    attaches, which keeps a background tab visible: the driver's active:false tab would never be
    throttled and the run would prove nothing about background tabs."""
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    proc = subprocess.Popen([pw.chromium.executable_path, f"--remote-debugging-port={port}",
                             f"--user-data-dir={user_dir}", "--no-first-run", "--no-default-browser-check",
                             "--window-size=1280,900", f"--disable-extensions-except={cf.EXT_DIST}",
                             f"--load-extension={cf.EXT_DIST}", "about:blank"])
    for _ in range(100):
        try:
            httpx.get(f"http://127.0.0.1:{port}/json/version").raise_for_status()
            break
        except httpx.HTTPError:
            await asyncio.sleep(0.2)
    browser = await pw.chromium.connect_over_cdp(f"http://127.0.0.1:{port}", no_defaults=True)
    await browser.contexts[0].add_init_script(BLOCK_SW)
    return proc, browser.contexts[0]


def mode_failures(report: dict, mode: str) -> list[str]:
    """Verdict for the fixture / url modes (the default Greenhouse mode keeps its own checks in run)."""
    passes = report.get("passes") or []
    tabs = [t for p in passes for t in p.get("tabs") or []]
    marks = [m for p in passes for m in p.get("marks") or []]
    hits = report.get("server_hits") or {}
    out = [report["error"]] if report.get("error") else []
    if report.get("guard_error") or not (report.get("guard") or {}).get("installed") or not tabs \
            or any(not t.get("guard_verified") for t in tabs):
        out.append(f"guard missing or unverified: {report.get('guard_error') or [t.get('guard_error') for t in tabs]}")
    pw = [x for t in tabs for x in t.get("passwords_filled") or []] + \
         [m["label"] for m in marks if m.get("type") == "password" and m.get("value")]
    if pw:
        out.append(f"a password field got a value: {pw}")
    for path in ("/account", "/submitted"):
        if hits.get(path):
            out.append(f"{path} was POSTed {hits[path]} time(s)")
    demo = [d for t in tabs for d in t.get("demographic_violations") or []]
    if demo:
        out.append(f"demographic field got a value: {demo}")
    if mode == "url":
        return out
    last = passes[-1] if passes else {}
    if last.get("status_after") != "ready_for_review":
        out.append(f"final status {last.get('status_after')!r}, expected 'ready_for_review'")
    if mode == "wall":
        lines = (last.get("notes") or "").strip().splitlines()
        if not lines or "sign in" not in lines[-1].lower():
            out.append(f"last notes line doesn't ask to sign in: {lines[-1] if lines else None!r}")
        return out
    if hits.get("/save", 0) < 2:
        out.append(f"/save POSTed {hits.get('/save', 0)} time(s): fewer than 2 pages saved")
    if mode == "workday-noconsent" and not any(
            "review" in s.get("step", "").lower() or s.get("next", "").strip() == "Submit"
            for t in tabs for s in t.get("trail") or []):
        out.append("the Review page was never reached")
    return out


def add_job(url: str) -> str:
    r = subprocess.run([str(cf.API_PY), str(cf.HERE / "cleanup_accounts.py"), "--add-job", url],
                       capture_output=True, encoding="utf-8", errors="replace", timeout=120)
    if r.returncode:
        raise RuntimeError(f"add-job failed: {r.stderr[-300:]}")
    return r.stdout.strip().splitlines()[-1]


class Watcher:
    """Follows the tab the driver opens: proves the guard on it, snapshots both frames until it closes."""

    def __init__(self, guard):
        self.guard, self.tabs = guard, []

    def attach(self, page) -> None:
        if not page.url.startswith("chrome-extension://"):
            rec = {"dialogs": [], "snapshots": 0, "iframe": None, "iframe_first": None, "top": None,
                   "top_first": None, "guard_verified": False, "trail": [], "passwords": set(), "demographic": {}}
            rec["task"] = asyncio.ensure_future(self.watch(page, rec))
            self.tabs.append(rec)

    async def watch(self, page, rec: dict) -> None:
        page.on("dialog", lambda d: (rec["dialogs"].append(d.message), asyncio.ensure_future(d.dismiss())))
        try:
            await page.wait_for_load_state("load", timeout=60000)
            rec["url"] = page.url
            await verify_guard(page, self.guard)
            rec["guard_verified"] = True
            while not page.is_closed():
                gh = next((f for f in page.frames if "greenhouse.io" in f.url), None)
                try:
                    rec["top"] = top = await page.main_frame.evaluate(cf.SNAPSHOT_JS)
                    rec["top_first"] = rec["top_first"] or top
                    self.scan(rec, rec["top_first"], top)
                    at = await page.main_frame.evaluate(TRAIL_JS, WORKDAY_IDS)
                    if not rec["trail"] or rec["trail"][-1] != at:
                        rec["trail"].append(at)
                    if gh:
                        snap = await gh.evaluate(cf.SNAPSHOT_JS)
                        rec["iframe_first"] = rec["iframe_first"] or snap
                        rec["iframe"], rec["iframe_url"] = snap, gh.url
                        rec["timer_probe"] = await gh.evaluate(
                            "() => ({...window.__jcTimerProbe, refs: (window.__refs || []).map((e) => [e.id.slice(-6), e.isConnected, e.getAttribute('aria-expanded'), document.activeElement === e]), comboboxes: [...document.querySelectorAll('input[role=combobox]')].map((e) => e.id)})")
                        self.scan(rec, rec["iframe_first"], snap)
                    rec["snapshots"] += 1
                except Exception:  # closing / re-rendering mid-evaluate
                    pass
                await asyncio.sleep(1)
        except GuardMissing as e:
            rec["guard_error"] = str(e)
            await page.close()  # never let an unguarded tab go on
        except Exception as e:
            if not page.is_closed():
                rec["error"] = f"{type(e).__name__}: {e}"[:300]

    @staticmethod
    def scan(rec: dict, first: list, snap: list) -> None:
        """Every snapshot, not just the last: a multi-page flow drops a page's fields when it advances."""
        rec["passwords"] |= {f["label"] or f["id"] for f in snap if f["type"] == "password" and f["value"]}
        for d in cf.analyse(first, snap)["demographic_violations"]:
            rec["demographic"][d["key"]] = d["label"] or d["key"]


async def run(headed: bool, passes: int, job: str, mode: str = "greenhouse", url: str | None = None) -> dict:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    report: dict = {"mode": "auto-apply", "target": mode, "started_at": stamp, "passes": []}
    if not (cf.EXT_DIST / "manifest.json").exists():
        sys.exit(f"{cf.EXT_DIST} missing - npm run build in apps/extension")
    srv, timeout = None, LONG_RUN_TIMEOUT_S
    if mode == "greenhouse":
        with httpx.Client(timeout=30) as c:
            board, token = job.split("/")
            embed = EMBED.format(board=board, token=token)
            c.get(embed).raise_for_status()  # the posting must still be live
        srv, host_url = serve_host_page(HOST_PAGE.replace("{embed}", embed.replace("&", "&amp;")))
        report["embed"], timeout = embed, RUN_TIMEOUT_S
    elif mode == "url":
        host_url = url
    else:
        name, query = FIXTURE[mode]
        srv, host_url = serve_host_page((FIXTURES / name).read_text(encoding="utf-8"))
        host_url += query
    report["apply_url"] = host_url
    acct = cf.provision(stamp)
    report["account"] = {"email": acct["email"], "profile_id": acct["profile_id"]}
    user_dir = tempfile.mkdtemp(prefix="bu-harness-profile-")
    guard = proc = None
    try:
        api = httpx.Client(base_url=cf.API, timeout=60, headers={"Authorization": f"Bearer {acct['token']}"})
        pid = acct["profile_id"]
        # given/family names: without them First/Last Name map low_confidence and every pass stops there
        api.put(f"/profiles/{pid}/basics", json={**acct["basics"], "given_name": "Morgan",
                                                 "family_name": "Ellery"}).raise_for_status()
        job_id = add_job(host_url)
        app_id = api.post("/applications", json={"job_id": job_id, "profile_id": pid}).raise_for_status().json()["id"]
        report["application_id"] = app_id

        async with async_playwright() as pw:
            if headed:
                proc, context = await launch_like_a_user(pw, user_dir)
            else:
                context = await pw.chromium.launch_persistent_context(
                    user_dir, channel="chromium", headless=True, service_workers="block",
                    viewport={"width": 1280, "height": 900},
                    args=[f"--disable-extensions-except={cf.EXT_DIST}", f"--load-extension={cf.EXT_DIST}"],
                )
            guard = await install_guard(context)  # before ANY navigation, covers every tab the driver opens
            marks: list = []
            await context.expose_binding(MARKS_BINDING, lambda src, label, title, value, typ="": marks.append(
                {"frame": src["frame"].url[:120], "label": label, "mark": title.split(" —")[0], "value": value,
                 "type": typ}))
            await context.add_init_script(MARKS_SCRIPT)
            await context.add_init_script(TIMER_PROBE)
            ours = lambda w: w.url.endswith("/service-worker-loader.js")  # a CDP-joined browser lists others too
            sw = next(filter(ours, context.service_workers), None) or \
                await context.wait_for_event("serviceworker", predicate=ours, timeout=20000)
            await sw.evaluate("(v) => chrome.storage.local.set(v)", {"jc_token": acct["token"], "jc_profile_id": pid})
            ext_id = sw.url.split("/")[2]
            popup = await context.new_page()
            await popup.goto(f"chrome-extension://{ext_id}/index.html")
            for p in context.pages:
                if p is not popup:
                    await p.close()

            for n in range(1, passes + 1):
                api.patch(f"/applications/{app_id}", json={"status": "ready_for_review"}).raise_for_status()
                api.post("/applications/batch-approve", json={"application_ids": [app_id]}).raise_for_status()
                queue = api.get("/extension/work-queue").raise_for_status().json()
                watcher = Watcher(guard)
                marks.clear()
                context.on("page", watcher.attach)
                t = time.monotonic()
                try:
                    result = await asyncio.wait_for(
                        popup.evaluate("() => chrome.runtime.sendMessage({type: 'jc:run-queue'})"), timeout)
                except asyncio.TimeoutError:
                    result = {"error": f"no answer in {timeout}s"}
                context.remove_listener("page", watcher.attach)
                for tab in watcher.tabs:
                    tab["task"].cancel()
                row = next(a for a in api.get("/applications", params={"profile_id": pid}).raise_for_status().json() if a["id"] == app_id)
                p = {"pass": n, "queue_items": len(queue), "run_queue": result,
                     "seconds": round(time.monotonic() - t, 1), "status_after": row["status"],
                     "notes": row.get("notes"), "marks": list(marks), "tabs": []}
                for tab in watcher.tabs:
                    ifr, top = tab.get("iframe") or [], tab.get("top") or []
                    p["tabs"].append({
                        "url": tab.get("url"), "guard_verified": tab.get("guard_verified"),
                        "guard_error": tab.get("guard_error"), "error": tab.get("error"),
                        "dialogs": tab.get("dialogs"), "snapshots": tab.get("snapshots"),
                        "iframe_url": tab.get("iframe_url"), "timer_probe": tab.get("timer_probe"),
                        "iframe": cf.analyse(tab.get("iframe_first") or [], ifr) if ifr else None,
                        "talent_community": [{"id": f["id"], "value": f["value"]} for f in top],
                        "trail": tab["trail"], "passwords_filled": sorted(tab["passwords"]),
                        "demographic_violations": sorted(tab["demographic"].values()),
                    })
                report["passes"].append(p)
                if row["status"] != "ready_for_review":
                    break
                # needs_human: answer what it asked, like the user would in the review queue
                rq = api.get("/applications/review-queue", params={"profile_id": pid}).raise_for_status().json()
                qs = next((r["pending_questions"] for r in rq if r["id"] == app_id), [])
                p["answered"] = {}
                for q in qs:
                    a = canned(q)
                    if api.put(f"/profiles/{pid}/answers", json={"question_text": q, "answer_text": a}).is_success:
                        p["answered"][q] = a
                if not p["answered"]:
                    break
            if not proc:
                await context.close()
    except GuardMissing as e:
        report["guard_error"] = str(e)
    except Exception as e:  # still report and clean up
        report["error"] = f"{type(e).__name__}: {e}"[:1000]
    finally:
        report["guard"] = guard.summary() if guard else {"installed": False}
        report["cleanup"] = cf.cleanup(acct["email"])
        if srv:
            report["server_hits"] = dict(srv.hits)
            srv.shutdown()
        if proc:
            proc.terminate()
            proc.wait(timeout=30)
        shutil.rmtree(user_dir, ignore_errors=True)

    if mode != "greenhouse":
        return finish(report, stamp, mode_failures(report, mode))
    g, last = report["guard"], (report["passes"] or [{}])[-1]
    tabs = [t for p in report["passes"] for t in p["tabs"]]
    failures = [report["error"]] if report.get("error") else []
    if report.get("guard_error") or not g.get("installed") or any(not t["guard_verified"] for t in tabs):
        failures.append(f"guard missing: {report.get('guard_error') or [t['guard_error'] for t in tabs]}")
    marks = [m for p in report["passes"] for m in p["marks"]]
    if any(v["value"] for t in tabs for v in t["talent_community"]) or             any("greenhouse.io" not in m["frame"] for m in marks):
        failures.append("the talent-community form got a value or a mark")
    for t in tabs:
        for d in (t["iframe"] or {}).get("demographic_violations", []):
            failures.append(f"demographic field got a value: {d['label'] or d['key']}")
    if not any("greenhouse.io" in m["frame"] and m["mark"].startswith(("Auto-filled", "Resume attached"))
               for m in marks):
        failures.append("nothing filled in the Greenhouse iframe")
    if last.get("status_after") in ("applied", "submitted_unconfirmed") and not g.get("submit_attempts_blocked"):
        failures.append("a submit was reported but the guard saw none")
    return finish(report, stamp, failures)


def finish(report: dict, stamp: str, failures: list[str]) -> dict:
    report["failures"] = failures
    report["passed"] = not failures
    cf.REPORTS.mkdir(exist_ok=True)
    mode = report["target"]
    out = cf.REPORTS / f"{stamp}-auto-apply{'' if mode == 'greenhouse' else '-' + mode}.json"
    out.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"report: {out}")
    return report


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--headed", action="store_true",
                    help="visible window with Chrome's real background-tab timer throttling (the driver's tab is hidden)")
    ap.add_argument("--job", default=DEFAULT_JOB, help="Greenhouse <board>/<job id> to embed")
    target = ap.add_mutually_exclusive_group()
    target.add_argument("--fixture", choices=list(FIXTURE), help="local Workday-like fixture instead of the embed")
    target.add_argument("--url", help="recon: a real job URL as the apply_url (guarded; outcome recorded, not judged)")
    ap.add_argument("--passes", type=int, default=2, help="driver passes; a needs_human pass answers and re-approves")
    ap.add_argument("--ext-dist", type=Path, help=f"built extension to load (default {cf.EXT_DIST})")
    a = ap.parse_args()
    if a.ext_dist:
        cf.EXT_DIST = a.ext_dist.resolve()
    mode = a.fixture or ("url" if a.url else "greenhouse")
    r = asyncio.run(run(a.headed, a.passes, a.job, mode, a.url))
    for p in r["passes"]:
        print(f"pass {p['pass']}: {p['run_queue']} -> {p['status_after']} ({p['seconds']} s)")
        if mode != "greenhouse":
            print(f"  notes: {p['notes']!r}")
            for t in p["tabs"]:
                print("  trail: " + " | ".join(f"{s['step'] or ','.join(s['ids']) or s['href']}" for s in t["trail"]))
    if "server_hits" in r:
        print(f"server POSTs: {r['server_hits']}")
    g = r["guard"]
    print(f"guard: submit attempts blocked={g.get('submit_attempts_blocked')}, "
          f"non-GET blocked={g.get('blocked_non_get_requests')}, canary={g.get('canary_blocked')}")
    print("PASS" if r["passed"] else "FAIL: " + "; ".join(r["failures"]))
    return 0 if r["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
