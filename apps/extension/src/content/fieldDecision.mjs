// F11 field-fill decision logic (SPEC.md §3.7). Pure — no DOM access — so it
// can be unit-tested with Node's built-in test runner (`node --test`), zero
// new dependencies. DOM extraction/mutation lives in formFill.content.ts,
// which is thin glue around this and not covered by this test run (needs a
// real browser — not available this session, see WORKLOG).

export const CONFIDENCE_THRESHOLD = 0.75;

// The EEO rule, a SHARED SPEC (latest+37): apps/api (answer_bank.py /
// map_fields.py) implements the identical rule server-side — defense-in-depth, a
// client that only trusted the backend would have a single point of failure.
// NEVER fillable, by anything, under any circumstances. Keep both sides in sync.
//
// A field/group is demographic if (a) its question text contains any keyword
// below (substring, case-insensitive) or the whole word "sex"; or (b) its options
// include a decline option together with >= 1 demographic option, or >= 2
// distinct demographic options. Option matching (norm = lowercase, runs of
// non-alphanumerics -> one space, trimmed): a decline phrase matches when it
// appears whole-word inside the option; a demographic term matches when the
// option equals it or starts with it followed by a space ("White (Not Hispanic
// or Latino)" -> white). Prefix, not "anywhere": a university list holding
// "Texas Woman's University" and "Asian Institute of Technology" is not EEO.
export const DEMOGRAPHIC_LABEL_KEYWORDS = [
  "race", "ethnicity", "ethnic", "hispanic", "latino", "latina", "latinx",
  "gender", "sexual orientation", "transgender", "pronoun", "veteran",
  "disability", "disabled",
];
const SEX_WORD = /\bsex\b/i;

export const DEMOGRAPHIC_DECLINE_OPTIONS = [
  "decline to self-identify", "i don't wish to answer", "prefer not to say",
];
export const DEMOGRAPHIC_OPTIONS = [
  "man", "woman", "male", "female", "non-binary", "white", "black or african american",
  "asian", "hispanic or latino", "native hawaiian", "american indian", "two or more races",
  "protected veteran", "i am a veteran", "not a veteran", "i have a disability", "no disability",
];

const norm = (s) => String(s ?? "").toLowerCase().replace(/[^a-z0-9]+/g, " ").trim();

// Age (latest+48), identical to answer_bank.AGE_LABEL_PHRASES / _AGE_BRACKET — see
// the comment there. Kept out of DEMOGRAPHIC_LABEL_KEYWORDS ("dob" in "job" once
// anything substring-matches that list). Question: normalized label starts with
// "age" or contains a phrase (whole words, optional plural); "18 years of age or
// older" / "over the age of 21" are eligibility, not caught. Options: distinct age
// brackets count as demographic terms; open ends at 18/21 are legal-age thresholds.
export const AGE_LABEL_PHRASES = [
  "age range", "age group", "age bracket", "date of birth", "year of birth", "birth date",
  "birthdate", "birth year", "birthday", "dob", "how old", "your age",
];
const AGE_QUESTION_RE = new RegExp(`^ages?\\b|\\b(?:${AGE_LABEL_PHRASES.join("|")})s?\\b`);
const AGE_BRACKET_RE =
  /^(?:(?:under|over|less than|younger than|older than) (\d\d)|(\d\d) (?:to )?(\d\d)|(\d\d) (?:or|and) (?:older|over|above))(?: years(?: old)?)?$/;
const LEGAL_AGES = new Set([18, 21]);

function isAgeBracket(option) {
  const m = AGE_BRACKET_RE.exec(option);
  if (!m) return false;
  if (m[2]) {
    const lo = Number(m[2]), hi = Number(m[3]);
    return lo >= 16 && lo < hi && hi <= lo + 10;
  }
  const bound = Number(m[1] ?? m[4]);
  return bound >= 16 && !LEGAL_AGES.has(bound);
}

function hasDemographicOptions(options) {
  if (!options?.length) return false;
  const opts = options.map(norm);
  const terms = new Set([
    ...DEMOGRAPHIC_OPTIONS.filter((t) => opts.some((o) => o === norm(t) || o.startsWith(`${norm(t)} `))),
    ...opts.filter(isAgeBracket),
  ]);
  const decline = opts.some((o) => DEMOGRAPHIC_DECLINE_OPTIONS.some((p) => ` ${o} `.includes(` ${norm(p)} `)));
  return terms.size >= 2 || (decline && terms.size >= 1);
}

// Mirrors apps/api/formfill/map_fields.py's ESSAY_LABEL_KEYWORDS. These were in
// the same list as the demographic keywords until the answer bank (ADR-015)
// existed, and lumping them together was wrong: an essay question is unfillable
// only for as long as the user has never written the answer. The backend now
// returns `maps_to: "answer_bank"` with the user's own text for these, so
// flagging them here before looking at the mapping would throw that away and
// stop the run for a question that was already answered.
export const ESSAY_LABEL_KEYWORDS = [
  "why do you want to work", "why are you interested",
];

// The union, kept because "nothing here is fillable from profile data alone" is
// still a true and useful statement.
export const FORBIDDEN_LABEL_KEYWORDS = [
  ...DEMOGRAPHIC_LABEL_KEYWORDS, ...ESSAY_LABEL_KEYWORDS,
];

function matchesAny(labelText, keywords) {
  if (!labelText) return false;
  const lower = labelText.toLowerCase();
  return keywords.some((keyword) => lower.includes(keyword));
}

// The unconditional rail. A true here is not "flag for review" — it is "no
// value may ever be written into this field".
// Whole words with an optional plural "s", mirroring answer_bank.is_demographic_field:
// a substring match treated "embrace" as "race" and stopped runs on it.
const DEMOGRAPHIC_KEYWORD_RE = new RegExp(
  `(?<![a-z])(?:${DEMOGRAPHIC_LABEL_KEYWORDS.map((k) => k.replace(/ /g, "\\s+")).join("|")})s?(?![a-z])`,
  "i",
);

export function isDemographicLabel(labelText) {
  return (
    !!labelText &&
    (DEMOGRAPHIC_KEYWORD_RE.test(labelText) || SEX_WORD.test(labelText) || AGE_QUESTION_RE.test(norm(labelText)))
  );
}

// The question text OR the options: Ashby's EEO radios carry no question text the
// label rail can see, only "Man" / "Woman" / "White".
export function isDemographicField(field) {
  return isDemographicLabel(field.label_text) || hasDemographicOptions(field.options);
}

export function isEssayLabel(labelText) {
  return matchesAny(labelText, ESSAY_LABEL_KEYWORDS);
}

export function isForbiddenLabel(labelText) {
  return isDemographicLabel(labelText) || isEssayLabel(labelText);
}

// fields: FieldDescriptor[] ({field_id, label_text, ...})
// mappings: FieldMapping[] from POST /extension/map-fields
// returns { fill: [{field_id, value}], flag: [{field_id, reason}] }
export function decideFieldActions(fields, mappings) {
  const mappingById = new Map(mappings.map((m) => [m.field_id, m]));
  const fill = [];
  const flag = [];
  // A radio group is required if any member is (that is how HTML validates it).
  const requiredRadioNames = new Set(
    fields.filter((f) => f.input_type === "radio" && f.name && f.required).map((f) => f.name),
  );

  for (const field of fields) {
    // Unconditional, and before anything else looks at the mapping: never
    // filled. Whether it blocks depends only on whether the form requires it.
    if (isDemographicField(field)) {
      const required =
        field.required || (field.input_type === "radio" && requiredRadioNames.has(field.name));
      flag.push({
        field_id: field.field_id,
        reason: required ? "demographic_required" : "demographic_left_blank",
      });
      continue;
    }
    const mapping = mappingById.get(field.field_id);
    if (!mapping || mapping.maps_to === "unknown" || mapping.confidence < CONFIDENCE_THRESHOLD || !mapping.value) {
      // An essay question with no answer gets its own reason rather than
      // "low_confidence": it is the one flag the user can clear permanently, by
      // writing the answer once into the answer bank.
      const reason = isEssayLabel(field.label_text) ? "essay_no_stored_answer" : "low_confidence";
      flag.push({ field_id: field.field_id, reason });
      continue;
    }
    fill.push({ field_id: field.field_id, value: mapping.value });
  }

  return { fill, flag };
}

// --- what stops a run --------------------------------------------------------

// Flag reasons that stop auto-apply at needs_human. `demographic_left_blank` is
// deliberately absent: an optional EEO question is left empty (never answered,
// not even "Decline to self-identify" — picking that is answering) and the form
// is submitted without it. Only a REQUIRED one stops the run, since the form
// cannot go without an answer only the user may give.
export const NEEDS_USER_REASONS = new Set([
  "demographic_required",
  "essay_no_stored_answer",
  "low_confidence",
  "file_upload", // a required upload that isn't the resume
]);

// apps/api/needs_input.py sets demographic_left_blank on /\bdemographic\b/, and
// "_" is a word char, so the raw reason code alone would not match.
const REASON_TEXT = {
  demographic_required: "required demographic self-identification question",
};

export function needsHumanReason(blocking) {
  return (
    `${blocking.length} field(s) need your input and were not answered: ` +
    blocking.map((f) => REASON_TEXT[f.reason] ?? f.reason).join(", ")
  );
}

// --- file inputs --------------------------------------------------------------

// Letter-bounded (not \b, which treats "_" as a word char and misses
// "cv_upload") so "cv" inside "cvs" or "cvv" is not a CV. Checked against the
// label, name and id together, because ATS upload widgets often hide the real
// <input type=file> and only its name/id says what it is for.
const RESUME_UPLOAD = /(?<![a-z])(resume|résumé|cv|curriculum vitae)(?![a-z])/i;
const COVER_LETTER_UPLOAD = /cover.?letter/i;

// "resume" -> attach the generated resume docx
// "flag"   -> a required upload we cannot satisfy: the user has to finish it
// "skip"   -> optional and not ours to fill; leaving it empty is fine
export function classifyFileInput(field) {
  const text = [field.label_text, field.name, field.dom_id].filter(Boolean).join(" ");
  // Cover letter wins: "attach with your resume" on a cover-letter field must not
  // put the resume in the wrong slot.
  if (!COVER_LETTER_UPLOAD.test(text) && RESUME_UPLOAD.test(text)) return "resume";
  return field.required ? "flag" : "skip";
}

// --- questions for the answer bank -------------------------------------------

// Flags the user can clear by writing an answer once. Demographic never (it is
// never answerable); file_upload is not a text question.
const ANSWERABLE_REASONS = new Set(["essay_no_stored_answer", "low_confidence"]);

// The labels of flagged fields, verbatim, for the backend to hold as the
// questions this run stopped on (POST /submission-result unanswered_questions).
export function unansweredQuestions(fields, flag) {
  const fieldById = new Map(fields.map((f) => [f.field_id, f]));
  return flag
    .filter((f) => ANSWERABLE_REASONS.has(f.reason))
    .map((f) => fieldById.get(f.field_id))
    .filter((field) => field && !isDemographicField(field))
    .map((field) => field.label_text?.trim())
    .filter(Boolean);
}

// --- extraction: what the page's controls ARE (LIVE-FORM-TEST #8, #10, #15) ---
//
// formFill.content.ts reads each input/select/textarea into a plain record (see
// fieldDecision.d.mts RawControl); everything decided about those records lives
// here so it is tested without a browser.

// One Lever <select> had 3,302 options (a 122 KB prompt). The LLM sees the first
// 50; filling still matches against every option (targets keep them all).
export const MAX_OPTIONS = 50;

const SKIP_TYPES = new Set(["hidden", "submit", "button", "reset", "image"]);
const CAPTCHA = /g-recaptcha|h-captcha|cf-turnstile/i;
const HONEYPOT = /honey.?pot/i;

function isJunk(r) {
  if (SKIP_TYPES.has(r.type)) return true;
  if (CAPTCHA.test(`${r.name ?? ""} ${r.dom_id ?? ""}`) || HONEYPOT.test(`${r.name ?? ""} ${r.dom_id ?? ""}`)) return true;
  // react-select: its visible control is the role=combobox input; the rest
  // (requiredInput, hidden value inputs) are internals.
  if (r.inReactSelect && r.role !== "combobox") return true;
  if (r.type === "file") return false; // routinely display:none behind a styled button
  // Styled radios/checkboxes hide the native input and show the label.
  if (r.type === "radio" || r.type === "checkbox") return !r.visible && !r.labelVisible;
  return !r.visible;
}

// Radios (and checkboxes sharing a name) become ONE descriptor per group, labelled
// with the question and listing the option labels — not one "Yes"/"Man" per input.
// returns { descriptors, files: [{descriptor, key}], targets: Map<field_id,
// {input_type, keys, choices}> } — keys are the raw records' keys, for the glue to
// find the elements again.
export function buildDescriptors(raws) {
  const units = [];
  const groups = new Map();
  for (const r of raws) {
    if (isJunk(r)) continue;
    const groupKey = (r.type === "radio" || r.type === "checkbox") && r.name ? `${r.type}:${r.name}` : null;
    if (groupKey && groups.has(groupKey)) {
      groups.get(groupKey).push(r);
      continue;
    }
    const unit = [r];
    units.push(unit);
    if (groupKey) groups.set(groupKey, unit);
  }

  const descriptors = [];
  const files = [];
  const targets = new Map();
  for (const members of units) {
    const [first] = members;
    const field_id = `jc-field-${first.key}`;
    const isSelect = first.tag === "SELECT";
    const isChoice = first.type === "radio" || first.type === "checkbox";
    const isGroup = first.type === "radio" || (first.type === "checkbox" && members.length > 1);
    // A combobox whose menu was opened and read (combobox.mjs) is a select to the
    // backend, so its answer is bound to one of these labels; it is still filled
    // through the widget (target input_type "combobox").
    const isReadCombobox = first.role === "combobox" && first.options.length > 0;
    const choices = isSelect || isReadCombobox
      ? first.options
      : isChoice
        ? members.map((m) => ({ label: m.label ?? m.value, value: m.value }))
        : [];
    const input_type = isSelect
      ? "select"
      : first.tag === "TEXTAREA"
        ? "textarea"
        : first.role === "combobox"
          ? "combobox"
          : first.type || "text";
    const descriptor = {
      field_id,
      label_text: (isGroup ? first.question : first.label ?? first.question) ?? null,
      input_type: isReadCombobox ? "select" : input_type,
      options: isSelect || isGroup || isReadCombobox ? choices.slice(0, MAX_OPTIONS).map((c) => c.label) : [],
      required: members.some((m) => m.required),
      autocomplete: first.autocomplete,
      name: first.name,
      dom_id: first.dom_id,
    };
    if (first.type === "file") {
      files.push({ descriptor, key: first.key });
      continue;
    }
    descriptors.push(descriptor);
    targets.set(field_id, { input_type, keys: members.map((m) => m.key), choices });
  }
  return { descriptors, files, targets };
}

// The question a group/unlabeled field belongs to: the nearest preceding text
// (texts in document order, nearest last) that has letters and isn't one of the
// options themselves. Trailing required markers ("*", "✱") are dropped.
export function pickQuestionText(texts, optionLabels) {
  const options = new Set(optionLabels.map(norm));
  for (let i = texts.length - 1; i >= 0; i--) {
    const text = String(texts[i]).replace(/[\s*✱]+$/u, "").trim();
    if (/\p{L}/u.test(text) && !options.has(norm(text))) return text;
  }
  return null;
}

// --- mutation plans (LIVE-FORM-TEST #7) ----------------------------------------

const AFFIRMATIVE = /^(yes|true|y|on|checked)$/i;
const NEGATIVE = /^(no|false|n|off|unchecked)$/i;

// How to put `value` into a target, or null when it can't be put there honestly
// (the caller flags low_confidence). Never writes .value into a radio/checkbox;
// choices match exactly (case-insensitive, trimmed) on label or value — "San
// Francisco" is not an answer to a Yes/No question.
export function planFill(target, value) {
  const { input_type, keys, choices } = target;
  const want = String(value).trim().toLowerCase();
  // Options come from opening the menu at extraction; none read = nothing to
  // match against, so never typed into.
  if (input_type === "combobox") {
    const i = choices.findIndex((c) => String(c.label).trim().toLowerCase() === want);
    return i < 0 ? null : { kind: "combobox", key: keys[0], label: choices[i].label };
  }
  if (input_type === "checkbox" && keys.length === 1) {
    if (AFFIRMATIVE.test(want)) return { kind: "check", key: keys[0] };
    if (NEGATIVE.test(want)) return { kind: "none" };
    return null;
  }
  if (input_type === "select" || input_type === "radio" || input_type === "checkbox") {
    const i = choices.findIndex((c) =>
      [c.label, c.value].some((s) => s != null && String(s).trim().toLowerCase() === want),
    );
    if (i < 0) return null;
    return input_type === "select"
      ? { kind: "select", key: keys[0], value: choices[i].value }
      : { kind: "check", key: keys[i] };
  }
  return { kind: "text", key: keys[0], value };
}

// React (Greenhouse, Ashby) tracks an input's value with an own property on the
// node; assigning through it makes React swallow the next input event, so its
// state stays "" and the next render wipes the field (LIVE-FORM-TEST #3). The
// prototype's native setter bypasses the tracker.
export function setNativeValue(el, value) {
  let proto = Object.getPrototypeOf(el);
  let setter;
  while (proto && !(setter = Object.getOwnPropertyDescriptor(proto, "value")?.set)) {
    proto = Object.getPrototypeOf(proto);
  }
  if (setter) setter.call(el, value);
  else el.value = value;
  el.dispatchEvent(new Event("input", { bubbles: true }));
  el.dispatchEvent(new Event("change", { bubbles: true }));
}
