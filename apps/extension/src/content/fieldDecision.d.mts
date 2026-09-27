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
  fields: { field_id: string; label_text: string | null; options?: string[] }[],
  flag: { field_id: string; reason: string }[],
): string[];

export const DEMOGRAPHIC_DECLINE_OPTIONS: string[];
export const DEMOGRAPHIC_OPTIONS: string[];
export function isDemographicField(field: { label_text: string | null; options?: string[] }): boolean;

export type Choice = { label: string; value: string };

// One input/select/textarea as formFill.content.ts reads it off the page.
export interface RawControl {
  key: number;
  tag: string;
  type: string;
  role: string | null;
  name: string | null;
  dom_id: string | null;
  autocomplete: string | null;
  required: boolean;
  label: string | null; // the control's own label (an option's, for a radio)
  question: string | null; // the group/question text around it
  value: string;
  options: Choice[]; // <select> only
  visible: boolean;
  labelVisible: boolean;
  inReactSelect: boolean;
}

export interface SentDescriptor extends FieldDescriptor {
  input_type: string;
  options: string[];
  required: boolean;
  autocomplete: string | null;
  name: string | null;
  dom_id: string | null;
}

export type FillTarget = { input_type: string; keys: number[]; choices: Choice[] };

export const MAX_OPTIONS: number;
export function buildDescriptors(raws: RawControl[]): {
  descriptors: SentDescriptor[];
  files: { descriptor: SentDescriptor; key: number }[];
  targets: Map<string, FillTarget>;
};
export function pickQuestionText(texts: string[], optionLabels: string[]): string | null;
export function planFill(
  target: FillTarget,
  value: string,
):
  | { kind: "text"; key: number; value: string }
  | { kind: "select"; key: number; value: string }
  | { kind: "check"; key: number }
  | { kind: "none" }
  | null;
export function setNativeValue(el: EventTarget & { value: string }, value: string): void;
