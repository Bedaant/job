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
import { API_BASE_URL } from "../apiConfig";

export async function submitApprovedApplication(form: HTMLFormElement, applicationId: string): Promise<void> {
  const { jc_token: token } = await chrome.storage.local.get("jc_token");
  if (!token) {
    throw new Error("Job Copilot: not logged in — cannot claim submission.");
  }

  const resp = await fetch(`${API_BASE_URL}/applications/${applicationId}/claim-submission`, {
    method: "POST",
    headers: { Authorization: `Bearer ${token}` },
  });

  if (!resp.ok) {
    throw new Error(
      `Job Copilot: backend refused the submission claim (${resp.status}) — the human-approval gate was not satisfied, so the form was not submitted.`,
    );
  }

  _adr001OriginalRequestSubmit.call(form);
}
