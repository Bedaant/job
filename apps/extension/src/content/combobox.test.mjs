import { mock, test } from "node:test";
import assert from "node:assert/strict";

import {
  COMBOBOX_MAX_WIDGETS,
  comboboxKind,
  fillCityTypeahead,
  fillCombobox,
  isCityQuestion,
  matchCityOption,
  matchOption,
  optionLabels,
  readAllOptions,
  readOptions,
  waitFor,
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
    waitForOptions: async () => opts(),
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

// Found live (embedded Greenhouse, auto-apply): the phone-country select's option is
// "United States +1", but once chosen the widget shows only "+1". The exact check
// called that a failed fill: a required field flagged low_confidence on every pass.
test("fillCombobox: a widget showing the chosen option's trailing words (dial code) is a selection", async () => {
  const w = fillWidget({ rendered: ["United States +1", "Canada +1"], shown: "+1" });
  w.click = async (opt) => { w.calls.push(`click:${opt.label}`); w.shown = opt.label.split(" ").at(-1); };
  assert.equal(await fillCombobox(w, "United States +1"), true);
  assert.ok(w.calls.includes("click:United States +1"), "a '+1' shown before the click is not trusted: Canada is +1 too");
});

test("fillCombobox: a shown value that is not the chosen option's tail is still a failure", async () => {
  const w = fillWidget({ rendered: ["United States +1"], shown: "+44", clickWorks: false });
  assert.equal(await fillCombobox(w, "United States +1"), false);
  const v = fillWidget({ rendered: ["United States +1"], shown: "States", clickWorks: false });
  assert.equal(await fillCombobox(v, "United States +1"), false);
});

test("fillCombobox: a typeahead showing our own typed text is NOT a selection", async () => {
  // the input's value is what it displays: typing "Yes" makes it "show" Yes with nothing chosen
  const w = fillWidget({ rendered: [], afterType: [] });
  w.displayed = () => w.text;
  assert.equal(await fillCombobox(w, "Yes"), false);
  assert.equal(w.text, "");
});

// --- a typeahead with no options until typed: the user's own city -------------
// Options as Greenhouse's "Location (City)" returned them live for "San Francisco".
const SF = [
  "San Francisco, California, United States",
  "San Francisco de Macorís, Duarte, Dominican Republic",
  "San Francisco, Agusan del Sur, Philippines",
  "San Francisco De Borja, Lima, Peru",
  "San Francisco, Cebu, Philippines",
  "South San Francisco, California, United States",
];
const HOME = { city: "San Francisco", region: "CA", country_code: "US" };

test("isCityQuestion: a question that opens with location/city, not a preference", () => {
  for (const l of ["Location (City)*", "City", "Current location", "Location"]) assert.ok(isCityQuestion(l), l);
  for (const l of ["What is your preferred office location?*", "Which city would you like to work in?", "Country*", "", null]) {
    assert.ok(!isCityQuestion(l), String(l));
  }
});

test("matchCityOption: only the user's city in the user's region and country", () => {
  assert.equal(matchCityOption(SF, HOME), 0);
  assert.equal(matchCityOption(SF, { ...HOME, region: "California" }), 0);
  assert.equal(matchCityOption(["San Francisco"], HOME), 0);
  assert.equal(matchCityOption(SF, { ...HOME, country_code: "PH", region: "Cebu" }), 4);
});

test("matchCityOption: a different city, region or country is never picked", () => {
  assert.equal(matchCityOption(SF.slice(1), HOME), -1); // only South SF and foreign ones
  assert.equal(matchCityOption(["Springfield, Illinois, United States"], { city: "Springfield", region: "MO", country_code: "US" }), -1);
  assert.equal(matchCityOption(["London, Canada"], { city: "London", region: "CA", country_code: "US" }), -1);
  assert.equal(matchCityOption(SF, { city: "San Francisco", country_code: "PH" }), -1); // two in PH, no region
  assert.equal(matchCityOption(SF, { city: "", region: "CA", country_code: "US" }), -1);
  assert.equal(matchCityOption(SF, { city: "San Francisco" }), -1); // qualifiers can't be checked
});

test("fillCityTypeahead: types the city, clicks the one matching option, verifies", async () => {
  const w = fillWidget({ rendered: [], afterType: SF });
  assert.equal(await fillCityTypeahead(w, HOME), true);
  assert.equal(w.shown, SF[0]);
  assert.ok(w.calls.includes("type:San Francisco"));
  assert.ok(w.calls.includes(`click:${SF[0]}`));
  assert.ok(!w.calls.includes("clear"));
  assert.equal(w.calls.at(-1), "close");
});

test("fillCityTypeahead: no unambiguous match -> nothing clicked, typed text cleared", async () => {
  const w = fillWidget({ rendered: [], afterType: SF.slice(1) });
  assert.equal(await fillCityTypeahead(w, HOME), false);
  assert.ok(!w.calls.some((c) => c.startsWith("click")));
  assert.equal(w.text, "");
  assert.deepEqual(w.calls.slice(-2), ["clear", "close"]);
});

test("fillCityTypeahead: no city in the profile, or a read-only widget -> never typed into", async () => {
  for (const [place, canType] of [[{ region: "CA", country_code: "US" }, true], [{}, true], [HOME, false]]) {
    const w = fillWidget({ rendered: [], afterType: SF, canType });
    assert.equal(await fillCityTypeahead(w, place), false);
    assert.ok(!w.calls.some((c) => c.startsWith("type") || c.startsWith("click")));
  }
});

test("fillCityTypeahead: the click didn't take -> false, typed text cleared", async () => {
  const w = fillWidget({ rendered: [], afterType: SF, clickWorks: false });
  assert.equal(await fillCityTypeahead(w, HOME), false);
  assert.equal(w.text, "");
});

// Review: "MA" must never fit "Maryland" (the old letter-order check did). A wrong
// state is wrong data sent to an employer.
test("matchCityOption: a state code only matches its own state", () => {
  const ma = { city: "Springfield", region: "MA", country_code: "US" };
  assert.equal(matchCityOption(["Springfield, Maryland, United States"], ma), -1);
  assert.equal(matchCityOption(["Springfield, Maryland, United States", "Springfield, Massachusetts, United States"], ma), 1);
  assert.equal(matchCityOption(["Portland, Oregon, United States"], { city: "Portland", region: "ME", country_code: "US" }), -1);
  assert.equal(matchCityOption(["San Francisco, California, United States"], { city: "San Francisco", region: "CA", country_code: "US" }), 0);
});

// --- waitFor: the driver's tab is a background tab, where Chrome runs timers at most
// once a second (measured live: a 25 ms timer took ~1000 ms). A wait must wake on
// the DOM change it is waiting for, not on a timer tick.

function fakeDom() {
  const subs = new Set();
  return {
    onChange: (cb) => (subs.add(cb), () => subs.delete(cb)),
    change: () => subs.forEach((cb) => cb()),
    subs,
  };
}

test("waitFor resolves on the DOM change, with no timer firing", async () => {
  mock.timers.enable({ apis: ["setTimeout"] }); // no timer fires unless ticked
  try {
    const dom = fakeDom();
    let open = false;
    const waiting = waitFor(() => open, 150, dom.onChange);
    open = true;
    dom.change();
    assert.equal(await waiting, true);
    assert.equal(dom.subs.size, 0, "stops listening once resolved");
  } finally {
    mock.timers.reset();
  }
});

test("waitFor gives up after ms with the probe's last answer, and stops listening", async () => {
  mock.timers.enable({ apis: ["setTimeout"] });
  try {
    const dom = fakeDom();
    const waiting = waitFor(() => null, 150, dom.onChange);
    dom.change(); // an unrelated change: still nothing
    mock.timers.tick(150);
    assert.equal(await waiting, null);
    assert.equal(dom.subs.size, 0);
  } finally {
    mock.timers.reset();
  }
});

test("waitFor answers at once when the probe already holds", async () => {
  const dom = fakeDom();
  assert.equal(await waitFor(() => "x", 150, dom.onChange), "x");
  assert.equal(dom.subs.size, 0);
});
