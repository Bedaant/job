// Sub-project #4 (gated batch execution) — the ONE explicitly reviewed
// exception to ADR-001's guard, registered by exact file path in
// architectureInvariants.test.mjs's ALLOWLIST. This file exists to make
// that exception narrow and auditable rather than a blanket carve-out:
// it does nothing except (1) call the real backend claim endpoint, which
// atomically checks the application is genuinely `approved` (a human
// already clicked "Approve" in the review queue) and flips it to
// `applied` in one locked transaction, and (2) only if that call returns
// 200, invoke the ORIGINAL native form.requestSubmit() captured in
// formFill.content.ts before the guard patched it. If the backend claim
// fails for any reason — already claimed, not approved, network error,
// anything — this throws and the native submit is never reached.
//
// Not live-browser-tested this session (no Playwright/loaded-extension
// access, same standing limitation as the rest of F11's content-script
// code) — the backend half (POST /applications/{id}/claim-submission) is
// tested and live-verified against real Neon; this file is the thin,
// deliberately minimal glue on top of it.
import { _adr001OriginalRequestSubmit } from "./formFill.content";

// `beforeSubmit` runs after the claim succeeds and before the native submit; if it
// throws, nothing is submitted. autoApply uses it to tell the driver "verify from
// here on" — it must land before the submit can navigate the tab away.
export async function submitApprovedApplication(
  form: HTMLFormElement,
  applicationId: string,
  beforeSubmit: () => Promise<void> = async () => {},
): Promise<void> {
  // Through the background worker (apiProxy.ts): a fetch from the employer page
  // is CORS-refused, and the worker holds the token (LIVE-FORM-TEST #1).
  const resp = await chrome.runtime.sendMessage({
    type: "jc:api",
    method: "POST",
    path: `/applications/${applicationId}/claim-submission`,
  });
  if (!resp?.ok) {
    throw new Error(
      `ApplyScout: the submission claim was refused (${resp?.error ?? "no answer from the extension"}) — nothing was submitted.`,
    );
  }

  await beforeSubmit();
  _adr001OriginalRequestSubmit.call(form);
}
