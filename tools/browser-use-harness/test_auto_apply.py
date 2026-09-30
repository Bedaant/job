"""Offline checks for auto_apply.py: the per-mode verdict (mode_failures), the fixture server's POST
counts, and the Workday-like fixtures under the guard in Chromium (127.0.0.1 only).

Run (in this dir):  ..\\.venv-browser-use\\Scripts\\python -m unittest test_auto_apply -v
"""

import unittest
import urllib.request

from playwright.async_api import async_playwright

import auto_apply as aa
from guard import install_guard, verify_guard

TRAIL_REVIEW = [{"href": "http://127.0.0.1/careers", "ids": ["progressBarActiveStep"],
                 "step": "current step 4 of 4 Review", "next": "Submit"}]


def report(status="ready_for_review", notes="Needs you: Sign in or create an account", hits=None,
           trail=None, **tab):
    t = {"guard_verified": True, "passwords_filled": [], "demographic_violations": [], "trail": trail or []}
    t.update(tab)
    return {"guard": {"installed": True}, "server_hits": hits if hits is not None else {"/save": 3},
            "passes": [{"status_after": status, "notes": notes, "marks": [], "tabs": [t]}]}


class ModeFailuresTest(unittest.TestCase):
    def test_passing_reports(self):
        self.assertEqual(aa.mode_failures(report(), "wall"), [])
        self.assertEqual(aa.mode_failures(report(notes="x"), "workday"), [])
        self.assertEqual(aa.mode_failures(report(notes="x", trail=TRAIL_REVIEW), "workday-noconsent"), [])
        self.assertEqual(aa.mode_failures(report(status="failed", notes="x", hits={}), "url"), [])
        # only the button text shows Review was reached
        trail = [{"href": "", "ids": [], "step": "", "next": "Submit"}]
        self.assertEqual(aa.mode_failures(report(notes="x", trail=trail), "workday-noconsent"), [])

    def test_all_mode_checks(self):
        bad = {
            "guard not installed": {**report(), "guard": {"installed": False}},
            "guard error": {**report(), "guard_error": "flag missing"},
            "tab unverified": report(guard_verified=False),
            "no tab": {**report(), "passes": [{**report()["passes"][0], "tabs": []}]},
            "password": report(passwords_filled=["Password"]),
            "account": report(hits={"/save": 3, "/account": 1}),
            "submitted": report(hits={"/save": 3, "/submitted": 1}),
            "demographic": report(demographic_violations=["Gender"]),
            "error": {**report(), "error": "RuntimeError: boom"},
        }
        for mode in ("wall", "workday", "workday-noconsent", "url"):
            for name, r in bad.items():
                if mode == "workday-noconsent":
                    r["passes"][0]["tabs"] = [{**t, "trail": TRAIL_REVIEW} for t in r["passes"][0]["tabs"]]
                with self.subTest(mode=mode, case=name):
                    self.assertTrue(aa.mode_failures(r, mode))

    def test_password_mark_counts(self):
        r = report()
        r["passes"][0]["marks"] = [{"label": "Password", "type": "password", "value": "hunter2", "mark": "x"}]
        self.assertTrue(aa.mode_failures(r, "url"))

    def test_wall(self):
        self.assertTrue(aa.mode_failures(report(status="failed"), "wall"))
        self.assertTrue(aa.mode_failures(report(notes="Needs you: consent"), "wall"))
        # the LAST notes line is what counts
        self.assertTrue(aa.mode_failures(report(notes="sign in\nstopped: timeout"), "wall"))
        self.assertTrue(aa.mode_failures(report(notes=None), "wall"))
        self.assertEqual(aa.mode_failures(report(notes="old\nPlease SIGN IN first"), "wall"), [])

    def test_workday(self):
        for mode in ("workday", "workday-noconsent"):
            with self.subTest(mode=mode):
                self.assertTrue(aa.mode_failures(report(hits={"/save": 1}, trail=TRAIL_REVIEW), mode))
                self.assertTrue(aa.mode_failures(report(hits={}, trail=TRAIL_REVIEW), mode))
                self.assertTrue(aa.mode_failures(report(status="failed", trail=TRAIL_REVIEW), mode))

    def test_noconsent_needs_review(self):
        trail = [{"href": "", "ids": ["progressBarActiveStep"], "step": "current step 3 of 4 Application Questions",
                  "next": "Save and Continue"}]
        self.assertTrue(aa.mode_failures(report(trail=trail), "workday-noconsent"))
        self.assertTrue(aa.mode_failures(report(), "workday-noconsent"))
        self.assertEqual(aa.mode_failures(report(trail=trail), "workday"), [])

    def test_url_does_not_judge_outcome(self):
        self.assertEqual(aa.mode_failures(report(status="needs_human", notes="", hits={}), "url"), [])


class ServerTest(unittest.TestCase):
    def test_counts_posts_and_serves_body(self):
        srv, url = aa.serve_host_page("<p>fixture</p>")
        try:
            self.assertTrue(url.endswith("/careers"))
            with urllib.request.urlopen(url + "?consent=0") as r:
                self.assertEqual(r.read(), b"<p>fixture</p>")
            for path in ("/save", "/save", "/account"):
                req = urllib.request.Request(url.replace("/careers", path), data=b"x", method="POST")
                with urllib.request.urlopen(req) as r:
                    self.assertEqual(r.status, 204)
            self.assertEqual(dict(srv.hits), {"/save": 2, "/account": 1})
        finally:
            srv.shutdown()
            srv.server_close()

    def test_fixtures_carry_workday_ids(self):
        wd = (aa.FIXTURES / "workday_like.html").read_text(encoding="utf-8")
        for i in ("adventureButton", "applyManually", "progressBarActiveStep", "bottom-navigation-next-button",
                  "errorMessage", "agreementCheckbox", "file-upload-input-ref", "legalNameSection_firstName",
                  '"email"'):
            with self.subTest(id=i):
                self.assertIn(i, wd)
        self.assertNotIn("<form", wd)
        wall = (aa.FIXTURES / "account_wall.html").read_text(encoding="utf-8")
        for i in ("signInContent", "verifyPassword", "createAccountCheckbox", "createAccountSubmitButton", "/account"):
            with self.subTest(id=i):
                self.assertIn(i, wall)


class FixtureBrowserTest(unittest.IsolatedAsyncioTestCase):
    """The fixtures behave like Workday under the guard: entry dialog, required-field errors, a
    /save per step, Review last; the wall asks for a password."""

    async def asyncSetUp(self):
        self.pw = await async_playwright().start()
        self.browser = await self.pw.chromium.launch()
        self.context = await self.browser.new_context()
        self.guard = await install_guard(self.context)
        self.page = await self.context.new_page()

    async def asyncTearDown(self):
        await self.browser.close()
        await self.pw.stop()

    async def open(self, name: str, query: str = ""):
        srv, url = aa.serve_host_page((aa.FIXTURES / name).read_text(encoding="utf-8"))
        self.addCleanup(srv.server_close)
        self.addCleanup(srv.shutdown)  # LIFO: shutdown first
        await self.page.goto(url + query)
        await verify_guard(self.page, self.guard)
        self.assertEqual(self.guard.canary_blocked, 1)
        await self.page.click("[data-automation-id=adventureButton]")
        await self.page.click("[data-automation-id=applyManually]")
        return srv

    async def step(self) -> str:
        return await self.page.inner_text("[data-automation-id=progressBarActiveStep]")

    async def next(self, srv, saves: int):
        await self.page.click("[data-automation-id=bottom-navigation-next-button]")
        await self.page.wait_for_function(f"() => !document.querySelector('[data-automation-id=loadingSpinner]')")
        self.assertEqual(srv.hits["/save"], saves)

    async def test_workday_steps(self):
        srv = await self.open("workday_like.html")
        self.assertIn("My Information", await self.step())
        await self.next(srv, 0)  # empty required fields: error, stays
        self.assertTrue(await self.page.locator("[data-automation-id=errorMessage][role=alert]").count())
        self.assertEqual(await self.page.get_attribute("#firstName", "aria-invalid"), "true")
        for sel, v in (("#firstName", "Morgan"), ("#lastName", "Ellery"), ("#email", "m@example.com"),
                       ("#phone", "4158672931"), ("#city", "San Francisco")):
            await self.page.fill(sel, v)
        self.assertEqual(await self.page.inner_text("label[for=firstName]"), "First Name *")
        await self.next(srv, 1)
        self.assertIn("My Experience", await self.step())
        await self.next(srv, 2)
        self.assertIn("Application Questions", await self.step())
        await self.page.check("#authorizedYes")
        await self.page.fill("#hear", "Company website")
        await self.next(srv, 3)
        self.assertIn("Voluntary Disclosures", await self.step())
        await self.next(srv, 3)  # consent required
        await self.page.check("[data-automation-id=agreementCheckbox]")
        await self.next(srv, 4)
        self.assertIn("Review", await self.step())
        self.assertEqual(await self.page.inner_text("[data-automation-id=bottom-navigation-next-button]"), "Submit")
        self.assertEqual(await self.page.locator("input, select, textarea").count(), 0)
        self.assertNotIn("/submitted", srv.hits)

    async def test_noconsent_skips_disclosures(self):
        srv = await self.open("workday_like.html", "?consent=0")
        self.assertIn("of 4", await self.step())
        for sel, v in (("#firstName", "Morgan"), ("#lastName", "Ellery"), ("#email", "m@example.com"),
                       ("#phone", "4158672931"), ("#city", "San Francisco")):
            await self.page.fill(sel, v)
        await self.next(srv, 1)
        await self.next(srv, 2)
        await self.page.check("#authorizedNo")
        await self.page.fill("#hear", "Company website")
        await self.next(srv, 3)
        self.assertIn("Review", await self.step())

    async def test_account_wall(self):
        srv = await self.open("account_wall.html")
        self.assertEqual(await self.page.locator("[data-automation-id=signInContent] input[type=password]").count(), 2)
        self.assertEqual(await self.page.locator("[data-automation-id=bottom-navigation-next-button]").count(), 0)
        self.assertEqual(dict(srv.hits), {})


if __name__ == "__main__":
    unittest.main()
