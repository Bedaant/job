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
  isDemographicField,
  isDemographicLabel,
  pickQuestionText,
  planFill,
  setNativeValue,
  unansweredQuestions,
  type FieldMapping,
  type RawControl,
} from "./fieldDecision.mjs";
import {
  COMBOBOX_TYPE_WAIT_MS,
  COMBOBOX_WAIT_MS,
  comboboxKind,
  fillCityTypeahead,
  fillCombobox,
  isCityQuestion,
  matchOption,
  readAllOptions,
  type Place,
} from "./combobox.mjs";
import { readLive, relink } from "./relink.mjs";
import { base64ToBytes } from "../background/apiProxyCore.mjs";
import { fillsOnPopup } from "../background/driverCore.mjs";
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

// --- custom comboboxes (combobox.mjs has the sequencing; this is the DOM) ------

const sleep = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));

async function waitFor<T>(probe: () => T, ms: number): Promise<T> {
  const end = Date.now() + ms;
  let hit = probe();
  while (!hit && Date.now() < end) {
    await sleep(25);
    hit = probe();
  }
  return hit;
}

// Greenhouse opens its react-select on key/mouse UP: a lone keydown does nothing.
function pressKey(el: HTMLElement, key: string) {
  for (const type of ["keydown", "keyup"]) el.dispatchEvent(new KeyboardEvent(type, { key, bubbles: true, cancelable: true }));
}

function pressMouse(el: Element) {
  for (const type of ["mousedown", "mouseup"]) {
    el.dispatchEvent(new MouseEvent(type, { bubbles: true, cancelable: true, button: 0 }));
  }
}

const controlOf = (el: HTMLElement) => el.closest<HTMLElement>('[class*="control"]');

// The widget's OWN listbox — never a page-wide [role=option]: Greenhouse keeps
// intl-tel-input's 244 phone-country options in the DOM at all times.
function optionsOf(el: HTMLElement): HTMLElement[] {
  const ids = [el.getAttribute("aria-controls"), el.getAttribute("aria-owns"), el.id && `react-select-${el.id}-listbox`];
  const listbox =
    ids.map((id) => id && document.getElementById(id)).find(Boolean) ||
    el.closest('[class*="container"]')?.querySelector('[role="listbox"]');
  return listbox ? Array.from(listbox.querySelectorAll<HTMLElement>('[role="option"]')) : [];
}

const isOpen = (el: HTMLElement) => el.getAttribute("aria-expanded") === "true" || optionsOf(el).length > 0;

async function openMenu(el: HTMLElement) {
  el.focus({ preventScroll: true });
  pressKey(el, "ArrowDown");
  if (await waitFor(() => isOpen(el), 150)) return;
  pressMouse(controlOf(el) ?? el);
  await waitFor(() => isOpen(el), 150);
}

async function closeMenu(el: HTMLElement) {
  // Blur, never Escape: on a closed Greenhouse select Escape CLEARS the chosen value
  // (seen live), and on an open one it doesn't even close the menu.
  el.blur();
  await waitFor(() => !isOpen(el), 150);
}

type ComboKind = "react-select" | "listbox";

function comboKindOf(el: HTMLElement, raw: RawControl): ComboKind | null {
  return comboboxKind({
    tag: el.tagName,
    role: raw.role,
    visible: raw.visible,
    // raw.inReactSelect marks the siblings AROUND a control; the combobox input sits INSIDE it
    inReactSelect: controlOf(el) !== null,
    ariaAutocomplete: el.getAttribute("aria-autocomplete"),
    ariaHaspopup: el.getAttribute("aria-haspopup"),
    ariaControls: el.getAttribute("aria-controls") ?? el.getAttribute("aria-owns"),
  });
}

// Opens each combobox's menu once, reads its option labels, closes it: sent as the
// field's options so the backend binds its answer to one of them. Nothing is
// selected or typed. A demographic question is not opened at all (its label
// already rules it out); one with an innocent label is read, so its options can
// rule it out.
async function readComboboxOptions(controls: HTMLElement[], raws: RawControl[]): Promise<Map<number, ComboKind>> {
  const kinds = new Map<number, ComboKind>();
  for (const raw of raws) {
    const kind = comboKindOf(controls[raw.key], raw);
    if (kind) kinds.set(raw.key, kind);
  }
  const toRead = raws.filter((r) => kinds.has(r.key) && !isDemographicLabel(r.label ?? r.question));
  const read = await readAllOptions(
    toRead.map((r) => {
      const el = controls[r.key];
      return {
        open: () => openMenu(el),
        waitForOptions: async () => {
          await waitFor(() => optionsOf(el).length > 0, COMBOBOX_WAIT_MS);
          return optionsOf(el).map((o) => o.textContent ?? "");
        },
        close: () => closeMenu(el),
      };
    }),
  );
  toRead.forEach((r, i) => {
    r.options = (read[i] ?? []).map((label) => ({ label, value: label }));
  });
  return kinds;
}

// The DOM side of combobox.mjs's fill sequencing for one widget.
function comboboxOps(el: HTMLInputElement, kind: ComboKind) {
  let wait = COMBOBOX_WAIT_MS;
  return {
    // react-select shows the choice as text in its control; a typeahead in its input
    displayed: () => (kind === "react-select" ? textOf(controlOf(el)) ?? "" : el.value),
    open: () => openMenu(el),
    findOption: (want: string) =>
      waitFor(() => optionsOf(el).find((o) => matchOption([o.textContent ?? ""], want) === 0) ?? null, wait),
    waitForOptions: async () => {
      await waitFor(() => optionsOf(el).length > 0, wait);
      return optionsOf(el).map((o) => o.textContent ?? "");
    },
    canType: !el.readOnly && !el.disabled,
    type: async (text: string) => {
      wait = COMBOBOX_TYPE_WAIT_MS; // an async search has to come back
      setNativeValue(el, text);
    },
    click: async (option: HTMLElement) => {
      // click only: a mouseup first makes Greenhouse's wrapper toggle the menu shut,
      // detaching the option before its click lands
      option.click();
      await sleep(50);
    },
    clear: async () => setNativeValue(el, ""),
    close: () => closeMenu(el),
  };
}

// Picks `label` through the widget's own option click, then checks what it shows.
const selectComboboxOption = (el: HTMLInputElement, kind: ComboKind, label: string) =>
  fillCombobox<HTMLElement>(comboboxOps(el, kind), label);

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
  // a combobox's input is a sliver inside its control: outline the control
  const box = el.getAttribute("role") === "combobox" ? controlOf(el) ?? el : el;
  box.style.outline = OUTLINES[kind];
  el.title = title;
}

export type FillOutcome = {
  filled: number;
  flagged: { field_id: string; reason: string; label: string | null }[];
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
  optional_left_blank: "Left blank: optional, and ApplyScout has no answer for it.",
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
  // Read again if the form was replaced mid-read (relink.mjs readLive).
  const { controls, raws, comboKinds } = await readLive(
    async () => {
      const controls = Array.from(document.querySelectorAll<HTMLElement>("input, select, textarea"));
      const raws = readControls(controls);
      return { controls, raws, comboKinds: await readComboboxOptions(controls, raws) };
    },
    ({ controls }) => controls.some((el) => !el.isConnected),
  );
  // File inputs never go to map-fields: no text value can fill one.
  const { descriptors, files, targets } = buildDescriptors(raws);
  const descriptorById = new Map(descriptors.map((d) => [d.field_id, d]));
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

  // The form may have been re-rendered while we waited (Greenhouse's embed does):
  // write to the live elements, never to detached ones.
  if (controls.some((el) => !el.isConnected)) {
    const fresh = Array.from(document.querySelectorAll<HTMLElement>("input, select, textarea"));
    const sig = (el: HTMLElement) => ({
      tag: el.tagName, type: (el as HTMLInputElement).type ?? "", id: el.id, name: el.getAttribute("name") ?? "",
    });
    relink(controls.map(sig), fresh.map(sig)).forEach((j, i) => {
      if (j >= 0 && !controls[i].isConnected) controls[i] = fresh[j];
    });
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
    if (plan.kind === "combobox") {
      // decideFieldActions never fills a demographic field; this is the belt to that brace
      const kind = comboKinds.get(plan.key);
      if (!kind || isDemographicField(descriptorById.get(field_id)!) || !(await selectComboboxOption(el, kind, plan.label))) {
        flag.push({ field_id, reason: "low_confidence" });
        continue;
      }
    } else if (plan.kind === "check") {
      if (!el.checked) el.click(); // React listens for the click, not .checked
    } else {
      setNativeValue(el, plan.value);
    }
    markField(el, "filled", "Auto-filled by ApplyScout — verify before submitting.");
    filled++;
  }

  // A location typeahead has no options until typed, so nothing could bind to it:
  // type the user's own city and pick only the option that is that city.
  let place: Place | null | undefined;
  for (const f of [...flag]) {
    const target = targets.get(f.field_id);
    const descriptor = descriptorById.get(f.field_id);
    const kind = target && comboKinds.get(target.keys[0]);
    if (f.reason !== "low_confidence" || !kind || target.choices.length || !descriptor) continue;
    if (isDemographicField(descriptor) || !isCityQuestion(descriptor.label_text)) continue;
    if (place === undefined) {
      place = await callApi("GET", `/profiles/${profileId}/basics`).then((r) => r.json as Place, () => null);
    }
    const el = controls[target.keys[0]] as HTMLInputElement;
    if (!place || !(await fillCityTypeahead(comboboxOps(el, kind), place))) continue;
    flag.splice(flag.indexOf(f), 1);
    markField(el, "filled", "Auto-filled by ApplyScout — verify before submitting.");
    filled++;
  }

  for (const { field_id, reason } of flag) {
    const el = elementOf(field_id);
    if (!el) continue;
    markField(
      el,
      reason.endsWith("_left_blank") ? "left_blank" : "flagged",
      FLAG_MESSAGES[reason] ?? FLAG_MESSAGES.low_confidence,
    );
  }

  return {
    filled,
    flagged: flag.map((f) => {
      const d = descriptorById.get(f.field_id) ?? files.find((x) => x.descriptor.field_id === f.field_id)?.descriptor;
      return { field_id: f.field_id, reason: f.reason, label: d?.label_text?.trim() || d?.name || null };
    }),
    questions: unansweredQuestions(descriptors, flag),
  };
}

/** Input types (or tag names) of this frame's controls — driverCore.holdsApplicationForm decides. */
export function controlTypes(): string[] {
  return Array.from(document.querySelectorAll<HTMLElement>("input, select, textarea")).map((el) =>
    el instanceof HTMLInputElement ? el.type : el.tagName.toLowerCase(),
  );
}

chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
  // The popup's message reaches every frame (all_frames) and the first answer wins.
  // A frame without the application form (captcha, ads, a careers page around an
  // embedded board) stays out of it: no fill, no alert, no answer.
  const frame = { isTop: window === window.top, controlTypes: controlTypes(), hasIframes: !!document.querySelector("iframe") };
  if (message?.type === "jc:fill-form" && fillsOnPopup(frame)) {
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
