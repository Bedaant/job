const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

async function request(path, options = {}) {
  const res = await fetch(`${API_URL}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!res.ok) throw new Error(`API error ${res.status} on ${path}`);
  return res.json();
}

export const api = {
  listJobs: () => request("/jobs"),
  runDiscovery: () => request("/discover/run", { method: "POST" }),
  listApplications: () => request("/applications"),
  createApplication: (jobId, portal) =>
    request("/applications", {
      method: "POST",
      body: JSON.stringify({ job_id: jobId, portal }),
    }),
  updateApplication: (id, patch) =>
    request(`/applications/${id}`, { method: "PATCH", body: JSON.stringify(patch) }),
  tailor: (jobId) =>
    request("/tailor", { method: "POST", body: JSON.stringify({ job_id: jobId }) }),
  listResumeFacts: () => request("/resume-facts"),
};
