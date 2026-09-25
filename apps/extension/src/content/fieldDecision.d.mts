// Type contract for fieldDecision.mjs — kept as plain JS so its logic runs
// unchanged under `node --test` (zero new dependencies), typed separately
// here for the TS content script that consumes it.
export interface FieldDescriptor {
  field_id: string;
  label_text: string | null;
  input_type?: string;
  options?: string[];
  required?: boolean;
}

export interface FieldMapping {
  field_id: string;
  maps_to: string;
  confidence: number;
  value: string | null;
}

export const CONFIDENCE_THRESHOLD: number;
export const FORBIDDEN_LABEL_KEYWORDS: string[];
export function isForbiddenLabel(labelText: string | null | undefined): boolean;
export function decideFieldActions(
  fields: FieldDescriptor[],
  mappings: FieldMapping[],
): { fill: { field_id: string; value: string }[]; flag: { field_id: string; reason: string }[] };
