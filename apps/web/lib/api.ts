import { getToken } from "./auth";

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

export interface ResumeUploadResult {
  upload_id: string;
  status: "parsing" | "ready" | "failed";
  facts: FactDraft[];
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
};

export { ApiError };
