// F11 field-fill decision logic (SPEC.md §3.7). Pure — no DOM access — so it
// can be unit-tested with Node's built-in test runner (`node --test`), zero
// new dependencies. DOM extraction/mutation lives in formFill.content.ts,
// which is thin glue around this and not covered by this test run (needs a
// real browser — not available this session, see WORKLOG).

export const CONFIDENCE_THRESHOLD = 0.75;

// Mirrors apps/api/answer_bank.py's DEMOGRAPHIC_LABEL_KEYWORDS exactly —
// defense-in-depth: the backend already never returns a value for these, but a
// client that only trusted the backend would have a single point of failure.
// NEVER fillable, by anything, under any circumstances. Keep both lists in sync
// if either changes.
export const DEMOGRAPHIC_LABEL_KEYWORDS = [
  "race", "ethnicity", "gender", "veteran status", "disability status",
  "sexual orientation",
];

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
export function isDemographicLabel(labelText) {
  return matchesAny(labelText, DEMOGRAPHIC_LABEL_KEYWORDS);
}

export function isEssayLabel(labelText) {
  return matchesAny(labelText, ESSAY_LABEL_KEYWORDS);
}

export function isForbiddenLabel(labelText) {
  return matchesAny(labelText, FORBIDDEN_LABEL_KEYWORDS);
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
    if (isDemographicLabel(field.label_text)) {
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
  const labelById = new Map(fields.map((f) => [f.field_id, f.label_text]));
  return flag
    .filter((f) => ANSWERABLE_REASONS.has(f.reason))
    .map((f) => labelById.get(f.field_id)?.trim())
    .filter((label) => label && !isDemographicLabel(label));
}
