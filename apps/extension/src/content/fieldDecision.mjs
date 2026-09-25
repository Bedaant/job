// F11 field-fill decision logic (SPEC.md §3.7). Pure — no DOM access — so it
// can be unit-tested with Node's built-in test runner (`node --test`), zero
// new dependencies. DOM extraction/mutation lives in formFill.content.ts,
// which is thin glue around this and not covered by this test run (needs a
// real browser — not available this session, see WORKLOG).

export const CONFIDENCE_THRESHOLD = 0.75;

// Mirrors apps/api/formfill/map_fields.py's FORBIDDEN_LABEL_KEYWORDS exactly —
// defense-in-depth: the backend already never returns a value for these, but
// a client that only trusted the backend would have a single point of
// failure. Keep both lists in sync if either changes.
export const FORBIDDEN_LABEL_KEYWORDS = [
  "race", "ethnicity", "gender", "veteran status", "disability status",
  "sexual orientation", "why do you want to work", "why are you interested",
];

export function isForbiddenLabel(labelText) {
  if (!labelText) return false;
  const lower = labelText.toLowerCase();
  return FORBIDDEN_LABEL_KEYWORDS.some((keyword) => lower.includes(keyword));
}

// fields: FieldDescriptor[] ({field_id, label_text, ...})
// mappings: FieldMapping[] from POST /extension/map-fields
// returns { fill: [{field_id, value}], flag: [{field_id, reason}] }
export function decideFieldActions(fields, mappings) {
  const mappingById = new Map(mappings.map((m) => [m.field_id, m]));
  const fill = [];
  const flag = [];

  for (const field of fields) {
    if (isForbiddenLabel(field.label_text)) {
      flag.push({ field_id: field.field_id, reason: "demographic_or_essay" });
      continue;
    }
    const mapping = mappingById.get(field.field_id);
    if (!mapping || mapping.maps_to === "unknown" || mapping.confidence < CONFIDENCE_THRESHOLD || !mapping.value) {
      flag.push({ field_id: field.field_id, reason: "low_confidence" });
      continue;
    }
    fill.push({ field_id: field.field_id, value: mapping.value });
  }

  return { fill, flag };
}
