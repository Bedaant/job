// F11 content script (SPEC.md §3.7). Thin DOM glue around fieldDecision.mjs's
// pure logic — extraction/mutation here needs a real browser to verify and
// was NOT live-tested this session (no Playwright/loaded-extension access);
// fieldDecision.mjs's own logic is unit-tested (see fieldDecision.test.mjs).
// Only runs when messaged by the popup ("Fill this form" click) — it does
// not scan every page automatically.
import { decideFieldActions } from "./fieldDecision.mjs";
import { API_BASE_URL } from "../apiConfig";

// ADR-001 runtime guard, defense-in-depth alongside the static source-text
// scan (architectureInvariants.test.mjs): MV3 content scripts execute in an
// isolated JS world with their own copy of built-in prototypes, sharing only
// the DOM with the host page — patching HTMLFormElement.prototype here
// affects this content script's own calls (the actual threat model) without
// touching the host page's own JS. Catches a dynamically-constructed call
// (e.g. el["submit"]()) that a source-text regex scan could miss. The human
// always clicks the ATS's own Submit button; this script never does.
for (const method of ["submit", "requestSubmit"] as const) {
  HTMLFormElement.prototype[method] = function () {
    throw new Error(
      `Job Copilot: form.${method}() is forbidden by ADR-001 — this extension never submits a form.`,
    );
  };
}

interface FieldDescriptor {
  field_id: string;
  label_text: string | null;
  input_type: string;
  options: string[];
  required: boolean;
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

function extractFields(): { descriptors: FieldDescriptor[]; elements: Map<string, HTMLElement> } {
  const elements = new Map<string, HTMLElement>();
  const descriptors: FieldDescriptor[] = [];

  document.querySelectorAll<HTMLElement>("input, select, textarea").forEach((el, index) => {
    const inputEl = el as HTMLInputElement;
    if (inputEl.type === "hidden" || inputEl.type === "submit" || inputEl.type === "button") return;

    const fieldId = `jc-field-${index}`;
    elements.set(fieldId, el);

    const options =
      el.tagName === "SELECT"
        ? Array.from((el as HTMLSelectElement).options).map((o) => o.text)
        : [];

    descriptors.push({
      field_id: fieldId,
      label_text: extractLabel(el),
      input_type: el.tagName === "SELECT" ? "select" : el.tagName === "TEXTAREA" ? "textarea" : inputEl.type || "text",
      options,
      required: inputEl.required ?? false,
    });
  });

  return { descriptors, elements };
}

function markField(el: HTMLElement, kind: "filled" | "flagged", title: string) {
  el.style.outline = kind === "filled" ? "2px solid #2e7d32" : "2px solid #c62828";
  el.title = title;
}

async function fillForm(profileId: string) {
  const { descriptors, elements } = extractFields();
  if (descriptors.length === 0) return;

  const { jc_token: token } = await chrome.storage.local.get("jc_token");
  if (!token) {
    alert("Job Copilot: please log in from the extension popup first.");
    return;
  }

  const resp = await fetch(`${API_BASE_URL}/extension/map-fields`, {
    method: "POST",
    headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
    body: JSON.stringify({ profile_id: profileId, url: location.href, fields: descriptors }),
  });
  if (!resp.ok) {
    alert(`Job Copilot: could not map fields (${resp.status}).`);
    return;
  }
  const mappings = await resp.json();

  const { fill, flag } = decideFieldActions(descriptors, mappings);

  for (const { field_id, value } of fill) {
    const el = elements.get(field_id) as HTMLInputElement | undefined;
    if (!el) continue;
    el.value = value;
    el.dispatchEvent(new Event("input", { bubbles: true }));
    el.dispatchEvent(new Event("change", { bubbles: true }));
    markField(el, "filled", "Auto-filled by Job Copilot — verify before submitting.");
  }

  for (const { field_id, reason } of flag) {
    const el = elements.get(field_id);
    if (!el) continue;
    markField(
      el,
      "flagged",
      reason === "demographic_or_essay"
        ? "Job Copilot: needs your input (never auto-answered)."
        : "Job Copilot: needs your input (low confidence).",
    );
  }
}

chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
  if (message?.type === "jc:fill-form") {
    fillForm(message.profileId).then(() => sendResponse({ ok: true }));
    return true; // keep the message channel open for the async response
  }
});
