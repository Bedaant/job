// Type contract for driverCore.mjs — kept as plain JS so its logic runs
// unchanged under `node --test` (zero new dependencies), typed separately here
// for the TS driver and content script that consume it. Same split as
// src/content/fieldDecision.d.mts.
export interface WorkQueueItem {
  application_id: string;
  profile_id?: string;
  apply_url?: string;
  company?: string;
  title?: string;
}

export const MAX_ATTEMPTS_PER_ITEM: number;

export const PAUSED_STATUS: number;
export function pausedMessage(status: number | undefined, atsType?: string | null): string | null;

export function classifyFailure(error: unknown): {
  outcome: "failed" | "needs_human";
  reason: string;
};

export function planRun<T extends WorkQueueItem>(
  queue: T[],
  attempts: Map<string, number>,
): T[];

export type Verify = { urlBefore: string; sentAt: number };
export interface FrameAssignment<T> {
  item: T;
  frameId?: number;
  verify?: Verify;
  pages?: number; // Next clicks acked so far (multi-page forms)
}
export const MIN_APPLICATION_FIELDS: number;
export function countFields(controlTypes: string[]): number;
export function holdsApplicationForm(controlTypes: string[]): boolean;
export function chooseFrame(claims: { frameId: number; fieldCount: number }[]): number | undefined;
export function answerForFrame<T extends object>(
  assignment: FrameAssignment<T> | undefined,
  frameId: number | undefined,
): (T & { verify?: Verify }) | null;
export function isFromAssignedFrame<T>(
  assignment: FrameAssignment<T> | undefined,
  frameId: number | undefined,
): boolean;
export const ITEM_TIMEOUT_MS: number;
export function fillsOnPopup(frame: { isTop: boolean; controlTypes: string[]; hasIframes: boolean }): boolean;

export type PageButton = { text: string; submitsForm: boolean; disabled: boolean; inOverlay: boolean };
export const MAX_PAGES: number;
export function normalize(text: string): string;
export function pickNextButton(buttons: PageButton[]): null | { index: number } | { stop: string };
export function pickEntryButton(buttons: PageButton[], clickedTexts: Set<string>): number;
