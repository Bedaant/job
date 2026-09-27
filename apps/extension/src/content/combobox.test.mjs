import { test } from "node:test";
import assert from "node:assert/strict";

import {
  COMBOBOX_MAX_WIDGETS,
  comboboxKind,
  fillCombobox,
  matchOption,
  optionLabels,
  readAllOptions,
  readOptions,
} from "./combobox.mjs";

// --- widget kind, from attribute snapshots taken on the real pages ------------

const snap = (over = {}) => ({
  tag: "INPUT", role: "combobox", visible: true, inReactSelect: false,
  ariaAutocomplete: null, ariaHaspopup: null, ariaControls: null, ...over,
});

test("comboboxKind: Greenhouse react-select, generic ARIA listbox comboboxes, and not-a-widget", () => {
  // Greenhouse #country / question_*: aria-autocomplete=list aria-haspopup=true, no aria-controls until open
  assert.equal(comboboxKind(snap({ inReactSelect: true, ariaAutocomplete: "list", ariaHaspopup: "true" })), "react-select");
  // Ashby location typeahead: role=combobox aria-autocomplete=list, no react-select markup
  assert.equal(comboboxKind(snap({ ariaAutocomplete: "list" })), "listbox");
  assert.equal(comboboxKind(snap({ ariaControls: "menu-1" })), "listbox");
  assert.equal(comboboxKind(snap({ ariaHaspopup: "listbox" })), "listbox");
  assert.equal(comboboxKind(snap({ role: null, inReactSelect: true })), null); // react-select internals
  assert.equal(comboboxKind(snap({ ariaAutocomplete: "none" })), null); // a combobox with no popup
  // intl-tel-input's phone-country "Search": role=combobox but hidden
  assert.equal(comboboxKind(snap({ visible: false, ariaControls: "iti-0__country-listbox" })), null);
  assert.equal(comboboxKind(snap({ tag: "SELECT", ariaControls: "x" })), null);
});

// --- options ------------------------------------------------------------------

test("optionLabels: whitespace collapsed, empties and duplicates dropped", () => {
  assert.deepEqual(optionLabels(["  United States\n +1 ", "Yes", "", "Yes", null, "No"]), ["United States +1", "Yes", "No"]);
});

test("matchOption: exact (case/space-insensitive) or -1; no partial or prefix match", () => {
  const labels = ["Yes", "No", "United States +1"];
  assert.equal(matchOption(labels, " yes"), 0);
  assert.equal(matchOption(labels, "united  states +1"), 2);
  assert.equal(matchOption(labels, "United States"), -1);
  assert.equal(matchOption(labels, "Y"), -1);
  assert.equal(matchOption(labels, ""), -1);
});

// --- reading a menu: open, read, ALWAYS close, never change the value ---------

function fakeWidget({ options = ["Yes", "No"], failRead = false } = {}) {
  const calls = [];
  return {
    calls,
    open: async () => calls.push("open"),
    waitForOptions: async () => {
      calls.push("read");
      if (failRead) throw new Error("boom");
      return options;
    },
    close: async () => calls.push("close"),
  };
}

test("readOptions: open -> read -> close, and returns the cleaned labels", async () => {
  const w = fakeWidget({ options: [" Yes ", "No"] });
  assert.deepEqual(await readOptions(w), ["Yes", "No"]);
  assert.deepEqual(w.calls, ["open", "read", "close"]);
});

test("readOptions: the menu is closed even when reading throws; the result is no options", async () => {
  const w = fakeWidget({ failRead: true });
  assert.deepEqual(await readOptions(w), []);
  assert.deepEqual(w.calls, ["open", "read", "close"]);
});

test("readAllOptions: stops at the widget cap and the time budget; the rest stay unread", async () => {
  const widgets = Array.from({ length: COMBOBOX_MAX_WIDGETS + 5 }, () => fakeWidget());
  const read = await readAllOptions(widgets, { now: () => 0 });
  assert.equal(read.filter(Boolean).length, COMBOBOX_MAX_WIDGETS);
  assert.equal(read[COMBOBOX_MAX_WIDGETS], null);
  assert.equal(widgets[COMBOBOX_MAX_WIDGETS].calls.length, 0);

  let t = 0;
  const slow = Array.from({ length: 5 }, () => ({ ...fakeWidget(), open: async () => { t += 1000; } }));
  const timed = await readAllOptions(slow, { now: () => t, totalMs: 2500 });
  assert.deepEqual(timed.map((r) => r !== null), [true, true, true, false, false]);
});

// --- filling: click the widget's own option, verify, never leave typed text ---

function fillWidget({ rendered = ["Yes", "No"], afterType = null, canType = true, clickWorks = true, shown = "" } = {}) {
  const state = { calls: [], text: "", shown, menu: rendered };
  const opts = () => (state.text && afterType ? afterType : state.menu);
  Object.assign(state, {
    canType,
    displayed: () => state.shown,
    open: async () => state.calls.push("open"),
    findOption: async (label) => {
      state.calls.push(`find:${label}`);
      const i = matchOption(opts(), label);
      return i < 0 ? null : { label: opts()[i] };
    },
    type: async (text) => { state.calls.push(`type:${text}`); state.text = text; },
    click: async (opt) => {
      state.calls.push(`click:${opt.label}`);
      if (clickWorks) { state.shown = opt.label; state.text = ""; }
    },
    clear: async () => { state.calls.push("clear"); state.text = ""; },
    close: async () => state.calls.push("close"),
  });
  return state;
}

test("fillCombobox: opens, clicks the exact option, closes, verifies the shown value", async () => {
  const w = fillWidget();
  assert.equal(await fillCombobox(w, "Yes"), true);
  assert.deepEqual(w.calls, ["open", "find:Yes", "click:Yes", "close"]);
  assert.equal(w.shown, "Yes");
});

test("fillCombobox: already showing the option = nothing touched", async () => {
  const w = fillWidget({ shown: "Yes" });
  assert.equal(await fillCombobox(w, "yes"), true);
  assert.deepEqual(w.calls, []);
});

test("fillCombobox: an option not rendered is searched for by typing, then clicked", async () => {
  const w = fillWidget({ rendered: [], afterType: ["San Francisco, CA"] });
  assert.equal(await fillCombobox(w, "San Francisco, CA"), true);
  assert.deepEqual(w.calls, ["open", "find:San Francisco, CA", "type:San Francisco, CA", "find:San Francisco, CA", "click:San Francisco, CA", "close"]);
  assert.equal(w.text, "");
});

test("fillCombobox: no matching option after typing -> typed text cleared, closed, false", async () => {
  const w = fillWidget({ rendered: [], afterType: ["San Francisco, CA"] });
  assert.equal(await fillCombobox(w, "San Francisco"), false);
  assert.equal(w.text, "");
  assert.deepEqual(w.calls.slice(-2), ["clear", "close"]);
  assert.ok(!w.calls.some((c) => c.startsWith("click")));
});

test("fillCombobox: a non-searchable widget is never typed into", async () => {
  const w = fillWidget({ rendered: ["Yes", "No"], canType: false });
  assert.equal(await fillCombobox(w, "Maybe"), false);
  assert.ok(!w.calls.some((c) => c.startsWith("type")));
  assert.deepEqual(w.calls.at(-1), "close");
});

test("fillCombobox: the click didn't take (shown value differs) -> false, typed text cleared", async () => {
  const w = fillWidget({ rendered: [], afterType: ["Yes"], clickWorks: false });
  assert.equal(await fillCombobox(w, "Yes"), false);
  assert.equal(w.text, "");
  assert.ok(w.calls.includes("clear"));
});

test("fillCombobox: the menu is closed even if a step throws", async () => {
  const w = fillWidget();
  w.click = async () => { throw new Error("detached"); };
  assert.equal(await fillCombobox(w, "Yes"), false);
  assert.equal(w.calls.at(-1), "close");
});

test("fillCombobox: a typeahead showing our own typed text is NOT a selection", async () => {
  // the input's value is what it displays: typing "Yes" makes it "show" Yes with nothing chosen
  const w = fillWidget({ rendered: [], afterType: [] });
  w.displayed = () => w.text;
  assert.equal(await fillCombobox(w, "Yes"), false);
  assert.equal(w.text, "");
});
