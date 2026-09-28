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

// --- a location typeahead: no options until typed (Greenhouse "Location (City)") --

// Where the applicant is, not where they'd like to work.
export function isCityQuestion(label) {
  return /^\s*(current\s+)?(location|city)\b/i.test(label ?? "");
}

const countryName = (code) => {
  try {
    return new Intl.DisplayNames(["en"], { type: "region" }).of(String(code).toUpperCase());
  } catch {
    return null;
  }
};

// A region fits when it is spelled the same, or is a US state code for that state
// ("CA" -> California; "MA" is Massachusetts, never Maryland).
// ponytail: US codes only; elsewhere the region must be written out in full.
const US_STATES = Object.fromEntries(
  ("al alabama|ak alaska|az arizona|ar arkansas|ca california|co colorado|ct connecticut|" +
    "de delaware|dc district of columbia|fl florida|ga georgia|hi hawaii|id idaho|il illinois|" +
    "in indiana|ia iowa|ks kansas|ky kentucky|la louisiana|me maine|md maryland|ma massachusetts|" +
    "mi michigan|mn minnesota|ms mississippi|mo missouri|mt montana|ne nebraska|nv nevada|" +
    "nh new hampshire|nj new jersey|nm new mexico|ny new york|nc north carolina|nd north dakota|" +
    "oh ohio|ok oklahoma|or oregon|pa pennsylvania|ri rhode island|sc south carolina|" +
    "sd south dakota|tn tennessee|tx texas|ut utah|vt vermont|va virginia|wa washington|" +
    "wv west virginia|wi wisconsin|wy wyoming")
    .split("|")
    .map((s) => [s.slice(0, 2), s.slice(3)]),
);
const regionFits = (part, region) => {
  const r = key(region), p = key(part);
  return r !== "" && (r === p || US_STATES[r] === p);
};

// The one option that is the user's city, e.g. "San Francisco, California, United
// States" for {city: "San Francisco", region: "CA", country_code: "US"}: its first
// part is the city and every other part is the user's region or country (the
// country must be among them when the profile has one). Zero or several -> -1.
export function matchCityOption(labels, { city, region, country_code } = {}) {
  const want = key(city);
  if (!want) return -1;
  const country = country_code ? [key(country_code), key(countryName(country_code))] : [];
  const hits = labels.flatMap((l, i) => {
    const [first, ...rest] = String(l).split(",").map(key);
    const isCountry = (p) => country.includes(p);
    const ok =
      first === want &&
      rest.every((p) => isCountry(p) || regionFits(p, region)) &&
      (rest.length === 0 || !country.length || rest.some(isCountry));
    return ok ? [i] : [];
  });
  return hits.length === 1 ? hits[0] : -1;
}

// ops: FillOps + waitForOptions() -> string[] (after typing). Types the user's city,
// picks only matchCityOption's option through fillCombobox (click + verify), and
// clears the typed text unless that pick shows.
export async function fillCityTypeahead(ops, place) {
  if (!key(place?.city) || !ops.canType) return false;
  let picked = false;
  try {
    await ops.open();
    await ops.type(norm(place.city));
    const labels = optionLabels(await ops.waitForOptions());
    const i = matchCityOption(labels, place);
    if (i >= 0) picked = await fillCombobox(ops, labels[i]);
  } catch {
    picked = false;
  } finally {
    try {
      if (!picked) await ops.clear();
    } finally {
      await ops.close();
    }
  }
  return picked;
}
