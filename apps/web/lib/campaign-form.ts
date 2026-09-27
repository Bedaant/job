// /campaign's decision logic, kept out of the page so it is testable without a
// DOM: what the settings form holds, what a Save actually sends, and what each
// campaign status means to the user.
import type { Campaign, CampaignStatus, CampaignUpdate } from "./api";
import { validateCampaign, validatePreferences, type Errors } from "./onboarding";

export interface CampaignForm {
  roles: string[];
  locations: string[];
  remote_only: boolean;
  min_match_score: number;
  daily_cap: number;
  auto_submit: boolean;
  tailoring_notes: string;
}

export function formFromCampaign(c: Campaign): CampaignForm {
  return {
    roles: c.roles,
    locations: c.locations,
    remote_only: c.remote_only,
    min_match_score: c.min_match_score,
    daily_cap: c.daily_cap,
    auto_submit: c.auto_submit,
    tailoring_notes: c.tailoring_notes ?? "",
  };
}

/** Only the fields that differ from `original`. Empty object = nothing to save.
 * Notes are trimmed; clearing one sends "" because the API drops nulls. */
export function buildCampaignPatch(original: CampaignForm, edited: CampaignForm): CampaignUpdate {
  const next = { ...edited, tailoring_notes: edited.tailoring_notes.trim() };
  const patch: Record<string, unknown> = {};
  for (const key of Object.keys(next) as (keyof CampaignForm)[]) {
    if (JSON.stringify(next[key]) !== JSON.stringify(original[key])) patch[key] = next[key];
  }
  return patch as CampaignUpdate;
}

/** Same rules the user met in onboarding, reused — not restated. */
export function validateCampaignForm(f: CampaignForm): Errors {
  const prefs = validatePreferences({ ...f, min_salary: null });
  const bounds = validateCampaign({ name: "-", sources: ["-"], ...f });
  return { ...prefs, ...bounds };
}

export interface StatusView {
  label: string;
  headline: string;
  tone: "success" | "warning" | "muted";
  action: { label: string; next: CampaignStatus } | null;
}

export function statusView(status: CampaignStatus): StatusView {
  switch (status) {
    case "active":
      return { label: "Active", headline: "Maggie is applying", tone: "success", action: { label: "Pause", next: "paused" } };
    case "paused":
      return { label: "Paused", headline: "Nothing will be sent until you resume", tone: "warning", action: { label: "Resume", next: "active" } };
    case "draft":
      return { label: "Draft", headline: "Not started — nothing is sent until you start it", tone: "muted", action: { label: "Start", next: "active" } };
    case "archived":
      return { label: "Archived", headline: "This campaign is finished — nothing more will be sent", tone: "muted", action: null };
  }
}
