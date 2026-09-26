import test from "node:test";
import assert from "node:assert/strict";

import { classifyFailure, planRun, MAX_ATTEMPTS_PER_ITEM } from "./driverCore.mjs";

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
