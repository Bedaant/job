// ADR-015 Phase 1 — the driver's decisions, kept pure and away from the chrome
// APIs so they are testable without a loaded extension (there is no
// browser-automation access in this project; driver.ts's glue is verified by
// reading, this file is verified by driverCore.test.mjs).
//
// .mjs, matching fieldDecision.mjs: plain Node-testable modules for logic that
// must not depend on a bundler or a DOM.

// One application gets this many attempts across driver passes before the driver
// stops picking it up. Without a ceiling, a job whose form never works is
// retried on every pass and starves everything behind it — and because a
// `failed` outcome deliberately returns the row to `approved` (it is genuinely
// retryable), the server-side queue alone cannot express "stop trying this one".
// ponytail: in-memory per-session count; if it needs to survive a service-worker
// restart, move it to chrome.storage.local keyed by application_id.
export const MAX_ATTEMPTS_PER_ITEM = 3;

const REASON_MAX = 2000; // schemas.SubmissionResultIn caps `reason` at 2000

// Failures a human can actually resolve. Everything else is transient or ours to
// fix, so it stays retryable. Ordered by how unambiguous the signal is.
const NEEDS_HUMAN_PATTERNS = [
  /captcha/i,
  /recaptcha/i,
  /hcaptcha/i,
  /cloudflare.{0,20}challenge/i,
  // Account walls: Workday and friends require an account per employer, which no
  // amount of form-filling solves.
  /\bsign ?in\b/i,
  /\blog ?in\b/i,
  /\blogged in\b/i,
  /create an account/i,
  /register.{0,20}to apply/i,
  // Questions we must never invent an answer to (ADR-006/009). map-fields
  // already refuses these; reaching here means the form cannot be completed
  // without the user.
  /why do you want to work/i,
  /why are you interested/i,
  /cover letter.{0,30}required/i,
  /\bessay\b/i,
  // A file input we could not satisfy.
  /file input/i,
  /upload.{0,20}(required|failed)/i,
];

function messageOf(error) {
  if (error instanceof Error) return error.message || String(error);
  if (typeof error === "string") return error;
  try {
    return JSON.stringify(error);
  } catch {
    return String(error);
  }
}

/**
 * Decide how to report a failed attempt.
 *
 * `failed`      -> the backend returns the application to `approved`; it is work
 *                  again. Correct only when the form genuinely never went through.
 * `needs_human` -> the backend moves it to `ready_for_review`, where the user
 *                  sees it in the existing review queue.
 *
 * Defaulting to `failed` is the safe direction: a retry costs a page load,
 * whereas wrongly parking something as needs_human silently stops applying to it.
 */
export function classifyFailure(error) {
  const message = messageOf(error);
  const reason = message.slice(0, REASON_MAX);
  const outcome = NEEDS_HUMAN_PATTERNS.some((p) => p.test(message)) ? "needs_human" : "failed";
  return { outcome, reason };
}

/**
 * Which queue items this pass should attempt, in order.
 * `attempts` is a Map<application_id, count> carried across passes.
 */
export function planRun(queue, attempts) {
  return queue.filter(
    (item) =>
      Boolean(item.apply_url) && (attempts.get(item.application_id) ?? 0) < MAX_ATTEMPTS_PER_ITEM,
  );
}
