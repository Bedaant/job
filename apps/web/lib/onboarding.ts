// Onboarding wizard state, gating and payload shaping — kept out of the React
// components on purpose so the rules that decide "can this user move on" and
// "what exactly gets posted" are testable without a DOM (no jsdom installed).
import { api, type ApplicantBasics, type Campaign, type CampaignCreate, type FactDraft } from "./api";

export type WizardStep = "resume" | "facts" | "preferences" | "campaign" | "done";

export const STEPS: WizardStep[] = ["resume", "facts", "preferences", "campaign", "done"];

export const STEP_TITLES: Record<WizardStep, string> = {
  resume: "Upload your resume",
  facts: "Confirm your facts",
  preferences: "What you're looking for",
  campaign: "Create your campaign",
  done: "You're live",
};

export interface Preferences {
  roles: string[];
  locations: string[];
  remote_only: boolean;
  min_salary: number | null;
}

export interface CampaignDraft {
  name: string;
  sources: string[];
  min_match_score: number;
  daily_cap: number;
  auto_submit: boolean;
}

export interface WizardState {
  facts: FactDraft[];
  basics: ApplicantBasics;
  prefs: Preferences;
  campaign: CampaignDraft;
}

// The authoritative source list lives in apps/api/connectors/. Mirrored here
// because there is no endpoint that enumerates it; if a connector is added there
// this list needs updating (the server re-validates either way).
export const AVAILABLE_SOURCES = [
  { id: "remotive", label: "Remotive", note: "Remote-first job board" },
  { id: "greenhouse", label: "Greenhouse", note: "Company ATS boards" },
  { id: "lever", label: "Lever", note: "Company ATS boards" },
  { id: "ashby", label: "Ashby", note: "Company ATS boards" },
  { id: "reed", label: "Reed", note: "UK listings" },
  { id: "jobspy_google", label: "Google Jobs", note: "Currently returning no results" },
];

export const emptyPreferences = (): Preferences => ({
  roles: [],
  locations: [],
  remote_only: false,
  min_salary: null,
});

export const emptyCampaignDraft = (): CampaignDraft => ({
  name: "My job search",
  sources: ["remotive", "greenhouse", "lever", "ashby"],
  min_match_score: 0.7,
  daily_cap: 10,
  auto_submit: false,
});

/** Field-keyed errors; `_` is the form-level error. Empty object = valid. */
export type Errors = Record<string, string>;

export function editFact(facts: FactDraft[], index: number, patch: Partial<FactDraft>): FactDraft[] {
  return facts.map((f, i) => (i === index ? { ...f, ...patch } : f));
}

// Mirrors the categories apps/api/models.py ResumeFact and the parser use.
export const FACT_CATEGORIES = ["experience", "project", "skill", "certification", "education"];

/** A row the user fills in themselves — their own words, so nothing is fabricated. */
export const blankFact = (): FactDraft => ({ category: "experience", achievement: "", proof: null, metric: null, tags: [] });

export function validateFacts(facts: FactDraft[]): Errors {
  if (facts.length === 0) {
    return { _: "You have no facts yet. Upload a resume, or add a fact by hand — nothing can be written without it." };
  }
  const errors: Errors = {};
  facts.forEach((f, i) => {
    if (!f.achievement.trim()) errors[i] = "A fact cannot be empty — correct it or remove it.";
    if (!FACT_CATEGORIES.includes(f.category)) errors[`${i}.category`] = "Pick what kind of fact this is.";
  });
  return errors;
}

// ---------------------------------------------------------------------------
// Basics validation. Deliberately mirrors apps/api/schemas.py ApplicantBasics
// field-for-field so the user sees the problem next to the input instead of a
// 422 after pressing Continue. This is UX: the server still re-validates.
// ---------------------------------------------------------------------------

const PLACEHOLDER_NAMES = new Set([
  "john doe", "jane doe", "john smith", "jane smith", "your name", "full name",
  "first last", "firstname lastname", "n/a", "na", "none", "unknown", "candidate name",
]);
const FICTIONAL_PHONE_RE = /555-?01\d{2}/;
const MIN_PHONE_DIGITS = 7;
const MAX_PHONE_DIGITS = 15;

export function validateBasics(basics: ApplicantBasics): Errors {
  const errors: Errors = {};

  if (basics.full_name && PLACEHOLDER_NAMES.has(basics.full_name.trim().toLowerCase())) {
    errors.full_name = "That looks like a placeholder, not your name. Leave it blank rather than guess.";
  }

  if (basics.phone) {
    const digits = basics.phone.replace(/\D/g, "");
    if (digits.length < MIN_PHONE_DIGITS || digits.length > MAX_PHONE_DIGITS) {
      errors.phone = `That's ${digits.length} digits. A real number has ${MIN_PHONE_DIGITS}-${MAX_PHONE_DIGITS} — leave it blank rather than send a partial one.`;
    } else if (FICTIONAL_PHONE_RE.test(basics.phone) || FICTIONAL_PHONE_RE.test(digits)) {
      errors.phone = "That's in the reserved fictional 555-01XX range — the parser guessed. Replace it or clear it.";
    }
  }

  if (basics.website_url && !/^https?:\/\//.test(basics.website_url)) {
    errors.website_url = "Include http:// or https://.";
  }

  if (basics.country_code && !/^[A-Za-z]{2}$/.test(basics.country_code.trim())) {
    errors.country_code = "Two-letter country code, e.g. US or IN.";
  }

  (basics.network_profiles || []).forEach((p, i) => {
    if (p.url && !/^https?:\/\//.test(p.url)) errors[`network_profiles.${i}`] = "Include http:// or https://.";
    if (!p.network?.trim()) errors[`network_profiles.${i}.network`] = "Name the network, e.g. LinkedIn.";
  });

  return errors;
}

export function validatePreferences(prefs: Preferences): Errors {
  const errors: Errors = {};
  if (prefs.roles.filter((r) => r.trim()).length === 0) {
    errors.roles = "Add at least one role — this is what we search for.";
  }
  if (prefs.locations.filter((l) => l.trim()).length === 0 && !prefs.remote_only) {
    errors.locations = "Add a location, or switch on remote-only.";
  }
  if (prefs.min_salary !== null && (!Number.isFinite(prefs.min_salary) || prefs.min_salary < 0)) {
    errors.min_salary = "Enter a positive number, or leave it blank.";
  }
  return errors;
}

export const DAILY_CAP_MAX = 50;

export function validateCampaign(campaign: CampaignDraft): Errors {
  const errors: Errors = {};
  if (!campaign.name.trim()) errors.name = "Give the campaign a name so you can tell it apart later.";
  if (campaign.sources.length === 0) errors.sources = "Pick at least one source to search.";
  if (!(campaign.min_match_score >= 0 && campaign.min_match_score <= 1)) {
    errors.min_match_score = "Match score must be between 0 and 100%.";
  }
  if (!Number.isInteger(campaign.daily_cap) || campaign.daily_cap < 1 || campaign.daily_cap > DAILY_CAP_MAX) {
    errors.daily_cap = `Daily cap must be a whole number from 1 to ${DAILY_CAP_MAX}.`;
  }
  return errors;
}

export function stepErrors(step: WizardStep, state: WizardState): Errors {
  switch (step) {
    case "resume":
      return state.facts.length === 0 ? { _: "Upload a resume, or add your facts by hand, to continue." } : {};
    case "facts":
      return { ...validateFacts(state.facts), ...validateBasics(state.basics) };
    case "preferences":
      return validatePreferences(state.prefs);
    case "campaign":
      return validateCampaign(state.campaign);
    case "done":
      return {};
  }
}

export function canAdvance(step: WizardStep, state: WizardState): boolean {
  return Object.keys(stepErrors(step, state)).length === 0;
}

/**
 * The exact `POST /campaigns` body. Nothing extra: an unknown key is a 422 from
 * a strict Pydantic model and a silent drop from a lax one, and neither is worth
 * finding out in production.
 *
 * `min_salary` has no home in the contract, so it rides in `tailoring_notes` —
 * the UI says plainly that it is a note, not a hard filter.
 */
export function buildCampaignBody(prefs: Preferences, campaign: CampaignDraft, profileId: string): CampaignCreate {
  const clean = (xs: string[]) => xs.map((x) => x.trim()).filter(Boolean);
  const body: CampaignCreate = {
    profile_id: profileId,
    name: campaign.name.trim(),
    roles: clean(prefs.roles),
    locations: clean(prefs.locations),
    remote_only: prefs.remote_only,
    sources: campaign.sources,
    min_match_score: campaign.min_match_score,
    daily_cap: campaign.daily_cap,
    auto_submit: campaign.auto_submit,
  };
  if (prefs.min_salary !== null) {
    body.tailoring_notes = `Minimum acceptable base salary: ${prefs.min_salary}`;
  }
  return body;
}

/**
 * Launch = the user's one approval (ADR-015). A campaign is created as `draft`
 * and the runner skips anything not `active`, so activate it before the first
 * run. A failed first run does not undo the (now active) campaign — it is
 * reported so the UI can say "saved but didn't start" instead of "you're live".
 */
export async function launchCampaign(body: CampaignCreate): Promise<{ campaign: Campaign; started: boolean }> {
  const created = await api.createCampaign(body);
  const campaign = await api.updateCampaign(created.id, { status: "active" });
  const started = await api.runCampaign(created.id).then(
    () => true,
    () => false,
  );
  return { campaign, started };
}
