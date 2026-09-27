// F11 content script (SPEC.md §3.7). Thin DOM glue around fieldDecision.mjs's
// pure logic — extraction/mutation here needs a real browser to verify and
// was NOT live-tested this session (no Playwright/loaded-extension access);
// fieldDecision.mjs's own logic is unit-tested (see fieldDecision.test.mjs).
// Only runs when messaged by the popup ("Fill this form" click) — it does
// not scan every page automatically.
import { classifyFileInput, decideFieldActions, unansweredQuestions } from "./fieldDecision.mjs";
import { API_BASE_URL } from "../apiConfig";

// ADR-001 runtime guard, defense-in-depth alongside the static source-text
// scan (architectureInvariants.test.mjs): MV3 content scripts execute in an
// isolated JS world with their own copy of built-in prototypes, sharing only
// the DOM with the host page — patching HTMLFormElement.prototype here
// affects this content script's own calls (the actual threat model) without
// touching the host page's own JS. Catches a dynamically-constructed call
// (e.g. el["submit"]()) that a source-text regex scan could miss. The human
// always clicks the ATS's own Submit button; this script never does.
//
// Sub-project #4: the ORIGINAL native methods are captured here, before
// patching, and exported ONLY for submitApprovedApplication.ts — the one
// file explicitly allowlisted in architectureInvariants.test.mjs's static
// scan — to call after it has confirmed a real backend claim succeeded
// (POST /applications/{id}/claim-submission). Real authority lives
// server-side; this export is the mechanical trigger, never used directly
// by anything else, never attached to window/globalThis.
export const _adr001OriginalSubmit = HTMLFormElement.prototype.submit;
export const _adr001OriginalRequestSubmit = HTMLFormElement.prototype.requestSubmit;

for (const method of ["submit", "requestSubmit"] as const) {
  HTMLFormElement.prototype[method] = function () {
    throw new Error(
      `ApplyScout: form.${method}() is forbidden by ADR-001 — this extension never submits a form.`,
    );
  };
}

interface FieldDescriptor {
  field_id: string;
  label_text: string | null;
  input_type: string;
  options: string[];
  required: boolean;
  // Raw DOM attributes the backend's deterministic rule matcher
  // (formfill/deterministic.py) reads before ever calling the LLM.
  // autocomplete is a real web standard (WHATWG HTML autofill-field-name);
  // name/dom_id are the element's own name/id attributes.
  autocomplete: string | null;
  name: string | null;
  dom_id: string | null;
}

function extractLabel(el: HTMLElement): string | null {
  const ariaLabel = el.getAttribute("aria-label");
  if (ariaLabel) return ariaLabel;

  const id = el.getAttribute("id");
  if (id) {
    const label = document.querySelector(`label[for="${CSS.escape(id)}"]`);
    if (label?.textContent) return label.textContent.trim();
  }

  const closestLabel = el.closest("label");
  if (closestLabel?.textContent) return closestLabel.textContent.trim();

  return el.getAttribute("placeholder");
}

function extractFields(): {
  descriptors: FieldDescriptor[];
  elements: Map<string, HTMLElement>;
  fileFields: { descriptor: FieldDescriptor; el: HTMLInputElement }[];
} {
  const elements = new Map<string, HTMLElement>();
  const descriptors: FieldDescriptor[] = [];
  // File inputs never go to map-fields: no text value can fill one, and writing a
  // string into input.value on a file input throws.
  const fileFields: { descriptor: FieldDescriptor; el: HTMLInputElement }[] = [];

  document.querySelectorAll<HTMLElement>("input, select, textarea").forEach((el, index) => {
    const inputEl = el as HTMLInputElement;
    if (inputEl.type === "hidden" || inputEl.type === "submit" || inputEl.type === "button") return;

    const fieldId = `jc-field-${index}`;
    elements.set(fieldId, el);

    const options =
      el.tagName === "SELECT"
        ? Array.from((el as HTMLSelectElement).options).map((o) => o.text)
        : [];

    const descriptor: FieldDescriptor = {
      field_id: fieldId,
      label_text: extractLabel(el),
      input_type: el.tagName === "SELECT" ? "select" : el.tagName === "TEXTAREA" ? "textarea" : inputEl.type || "text",
      options,
      // aria-required on the element itself or on its radiogroup/group wrapper
      // (custom ATS widgets rarely set the native attribute).
      required: inputEl.required || el.closest('[aria-required="true"]') !== null,
      autocomplete: el.getAttribute("autocomplete"),
      name: el.getAttribute("name"),
      dom_id: el.getAttribute("id"),
    };
    if (inputEl.type === "file") fileFields.push({ descriptor, el: inputEl });
    else descriptors.push(descriptor);
  });

  return { descriptors, elements, fileFields };
}

const OUTLINES = { filled: "2px solid #2e7d32", flagged: "2px solid #c62828", left_blank: "2px dashed #9e9e9e" };

function markField(el: HTMLElement, kind: keyof typeof OUTLINES, title: string) {
  el.style.outline = OUTLINES[kind];
  el.title = title;
}

export type FillOutcome = {
  filled: number;
  flagged: { field_id: string; reason: string }[];
  // Labels of flagged fields the user can answer once into the answer bank.
  questions: string[];
};

// Keyed by fieldDecision.mjs's flag reasons. `essay_no_stored_answer` is the
// only one the user can clear for good — saving the answer once means every
// later form that asks it is filled from the answer bank.
const FLAG_MESSAGES: Record<string, string> = {
  demographic_required:
    "ApplyScout: required self-identification question — only you can answer it (never auto-answered).",
  demographic_left_blank: "Left blank for you — ApplyScout never answers these.",
  essay_no_stored_answer:
    "ApplyScout: needs your input — save the answer and we'll reuse it next time.",
  low_confidence: "ApplyScout: needs your input (low confidence).",
  file_upload: "ApplyScout: needs a file we don't have — please upload it.",
};

async function fetchResumeFile(profileId: string, token: string): Promise<File> {
  // The facts-only docx (ADR-009), linted and parse-back-checked server-side
  // before any bytes leave. ponytail: the profile's resume, not a per-application
  // tailored one; a tailored docx endpoint is the upgrade when tailoring is live.
  const resp = await fetch(`${API_BASE_URL}/profiles/${profileId}/resume.docx`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!resp.ok) throw new Error(`resume upload failed: could not fetch resume (${resp.status})`);
  return new File([await resp.blob()], "resume.docx", {
    type: "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
  });
}

function attachFile(el: HTMLInputElement, file: File): void {
  // DataTransfer is the only way to build a FileList a script can assign.
  const transfer = new DataTransfer();
  transfer.items.add(file);
  el.files = transfer.files;
  el.dispatchEvent(new Event("input", { bubbles: true }));
  el.dispatchEvent(new Event("change", { bubbles: true }));
}

/**
 * Throws rather than alert()s (ADR-015 Phase 1): the driver opens apply pages in
 * background tabs, and a modal alert in a background tab blocks that tab
 * indefinitely with nobody there to dismiss it — the whole queue then stalls on
 * the driver's per-item timeout. The interactive path below catches and alerts,
 * so nothing changes for a user who triggered the fill themselves.
 */
export async function fillForm(profileId: string, atsType?: string | null): Promise<FillOutcome> {
  const { descriptors, elements, fileFields } = extractFields();
  if (descriptors.length === 0 && fileFields.length === 0) {
    throw new Error("no form found on page");
  }

  const { jc_token: token } = await chrome.storage.local.get("jc_token");
  if (!token) {
    throw new Error("please log in from the extension popup first");
  }

  let mappings = [];
  if (descriptors.length > 0) {
    const resp = await fetch(`${API_BASE_URL}/extension/map-fields`, {
      method: "POST",
      headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
      body: JSON.stringify({ profile_id: profileId, url: location.href, fields: descriptors, ats_type: atsType ?? null }),
    });
    if (!resp.ok) {
      throw new Error(`could not map fields (${resp.status})`);
    }
    mappings = await resp.json();
  }

  const { fill, flag } = decideFieldActions(descriptors, mappings);

  for (const { field_id, value } of fill) {
    const el = elements.get(field_id) as HTMLInputElement | undefined;
    if (!el) continue;
    el.value = value;
    el.dispatchEvent(new Event("input", { bubbles: true }));
    el.dispatchEvent(new Event("change", { bubbles: true }));
    markField(el, "filled", "Auto-filled by ApplyScout — verify before submitting.");
  }

  let resume: File | null = null;
  let filesAttached = 0;
  for (const { descriptor, el } of fileFields) {
    const kind = classifyFileInput(descriptor);
    if (kind === "resume") {
      resume ??= await fetchResumeFile(profileId, token);
      attachFile(el, resume);
      markField(el, "filled", "Resume attached by ApplyScout — verify before submitting.");
      filesAttached++;
    } else if (kind === "flag") {
      flag.push({ field_id: descriptor.field_id, reason: "file_upload" });
    }
  }

  for (const { field_id, reason } of flag) {
    const el = elements.get(field_id);
    if (!el) continue;
    markField(
      el,
      reason === "demographic_left_blank" ? "left_blank" : "flagged",
      FLAG_MESSAGES[reason] ?? FLAG_MESSAGES.low_confidence,
    );
  }

  return {
    filled: fill.length + filesAttached,
    flagged: flag.map((f) => ({ field_id: f.field_id, reason: f.reason })),
    questions: unansweredQuestions(descriptors, flag),
  };
}

chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
  if (message?.type === "jc:fill-form") {
    // The interactive path keeps its alert — a user who clicked "fill" is present
    // to read it. The automated path (autoApply.content.ts) handles the throw.
    fillForm(message.profileId)
      .then((outcome) => sendResponse({ ok: true, ...outcome }))
      .catch((error) => {
        alert(`ApplyScout: ${error instanceof Error ? error.message : String(error)}`);
        sendResponse({ ok: false });
      });
    return true; // keep the message channel open for the async response
  }
});
