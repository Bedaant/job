import test from "node:test";
import assert from "node:assert/strict";

import {
  classifyFailure,
  fillsOnPopup,
  planRun,
  MAX_ATTEMPTS_PER_ITEM,
  MIN_APPLICATION_FIELDS,
  holdsApplicationForm,
  countFields,
  chooseFrame,
  answerForFrame,
  isFromAssignedFrame,
  ITEM_TIMEOUT_MS,
} from "./driverCore.mjs";

// Found live (auto-apply, embedded Greenhouse): page load (~8 s) + reading 12
// dropdowns (twice, when the embed hydrates mid-read) + /map-fields (22-51 s live,
// LLM) ran past the old 60 s, so a fill still in progress was reported `failed`.
test("ITEM_TIMEOUT_MS leaves a slow /map-fields call room to finish", () => {
  assert.ok(ITEM_TIMEOUT_MS >= 8_000 + 20_000 + 2 * 51_000, `${ITEM_TIMEOUT_MS} ms is too short`);
});

// --- classifyFailure ----------------------------------------------------------
// The distinction that matters: `failed` puts the application back in the work
// queue to be retried, `needs_human` hands it to the review queue. Retrying a
// captcha forever is the bug this classification exists to prevent.

test("a captcha is needs_human, never a retry", () => {
  const { outcome, reason } = classifyFailure(new Error("reCAPTCHA challenge detected on page"));
  assert.equal(outcome, "needs_human");
  assert.match(reason, /captcha/i);
});

test("an account wall is needs_human", () => {
  for (const message of [
    "Please sign in to continue your application",
    "Create an account to apply",
    "You must be logged in to apply",
  ]) {
    assert.equal(classifyFailure(new Error(message)).outcome, "needs_human", message);
  }
});

test("a free-text essay question is needs_human", () => {
  // ADR-006/009: an unanswerable essay field must not be guessed at, and
  // map-fields already refuses to fill these.
  const { outcome } = classifyFailure(new Error("unfilled required field: why do you want to work here?"));
  assert.equal(outcome, "needs_human");
});

test("a file upload we cannot satisfy is needs_human", () => {
  assert.equal(classifyFailure(new Error("required file input could not be filled")).outcome, "needs_human");
});

test("a transient network error is failed, so it is retried", () => {
  const { outcome } = classifyFailure(new Error("Failed to fetch"));
  assert.equal(outcome, "failed");
});

test("no form on the page is failed", () => {
  assert.equal(classifyFailure(new Error("no form found on page")).outcome, "failed");
});

test("a refused claim is failed, not needs_human", () => {
  // The backend refusing the claim means another driver owns it or it is not
  // approved — a human cannot help with that, so it must not clutter the queue.
  const { outcome } = classifyFailure(new Error("backend refused the submission claim (409)"));
  assert.equal(outcome, "failed");
});

test("an unknown error is failed and carries its message as the reason", () => {
  const { outcome, reason } = classifyFailure(new Error("something nobody predicted"));
  assert.equal(outcome, "failed");
  assert.match(reason, /something nobody predicted/);
});

test("a non-Error rejection still classifies rather than throwing", () => {
  const { outcome, reason } = classifyFailure("bare string failure");
  assert.equal(outcome, "failed");
  assert.match(reason, /bare string failure/);
});

test("the reason is always a bounded string", () => {
  const { reason } = classifyFailure(new Error("x".repeat(5000)));
  assert.ok(reason.length <= 2000, "the backend caps reason at 2000 chars");
});

// --- planRun ------------------------------------------------------------------

test("planRun runs each queue item once, in order", () => {
  const queue = [
    { application_id: "a", apply_url: "https://x/a" },
    { application_id: "b", apply_url: "https://x/b" },
    { application_id: "c", apply_url: "https://x/c" },
  ];
  assert.deepEqual(planRun(queue, new Map()).map((i) => i.application_id), ["a", "b", "c"]);
});

test("planRun drops an item that has already burned its attempts", () => {
  // Without this, a job whose form never works is retried every single pass and
  // consumes the whole run, so nothing else is ever attempted.
  const queue = [
    { application_id: "a", apply_url: "https://x/a" },
    { application_id: "b", apply_url: "https://x/b" },
  ];
  const attempts = new Map([["a", MAX_ATTEMPTS_PER_ITEM]]);
  assert.deepEqual(planRun(queue, attempts).map((i) => i.application_id), ["b"]);
});

test("planRun keeps an item that still has attempts left", () => {
  const queue = [{ application_id: "a", apply_url: "https://x/a" }];
  const attempts = new Map([["a", MAX_ATTEMPTS_PER_ITEM - 1]]);
  assert.equal(planRun(queue, attempts).length, 1);
});

test("planRun skips items with no apply_url even if the server sent one", () => {
  // The server filters these out, but a driver that trusts its input blindly is
  // one API change away from opening about:blank and reporting a failure.
  const queue = [
    { application_id: "a", apply_url: "" },
    { application_id: "b", apply_url: "https://x" },
  ];
  assert.deepEqual(planRun(queue, new Map()).map((i) => i.application_id), ["b"]);
});

test("planRun tolerates an empty queue", () => {
  assert.deepEqual(planRun([], new Map()), []);
});

// --- frames (latest+48) -------------------------------------------------------
// With all_frames, every frame of the apply tab (captcha widgets included) runs the
// content script. Only the frame holding the application form may fill, submit or
// report; the rest must stay silent, or a captcha frame's "no form" wins the race.

test("captcha and search frames don't hold an application form; a real form does", () => {
  // reCAPTCHA anchor frame: hidden inputs + one response textarea
  assert.equal(holdsApplicationForm(["hidden", "hidden", "textarea"]), false);
  // careers-page search + newsletter
  assert.equal(holdsApplicationForm(["search", "email", "submit", "button"]), false);
  assert.equal(holdsApplicationForm(["text", "text", "email", "tel", "file", "select", "textarea", "submit"]), true);
  assert.equal(MIN_APPLICATION_FIELDS, 4);
  assert.equal(holdsApplicationForm(["text", "email", "tel", "hidden", "submit", "reset", "image"]), false);
  assert.equal(holdsApplicationForm([]), false);
  assert.equal(countFields(["text", "hidden", "SELECT", "textarea", "submit"]), 3);
});

test("chooseFrame picks the frame with the most fields; ties go to the lower frameId", () => {
  assert.equal(chooseFrame([{ frameId: 0, fieldCount: 5 }, { frameId: 7, fieldCount: 22 }]), 7);
  assert.equal(chooseFrame([{ frameId: 9, fieldCount: 22 }, { frameId: 0, fieldCount: 22 }]), 0);
  assert.equal(chooseFrame([{ frameId: 3, fieldCount: 8 }]), 3);
  assert.equal(chooseFrame([]), undefined);
});

const ITEM = { application_id: "a1", profile_id: "p1", apply_url: "https://x", company: "C", title: "T" };

test("before a frame is chosen every frame learns the item; after, only the chosen one", () => {
  assert.equal(answerForFrame(undefined, 0), null);
  assert.deepEqual(answerForFrame({ item: ITEM }, 5), ITEM);
  assert.deepEqual(answerForFrame({ item: ITEM, frameId: 5 }, 5), ITEM);
  assert.equal(answerForFrame({ item: ITEM, frameId: 5 }, 0), null);
});

test("after the submit only the submitting frame verifies (the page it navigated to)", () => {
  const verify = { urlBefore: "https://x/form", sentAt: 1 };
  assert.deepEqual(answerForFrame({ item: ITEM, frameId: 5, verify }, 5), { ...ITEM, verify });
  assert.equal(answerForFrame({ item: ITEM, frameId: 5, verify }, 0), null, "top frame must not verify an iframe's submit");
  assert.equal(answerForFrame({ item: ITEM, frameId: 5, verify }, 6), null);
});

test("reports and submit-sent are accepted only from the chosen frame", () => {
  assert.equal(isFromAssignedFrame({ item: ITEM, frameId: 5 }, 5), true);
  assert.equal(isFromAssignedFrame({ item: ITEM, frameId: 5 }, 0), false, "a captcha/top frame's report is ignored");
  assert.equal(isFromAssignedFrame({ item: ITEM }, 0), false, "no frame chosen yet: nobody may report");
  assert.equal(isFromAssignedFrame(undefined, 0), false);
  assert.equal(isFromAssignedFrame({ item: ITEM, frameId: 5 }, undefined), false);
});

// Found live (harness, careers page embedding boards.greenhouse.io): the top frame
// answered the popup first and filled the page's one-field "talent community" box.
test("fillsOnPopup: only a frame with the application form fills; a formless top page with iframes stays out", () => {
  const form = ["text", "text", "email", "tel", "file", "textarea"];
  const tiny = ["email", "button"];
  assert.equal(fillsOnPopup({ isTop: false, controlTypes: form, hasIframes: false }), true);
  assert.equal(fillsOnPopup({ isTop: false, controlTypes: ["hidden", "textarea"], hasIframes: false }), false);
  assert.equal(fillsOnPopup({ isTop: true, controlTypes: tiny, hasIframes: true }), false);
  assert.equal(fillsOnPopup({ isTop: true, controlTypes: form, hasIframes: true }), true);
  assert.equal(fillsOnPopup({ isTop: true, controlTypes: tiny, hasIframes: false }), true); // plain page: as before
});
