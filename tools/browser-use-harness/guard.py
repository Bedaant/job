"""No-submit guard: installed on a Playwright BrowserContext BEFORE any navigation.

Layer 1 (network): every request that is not GET/HEAD/OPTIONS is aborted unless its host is
localhost/127.0.0.1. A native form POST, a fetch/XHR submit, a sendBeacon and an employer S3
resume upload all die here. WebSockets to non-local hosts are closed. One exception, so Ashby's
form can render: a POST to https://jobs.ashbyhq.com/api/non-user-graphql whose JSON body is a
GraphQL query with no mutation/subscription anywhere (is_readonly_ashby_query).
Layer 2 (DOM): an init script in every frame makes HTMLFormElement.prototype.submit /
requestSubmit throw and cancels every `submit` event in the capture phase.
Every hit is recorded on the Guard; verify_guard() proves both layers are live on a page.
"""

import json
import re
from dataclasses import dataclass, field
from urllib.parse import urlsplit

SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}
LOCAL_HOSTS = {"localhost", "127.0.0.1", "[::1]", "::1"}
CANARY_PATH = "/__applyscout_guard_canary__"
CANARY_URL = "https://applyscout-guard-canary.invalid" + CANARY_PATH  # .invalid never resolves (RFC 2606)
FLAG = "__applyscoutNoSubmitGuard"
BINDING = "__applyscoutGuardHit"

INIT_SCRIPT = """(() => {
  if (window.%(flag)s) return;
  const report = (kind, detail) => { try { window.%(binding)s(kind, String(detail || '')); } catch (_) {} };
  const describe = (f) => (f && (f.action || f.id || f.name)) || location.href;
  for (const m of ['submit', 'requestSubmit']) {
    HTMLFormElement.prototype[m] = function () {
      report('form.' + m, describe(this));
      throw new Error('ApplyScout harness no-submit guard: form.' + m + '() blocked');
    };
  }
  window.addEventListener('submit', (e) => {
    e.preventDefault();
    e.stopImmediatePropagation();
    report('submit-event', describe(e.target));
  }, true);
  Object.defineProperty(window, '%(flag)s', { value: true, writable: false, configurable: false });
})();""" % {"flag": FLAG, "binding": BINDING}


class GuardMissing(RuntimeError):
    """The no-submit guard is not active on a page. Never continue past this."""


def _is_local(url: str) -> bool:
    return (urlsplit(url).hostname or "") in LOCAL_HOSTS


ASHBY_GRAPHQL = ("https", "jobs.ashbyhq.com", "/api/non-user-graphql")
_GQL_NOISE = re.compile(r'"""[\s\S]*?"""|"(?:\\.|[^"\\])*"|#[^\n]*')  # block strings, strings, comments


def is_readonly_ashby_query(method: str, url: str, body: str | None) -> bool:
    """The ONE remote non-GET the guard lets through: Ashby's form page loads its job posting with a
    GraphQL POST. Allowed only for that exact https host+path, a JSON object body, and a document
    whose every top-level definition is a `query` (or anonymous `{`) or a fragment, with at least one
    operation. The words mutation/subscription anywhere (case-insensitive, even in strings) refuse it:
    Ashby's submit and resume upload are mutations to this same URL."""
    u = urlsplit(url)
    if method.upper() != "POST" or (u.scheme, u.netloc, u.path) != ASHBY_GRAPHQL:
        return False
    try:
        doc = json.loads(body or "")
    except ValueError:
        return False
    query = doc.get("query") if isinstance(doc, dict) else None
    if not isinstance(query, str) or re.search(r"mutation|subscription", json.dumps(doc), re.I):
        return False
    depth, ops, text = 0, 0, _GQL_NOISE.sub(" ", query)
    for m in re.finditer(r"[{}]|[A-Za-z_]\w*", text):
        tok = m.group()
        if depth == 0 and tok not in "{}":
            if tok == "query":
                ops += 1
            elif tok != "fragment":
                return False
            depth = -1  # skip this definition's header (name, variables, `on T`) up to its `{`
        elif tok == "{":
            if depth <= 0:
                ops += depth == 0  # anonymous `{ ... }` query
                depth = 1
            else:
                depth += 1
        elif tok == "}":
            if depth <= 0:
                return False
            depth -= 1
    return depth == 0 and ops > 0


@dataclass
class Guard:
    blocked_requests: list = field(default_factory=list)
    blocked_websockets: list = field(default_factory=list)
    submit_attempts: list = field(default_factory=list)
    canary_blocked: int = 0
    allowed_readonly_queries: list = field(default_factory=list)

    @property
    def submit_attempts_count(self) -> int:
        return len(self.submit_attempts)

    def summary(self) -> dict:
        return {
            "installed": True,
            "blocked_non_get_requests": len(self.blocked_requests),
            "blocked_websockets": len(self.blocked_websockets),
            "submit_attempts_blocked": self.submit_attempts_count,
            "canary_blocked": self.canary_blocked,
            "allowed_readonly_graphql_queries": len(self.allowed_readonly_queries),
            "blocked_request_samples": self.blocked_requests[:50],
            "submit_attempt_details": self.submit_attempts,
        }


async def install_guard(context) -> Guard:
    guard = Guard()

    async def on_request(route):
        req = route.request
        if req.method.upper() in SAFE_METHODS or _is_local(req.url):
            await route.continue_()
            return
        buf = req.post_data_buffer
        body = buf.decode("utf-8", "replace") if buf else None
        if is_readonly_ashby_query(req.method, req.url, body):
            guard.allowed_readonly_queries.append(req.url[:300])
            await route.continue_(post_data=buf)  # the exact bytes that were checked
            return
        if urlsplit(req.url).path == CANARY_PATH:
            guard.canary_blocked += 1
        else:
            guard.blocked_requests.append({"method": req.method, "url": req.url[:300]})
        await route.abort("blockedbyclient")

    async def on_websocket(ws):
        guard.blocked_websockets.append(ws.url[:300])
        await ws.close(code=1008, reason="ApplyScout harness: remote websockets blocked")

    def on_hit(_source, kind, detail):
        guard.submit_attempts.append({"kind": kind, "detail": detail[:300]})

    await context.route(re.compile(r".*"), on_request)
    await context.route_web_socket(lambda url: not _is_local(url), on_websocket)
    await context.expose_binding(BINDING, on_hit)
    await context.add_init_script(INIT_SCRIPT)
    return guard


async def verify_guard(page, guard: Guard | None) -> None:
    """Raise GuardMissing unless the DOM layer is on this page AND a canary POST is aborted."""
    if not await page.evaluate(f"() => window.{FLAG} === true"):
        raise GuardMissing(f"init-script flag missing on {page.url}")
    if guard is None:
        raise GuardMissing("no Guard object: install_guard() was never called on this context")
    # Remote pages: same-origin path, because real ATS pages set CSP connect-src and a foreign
    # canary would die in CSP before the route ever saw it. Local pages: the .invalid host (a
    # local POST is allowed through by design). Either way the route aborts it; if the guard
    # were gone, the worst case is one POST to a 404 path.
    canary = CANARY_URL if _is_local(page.url) else CANARY_PATH
    before = guard.canary_blocked
    await page.evaluate(
        "(u) => fetch(u, {method: 'POST', body: 'canary', mode: 'no-cors'}).catch(() => null)", canary
    )
    if guard.canary_blocked != before + 1:
        raise GuardMissing(f"canary POST was not intercepted on {page.url}")
