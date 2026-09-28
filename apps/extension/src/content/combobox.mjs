// Custom "combobox" dropdowns (react-select on Greenhouse, ARIA listbox typeaheads
// elsewhere): their options exist in the DOM only while the menu is open. Pure
// sequencing and matching here, tested with node --test; formFill.content.ts
// supplies the DOM operations (open / read / click / close) as plain functions.
//
// Verified live on Greenhouse (2026-09-27): a dispatched keydown ALONE does not
// open the menu (Greenhouse opens it on key/mouse UP); keydown+keyup ArrowDown
// does. Escape keeps it open; Escape + blur closes it. Clicking the
// [role=option] selects it through react-select's own handler.

export const COMBOBOX_MAX_WIDGETS = 40;
export const COMBOBOX_WAIT_MS = 300; // per menu, for its options to render
export const COMBOBOX_TYPE_WAIT_MS = 1000; // an async (typeahead) search round-trip
export const COMBOBOX_TOTAL_MS = 8000; // all menus read in one extraction

// Resolves with probe()'s first truthy answer, or its last one after `ms`. Wakes on
// onChange(cb) -> unsubscribe (a MutationObserver in the page), never on a polling
// timer: the driver's tab is a background tab, where Chrome runs timers at most once
// a second (measured live: ~1.9 s per menu instead of ~0.16 s, so the 8 s read budget
// covered 5 of Anthropic's 8 dropdowns). Only the give-up timer is still throttled.
export function waitFor(probe, ms, onChange) {
  const hit = probe();
  if (hit) return Promise.resolve(hit);
  return new Promise((resolve) => {
    const done = () => {
      const v = probe();
      if (!v && !timedOut) return;
      clearTimeout(timer);
      stop();
      resolve(v);
    };
    let timedOut = false;
    const timer = setTimeout(() => ((timedOut = true), done()), ms);
    const stop = onChange(done);
  });
}

// "react-select" | "listbox" | null (not a menu widget we can open and read).
// s: {tag, role, visible, inReactSelect, ariaAutocomplete, ariaHaspopup, ariaControls}
export function comboboxKind(s) {
  if (s.tag !== "INPUT" || s.role !== "combobox" || !s.visible) return null;
  if (s.inReactSelect) return "react-select";
  const popup =
    ["list", "both"].includes(s.ariaAutocomplete ?? "") ||
    ["listbox", "true"].includes(s.ariaHaspopup ?? "") ||
    !!s.ariaControls;
  return popup ? "listbox" : null;
}

const norm = (s) => String(s ?? "").replace(/\s+/g, " ").trim();
const key = (s) => norm(s).toLowerCase();

export function optionLabels(texts) {
  return [...new Set(texts.map(norm).filter(Boolean))];
}

// Exact, case- and whitespace-insensitive. The backend already bound its value to
// one of the options it was sent; anything else is not an answer to this question.
export function matchOption(labels, value) {
  const want = key(value);
  return want ? labels.findIndex((l) => key(l) === want) : -1;
}

// ops: {open(), waitForOptions() -> string[], close()}. The menu is always closed
// again; nothing is selected or typed.
export async function readOptions(ops) {
  let texts = [];
  try {
    await ops.open();
    texts = await ops.waitForOptions();
  } catch {
    texts = [];
  } finally {
    await ops.close();
  }
  return optionLabels(texts);
}

// One read per widget, in order, until the widget cap or the time budget runs out:
// the rest stay null (sent without options, so never filled — flagged instead).
export async function readAllOptions(
  widgets,
  { now = Date.now, maxWidgets = COMBOBOX_MAX_WIDGETS, totalMs = COMBOBOX_TOTAL_MS } = {},
) {
  const start = now();
  const out = [];
  for (const w of widgets) {
    if (out.filter(Boolean).length >= maxWidgets || now() - start >= totalMs) out.push(null);
    else out.push(await readOptions(w));
  }
  return out;
}

// ops: {displayed() -> string, open(), findOption(label) -> handle|null, canType,
// type(text), click(handle), clear(), close()}.
// true only when an option was clicked AND the widget then SHOWS `label` (a
// typeahead's input showing our own typed text is not a selection). Search text
// we typed is cleared unless it became the selection.
export async function fillCombobox(ops, label) {
  const shows = () => key(ops.displayed()) === key(label);
  if (shows()) return true;
  let typed = false;
  let clicked = false;
  try {
    await ops.open();
    let option = await ops.findOption(label);
    if (!option && ops.canType) {
      typed = true;
      await ops.type(label);
      option = await ops.findOption(label);
    }
    if (option) {
      await ops.click(option);
      clicked = true;
    }
  } catch {
    // fall through: cleared, closed, reported false
  } finally {
    try {
      if (typed && !(clicked && shows())) await ops.clear();
    } finally {
      await ops.close();
    }
  }
  // After OUR click only: a widget may show just the option's trailing words
  // (Greenhouse's phone country: "United States +1" shows "+1"). Never trusted
  // before the click — "+1" is Canada too.
  const showsTail = () => {
    const shown = key(ops.displayed());
    return shown !== "" && key(label).endsWith(" " + shown);
  };
  return clicked && (shows() || showsTail());
}
