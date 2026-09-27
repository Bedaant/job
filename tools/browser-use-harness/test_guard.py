"""Offline proof of the no-submit guard.

Run (in this dir):  ..\\.venv-browser-use\\Scripts\\python -m unittest test_guard -v
Only 127.0.0.1 is loaded; the one "remote" request is aborted by the guard before DNS.
"""

import http.server
import threading
import unittest

from playwright.async_api import async_playwright

from guard import GuardMissing, install_guard, verify_guard

PAGE = b"""<!doctype html><title>t</title>
<form id=f method=post action=/apply><input name=email><button id=go type=submit>Submit</button></form>"""


class _Handler(http.server.BaseHTTPRequestHandler):
    posts = 0

    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.end_headers()
        self.wfile.write(PAGE)

    def do_POST(self):
        type(self).posts += 1
        self.send_response(200)
        self.end_headers()

    def log_message(self, *_):
        pass


class GuardTest(unittest.IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()
        cls.url = f"http://127.0.0.1:{cls.server.server_address[1]}/"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()

    async def asyncSetUp(self):
        self.pw = await async_playwright().start()
        self.browser = await self.pw.chromium.launch()
        self.context = await self.browser.new_context()
        self.guard = await install_guard(self.context)
        self.page = await self.context.new_page()
        await self.page.goto(self.url)

    async def asyncTearDown(self):
        await self.browser.close()
        await self.pw.stop()

    async def test_form_submit_and_request_submit_throw(self):
        for method in ("submit", "requestSubmit"):
            msg = await self.page.evaluate(
                f"() => {{ try {{ document.getElementById('f').{method}(); return 'no throw'; }}"
                " catch (e) { return String(e); } }"
            )
            self.assertIn("no-submit guard", msg)
        await self.page.wait_for_timeout(100)
        self.assertEqual(self.guard.submit_attempts_count, 2)
        self.assertEqual(self.page.url, self.url)

    async def test_submit_button_click_is_prevented(self):
        posts = _Handler.posts
        await self.page.click("#go")
        await self.page.wait_for_timeout(300)
        self.assertEqual(self.page.url, self.url)
        self.assertEqual(self.guard.submit_attempts_count, 1)
        self.assertEqual(_Handler.posts, posts)

    async def test_non_get_to_remote_host_is_aborted(self):
        result = await self.page.evaluate(
            "() => fetch('https://employer.example.com/apply', {method: 'POST', body: 'x'})"
            ".then(() => 'sent', e => String(e))"
        )
        self.assertNotEqual(result, "sent")
        self.assertEqual([b["method"] for b in self.guard.blocked_requests], ["POST"])
        self.assertIn("employer.example.com", self.guard.blocked_requests[0]["url"])

    async def test_non_get_to_localhost_passes(self):
        before = _Handler.posts
        status = await self.page.evaluate("() => fetch('/x', {method: 'POST'}).then(r => r.status)")
        self.assertEqual(status, 200)
        self.assertEqual(_Handler.posts, before + 1)
        self.assertEqual(self.guard.blocked_requests, [])

    async def test_verify_guard_passes_on_guarded_page(self):
        await verify_guard(self.page, self.guard)  # init-script flag set + canary POST blocked
        self.assertEqual(self.guard.canary_blocked, 1)

    async def test_canary_survives_strict_csp_on_remote_origin(self):
        # Real ATS pages set CSP connect-src; a canary to a foreign host never reaches the route.
        # Serve a "remote" page (fulfilled by a page-level route, no network) with a strict CSP.
        async def fake_remote(route):
            await route.fulfill(status=200, body=PAGE, headers={
                "Content-Type": "text/html", "Content-Security-Policy": "connect-src 'self'"})

        page = await self.context.new_page()
        await page.route("https://employer.example.com/job", fake_remote)
        await page.goto("https://employer.example.com/job")
        await verify_guard(page, self.guard)
        self.assertEqual(self.guard.canary_blocked, 1)
        self.assertEqual(self.guard.blocked_requests, [])

    async def test_verify_guard_fails_loudly_without_guard(self):
        bare = await self.browser.new_context()
        page = await bare.new_page()
        await page.goto(self.url)
        with self.assertRaises(GuardMissing):
            await verify_guard(page, None)


if __name__ == "__main__":
    unittest.main()
