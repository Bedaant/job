import { useEffect, useState } from "react";
import { api } from "../lib/legacy-api";

const STATUS_LABELS = {
  saved: "Saved",
  applied: "Applied",
  oa: "Assessment",
  recruiter: "Recruiter Call",
  interview: "Interview",
  offer: "Offer",
  rejected: "Rejected",
};

export default function Home() {
  const [tab, setTab] = useState("jobs");
  const [jobs, setJobs] = useState([]);
  const [applications, setApplications] = useState([]);
  const [facts, setFacts] = useState([]);
  const [loadingDiscover, setLoadingDiscover] = useState(false);
  const [tailorResult, setTailorResult] = useState(null);
  const [tailoringJobId, setTailoringJobId] = useState(null);

  const refreshAll = async () => {
    const [j, a, f] = await Promise.all([
      api.listJobs(),
      api.listApplications(),
      api.listResumeFacts(),
    ]);
    setJobs(j);
    setApplications(a);
    setFacts(f);
  };

  useEffect(() => {
    refreshAll().catch(console.error);
  }, []);

  const handleDiscover = async () => {
    setLoadingDiscover(true);
    try {
      await api.runDiscovery();
      await refreshAll();
    } finally {
      setLoadingDiscover(false);
    }
  };

  const handleSave = async (jobId) => {
    await api.createApplication(jobId, "");
    await refreshAll();
  };

  const handleTailor = async (jobId) => {
    setTailoringJobId(jobId);
    setTailorResult(null);
    try {
      const result = await api.tailor(jobId);
      setTailorResult(result);
    } finally {
      setTailoringJobId(null);
    }
  };

  const handleStatusChange = async (appId, status) => {
    await api.updateApplication(appId, { status });
    await refreshAll();
  };

  return (
    <div className="min-h-screen font-body">
      <header className="border-b border-ledgerLight px-8 py-6 flex items-baseline justify-between">
        <div>
          <h1 className="font-display text-2xl text-parchment tracking-tight">
            The Ledger
          </h1>
          <p className="text-sm text-parchment/60 font-mono mt-1">
            job discovery · evidence-backed tailoring · application tracker
          </p>
        </div>
        <nav className="flex gap-6 font-mono text-sm">
          {["jobs", "tracker", "facts"].map((t) => (
            <button
              key={t}
              onClick={() => setTab(t)}
              className={`uppercase tracking-wider pb-1 border-b-2 transition ${
                tab === t
                  ? "border-brass text-brass"
                  : "border-transparent text-parchment/50 hover:text-parchment"
              }`}
            >
              {t}
            </button>
          ))}
        </nav>
      </header>

      <main className="px-8 py-8 max-w-5xl mx-auto">
        {tab === "jobs" && (
          <section>
            <div className="flex items-center justify-between mb-6">
              <h2 className="font-display text-lg text-parchment">Open Roles</h2>
              <button
                onClick={handleDiscover}
                disabled={loadingDiscover}
                className="font-mono text-sm bg-brass text-ledger px-4 py-2 rounded-sm hover:opacity-90 disabled:opacity-50"
              >
                {loadingDiscover ? "Fetching…" : "Pull latest listings"}
              </button>
            </div>

            {jobs.length === 0 && (
              <p className="text-parchment/50 font-mono text-sm">
                No listings yet. Add company tokens in connectors/config.py, then hit
                "Pull latest listings."
              </p>
            )}

            <div className="grid gap-3">
              {jobs.map((job) => (
                <div
                  key={job.id}
                  className="bg-ledgerLight border border-brass/20 rounded-sm p-4 flex justify-between items-start"
                >
                  <div>
                    <p className="font-display text-parchment text-base">{job.title}</p>
                    <p className="font-mono text-xs text-parchment/60 mt-1">
                      {job.company} · {job.location || "remote"} · via {job.source}
                    </p>
                  </div>
                  <div className="flex gap-2 shrink-0">
                    <button
                      onClick={() => handleTailor(job.id)}
                      className="font-mono text-xs border border-verified text-verified px-3 py-1.5 rounded-sm hover:bg-verified/10"
                    >
                      {tailoringJobId === job.id ? "Tailoring…" : "Tailor"}
                    </button>
                    <button
                      onClick={() => handleSave(job.id)}
                      className="font-mono text-xs border border-brass text-brass px-3 py-1.5 rounded-sm hover:bg-brass/10"
                    >
                      Save to tracker
                    </button>
                    <a
                      href={job.apply_url}
                      target="_blank"
                      rel="noreferrer"
                      className="font-mono text-xs border border-parchment/30 text-parchment/70 px-3 py-1.5 rounded-sm hover:bg-parchment/10"
                    >
                      Open listing
                    </a>
                  </div>
                </div>
              ))}
            </div>

            {tailorResult && (
              <div className="mt-6 bg-ledgerLight border border-brass rounded-sm p-5">
                <h3 className="font-display text-parchment mb-2">Tailored draft</h3>
                <p className="font-mono text-sm text-parchment/80 mb-3">
                  {tailorResult.summary}
                </p>
                <ul className="list-disc list-inside font-mono text-sm text-parchment/80 space-y-1 mb-3">
                  {tailorResult.bullets.map((b, i) => (
                    <li key={i}>{b}</li>
                  ))}
                </ul>
                <p className="font-mono text-xs text-parchment/60 whitespace-pre-wrap border-t border-brass/20 pt-3">
                  {tailorResult.cover_letter}
                </p>
                {tailorResult.flagged_unsupported_claims?.length > 0 && (
                  <div className="mt-3 border border-flagged rounded-sm p-3">
                    <p className="font-mono text-xs text-flagged uppercase tracking-wider mb-1">
                      Flagged — not traced to a fact in your KB
                    </p>
                    <ul className="font-mono text-xs text-flagged/90 list-disc list-inside">
                      {tailorResult.flagged_unsupported_claims.map((c, i) => (
                        <li key={i}>{c}</li>
                      ))}
                    </ul>
                  </div>
                )}
              </div>
            )}
          </section>
        )}

        {tab === "tracker" && (
          <section>
            <h2 className="font-display text-lg text-parchment mb-6">Pipeline</h2>
            <div className="grid gap-3">
              {applications.length === 0 && (
                <p className="text-parchment/50 font-mono text-sm">
                  Nothing saved yet — save a role from the Jobs tab.
                </p>
              )}
              {applications.map((a) => (
                <div
                  key={a.id}
                  className="bg-ledgerLight border border-brass/20 rounded-sm p-4 flex justify-between items-center"
                >
                  <div>
                    <p className="font-mono text-xs text-parchment/60">{a.portal || "—"}</p>
                    <p className="font-mono text-xs text-parchment/40 mt-1">
                      {a.next_follow_up_at
                        ? `follow up ${new Date(a.next_follow_up_at).toLocaleDateString()}`
                        : "no follow-up set"}
                    </p>
                  </div>
                  <select
                    value={a.status}
                    onChange={(e) => handleStatusChange(a.id, e.target.value)}
                    className="font-mono text-xs bg-ledger border border-brass/40 text-brass rounded-sm px-2 py-1"
                  >
                    {Object.entries(STATUS_LABELS).map(([val, label]) => (
                      <option key={val} value={val}>
                        {label}
                      </option>
                    ))}
                  </select>
                </div>
              ))}
            </div>
          </section>
        )}

        {tab === "facts" && (
          <section>
            <h2 className="font-display text-lg text-parchment mb-2">Facts KB</h2>
            <p className="font-mono text-xs text-parchment/50 mb-6">
              Every tailored bullet traces back to one of these. Nothing else is used.
            </p>
            <div className="grid gap-3">
              {facts.map((f) => (
                <div
                  key={f.id}
                  className="bg-ledgerLight border border-brass/20 rounded-sm p-4"
                >
                  <div className="flex justify-between items-start gap-3">
                    <p className="font-mono text-sm text-parchment/90">{f.achievement}</p>
                    <span className="stamp font-mono text-[10px] uppercase px-2 py-0.5 shrink-0">
                      Verified
                    </span>
                  </div>
                  <p className="font-mono text-xs text-parchment/50 mt-2">
                    {f.proof} {f.metric ? `· ${f.metric}` : ""}
                  </p>
                </div>
              ))}
            </div>
          </section>
        )}
      </main>
    </div>
  );
}
