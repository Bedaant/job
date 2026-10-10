// What one fill did, per field: label, which source filled it, status. Never the value.
// Posted to /extension/fill-snapshots so a failed form can be debugged without re-running it.

export const MAX_SNAPSHOT_FIELDS = 300; // ats_controls.SnapshotIn caps fields at 300
const MAX_LABEL = 200; // and each label at 200 chars

export function buildFillSnapshot(descriptors, mappings, flag, filledIds, resumeIds = new Set()) {
  const mappingById = new Map(mappings.map((m) => [m.field_id, m]));
  const flagById = new Map(flag.map((f) => [f.field_id, f.reason]));
  return descriptors.slice(0, MAX_SNAPSHOT_FIELDS).map((d) => {
    const reason = flagById.get(d.field_id);
    const status = filledIds.has(d.field_id)
      ? "filled"
      : reason === undefined
        ? "skipped"
        : reason.endsWith("_left_blank")
          ? "left_blank"
          : "flagged";
    const source = resumeIds.has(d.field_id) ? "resume" : (mappingById.get(d.field_id)?.maps_to ?? "none");
    return {
      label: String(d.label_text ?? d.name ?? "").trim().slice(0, MAX_LABEL),
      source: String(source).slice(0, 64),
      status,
      required: Boolean(d.required),
    };
  });
}
