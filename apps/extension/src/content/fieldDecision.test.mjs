import { test } from "node:test";
import assert from "node:assert/strict";

import { CONFIDENCE_THRESHOLD, decideFieldActions, isForbiddenLabel } from "./fieldDecision.mjs";

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

test("decideFieldActions always flags forbidden fields, even with a high-confidence mapping", () => {
  const fields = [{ field_id: "f1", label_text: "What is your gender?" }];
  const mappings = [{ field_id: "f1", maps_to: "literal:Male", confidence: 0.99, value: "Male" }];

  const { fill, flag } = decideFieldActions(fields, mappings);

  assert.deepEqual(fill, []);
  assert.deepEqual(flag, [{ field_id: "f1", reason: "demographic_or_essay" }]);
});

test("decideFieldActions flags a field with no mapping returned at all", () => {
  const fields = [{ field_id: "f1", label_text: "Portfolio URL" }, { field_id: "f2", label_text: "Email" }];
  const mappings = [{ field_id: "f2", maps_to: "profile.email", confidence: 0.9, value: "a@b.com" }];

  const { fill, flag } = decideFieldActions(fields, mappings);

  assert.deepEqual(fill, [{ field_id: "f2", value: "a@b.com" }]);
  assert.deepEqual(flag, [{ field_id: "f1", reason: "low_confidence" }]);
});
