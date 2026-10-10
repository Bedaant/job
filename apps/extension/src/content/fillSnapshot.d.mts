// Type contract for fillSnapshot.mjs (plain JS so node --test runs it unchanged).
export interface SnapshotField {
  label: string;
  source: string;
  status: "filled" | "flagged" | "left_blank" | "skipped";
  required: boolean;
}
export const MAX_SNAPSHOT_FIELDS: number;
export function buildFillSnapshot(
  descriptors: { field_id: string; label_text: string | null; name?: string | null; required?: boolean }[],
  mappings: { field_id: string; maps_to: string }[],
  flag: { field_id: string; reason: string }[],
  filledIds: Set<string>,
  resumeIds?: Set<string>,
): SnapshotField[];
