// ADR-015 Phase 1 — the driver: the loop that turns `approved` applications into
// submitted ones. This is the connection that was missing; run_campaign_task
// produced approved rows and nothing ever collected them, so a campaign ended in
// a queue rather than a sent application.
//
// Runs in the user's OWN browser session (ADR-015 §3) — never a shared server
// bot, which is what keeps ban exposure off shared infrastructure.
//
// Deliberately manual: there is no alarm or scheduler here. The user presses a
// button in the popup and one pass runs. A background timer applying to jobs
// while the user sleeps is a bigger decision than Phase 1 should make on its own,
// and the daily cap already lives server-side.
//
// NOT live-browser-tested: this project has no loaded-extension or Playwright
// access, the same standing limitation recorded for the rest of the content-script
// code. The decisions live in driverCore.mjs and are unit-tested; everything here
// is chrome API glue, which is exactly why it is kept this thin.
import { API_BASE_URL } from "../apiConfig";
import { classifyFailure, planRun } from "./driverCore.mjs";
import { VERIFY_TIMEOUT_MS } from "../content/submitVerification.mjs";

export type WorkItem = {
  application_id: string;
  profile_id: string;
  apply_url: string;
  company: string;
  title: string;
  ats_type?: string | null;
  // Set once the content script says the submit is being sent: from then on the
  // tab (and any page it navigates to) only verifies. See autoApply.content.ts.
  verify?: { urlBefore: string; sentAt: number };
};

type Outcome = "submitted" | "unconfirmed" | "failed" | "needs_human";

// How long one application gets before the driver gives up on it. A real ATS
// page plus form fill plus submit is seconds; a minute means something is stuck.
const ITEM_TIMEOUT_MS = 60_000;
// After the submit is sent the page gets VERIFY_TIMEOUT_MS to decide; this slack
// covers a navigation + content-script injection. If it still hasn't reported,
// the outcome is `unconfirmed` — never `failed`, which would retry an application
// that may well have gone through.
const VERIFY_SLACK_MS = 10_000;

const attempts = new Map<string, number>();
// What each tab was opened to do, so the content script can ask "what am I here
// for?" instead of the driver trusting the page's own URL.
const assignments = new Map<number, WorkItem>();

async function authHeaders(): Promise<Record<string, string>> {
  const { jc_token: token } = await chrome.storage.local.get("jc_token");
  if (!token) throw new Error("not logged in — cannot run the apply queue");
  return { Authorization: `Bearer ${token}` };
}

export async function fetchWorkQueue(): Promise<WorkItem[]> {
  const resp = await fetch(`${API_BASE_URL}/extension/work-queue`, { headers: await authHeaders() });
  if (!resp.ok) throw new Error(`work-queue request failed (${resp.status})`);
  return resp.json();
}

async function reportResult(
  applicationId: string,
  outcome: Outcome,
  reason?: string,
  questions: string[] = [],
): Promise<void> {
  // Reporting is not optional: an unreported item stays `submitting` forever,
  // which is invisible to the user and to the next driver pass. If this throws,
  // it surfaces rather than being swallowed.
  const resp = await fetch(`${API_BASE_URL}/applications/${applicationId}/submission-result`, {
    method: "POST",
    headers: { ...(await authHeaders()), "Content-Type": "application/json" },
    body: JSON.stringify({ outcome, reason, unanswered_questions: questions }),
  });
  if (!resp.ok) {
    throw new Error(`could not report ${outcome} for ${applicationId} (${resp.status})`);
  }
}

/**
 * Open the apply page and wait for the content script to report what happened.
 * The tab is always closed and the assignment always cleared, including on
 * timeout — one leaked tab per failed application makes the browser unusable
 * after a dozen of them.
 */
type ItemResult = { outcome: Outcome; reason?: string; questions?: string[] };

function runItem(item: WorkItem): Promise<ItemResult> {
  return new Promise((resolve) => {
    let settled = false;
    let tabId: number | undefined;

    const finish = (result: ItemResult) => {
      if (settled) return;
      settled = true;
      clearTimeout(timer);
      chrome.runtime.onMessage.removeListener(onMessage);
      if (tabId !== undefined) {
        assignments.delete(tabId);
        chrome.tabs.remove(tabId).catch(() => {
          /* the user may have closed it themselves; not an error */
        });
      }
      resolve(result);
    };

    let timer = setTimeout(
      () => finish({ outcome: "failed", reason: `timed out after ${ITEM_TIMEOUT_MS}ms` }),
      ITEM_TIMEOUT_MS,
    );

    const onMessage = (
      message: any,
      sender: chrome.runtime.MessageSender,
      sendResponse: (response: unknown) => void,
    ) => {
      if (tabId === undefined || sender.tab?.id !== tabId) return; // another tab's message is not ours
      if (message?.type === "jc:submit-sent") {
        if (settled) return; // no ack -> the content script does not submit
        // The submit is about to fire: hand the tab over to verification, so the
        // page it navigates to only watches, and switch to the verify timer.
        assignments.set(tabId, { ...item, verify: { urlBefore: message.urlBefore, sentAt: message.sentAt } });
        clearTimeout(timer);
        timer = setTimeout(
          () =>
            finish({
              outcome: "unconfirmed",
              reason: "The form was sent but the page never reported back, so it couldn't be confirmed.",
            }),
          VERIFY_TIMEOUT_MS + VERIFY_SLACK_MS,
        );
        sendResponse(true);
        return;
      }
      if (message?.type !== "jc:apply-result") return;
      finish({ outcome: message.outcome, reason: message.reason, questions: message.questions });
    };

    chrome.runtime.onMessage.addListener(onMessage);

    chrome.tabs
      .create({ url: item.apply_url, active: false })
      .then((tab) => {
        tabId = tab.id;
        if (tabId === undefined) {
          finish({ outcome: "failed", reason: "could not open a tab for the apply page" });
          return;
        }
        assignments.set(tabId, item);
      })
      .catch((error) => finish(classifyFailure(error)));
  });
}

/**
 * One pass over the work queue, sequentially.
 *
 * Sequential on purpose: parallel tabs would race the same daily cap and make
 * "what went out" unreadable, for a speed-up nobody asked for.
 */
export async function runQueueOnce(): Promise<{ attempted: number; results: Record<string, number> }> {
  const queue = await fetchWorkQueue();
  const plan = planRun(queue, attempts);
  const results: Record<string, number> = {};

  for (const item of plan) {
    attempts.set(item.application_id, (attempts.get(item.application_id) ?? 0) + 1);
    const { outcome, reason, questions } = await runItem(item);
    try {
      await reportResult(item.application_id, outcome, reason, questions);
      results[outcome] = (results[outcome] ?? 0) + 1;
    } catch (error) {
      // The submission itself may well have succeeded; we just failed to record
      // it. Surfacing beats pretending — the row stays `submitting` and the user
      // can see that something went wrong.
      results.unreported = (results.unreported ?? 0) + 1;
      console.error("[job-copilot] failed to report a submission result", error);
    }
  }

  return { attempted: plan.length, results };
}

// The content script asks what it was opened for; the popup asks for a run.
chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (message?.type === "jc:what-am-i-doing") {
    const tabId = sender.tab?.id;
    sendResponse(tabId !== undefined ? (assignments.get(tabId) ?? null) : null);
    return true;
  }
  if (message?.type === "jc:run-queue") {
    runQueueOnce()
      .then(sendResponse)
      .catch((error) => sendResponse({ error: String(error) }));
    return true; // async response
  }
  return undefined;
});
