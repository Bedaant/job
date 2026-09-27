import { test } from "node:test";
import assert from "node:assert/strict";

import {
  CONFIDENCE_THRESHOLD,
  DEMOGRAPHIC_LABEL_KEYWORDS,
  ESSAY_LABEL_KEYWORDS,
  FORBIDDEN_LABEL_KEYWORDS,
  classifyFileInput,
  decideFieldActions,
  isDemographicLabel,
  isForbiddenLabel,
  unansweredQuestions,
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
  const fields = [{ field_id: "f1", label_text: "What is your gender?" }];
  const mappings = [{ field_id: "f1", maps_to: "literal:Male", confidence: 0.99, value: "Male" }];

  const { fill, flag } = decideFieldActions(fields, mappings);

  assert.deepEqual(fill, []);
  assert.deepEqual(flag, [{ field_id: "f1", reason: "demographic" }]);
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
    const { fill, flag } = decideFieldActions(
      [{ field_id: "f1", label_text: label }],
      [{ field_id: "f1", maps_to: "answer_bank", confidence: 1.0, value: "SHOULD NEVER BE FILLED" }],
    );
    assert.deepEqual(fill, [], `filled a demographic field: ${label}`);
    assert.deepEqual(flag, [{ field_id: "f1", reason: "demographic" }]);
  }
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
    { field_id: "d", label_text: "Portfolio PDF" },
    { field_id: "e", label_text: null },
    { field_id: "f", label_text: "Email" },
  ];
  const flag = [
    { field_id: "a", reason: "essay_no_stored_answer" },
    { field_id: "b", reason: "low_confidence" },
    { field_id: "c", reason: "demographic" },
    { field_id: "d", reason: "file_upload" },
    { field_id: "e", reason: "low_confidence" },
  ];
  assert.deepEqual(unansweredQuestions(fields, flag), [
    "Why do you want to work here?",
    "How did you hear about us?",
  ]);
});
