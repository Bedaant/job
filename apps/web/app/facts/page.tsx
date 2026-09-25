"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, ApiError, FactDraft } from "@/lib/api";
import { getToken } from "@/lib/auth";

export default function FactsPage() {
  const router = useRouter();
  const queryClient = useQueryClient();
  const [ready, setReady] = useState(false);
  const [draftFacts, setDraftFacts] = useState<FactDraft[] | null>(null);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [confirmedCount, setConfirmedCount] = useState<number | null>(null);

  useEffect(() => {
    if (!getToken()) {
      router.push("/login");
    } else {
      setReady(true);
    }
  }, [router]);

  const profilesQuery = useQuery({
    queryKey: ["profiles"],
    queryFn: api.listProfiles,
    enabled: ready,
  });

  const ensureProfile = useMutation({
    mutationFn: () => api.createProfile("developer"),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["profiles"] }),
  });

  const profile = profilesQuery.data?.[0];

  useEffect(() => {
    if (ready && profilesQuery.isSuccess && profilesQuery.data.length === 0 && !ensureProfile.isPending) {
      ensureProfile.mutate();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ready, profilesQuery.isSuccess, profilesQuery.data]);

  const factsQuery = useQuery({
    queryKey: ["facts", profile?.id],
    queryFn: () => api.listFacts(profile!.id),
    enabled: !!profile,
  });

  const uploadMutation = useMutation({
    mutationFn: (file: File) => api.uploadResume(profile!.id, file),
    onSuccess: (result) => {
      setUploadError(null);
      setConfirmedCount(null);
      if (result.status === "failed") {
        setUploadError(result.error || "Parsing failed");
        setDraftFacts(null);
      } else {
        setDraftFacts(result.facts);
      }
    },
    onError: (err) => setUploadError(err instanceof ApiError ? err.message : "Upload failed"),
  });

  const confirmMutation = useMutation({
    mutationFn: (facts: FactDraft[]) => api.confirmFacts(profile!.id, facts),
    onSuccess: (created) => {
      setConfirmedCount(created.length);
      setDraftFacts(null);
      queryClient.invalidateQueries({ queryKey: ["facts", profile?.id] });
    },
  });

  function handleFileChange(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (file) uploadMutation.mutate(file);
    e.target.value = "";
  }

  function updateDraft(index: number, patch: Partial<FactDraft>) {
    setDraftFacts((prev) => prev && prev.map((f, i) => (i === index ? { ...f, ...patch } : f)));
  }

  function removeDraft(index: number) {
    setDraftFacts((prev) => prev && prev.filter((_, i) => i !== index));
  }

  if (!ready) return null;

  return (
    <main style={{ maxWidth: 720, margin: "40px auto", fontFamily: "sans-serif", padding: "0 16px" }}>
      <a href="/matches" style={{ fontSize: 13 }}>View matches →</a>
      <h1>Your resume facts</h1>
      <p style={{ color: "#555" }}>
        Upload a resume (.pdf or .docx, under 5MB). We parse it into atomic facts you review and confirm — nothing
        is added to your Facts KB until you approve it.
      </p>

      {!profile && <p>Setting up your profile…</p>}

      {profile && (
        <>
          <input type="file" accept=".pdf,.docx" onChange={handleFileChange} disabled={uploadMutation.isPending} />
          {uploadMutation.isPending && <p>Parsing your resume…</p>}
          {uploadError && (
            <p style={{ color: "crimson" }}>
              Couldn&apos;t parse this resume: {uploadError}
            </p>
          )}
          {confirmedCount !== null && (
            <p style={{ color: "seagreen" }}>Saved {confirmedCount} fact{confirmedCount === 1 ? "" : "s"} to your KB.</p>
          )}

          {draftFacts && draftFacts.length > 0 && (
            <section style={{ marginTop: 24 }}>
              <h2>Review {draftFacts.length} parsed facts</h2>
              {draftFacts.map((fact, i) => (
                <div key={i} style={{ border: "1px solid #ddd", borderRadius: 6, padding: 12, marginBottom: 8 }}>
                  <textarea
                    value={fact.achievement}
                    onChange={(e) => updateDraft(i, { achievement: e.target.value })}
                    style={{ width: "100%", marginBottom: 6 }}
                    rows={2}
                  />
                  <div style={{ display: "flex", gap: 8, fontSize: 13, color: "#666" }}>
                    <span>{fact.category}</span>
                    {fact.proof && <span>· {fact.proof}</span>}
                    {fact.metric ? (
                      <span>· {fact.metric}</span>
                    ) : (
                      <span style={{ color: "#c60" }}>· no metric — consider adding one</span>
                    )}
                  </div>
                  <button onClick={() => removeDraft(i)} style={{ marginTop: 6 }}>
                    Remove
                  </button>
                </div>
              ))}
              <button
                onClick={() => confirmMutation.mutate(draftFacts)}
                disabled={confirmMutation.isPending || draftFacts.length === 0}
                style={{ padding: "8px 16px", marginTop: 8 }}
              >
                {confirmMutation.isPending ? "Saving…" : `Confirm ${draftFacts.length} facts`}
              </button>
            </section>
          )}

          <section style={{ marginTop: 32 }}>
            <h2>Confirmed facts ({factsQuery.data?.length ?? 0})</h2>
            {factsQuery.data?.map((fact) => (
              <div key={fact.id} style={{ padding: "6px 0", borderBottom: "1px solid #eee" }}>
                {fact.achievement}
              </div>
            ))}
          </section>
        </>
      )}
    </main>
  );
}
