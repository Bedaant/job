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

// --- frames (latest+48) -------------------------------------------------------
// The content scripts run in every frame (all_frames), so embedded boards
// (boards.greenhouse.io/embed, job-boards.greenhouse.io/embed/...) are reached. The
// catch: captcha and ad frames run it too. So a frame only claims the tab if it
// holds an application form, the driver gives the tab to ONE claiming frame (the
// most fields), and only that frame is answered, acked or listened to.
//
// An assignment is { item, frameId?, verify? }: frameId once a frame is chosen,
// verify once that frame said the submit is being sent.

// A real application form has name, email, phone, resume at the least. A
// reCAPTCHA/hCaptcha frame has a hidden response textarea and hidden inputs.
export const MIN_APPLICATION_FIELDS = 4;
const NOT_A_FIELD = new Set(["hidden", "submit", "button", "reset", "image"]);

/** controlTypes: input `type`s, or "select"/"textarea", of every control in the frame. */
export function countFields(controlTypes) {
  return controlTypes.filter((t) => !NOT_A_FIELD.has(String(t).toLowerCase())).length;
}

export function holdsApplicationForm(controlTypes) {
  return countFields(controlTypes) >= MIN_APPLICATION_FIELDS;
}

/** claims: [{frameId, fieldCount}] -> the frameId with the most fields (ties: lower id; the top frame is 0). */
export function chooseFrame(claims) {
  let best;
  for (const c of claims) {
    if (!best || c.fieldCount > best.fieldCount || (c.fieldCount === best.fieldCount && c.frameId < best.frameId)) {
      best = c;
    }
  }
  return best?.frameId;
}

/** What `jc:what-am-i-doing` answers a frame. null = stay silent. */
export function answerForFrame(assignment, frameId) {
  if (!assignment) return null;
  if (assignment.frameId !== undefined && assignment.frameId !== frameId) return null;
  // Verify lives only in the submitting frame: an iframe's form navigates the iframe,
  // which keeps its frameId. If the top frame navigated instead, nothing verifies
  // and the driver's timer reports `unconfirmed` — the safe direction.
  return assignment.verify ? { ...assignment.item, verify: assignment.verify } : assignment.item;
}

/** Whether a report / submit-sent from this frame counts. */
export function isFromAssignedFrame(assignment, frameId) {
  return assignment?.frameId !== undefined && assignment.frameId === frameId;
}
