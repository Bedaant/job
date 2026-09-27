import { test } from "node:test";
import assert from "node:assert/strict";

import {
  CONFIDENCE_THRESHOLD,
  DEMOGRAPHIC_LABEL_KEYWORDS,
  ESSAY_LABEL_KEYWORDS,
  FORBIDDEN_LABEL_KEYWORDS,
  NEEDS_USER_REASONS,
  classifyFileInput,
  needsHumanReason,
  decideFieldActions,
  isDemographicLabel,
  isForbiddenLabel,
  unansweredQuestions,
  MAX_OPTIONS,
  buildDescriptors,
  isDemographicField,
  pickQuestionText,
  planFill,
  setNativeValue,
} from "./fieldDecision.mjs";

test("confidence threshold is 0.75", () => {
  assert.equal(CONFIDENCE_THRESHOLD, 0.75);
});

test("isForbiddenLabel matches demographic and essay questions case-insensitively", () => {
  assert.equal(isForbiddenLabel("What is your Gender?"), true);
  assert.equal(isForbiddenLabel("WHY DO YOU WANT TO WORK HERE"), true);
  assert.equal(isForbiddenLabel("Email address"), false);
  assert.equal(isForbiddenLabel(null), false);
  assert.equal(isForbiddenLabel(undefined), false);
});

test("decideFieldActions fills high-confidence non-forbidden fields", () => {
  const fields = [{ field_id: "f1", label_text: "Email" }];
  const mappings = [{ field_id: "f1", maps_to: "profile.email", confidence: 0.9, value: "a@b.com" }];

  const { fill, flag } = decideFieldActions(fields, mappings);

  assert.deepEqual(fill, [{ field_id: "f1", value: "a@b.com" }]);
  assert.deepEqual(flag, []);
});

test("decideFieldActions flags low-confidence fields instead of filling them", () => {
  const fields = [{ field_id: "f1", label_text: "Cover letter summary" }];
  const mappings = [{ field_id: "f1", maps_to: "literal:something", confidence: 0.4, value: "guess" }];

  const { fill, flag } = decideFieldActions(fields, mappings);

  assert.deepEqual(fill, []);
  assert.deepEqual(flag, [{ field_id: "f1", reason: "low_confidence" }]);
});

test("decideFieldActions flags unknown mappings", () => {
  const fields = [{ field_id: "f1", label_text: "Salary expectation" }];
  const mappings = [{ field_id: "f1", maps_to: "unknown", confidence: 0.0, value: null }];

  const { fill, flag } = decideFieldActions(fields, mappings);

  assert.deepEqual(fill, []);
  assert.deepEqual(flag, [{ field_id: "f1", reason: "low_confidence" }]);
});

test("decideFieldActions always flags demographic fields, even with a high-confidence mapping", () => {
  const fields = [{ field_id: "f1", label_text: "What is your gender?", required: true }];
  const mappings = [{ field_id: "f1", maps_to: "literal:Male", confidence: 0.99, value: "Male" }];

  const { fill, flag } = decideFieldActions(fields, mappings);

  assert.deepEqual(fill, []);
  assert.deepEqual(flag, [{ field_id: "f1", reason: "demographic_required" }]);
});

test("decideFieldActions flags a field with no mapping returned at all", () => {
  const fields = [{ field_id: "f1", label_text: "Portfolio URL" }, { field_id: "f2", label_text: "Email" }];
  const mappings = [{ field_id: "f2", maps_to: "profile.email", confidence: 0.9, value: "a@b.com" }];

  const { fill, flag } = decideFieldActions(fields, mappings);

  assert.deepEqual(fill, [{ field_id: "f2", value: "a@b.com" }]);
  assert.deepEqual(flag, [{ field_id: "f1", reason: "low_confidence" }]);
});

// ---------- the demographic / essay split (ADR-015 answer bank) ----------
//
// The backend can now return a user-written answer for an essay question. This
// list used to flag every essay field before even looking at the mapping, so a
// bank answer would have been discarded client-side and the run would still
// have stopped with needs_human. Demographic stays unconditional.

test("the two keyword lists are disjoint and together are the old forbidden list", () => {
  const overlap = DEMOGRAPHIC_LABEL_KEYWORDS.filter((k) => ESSAY_LABEL_KEYWORDS.includes(k));
  assert.deepEqual(overlap, []);
  assert.deepEqual(
    [...FORBIDDEN_LABEL_KEYWORDS].sort(),
    [...DEMOGRAPHIC_LABEL_KEYWORDS, ...ESSAY_LABEL_KEYWORDS].sort(),
  );
});

test("isDemographicLabel is true for EEO questions and false for essay questions", () => {
  assert.equal(isDemographicLabel("What is your Gender?"), true);
  assert.equal(isDemographicLabel("Protected veteran status"), true);
  assert.equal(isDemographicLabel("WHY DO YOU WANT TO WORK HERE"), false);
  assert.equal(isDemographicLabel("Email address"), false);
  assert.equal(isDemographicLabel(null), false);
  assert.equal(isDemographicLabel(undefined), false);
});

test("a demographic field is never filled, even with a confident bank mapping", () => {
  for (const label of [
    "What is your race?",
    "Ethnicity",
    "Gender identity",
    "Protected veteran status",
    "Disability status",
    "Sexual orientation",
  ]) {
    for (const required of [true, false]) {
      const { fill, flag } = decideFieldActions(
        [{ field_id: "f1", label_text: label, required }],
        [{ field_id: "f1", maps_to: "answer_bank", confidence: 1.0, value: "SHOULD NEVER BE FILLED" }],
      );
      assert.deepEqual(fill, [], `filled a demographic field: ${label}`);
      assert.deepEqual(flag, [
        { field_id: "f1", reason: required ? "demographic_required" : "demographic_left_blank" },
      ]);
    }
  }
});

// ---------- EEO: optional ones are left blank, required ones still stop ----------

test("an optional EEO field is left blank and does not block; a required one blocks", () => {
  const { fill, flag } = decideFieldActions(
    [
      { field_id: "opt", label_text: "Gender (voluntary self-identification)", required: false },
      { field_id: "unset", label_text: "Veteran status" }, // required absent = optional
      { field_id: "req", label_text: "Race / Ethnicity", required: true },
    ],
    [
      { field_id: "opt", maps_to: "literal:Decline to self-identify", confidence: 1.0, value: "Decline to self-identify" },
      { field_id: "unset", maps_to: "literal:No", confidence: 1.0, value: "No" },
      { field_id: "req", maps_to: "literal:X", confidence: 1.0, value: "X" },
    ],
  );
  assert.deepEqual(fill, []);
  assert.deepEqual(flag, [
    { field_id: "opt", reason: "demographic_left_blank" },
    { field_id: "unset", reason: "demographic_left_blank" },
    { field_id: "req", reason: "demographic_required" },
  ]);
  assert.equal(NEEDS_USER_REASONS.has("demographic_left_blank"), false);
  assert.equal(NEEDS_USER_REASONS.has("demographic_required"), true);
  assert.deepEqual(flag.filter((f) => NEEDS_USER_REASONS.has(f.reason)).map((f) => f.field_id), ["req"]);
});

test("a radio group is required if any member is required", () => {
  const radio = (field_id, name, required) => ({
    field_id, label_text: "Gender", input_type: "radio", name, required,
  });
  const { fill, flag } = decideFieldActions(
    [
      radio("g1", "gender", false), radio("g2", "gender", true), radio("g3", "gender", false),
      radio("v1", "veteran", false), radio("v2", "veteran", false),
    ],
    [],
  );
  assert.deepEqual(fill, []);
  assert.deepEqual(flag.map((f) => [f.field_id, f.reason]), [
    ["g1", "demographic_required"], ["g2", "demographic_required"], ["g3", "demographic_required"],
    ["v1", "demographic_left_blank"], ["v2", "demographic_left_blank"],
  ]);
});

test("the needs_human reason names a required demographic question as a whole word", () => {
  const reason = needsHumanReason([
    { field_id: "a", reason: "demographic_required" },
    { field_id: "b", reason: "low_confidence" },
  ]);
  // apps/api/needs_input.py keys demographic_left_blank on /\bdemographic\b/ ("_" is a word char).
  assert.match(reason, /\bdemographic\b/i);
  assert.match(reason, /required/i);
  assert.match(reason, /self-identification/i);
  assert.match(reason, /^2 field\(s\)/);
  assert.doesNotMatch(needsHumanReason([{ field_id: "b", reason: "low_confidence" }]), /demographic/i);
});

test("an essay field IS filled when the backend supplies a user-written answer", () => {
  const { fill, flag } = decideFieldActions(
    [{ field_id: "f1", label_text: "Why do you want to work here?" }],
    [{ field_id: "f1", maps_to: "answer_bank", confidence: 1.0, value: "My own words." }],
  );

  assert.deepEqual(fill, [{ field_id: "f1", value: "My own words." }]);
  assert.deepEqual(flag, []);
});

test("an essay field with no stored answer is still flagged", () => {
  const { fill, flag } = decideFieldActions(
    [{ field_id: "f1", label_text: "Why are you interested in this role?" }],
    [{ field_id: "f1", maps_to: "unknown", confidence: 0.0, value: null }],
  );

  assert.deepEqual(fill, []);
  assert.deepEqual(flag, [{ field_id: "f1", reason: "essay_no_stored_answer" }]);
});

// --- file inputs (resume upload) ---------------------------------------------

test("classifyFileInput attaches the resume to a resume/CV upload by label, name or id", () => {
  assert.equal(classifyFileInput({ label_text: "Resume/CV", required: true }), "resume");
  assert.equal(classifyFileInput({ label_text: null, name: "resume", required: false }), "resume");
  assert.equal(classifyFileInput({ label_text: "Attach", dom_id: "cv_upload" }), "resume");
  assert.equal(classifyFileInput({ label_text: "Upload your CV" }), "resume");
});

test("classifyFileInput never puts the resume into a cover-letter upload", () => {
  // "Cover letter" must win even though the label may also mention the resume.
  assert.equal(classifyFileInput({ label_text: "Cover Letter", required: true }), "flag");
  assert.equal(classifyFileInput({ label_text: "Cover letter (attach with resume)", required: false }), "skip");
});

test("classifyFileInput flags an unknown required upload and skips an optional one", () => {
  assert.equal(classifyFileInput({ label_text: "Portfolio PDF", required: true }), "flag");
  assert.equal(classifyFileInput({ label_text: "Anything else?", required: false }), "skip");
  // "cv" inside another word is not a CV.
  assert.equal(classifyFileInput({ label_text: "Certificate (CVS pharmacy)", name: "cvs_doc", required: true }), "flag");
});

// --- questions handed to the answer bank -------------------------------------

test("unansweredQuestions returns labels of flagged fields the user can answer", () => {
  const fields = [
    { field_id: "a", label_text: "Why do you want to work here?" },
    { field_id: "b", label_text: "How did you hear about us?" },
    { field_id: "c", label_text: "What is your gender?" },
    { field_id: "c2", label_text: "Disability status" },
    { field_id: "d", label_text: "Portfolio PDF" },
    { field_id: "e", label_text: null },
    { field_id: "f", label_text: "Email" },
  ];
  const flag = [
    { field_id: "a", reason: "essay_no_stored_answer" },
    { field_id: "b", reason: "low_confidence" },
    { field_id: "c", reason: "demographic_required" },
    { field_id: "c2", reason: "demographic_left_blank" },
    { field_id: "d", reason: "file_upload" },
    { field_id: "e", reason: "low_confidence" },
  ];
  assert.deepEqual(unansweredQuestions(fields, flag), [
    "Why do you want to work here?",
    "How did you hear about us?",
  ]);
});

// ============ latest+37: real-form fixes (docs/LIVE-FORM-TEST.md) ============

// --- EEO: the shared spec (backend mirrors it) -------------------------------

test("isDemographicField catches every question-text keyword, sex only as a whole word", () => {
  for (const q of [
    "Are you Hispanic/Latino?", "Race", "Ethnic background", "Latina/Latinx heritage",
    "Gender identity", "Sex", "What is your sex?", "Sexual orientation", "Do you identify as transgender?",
    "Preferred pronouns", "Veteran Status", "Disability", "Are you disabled?",
  ]) {
    assert.equal(isDemographicField({ label_text: q }), true, q);
  }
  assert.equal(isDemographicField({ label_text: "Sussex office preference" }), false);
  assert.equal(isDemographicField({ label_text: "Essex" }), false);
});

test("eligibility questions are NOT demographic", () => {
  for (const q of [
    "Are you 18 years of age or older?",
    "Are you legally authorized to work in the United States?",
    "Will you now or in the future require visa sponsorship?",
    "Are you willing to relocate?",
  ]) {
    assert.equal(isDemographicField({ label_text: q, options: ["Yes", "No"] }), false, q);
  }
});

test("a group with no demographic question text is caught by its options", () => {
  // Ashby: option-labelled EEO radios with no usable question text.
  assert.equal(isDemographicField({ label_text: null, options: ["Man", "Woman", "Another gender identity"] }), true);
  assert.equal(
    isDemographicField({ label_text: "Which describes you?", options: ["White (Not Hispanic or Latino)", "Asian", "Black or African American"] }),
    true,
  );
  // a decline option plus one demographic option
  assert.equal(isDemographicField({ label_text: "Please select", options: ["Female", "Decline To Self Identify"] }), true);
  assert.equal(isDemographicField({ label_text: "", options: ["Protected veteran", "Prefer not to say"] }), true);
  // a decline option alone, or several options of one term, is not enough
  assert.equal(isDemographicField({ label_text: "Salary band", options: ["<100k", "100k+", "Prefer not to say"] }), false);
  assert.equal(
    isDemographicField({ label_text: "University", options: ["Asian Institute of Technology", "Asian University for Women", "Texas Woman's University", "MIT"] }),
    false,
  );
  assert.equal(isDemographicField({ label_text: "Are you authorized?", options: ["Yes", "No"] }), false);
});

test("a demographic group is never filled and never becomes a bank question", () => {
  const fields = [
    { field_id: "g", label_text: null, input_type: "radio", options: ["Man", "Woman", "Decline to self-identify"], required: false },
    { field_id: "h", label_text: "Are you Hispanic/Latino?", input_type: "select", options: ["Yes", "No"], required: true },
  ];
  const { fill, flag } = decideFieldActions(fields, [
    { field_id: "g", maps_to: "answer_bank", confidence: 1, value: "Man" },
    { field_id: "h", maps_to: "answer_bank", confidence: 1, value: "No" },
  ]);
  assert.deepEqual(fill, []);
  assert.deepEqual(flag, [
    { field_id: "g", reason: "demographic_left_blank" },
    { field_id: "h", reason: "demographic_required" },
  ]);
  // even if something upstream flagged them low_confidence, they are not questions
  assert.deepEqual(
    unansweredQuestions(
      [{ field_id: "x", label_text: "Which describes you?", options: ["Man", "Woman"] }],
      [{ field_id: "x", reason: "low_confidence" }],
    ),
    [],
  );
});

// --- extraction: groups, junk, option cap ------------------------------------

const raw = (key, over = {}) => ({
  key, tag: "INPUT", type: "text", role: null, name: null, dom_id: null, autocomplete: null,
  required: false, label: null, question: null, value: "", options: [],
  visible: true, labelVisible: true, inReactSelect: false, ...over,
});

test("radios extract as ONE descriptor per group: the question, with option labels", () => {
  const { descriptors, targets } = buildDescriptors([
    raw(0, { type: "email", label: "Email", dom_id: "email" }),
    raw(1, { type: "radio", name: "gender", label: "Man", value: "1", question: "Gender" }),
    raw(2, { type: "radio", name: "gender", label: "Woman", value: "2", question: "Gender", required: true }),
  ]);
  assert.deepEqual(descriptors.map((d) => [d.field_id, d.label_text, d.input_type, d.options, d.required]), [
    ["jc-field-0", "Email", "email", [], false],
    ["jc-field-1", "Gender", "radio", ["Man", "Woman"], true],
  ]);
  assert.deepEqual(targets.get("jc-field-1").keys, [1, 2]);
  assert.deepEqual(targets.get("jc-field-1").choices, [{ label: "Man", value: "1" }, { label: "Woman", value: "2" }]);
});

test("a checkbox group is one descriptor; a lone checkbox keeps its own label", () => {
  const { descriptors } = buildDescriptors([
    raw(0, { type: "checkbox", name: "lang", label: "English (ENG)", question: "Languages spoken" }),
    raw(1, { type: "checkbox", name: "lang", label: "Telugu (TEL)", question: "Languages spoken" }),
    raw(2, { type: "checkbox", name: "consent", label: "I agree to the privacy policy", question: "Consent" }),
  ]);
  assert.deepEqual(descriptors.map((d) => [d.label_text, d.input_type, d.options]), [
    ["Languages spoken", "checkbox", ["English (ENG)", "Telugu (TEL)"]],
    ["I agree to the privacy policy", "checkbox", []],
  ]);
});

test("an unlabeled text field falls back to its question text", () => {
  const { descriptors } = buildDescriptors([raw(0, { tag: "TEXTAREA", type: "textarea", question: "Anything else?" })]);
  assert.equal(descriptors[0].label_text, "Anything else?");
  assert.equal(descriptors[0].input_type, "textarea");
});

test("junk fields are skipped: hidden, invisible, captcha, honeypot, react-select internals", () => {
  const { descriptors, files } = buildDescriptors([
    raw(0, { type: "hidden", name: "token" }),
    raw(1, { label: "Search", visible: false }),
    raw(2, { tag: "TEXTAREA", type: "textarea", name: "g-recaptcha-response" }),
    raw(3, { name: "h-captcha-response" }),
    raw(4, { name: "website_honeypot", label: "Leave blank" }),
    raw(5, { label: "Country", inReactSelect: true }), // react-select requiredInput shadow
    raw(6, { label: "Country", role: "combobox", inReactSelect: true, dom_id: "country" }),
    raw(7, { type: "submit" }),
    // styled radios hide the native input but show the label: kept
    raw(8, { type: "radio", name: "relo", label: "Yes", question: "Relocate?", visible: false, labelVisible: true }),
    raw(9, { type: "radio", name: "ghost", label: "Yes", visible: false, labelVisible: false }),
    // file inputs are routinely display:none behind a button: never skipped for visibility
    raw(10, { type: "file", name: "resume", visible: false }),
  ]);
  assert.deepEqual(descriptors.map((d) => [d.field_id, d.input_type]), [
    ["jc-field-6", "combobox"],
    ["jc-field-8", "radio"],
  ]);
  assert.deepEqual(files.map((f) => [f.key, f.descriptor.name]), [[10, "resume"]]);
});

test("options sent per field are capped", () => {
  const options = Array.from({ length: 3302 }, (_, i) => ({ label: `University ${i}`, value: String(i) }));
  const { descriptors, targets } = buildDescriptors([raw(0, { tag: "SELECT", type: "select-one", label: "School", options })]);
  assert.equal(MAX_OPTIONS, 50);
  assert.equal(descriptors[0].options.length, MAX_OPTIONS);
  assert.equal(descriptors[0].input_type, "select");
  assert.equal(targets.get("jc-field-0").choices.length, 3302); // matching still sees them all
});

test("pickQuestionText takes the nearest preceding real text, not an option label", () => {
  assert.equal(
    pickQuestionText(["Apply now", "Are you willing to relocate? ✱", "Yes"], ["Yes", "No"]),
    "Are you willing to relocate?",
  );
  assert.equal(pickQuestionText(["Gender *", "*", "  "], ["Man"]), "Gender");
  assert.equal(pickQuestionText(["Man", "Woman"], ["Man", "Woman"]), null);
  assert.equal(pickQuestionText([], []), null);
});

// --- mutation plans: never .value into a radio/checkbox ----------------------

test("planFill: text gets the value; select/radio pick the exactly matching option", () => {
  assert.deepEqual(planFill({ input_type: "email", keys: [0], choices: [] }, "a@b.com"), { kind: "text", key: 0, value: "a@b.com" });
  const sel = { input_type: "select", keys: [4], choices: [{ label: "Select...", value: "" }, { label: "United States", value: "US" }] };
  assert.deepEqual(planFill(sel, " united states "), { kind: "select", key: 4, value: "US" });
  assert.deepEqual(planFill(sel, "us"), { kind: "select", key: 4, value: "US" }); // by option value too
  assert.equal(planFill(sel, "San Francisco"), null);
  const radio = { input_type: "radio", keys: [7, 8], choices: [{ label: "Yes", value: "1" }, { label: "No", value: "0" }] };
  assert.deepEqual(planFill(radio, "No"), { kind: "check", key: 8 });
  assert.equal(planFill(radio, "San Francisco"), null);
  assert.equal(planFill(radio, "N"), null); // no partial match
});

test("planFill: a lone checkbox is checked only for an explicit yes/true", () => {
  const box = { input_type: "checkbox", keys: [3], choices: [{ label: "I agree", value: "on" }] };
  assert.deepEqual(planFill(box, "Yes"), { kind: "check", key: 3 });
  assert.deepEqual(planFill(box, "true"), { kind: "check", key: 3 });
  assert.deepEqual(planFill(box, "No"), { kind: "none" });
  assert.equal(planFill(box, "+1 415 867 2931"), null); // the Lever "Telugu" bug
  const group = { input_type: "checkbox", keys: [5, 6], choices: [{ label: "English (ENG)", value: "e" }, { label: "Telugu (TEL)", value: "t" }] };
  assert.deepEqual(planFill(group, "Telugu (TEL)"), { kind: "check", key: 6 });
  assert.equal(planFill(group, "+1 415 867 2931"), null);
});

test("planFill: a combobox with no options read is never typed into", () => {
  assert.equal(planFill({ input_type: "combobox", keys: [1], choices: [] }, "US"), null);
});

test("a combobox whose menu was read goes out as a select with its option labels", () => {
  const options = Array.from({ length: 244 }, (_, i) => ({ label: `Country ${i}`, value: `Country ${i}` }));
  const { descriptors, targets } = buildDescriptors([
    raw(0, { label: "Relocate?", role: "combobox", inReactSelect: true, options: [{ label: "Yes", value: "Yes" }, { label: "No", value: "No" }] }),
    raw(1, { label: "Country", role: "combobox", inReactSelect: true, options }),
  ]);
  assert.deepEqual(descriptors.map((d) => [d.input_type, d.options.length]), [["select", 2], ["select", MAX_OPTIONS]]);
  assert.deepEqual(descriptors[0].options, ["Yes", "No"]);
  // filled through the widget, matched against every option read
  assert.equal(targets.get("jc-field-1").input_type, "combobox");
  assert.equal(targets.get("jc-field-1").choices.length, 244);
});

test("planFill: a combobox with read options picks the exact option label, never a guess", () => {
  const combo = { input_type: "combobox", keys: [9], choices: [{ label: "Yes", value: "Yes" }, { label: "No", value: "No" }] };
  assert.deepEqual(planFill(combo, " yes "), { kind: "combobox", key: 9, label: "Yes" });
  assert.equal(planFill(combo, "San Francisco"), null);
  assert.equal(planFill(combo, "Y"), null);
});

// --- React-safe value setter ---------------------------------------------------

test("setNativeValue uses the prototype setter past an instance override, then bubbles input+change", () => {
  class FakeInput extends EventTarget {
    #v = "";
    get value() { return this.#v; }
    set value(v) { this.#v = v; }
  }
  const el = new FakeInput();
  // What React's value tracker does: an own property on the node.
  let trackerSaw = null;
  Object.defineProperty(el, "value", {
    configurable: true,
    get() { return Object.getOwnPropertyDescriptor(FakeInput.prototype, "value").get.call(this); },
    set(v) { trackerSaw = v; },
  });
  const events = [];
  el.addEventListener("input", (e) => events.push(["input", e.bubbles]));
  el.addEventListener("change", (e) => events.push(["change", e.bubbles]));

  setNativeValue(el, "Priya");

  assert.equal(el.value, "Priya");
  assert.equal(trackerSaw, null, "went through the instance setter; React would swallow the event");
  assert.deepEqual(events, [["input", true], ["change", true]]);
});

test("EEO keywords match whole words (plural allowed), same as the server", () => {
  // Substring matching treated "embrace" as "race": a required "How do you
  // embrace diversity?" would stop every run as a demographic question.
  assert.equal(isDemographicLabel("How do you embrace diversity in your team?"), false);
  assert.equal(isDemographicLabel("Tell us about a traced bug you fixed"), false);
  assert.equal(isDemographicLabel("Pronouns"), true);
  assert.equal(isDemographicLabel("Races (select all that apply)"), true);
  assert.equal(isDemographicLabel("Are you Hispanic/Latino?"), true);
  assert.equal(isDemographicLabel("Veteran status"), true);
  assert.equal(isDemographicLabel("Sexual orientation"), true);
});
