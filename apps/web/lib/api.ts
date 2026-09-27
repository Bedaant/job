import { expireSession, getToken, isSessionExpiry } from "./auth";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export interface Profile {
  id: string;
  persona: string;
  headline: string | null;
  location: string | null;
  prefs: Record<string, unknown>;
}

export interface FactDraft {
  category: string;
  achievement: string;
  proof: string | null;
  metric: string | null;
  tags: string[];
}

export interface NetworkProfile {
  network: string;
  username: string | null;
  url: string | null;
}

/** JSON Resume `basics` — mirrors apps/api/schemas.py ApplicantBasics. Every
 * field is optional there on purpose: null is always allowed, a plausible guess
 * is not. */
export interface ApplicantBasics {
  full_name?: string | null;
  phone?: string | null;
  website_url?: string | null;
  street_address?: string | null;
  city?: string | null;
  region?: string | null;
  country_code?: string | null;
  postal_code?: string | null;
  network_profiles?: NetworkProfile[];
  work_auth?: string[];
}

export interface ResumeUploadResult {
  upload_id: string;
  status: "parsing" | "ready" | "failed";
  facts: FactDraft[];
  /** Draft identity from the parse — never persisted until the user confirms it. */
  basics: ApplicantBasics | null;
  error: string | null;
}

export interface ResumeFact extends FactDraft {
  id: string;
  profile_id: string;
}

export interface Job {
  id: string;
  source: string;
  title: string;
  company: string;
  location: string | null;
  remote: boolean;
  salary: string | null;
  description: string | null;
  apply_url: string;
  tags: string[];
  posted_at: string | null;
}

export interface MatchBreakdown {
  score: number;
  semantic: number;
  skill_coverage: number;
  recency: number;
  matched_skills: string[];
  missing_skills: string[];
}

export interface Match {
  id: string;
  job: Job;
  score: number;
  breakdown: MatchBreakdown;
  state: "new" | "dismissed" | "saved";
}

export interface TailoredBullet {
  text: string;
  source_fact_ids: string[];
}

export interface ReviewMatchBreakdown {
  semantic: number;
  skill_coverage: number;
  recency: number;
  matched_skills: string[];
  missing_skills: string[];
}

export interface ReviewApplication {
  id: string;
  job: Job;
  match_score: number | null;
  match_breakdown: ReviewMatchBreakdown | null;
  status: string;
  tailored_summary: string | null;
  tailored_bullets: TailoredBullet[];
  tailored_cover_letter: string | null;
  flagged_unsupported_claims: string[];
  // Questions an auto-apply run stopped on that the answer bank can't answer yet.
  pending_questions: string[];
  created_at: string;
}

// ---------------------------------------------------------------------------
// Campaigns (ADR-015 — approval happens once, at campaign level, not per
// application). Built against the agreed contract while the backend branch is
// still in flight: a 404 here is expected until it merges, and every caller
// must show that failure rather than render an empty screen.
// ---------------------------------------------------------------------------

export interface CampaignCreate {
  profile_id: string;
  name: string;
  roles: string[];
  locations: string[];
  remote_only: boolean;
  sources: string[];
  min_match_score: number; // 0..1, default 0.7
  daily_cap: number; // default 10
  auto_submit: boolean; // default false
  tailoring_notes?: string;
}

export type CampaignStatus = "draft" | "active" | "paused" | "archived";

export interface Campaign extends CampaignCreate {
  id: string;
  status: CampaignStatus;
  created_at: string;
  updated_at: string;
  last_run_at: string | null;
}

/** PATCH /campaigns/{id} — every field optional; send only what changed.
 * `status` moves are validated server-side (campaigns.ALLOWED_TRANSITIONS). */
export type CampaignUpdate = Partial<CampaignCreate> & { status?: CampaignStatus };

export interface CampaignStats {
  applied_today: number;
  daily_cap: number;
  remaining_today: number;
  total_applied: number;
  last_run_at: string | null;
}

class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

// FastAPI's `detail` is a plain string for our own HTTPExceptions, but a LIST of
// {loc, msg, type} objects for 422 Pydantic validation errors — rendering it
// directly produces "[object Object],[object Object]".
function formatErrorDetail(detail: unknown): string {
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    return detail
      .map((e) => (e && typeof e === "object" && "msg" in e ? String((e as { msg: unknown }).msg) : String(e)))
      .join("; ");
  }
  return "";
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const token = getToken();
  // Caller-specified headers (e.g. login's x-www-form-urlencoded) must win over
  // this default — build the default first, then let options.headers override it.
  const headers: Record<string, string> = {};
  if (!(options.body instanceof FormData) && options.body) {
    headers["Content-Type"] = "application/json";
  }
  Object.assign(headers, options.headers as Record<string, string> | undefined);
  if (token) headers["Authorization"] = `Bearer ${token}`;

  const res = await fetch(`${API_URL}${path}`, { ...options, headers });
  if (!res.ok) {
    if (isSessionExpiry(res.status, path)) expireSession();
    const body = await res.json().catch(() => ({ detail: res.statusText }));
    throw new ApiError(res.status, formatErrorDetail(body.detail) || `API error ${res.status}`);
  }
  return res.json();
}

export const api = {
  login: (email: string, password: string) => {
    const body = new URLSearchParams({ username: email, password });
    return request<{ access_token: string; token_type: string }>("/auth/login", {
      method: "POST",
      body,
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
    });
  },
  signup: (email: string, password: string) =>
    request<{ id: string; email: string }>("/auth/signup", {
      method: "POST",
      body: JSON.stringify({ email, password }),
    }),
  listProfiles: () => request<Profile[]>("/profiles"),
  createProfile: (persona: string, headline?: string) =>
    request<Profile>("/profiles", { method: "POST", body: JSON.stringify({ persona, headline }) }),
  uploadResume: (profileId: string, file: File) => {
    const form = new FormData();
    form.append("file", file);
    return request<ResumeUploadResult>(`/profiles/${profileId}/resume`, { method: "POST", body: form });
  },
  getResumeUpload: (profileId: string, uploadId: string) =>
    request<ResumeUploadResult>(`/profiles/${profileId}/resume/${uploadId}`),
  confirmFacts: (profileId: string, facts: FactDraft[]) =>
    request<ResumeFact[]>(`/profiles/${profileId}/facts:bulk`, {
      method: "POST",
      body: JSON.stringify({ facts }),
    }),
  listFacts: (profileId: string) => request<ResumeFact[]>(`/resume-facts?profile_id=${profileId}`),
  listMatches: (profileId: string) => request<Match[]>(`/matches?profile_id=${profileId}`),
  listReviewQueue: (profileId: string) =>
    request<ReviewApplication[]>(`/applications/review-queue?profile_id=${profileId}`),
  batchApprove: (applicationIds: string[]) =>
    request<{ approved: string[] }>("/applications/batch-approve", {
      method: "POST",
      body: JSON.stringify({ application_ids: applicationIds }),
    }),
  dismissApplication: (applicationId: string) =>
    request<ReviewApplication>(`/applications/${applicationId}`, {
      method: "PATCH",
      body: JSON.stringify({ status: "dismissed" }),
    }),
  listCampaigns: () => request<Campaign[]>("/campaigns"),
  createCampaign: (body: CampaignCreate) =>
    request<Campaign>("/campaigns", { method: "POST", body: JSON.stringify(body) }),
  runCampaign: (campaignId: string) =>
    request<{ task_id: string; status: string }>(`/campaigns/${campaignId}/run`, { method: "POST" }),
  updateCampaign: (campaignId: string, body: CampaignUpdate) =>
    request<Campaign>(`/campaigns/${campaignId}`, { method: "PATCH", body: JSON.stringify(body) }),
  getCampaignStats: (campaignId: string) => request<CampaignStats>(`/campaigns/${campaignId}/stats`),
  getBasics: (profileId: string) => request<ApplicantBasics>(`/profiles/${profileId}/basics`),
  putBasics: (profileId: string, basics: ApplicantBasics) =>
    request<ApplicantBasics>(`/profiles/${profileId}/basics`, {
      method: "PUT",
      body: JSON.stringify(basics),
    }),
  saveAnswer: (profileId: string, questionText: string, answerText: string) =>
    request<{ id: string }>(`/profiles/${profileId}/answers`, {
      method: "PUT",
      body: JSON.stringify({ question_text: questionText, answer_text: answerText }),
    }),
  resumeDocxUrl: (profileId: string) => `${API_URL}/profiles/${profileId}/resume.docx`,
};

export { ApiError };
