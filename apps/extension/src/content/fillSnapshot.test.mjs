import { test } from "node:test";
import assert from "node:assert/strict";

import { buildFillSnapshot, MAX_SNAPSHOT_FIELDS } from "./fillSnapshot.mjs";

const descriptors = [
  { field_id: "jc-field-0", label_text: "Email *", required: true },
  { field_id: "jc-field-1", label_text: "Why us?", required: false },
  { field_id: "jc-field-2", label_text: "Gender", required: false },
  { field_id: "jc-field-3", label_text: "Portfolio", required: false },
];
const mappings = [
  { field_id: "jc-field-0", maps_to: "email", confidence: 0.99, value: "asha@example.com" },
  { field_id: "jc-field-1", maps_to: "unknown", confidence: 0.1, value: null },
];

test("records label, source and status per field, never the value", () => {
  const snap = buildFillSnapshot(descriptors, mappings, [
    { field_id: "jc-field-1", reason: "essay_no_stored_answer" },
    { field_id: "jc-field-2", reason: "demographic_left_blank" },
  ], new Set(["jc-field-0"]));
  assert.deepEqual(snap, [
    { label: "Email *", source: "email", status: "filled", required: true },
    { label: "Why us?", source: "unknown", status: "flagged", required: false },
    { label: "Gender", source: "none", status: "left_blank", required: false },
    { label: "Portfolio", source: "none", status: "skipped", required: false },
  ]);
  assert.ok(!JSON.stringify(snap).includes("asha@example.com"));
});

test("capped to what the server accepts", () => {
  const many = Array.from({ length: 400 }, (_, i) => ({ field_id: `f${i}`, label_text: "x".repeat(500) }));
  const snap = buildFillSnapshot(many, [], [], new Set());
  assert.equal(snap.length, MAX_SNAPSHOT_FIELDS);
  assert.equal(snap[0].label.length, 200);
});

test("resume uploads count as filled from the resume", () => {
  const snap = buildFillSnapshot([{ field_id: "f", label_text: "Resume" }], [], [], new Set(["f"]), new Set(["f"]));
  assert.deepEqual(snap[0], { label: "Resume", source: "resume", status: "filled", required: false });
});
