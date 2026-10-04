// The ONE reviewed path that may fire a real submit, registered by exact file
// path in architectureInvariants.test.mjs's ALLOWLIST so the carve-out stays
// narrow and auditable. It does nothing except (1) call the backend claim
// endpoint, which takes a row lock and moves the application `approved ->
// submitting` in one transaction, and (2) only if that returns 200, invoke the
// ORIGINAL native form.requestSubmit() captured in formFill.content.ts before
// the guard patched it. If the claim fails for any reason — already claimed,
// not approved, network error — this throws and the native submit is never
// reached.
//
// DO NOT remove the claim call to "finish the ADR-015 pivot" (amended
// 2026-10-04; ADR-015's own "code to remove" bullet reads that way and is
// wrong). `approved` no longer implies a human clicked Approve on this item —
// campaigns.run_campaign sets it directly when campaign.auto_submit is true,
// which IS ADR-015 §2's campaign-level approval, already implemented. What the
// claim provides is different and still required: the at-most-once guarantee
// for an irreversible outward-facing action (a real application to a real
// employer), plus the per-submission accounting ADR-015's daily-caps rail
// depends on. Pinned by test_claim_submission_still_cannot_fire_twice.
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
