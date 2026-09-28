// ADR-015 Phase 1 — the page half of the driver. Runs on every page, but does
// nothing at all unless the background driver says this tab was opened to submit
// a specific application.
//
// The order here is the whole point:
//   1. ask the driver what this tab is for (never infer it from location.href —
//      a redirect or a stale tab would otherwise make us submit the wrong job)
//   2. fill the form from the profile
//   3. if anything was flagged as needing the user, STOP and report needs_human
//   4. only then submit, through submitApprovedApplication, which claims
//      server-side first and is the single audited native-submit call site
//   5. VERIFY before reporting: `submitted` only when the employer's page confirms
//      it (submitVerification.mjs decides; this file only observes)
//
// Step 5 across a navigation: most ATS forms POST and load a new page, which
// kills this script and injects a fresh one. So right before the native submit,
// we tell the driver `jc:submit-sent` and wait for its ack; the driver marks the
// tab's assignment as verifying ({urlBefore, sentAt}). The fresh script's
// `jc:what-am-i-doing` then returns that `verify` block, and it only watches —
// never fills or submits again. The state lives in the driver's in-memory
// assignment, not chrome.storage.session: it is only useful while the driver's
// runItem loop is alive to receive the report, and that loop is in-memory too.
// Whichever script decides first reports; the driver takes the first report.
//
// Step 3 is not politeness: a blocking flag is a field nobody may or can answer
// for the user (a REQUIRED demographic question, or an essay). An optional
// demographic question is left blank and does not block. Submitting anyway would file an
// application with blanks where required answers belong, which is worse than not
// applying — and inventing an answer is what ADR-006/009 forbid outright.
//
// NOT live-browser-tested (no loaded-extension access in this project). The
// classification it relies on is unit-tested in ../background/driverCore.test.mjs.
import { classifyFailure, countFields, holdsApplicationForm } from "../background/driverCore.mjs";
// Which flag reasons stop the run (an optional EEO field does not — it is left
// blank) and the needs_human message, both pure and tested in fieldDecision.test.mjs.
import { NEEDS_USER_REASONS, needsHumanReason } from "./fieldDecision.mjs";
import { controlTypes, fillForm } from "./formFill.content";
import { submitApprovedApplication } from "./submitApprovedApplication";
import { decideVerification, isCaptchaChallengeSrc, verificationReport } from "./submitVerification.mjs";

type Verify = { urlBefore: string; sentAt: number };

type WorkItem = {
  application_id: string;
  profile_id: string;
  apply_url: string;
  company: string;
  title: string;
  ats_type?: string | null;
  // Set by the driver once the submit was sent: this page only verifies.
  verify?: Verify;
};

const POLL_MS = 500;
// How long an assigned frame waits for its application form to render (SPA boards
// render after document_idle) before concluding it doesn't hold one.
const FORM_WAIT_MS = 10_000;

/**
 * Frames (latest+48): the content scripts run in every frame, captcha widgets
 * included. A frame takes part only if it holds an application form, and then only
 * if the driver chooses it among the claiming frames (most fields wins). Everyone
 * else returns silently — never reports — so a captcha frame's "no form here"
 * can't win the race to the driver.
 */
async function claimThisFrame(): Promise<boolean> {
  const deadline = Date.now() + FORM_WAIT_MS;
  let types = controlTypes();
  while (!holdsApplicationForm(types)) {
    if (Date.now() > deadline) return false;
    await new Promise((resolve) => setTimeout(resolve, POLL_MS));
    types = controlTypes();
  }
  return (await chrome.runtime.sendMessage({ type: "jc:claim-frame", fieldCount: countFields(types) })) === true;
}

function report(
  outcome: "submitted" | "unconfirmed" | "failed" | "needs_human",
  reason?: string,
  questions: string[] = [],
): void {
  // Fire-and-forget: the driver is waiting on this message and has its own
  // timeout, so a failed send degrades to a timeout rather than a hang.
  chrome.runtime.sendMessage({ type: "jc:apply-result", outcome, reason, questions });
}

function findForm(): HTMLFormElement | null {
  // The form with the most fields is the application form; pages routinely also
  // carry a search or newsletter form with one or two inputs.
  const forms = Array.from(document.querySelectorAll("form"));
  if (forms.length === 0) return null;
  return forms.reduce((best, form) =>
    form.querySelectorAll("input, select, textarea").length >
    best.querySelectorAll("input, select, textarea").length
      ? form
      : best,
  );
}

const visible = (el: Element) => {
  const style = getComputedStyle(el);
  return el.getClientRects().length > 0 && style.visibility !== "hidden" && style.display !== "none";
};

function labelOf(el: HTMLElement): string {
  const labelled = (el as HTMLInputElement).labels?.[0]?.innerText;
  return (labelled || el.getAttribute("aria-label") || el.getAttribute("name") || "a field").trim();
}

// Error texts inside the form only — a page-level role=alert (cookie banner) is not ours.
function errorTexts(form: HTMLFormElement): string[] {
  const texts = new Set<string>();
  form
    .querySelectorAll<HTMLElement>('[role="alert"], .error, .errors, .field-error, .error-message, [class*="error-message"], [class*="field-error"]')
    .forEach((el) => {
      const text = el.innerText?.trim();
      if (text && visible(el)) texts.add(text.slice(0, 300));
    });
  form.querySelectorAll<HTMLElement>('[aria-invalid="true"]').forEach((el) => {
    const described = (el.getAttribute("aria-errormessage") || el.getAttribute("aria-describedby") || "")
      .split(/\s+/)
      .map((id) => (id ? document.getElementById(id)?.innerText?.trim() : ""))
      .filter(Boolean)
      .join(" ");
    texts.add(`${labelOf(el)}: ${described || "marked invalid"}`);
  });
  // requestSubmit() runs native constraint validation and silently doesn't submit.
  form.querySelectorAll<HTMLInputElement>("input, select, textarea").forEach((el) => {
    if (el.willValidate && !el.checkValidity()) texts.add(`${labelOf(el)}: ${el.validationMessage}`);
  });
  return [...texts];
}

/** Watch this page until submitVerification decides, then report once. */
async function verify(v: Verify, submittedForm: HTMLFormElement | null): Promise<void> {
  for (;;) {
    // Same page (SPA / slow POST): the form we submitted. After a navigation: the
    // application form, if the ATS re-rendered it (server-side validation).
    const form = submittedForm?.isConnected ? submittedForm : findForm();
    const formStillPresent =
      !!form && visible(form) && form.querySelectorAll("input, select, textarea").length >= 3;
    const result = decideVerification({
      urlBefore: v.urlBefore,
      urlAfter: location.href,
      pageText: (document.body?.innerText ?? "").slice(0, 5000),
      formStillPresent,
      visibleErrorTexts: formStillPresent && form ? errorTexts(form) : [],
      captchaVisible: Array.from(document.querySelectorAll("iframe")).some(
        (f) => isCaptchaChallengeSrc(f.src) && visible(f),
      ),
      elapsedMs: Date.now() - v.sentAt,
    });
    if (result.verdict !== "pending") {
      const { outcome, reason } = verificationReport(result);
      report(outcome, reason);
      return;
    }
    await new Promise((resolve) => setTimeout(resolve, POLL_MS));
  }
}

async function run(): Promise<void> {
  let item: WorkItem | null = null;
  try {
    item = await chrome.runtime.sendMessage({ type: "jc:what-am-i-doing" });
  } catch {
    return; // no background driver listening: an ordinary page visit
  }
  if (!item) return; // the user is just browsing, or another frame has this tab: do nothing

  // The page the submit navigated to: verify only. Filling or submitting here
  // would be a second application. The driver hands `verify` only to the frame
  // that submitted (same frameId after its navigation).
  if (item.verify) {
    try {
      await verify(item.verify, null);
    } catch (error) {
      report("unconfirmed", `Couldn't check the page after submit: ${String(error)}`.slice(0, 2000));
    }
    return;
  }

  try {
    if (!(await claimThisFrame())) return; // not the application frame: stay silent
  } catch {
    return; // driver gone
  }

  // Once the submit is sent, no error may become `failed`: that returns the row
  // to `approved` and a retry could apply twice.
  let sent = false;
  try {
    const { flagged, questions } = await fillForm(item.profile_id, item.ats_type);

    const blocking = flagged.filter((f) => NEEDS_USER_REASONS.has(f.reason));
    if (blocking.length > 0) {
      report(
        "needs_human",
        needsHumanReason(blocking),
        // What the user answers once in the review queue; the next pass fills
        // these from the answer bank instead of stopping again.
        questions,
      );
      return;
    }

    const form = findForm();
    if (!form) {
      // Ashby renders its application with no <form> at all. Submitting there means
      // clicking the ATS's own button, which also needs the React value fix
      // (LIVE-FORM-TEST.md #3) or it sends empty fields. Until both land, hand it
      // to the user rather than `failed`, which would just retry the same wall.
      report(
        "needs_human",
        "This application page has no form Maggie can submit (Ashby-style). Open the form and submit it yourself.",
      );
      return;
    }

    // Claims server-side, then submits. Throws if the claim is refused, in which
    // case nothing was submitted.
    const pending: Verify = { urlBefore: location.href, sentAt: Date.now() };
    await submitApprovedApplication(form, item.application_id, async () => {
      // The driver must know before the submit can navigate this tab away. No ack
      // (driver timed out or gone) -> throw, and the native submit never fires.
      pending.sentAt = Date.now(); // after the claim round trip, so the 20s is the page's
      const ack = await chrome.runtime.sendMessage({ type: "jc:submit-sent", ...pending });
      if (ack !== true) throw new Error("driver is no longer waiting for this tab; not submitting");
      sent = true;
    });
    await verify(pending, form);
  } catch (error) {
    if (sent) {
      report("unconfirmed", `Couldn't check the page after submit: ${String(error)}`.slice(0, 2000));
      return;
    }
    // The SAME classifier the driver uses. Reporting every error as `failed`
    // here would mean a captcha or an account wall is retried forever and never
    // reaches the user's review queue — the classification has to happen
    // wherever an error becomes an outcome, not in only one of the two places.
    const { outcome, reason } = classifyFailure(error);
    report(outcome, reason);
  }
}

void run();
