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
//
// Step 3 is not politeness: a flagged field is one map-fields refused to answer
// (a demographic question, or an essay). Submitting anyway would file an
// application with blanks where required answers belong, which is worse than not
// applying — and inventing an answer is what ADR-006/009 forbid outright.
//
// NOT live-browser-tested (no loaded-extension access in this project). The
// classification it relies on is unit-tested in ../background/driverCore.test.mjs.
import { classifyFailure } from "../background/driverCore.mjs";
import { fillForm } from "./formFill.content";
import { submitApprovedApplication } from "./submitApprovedApplication";

type WorkItem = {
  application_id: string;
  profile_id: string;
  apply_url: string;
  company: string;
  title: string;
};

// Reasons map-fields uses for a field it will not answer. Any of them means a
// human has to finish this application. `demographic_or_essay` split into
// `demographic` (never answerable) and `essay_no_stored_answer` (answerable
// once, via the answer bank) when the bank landed — an essay field that the
// bank DID answer is not flagged at all and so never appears here.
const NEEDS_USER_REASONS = new Set([
  "demographic",
  "essay_no_stored_answer",
  "low_confidence",
]);

function report(outcome: "submitted" | "failed" | "needs_human", reason?: string): void {
  // Fire-and-forget: the driver is waiting on this message and has its own
  // timeout, so a failed send degrades to a timeout rather than a hang.
  chrome.runtime.sendMessage({ type: "jc:apply-result", outcome, reason });
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

async function run(): Promise<void> {
  let item: WorkItem | null = null;
  try {
    item = await chrome.runtime.sendMessage({ type: "jc:what-am-i-doing" });
  } catch {
    return; // no background driver listening: an ordinary page visit
  }
  if (!item) return; // the user is just browsing; do nothing

  try {
    const { flagged } = await fillForm(item.profile_id);

    const blocking = flagged.filter((f) => NEEDS_USER_REASONS.has(f.reason));
    if (blocking.length > 0) {
      report(
        "needs_human",
        `${blocking.length} field(s) need your input and were not answered: ` +
          blocking.map((f) => f.reason).join(", "),
      );
      return;
    }

    const form = findForm();
    if (!form) {
      report("failed", "no form found on page");
      return;
    }

    // Claims server-side, then submits. Throws if the claim is refused, in which
    // case nothing was submitted.
    await submitApprovedApplication(form, item.application_id);
    report("submitted");
  } catch (error) {
    // The SAME classifier the driver uses. Reporting every error as `failed`
    // here would mean a captcha or an account wall is retried forever and never
    // reaches the user's review queue — the classification has to happen
    // wherever an error becomes an outcome, not in only one of the two places.
    const { outcome, reason } = classifyFailure(error);
    report(outcome, reason);
  }
}

void run();
