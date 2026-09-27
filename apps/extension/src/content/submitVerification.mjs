// Did the employer's ATS actually accept the application? Decided from what the
// page shows after the native submit fired — never assumed from having fired it.
//
// Pure (no DOM, no chrome): autoApply.content.ts gathers the observations, this
// decides. Same split as fieldDecision.mjs / driverCore.mjs, tested with node:test.
//
// Verdicts:
//   confirmed   -> report `submitted` (the only path to `applied`)
//   rejected    -> report `needs_human` (validation errors, required field, captcha)
//   unconfirmed -> report `unconfirmed` (no signal either way within the bound)
//   pending     -> keep watching

// How long after the submit we keep looking. A real ATS answers in a few seconds;
// the driver's own verify timer is this plus slack, so the page decides first.
export const VERIFY_TIMEOUT_MS = 20_000;
// Errors on a still-present form are only judged after this: a classic POST can
// take a moment to navigate away, and the old page is still visible meanwhile.
export const SETTLE_MS = 1_500;

const REASON_MAX = 2000; // schemas.SubmissionResultIn caps `reason` at 2000

// Generic wording plus what was verified on real pages (2026-09-27):
//   Lever:      jobs.lever.co/<co>/<id>/thanks, "Application submitted!" (fetched live)
//   Greenhouse: client route /:token/jobs/:id/confirmation (page source,
//               docs/LIVE-FORM-TEST.md); titled "Thank you for applying ..."
//   Ashby:      "Your application was successfully submitted." (page source,
//               LIVE-FORM-TEST.md; companies can customise it, so generic too)
const CONFIRMATION_TEXT = [
  /thanks? (you )?for (applying|your application|submitting)/i,
  /application (has been |was )?(successfully )?(submitted|received)/i,
  /we('ve| have) (successfully )?received your application/i,
];

// Path segments that mean "done", only trusted when the URL actually changed.
const CONFIRMATION_PATH = /\/(thanks|thank-you|thankyou|confirmation|application-submitted|submitted|success)(?=[/?#]|$)/i;

const REQUIRED_TEXT = /\brequired\b|can(no|')t be (blank|empty)|is mandatory|please (fill|complete|enter|select|provide)/i;

// Challenge frames only. reCAPTCHA's `anchor` and hCaptcha's `frame=checkbox`
// are the always-present badge/checkbox, not a challenge.
const CAPTCHA_CHALLENGE_SRC = [
  /recaptcha\/(api2|enterprise)\/bframe/i,
  /hcaptcha\.com\/.*frame=challenge/i,
  /challenges\.cloudflare\.com\//i,
];

export function isCaptchaChallengeSrc(src) {
  return Boolean(src) && CAPTCHA_CHALLENGE_SRC.some((p) => p.test(src));
}

function pathOf(url) {
  try {
    return new URL(url).pathname;
  } catch {
    return url || "";
  }
}

/**
 * obs: { urlBefore, urlAfter, pageText, formStillPresent, visibleErrorTexts,
 *        captchaVisible, elapsedMs }
 * returns { verdict, code?, reason }
 */
export function decideVerification(obs) {
  const urlChanged = Boolean(obs.urlAfter) && obs.urlAfter !== obs.urlBefore;
  const text = obs.pageText || "";
  const errors = (obs.visibleErrorTexts || []).map((t) => t.trim()).filter(Boolean);

  // Confirmation text only counts once the page moved on (new URL, or the form is
  // gone): a careers page can say "thank you for applying" above the form itself.
  const movedOn = urlChanged || !obs.formStillPresent;
  if (urlChanged && CONFIRMATION_PATH.test(pathOf(obs.urlAfter))) {
    return { verdict: "confirmed", reason: `Confirmation page: ${obs.urlAfter}` };
  }
  if (movedOn && CONFIRMATION_TEXT.some((p) => p.test(text))) {
    return { verdict: "confirmed", reason: "The employer's page confirmed the application." };
  }

  if (obs.captchaVisible) {
    return {
      verdict: "rejected",
      code: "captcha",
      reason: "A captcha appeared after submit, so the application did not go through.",
    };
  }

  if (obs.formStillPresent && errors.length > 0 && obs.elapsedMs >= SETTLE_MS) {
    const required = errors.some((t) => REQUIRED_TEXT.test(t));
    return {
      verdict: "rejected",
      code: required ? "required_field" : "validation_errors",
      reason:
        (required
          ? "The employer's form flagged a required field: "
          : "The employer's form showed errors: ") + errors.join("; "),
    };
  }

  if (obs.elapsedMs >= VERIFY_TIMEOUT_MS) {
    const seconds = Math.round(VERIFY_TIMEOUT_MS / 1000);
    return {
      verdict: "unconfirmed",
      reason: obs.formStillPresent
        ? `The form was sent but the page didn't change within ${seconds} seconds.`
        : `The form was sent but no confirmation appeared within ${seconds} seconds.`,
    };
  }

  return { verdict: "pending", reason: "" };
}

/** Verdict -> what the driver reports to POST /applications/{id}/submission-result. */
export function verificationReport(result) {
  const outcome = { confirmed: "submitted", rejected: "needs_human", unconfirmed: "unconfirmed" }[result.verdict];
  if (!outcome) throw new Error(`no report for verdict ${result.verdict}`);
  return { outcome, reason: (result.reason || "").slice(0, REASON_MAX) };
}
