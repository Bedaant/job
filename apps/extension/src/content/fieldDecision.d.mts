// Type contract for fieldDecision.mjs — kept as plain JS so its logic runs
// unchanged under `node --test` (zero new dependencies), typed separately
// here for the TS content script that consumes it.
export interface FieldDescriptor {
  field_id: string;
  label_text: string | null;
  input_type?: string;
  options?: string[];
  required?: boolean;
  name?: string | null; // groups radio buttons for required-ness
}

export interface FieldMapping {
  field_id: string;
  maps_to: string;
  confidence: number;
  value: string | null;
}

export const CONFIDENCE_THRESHOLD: number;
export const DEMOGRAPHIC_LABEL_KEYWORDS: string[];
export const ESSAY_LABEL_KEYWORDS: string[];
export const FORBIDDEN_LABEL_KEYWORDS: string[];
export function isDemographicLabel(labelText: string | null | undefined): boolean;
export function isEssayLabel(labelText: string | null | undefined): boolean;
export function isForbiddenLabel(labelText: string | null | undefined): boolean;
export function decideFieldActions(
  fields: FieldDescriptor[],
  mappings: FieldMapping[],
): { fill: { field_id: string; value: string }[]; flag: { field_id: string; reason: string }[] };
export const NEEDS_USER_REASONS: Set<string>;
export function needsHumanReason(blocking: { field_id: string; reason: string }[]): string;
export function classifyFileInput(field: {
  label_text: string | null;
  name?: string | null;
  dom_id?: string | null;
  required?: boolean;
}): "resume" | "flag" | "skip";
export function unansweredQuestions(
  fields: { field_id: string; label_text: string | null }[],
  flag: { field_id: string; reason: string }[],
): string[];
