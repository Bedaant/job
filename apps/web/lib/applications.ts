// The Applications tracker's decisions (columns, labels, where a card can move),
// kept out of the page so they test without a DOM.

export type ColumnId = "applied" | "heard_back" | "interviewing" | "offer" | "closed";

export const COLUMNS: { id: ColumnId; title: string; statuses: string[] }[] = [
  { id: "applied", title: "Applied", statuses: ["applied", "submitted_unconfirmed", "submitting"] },
  { id: "heard_back", title: "Heard back", statuses: ["recruiter", "oa"] },
  { id: "interviewing", title: "Interviewing", statuses: ["interview"] },
  { id: "offer", title: "Offer", statuses: ["offer"] },
  { id: "closed", title: "Closed", statuses: ["rejected", "withdrawn"] },
];

/** Null for applications not sent yet — those wait in Review, not the pipeline. */
export function columnOf(status: string): ColumnId | null {
  return COLUMNS.find((c) => c.statuses.includes(status))?.id ?? null;
}

export function groupPipeline<T extends { status: string }>(rows: T[]) {
  const columns = Object.fromEntries(COLUMNS.map((c) => [c.id, [] as T[]])) as Record<ColumnId, T[]>;
  let notSent = 0;
  for (const r of rows) {
    const col = columnOf(r.status);
    if (col) columns[col].push(r);
    else if (r.status !== "dismissed") notSent++;
  }
  return { columns, notSent };
}

const LABELS: Record<string, string> = {
  saved: "Saved",
  ready_for_review: "Ready for review",
  approved: "Approved",
  dismissed: "Dismissed",
  submitting: "Sending…",
  submitted_unconfirmed: "Couldn't confirm",
  applied: "Applied",
  recruiter: "Recruiter reached out",
  oa: "Online assessment",
  interview: "Interviewing",
  offer: "Offer",
  rejected: "Rejected",
  withdrawn: "Withdrawn",
};

export const statusLabel = (status: string) => LABELS[status] ?? status;

const TRACKER_STATUSES = ["applied", "recruiter", "oa", "interview", "offer", "rejected", "withdrawn"];

/** Where the "Move to" menu can send a card. */
export function moveOptions(status: string): { status: string; label: string }[] {
  return TRACKER_STATUSES.filter((s) => s !== status).map((s) => ({
    status: s,
    label: s === "applied" && status === "submitted_unconfirmed" ? "I've confirmed it was sent" : statusLabel(s),
  }));
}

export interface Keywords {
  matched: string[];
  reworded: string[];
  missing: string[];
}

export function keywordRows(k: Keywords) {
  return [
    { kind: "matched" as const, label: "Already in your facts", keywords: k.matched },
    { kind: "reworded" as const, label: "Reworded to the job's wording", keywords: k.reworded },
    { kind: "missing" as const, label: "Not in your facts — left out", keywords: k.missing },
  ].filter((r) => r.keywords.length > 0);
}
