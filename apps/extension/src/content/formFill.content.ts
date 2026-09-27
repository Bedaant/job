// F11 content script (SPEC.md §3.7). Thin DOM glue around fieldDecision.mjs's
// pure logic — extraction/mutation here needs a real browser to verify and
// was NOT live-tested this session (no Playwright/loaded-extension access);
// fieldDecision.mjs's own logic is unit-tested (see fieldDecision.test.mjs).
// Only runs when messaged by the popup ("Fill this form" click) — it does
// not scan every page automatically.
import {
  buildDescriptors,
  classifyFileInput,
  decideFieldActions,
  pickQuestionText,
  planFill,
  setNativeValue,
  unansweredQuestions,
  type FieldMapping,
  type RawControl,
} from "./fieldDecision.mjs";
import { base64ToBytes } from "../background/apiProxyCore.mjs";
import type { ApiProxyResponse } from "../background/apiProxy";

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

// --- reading the page: one RawControl per element; fieldDecision.mjs decides
// what they are (groups, junk, option cap) ------------------------------------

const textOf = (el: Element | null | undefined) => el?.textContent?.trim() || null;

function labelElement(el: HTMLElement): HTMLElement | null {
  const id = el.getAttribute("id");
  return (id && document.querySelector<HTMLElement>(`label[for="${CSS.escape(id)}"]`)) || el.closest("label");
}

function ownLabel(el: HTMLElement): string | null {
  const byIds = el
    .getAttribute("aria-labelledby")
    ?.split(/\s+/)
    .map((id) => textOf(document.getElementById(id)))
    .filter(Boolean)
    .join(" ");
  return el.getAttribute("aria-label") || byIds || textOf(labelElement(el));
}

function isVisible(el: Element | null): boolean {
  if (!el || el.closest('[aria-hidden="true"]')) return false;
  const rect = el.getBoundingClientRect(); // display:none -> 0x0
  return rect.width > 0 && rect.height > 0 && getComputedStyle(el).visibility !== "hidden";
}

// react-select renders its requiredInput / value inputs next to its control,
// and its combobox input inside it.
function inReactSelect(el: HTMLElement): boolean {
  for (let n = el.parentElement, i = 0; n && i < 3; n = n.parentElement, i++) {
    if (n.querySelector(':scope > [class*="control"] input[role="combobox"]')) return true;
  }
  return false;
}

// Text before the first member, nearest last, skipping labels that belong to
// OTHER controls (so an unlabeled group never borrows the previous field's label).
function precedingTexts(box: Element, first: HTMLElement, members: HTMLElement[]): string[] {
  const texts: string[] = [];
  const walker = document.createTreeWalker(box, NodeFilter.SHOW_TEXT);
  for (let n = walker.nextNode(); n; n = walker.nextNode()) {
    if (first.compareDocumentPosition(n) & Node.DOCUMENT_POSITION_FOLLOWING) break;
    const parent = n.parentElement;
    if (!parent || parent.closest("script, style, option")) continue;
    const control = parent.closest("label")?.control;
    if (control && !members.includes(control as HTMLElement)) continue;
    const text = n.textContent?.trim();
    if (text) texts.push(text);
  }
  return texts;
}

function questionText(members: HTMLElement[]): string | null {
  const [first] = members;
  const legend = textOf(first.closest("fieldset")?.querySelector("legend"));
  if (legend) return legend;
  const group = first.closest('[role="radiogroup"], [role="group"]');
  const groupLabel = group && ownLabel(group as HTMLElement);
  if (groupLabel) return groupLabel;
  let box = first.parentElement;
  while (box && !members.every((m) => box!.contains(m))) box = box.parentElement;
  const optionLabels = members.map(ownLabel).filter((l): l is string => !!l);
  for (let i = 0; box && i < 3; box = box.parentElement, i++) {
    const question = pickQuestionText(precedingTexts(box, first, members), optionLabels);
    if (question) return question;
  }
  return null;
}

function readControls(controls: HTMLElement[]): RawControl[] {
  const groupQuestion = new Map<string, string | null>();
  return controls.map((el, key) => {
    const input = el as HTMLInputElement;
    const type = el.tagName === "INPUT" ? input.type : el.tagName.toLowerCase();
    const name = el.getAttribute("name");
    const label = ownLabel(el);
    let question: string | null = null;
    if ((type === "radio" || type === "checkbox") && name) {
      const groupKey = `${type}:${name}`;
      if (!groupQuestion.has(groupKey)) {
        const members = controls.filter((c) => c.getAttribute("name") === name && (c as HTMLInputElement).type === type);
        groupQuestion.set(groupKey, questionText(members));
      }
      question = groupQuestion.get(groupKey)!;
    } else if (!label && type !== "hidden") {
      question = questionText([el]) ?? el.getAttribute("placeholder");
    }
    return {
      key,
      tag: el.tagName,
      type,
      role: el.getAttribute("role"),
      name,
      dom_id: el.getAttribute("id"),
      autocomplete: el.getAttribute("autocomplete"),
      // aria-required on the element itself or on its radiogroup/group wrapper
      // (custom ATS widgets rarely set the native attribute).
      required: input.required || el.closest('[aria-required="true"]') !== null,
      label,
      question,
      value: input.value ?? "",
      options:
        el.tagName === "SELECT"
          ? Array.from((el as HTMLSelectElement).options).map((o) => ({ label: o.text.trim(), value: o.value }))
          : [],
      visible: isVisible(el),
      labelVisible: isVisible(labelElement(el)),
      inReactSelect: inReactSelect(el),
    };
  });
}

// Content scripts can't fetch the API themselves (the employer page's origin is
// CORS-refused): the background worker does it, token and all (apiProxy.ts).
async function callApi(method: string, path: string, body?: unknown) {
  const resp: ApiProxyResponse | undefined = await chrome.runtime.sendMessage({ type: "jc:api", method, path, body });
  if (!resp) throw new Error("the extension's background worker did not answer");
  if (!resp.ok) throw new Error(resp.error);
  return resp;
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

async function fetchResumeFile(profileId: string): Promise<File> {
  // The facts-only docx (ADR-009), linted and parse-back-checked server-side
  // before any bytes leave. ponytail: the profile's resume, not a per-application
  // tailored one; a tailored docx endpoint is the upgrade when tailoring is live.
  let resp;
  try {
    resp = await callApi("GET", `/profiles/${profileId}/resume.docx`);
  } catch (error) {
    throw new Error(`resume upload failed: could not fetch resume (${error instanceof Error ? error.message : error})`);
  }
  return new File([base64ToBytes(resp.base64 ?? "")], "resume.docx", {
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
  const controls = Array.from(document.querySelectorAll<HTMLElement>("input, select, textarea"));
  // File inputs never go to map-fields: no text value can fill one.
  const { descriptors, files, targets } = buildDescriptors(readControls(controls));
  if (descriptors.length === 0 && files.length === 0) {
    throw new Error("no form found on page");
  }
  // field_id is `jc-field-<key>` of the field's first element.
  const elementOf = (fieldId: string) => controls[Number(fieldId.slice("jc-field-".length))];

  let mappings: FieldMapping[] = [];
  if (descriptors.length > 0) {
    try {
      const resp = await callApi("POST", "/extension/map-fields", {
        profile_id: profileId,
        url: location.href,
        fields: descriptors,
        ats_type: atsType ?? null,
      });
      mappings = resp.json as FieldMapping[];
    } catch (error) {
      throw new Error(`could not map fields (${error instanceof Error ? error.message : error})`);
    }
  }

  const { fill, flag } = decideFieldActions(descriptors, mappings);

  // Files FIRST: an upload re-renders React ATSes (Ashby wiped text filled before
  // it) and Lever parses the resume into its own fields.
  let resume: File | null = null;
  let filled = 0;
  for (const { descriptor, key } of files) {
    const kind = classifyFileInput(descriptor);
    if (kind === "resume") {
      resume ??= await fetchResumeFile(profileId);
      attachFile(controls[key] as HTMLInputElement, resume);
      markField(controls[key], "filled", "Resume attached by ApplyScout — verify before submitting.");
      filled++;
    } else if (kind === "flag") {
      flag.push({ field_id: descriptor.field_id, reason: "file_upload" });
    }
  }

  for (const { field_id, value } of fill) {
    const plan = planFill(targets.get(field_id)!, value);
    if (!plan) {
      // No option matches the value exactly: never guess one.
      flag.push({ field_id, reason: "low_confidence" });
      continue;
    }
    if (plan.kind === "none") continue; // a lone checkbox answered "no" stays unchecked
    const el = controls[plan.key] as HTMLInputElement;
    if (plan.kind === "check") {
      if (!el.checked) el.click(); // React listens for the click, not .checked
    } else {
      setNativeValue(el, plan.value);
    }
    markField(el, "filled", "Auto-filled by ApplyScout — verify before submitting.");
    filled++;
  }

  for (const { field_id, reason } of flag) {
    const el = elementOf(field_id);
    if (!el) continue;
    markField(
      el,
      reason === "demographic_left_blank" ? "left_blank" : "flagged",
      FLAG_MESSAGES[reason] ?? FLAG_MESSAGES.low_confidence,
    );
  }

  return {
    filled,
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
