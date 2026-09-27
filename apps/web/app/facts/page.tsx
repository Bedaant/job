"use client";

import { useEffect, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { FileUpIcon } from "lucide-react";
import { api, ApiError, FactDraft } from "@/lib/api";
import { AppShell, useRequireAuth } from "@/components/AppShell";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { Textarea } from "@/components/ui/textarea";

export default function FactsPage() {
  const queryClient = useQueryClient();
  const ready = useRequireAuth();
  const fileInput = useRef<HTMLInputElement>(null);
  const [draftFacts, setDraftFacts] = useState<FactDraft[] | null>(null);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [confirmedCount, setConfirmedCount] = useState<number | null>(null);

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

  const facts = factsQuery.data ?? [];

  return (
    <AppShell
      title="Your facts"
      description="Everything Maggie writes comes from these — nothing else. Upload a resume and check each fact before you keep it — once kept, a fact can't be edited or removed yet."
    >
      {!profile && <Skeleton className="h-40 w-full rounded-2xl" />}

      {profile && (
        <div className="space-y-10">
          <section aria-labelledby="upload-h">
            <h2 id="upload-h" className="sr-only">Upload a resume</h2>
            <input
              ref={fileInput}
              id="resume-file"
              type="file"
              accept=".pdf,.docx"
              onChange={handleFileChange}
              disabled={uploadMutation.isPending}
              className="sr-only"
            />
            <button
              type="button"
              onClick={() => fileInput.current?.click()}
              disabled={uploadMutation.isPending}
              className="flex w-full flex-col items-center gap-3 rounded-2xl border-2 border-dashed border-input bg-card px-6 py-10 text-center transition-colors hover:border-primary hover:bg-accent disabled:cursor-wait disabled:opacity-70"
            >
              <FileUpIcon className="size-9 text-primary" aria-hidden="true" />
              <span className="text-lg font-semibold">
                {uploadMutation.isPending ? "Reading your resume…" : "Choose a resume to add facts"}
              </span>
              <span className="text-sm text-muted-foreground">
                PDF or Word, under 5 MB · nothing is saved until you confirm
              </span>
            </button>

            <div aria-live="polite" className="mt-3 space-y-2">
              {uploadError && (
                <p role="alert" className="rounded-xl bg-destructive/10 px-4 py-3 text-sm font-medium text-destructive">
                  We couldn&apos;t read this resume: {uploadError}
                </p>
              )}
              {confirmedCount !== null && (
                <p className="rounded-xl bg-success-soft px-4 py-3 text-sm font-medium text-success">
                  Saved {confirmedCount} fact{confirmedCount === 1 ? "" : "s"}.
                </p>
              )}
            </div>
          </section>

          {draftFacts && draftFacts.length > 0 && (
            <section aria-labelledby="draft-h" className="space-y-4">
              <div className="space-y-1">
                <h2 id="draft-h" className="text-xl font-semibold">Check {draftFacts.length} facts we found</h2>
                <p className="text-muted-foreground">Fix anything that&apos;s off and remove anything that isn&apos;t true.</p>
              </div>
              <ul className="space-y-3">
                {draftFacts.map((fact, i) => (
                  <li key={i} className="space-y-3 rounded-2xl border bg-card p-5 shadow-sm">
                    <label htmlFor={`draft-${i}`} className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                      {fact.category}
                    </label>
                    <Textarea
                      id={`draft-${i}`}
                      value={fact.achievement}
                      onChange={(e) => updateDraft(i, { achievement: e.target.value })}
                      rows={2}
                    />
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <p className="text-sm text-muted-foreground">
                        {[fact.proof, fact.metric].filter(Boolean).join(" · ") ||
                          "No number yet — add one if you have it; Maggie never makes one up."}
                      </p>
                      <Button variant="ghost" size="sm" onClick={() => removeDraft(i)}>
                        Remove
                      </Button>
                    </div>
                  </li>
                ))}
              </ul>
              <Button
                size="lg"
                onClick={() => confirmMutation.mutate(draftFacts)}
                disabled={confirmMutation.isPending || draftFacts.length === 0}
              >
                {confirmMutation.isPending ? "Saving…" : `Keep ${draftFacts.length} facts`}
              </Button>
            </section>
          )}

          <section aria-labelledby="confirmed-h" className="space-y-4">
            <h2 id="confirmed-h" className="text-xl font-semibold">
              Confirmed <span className="text-muted-foreground tabular-nums">{facts.length}</span>
            </h2>
            {factsQuery.isLoading && <Skeleton className="h-24 w-full rounded-2xl" />}
            {factsQuery.isSuccess && facts.length === 0 && (
              <p className="rounded-2xl border border-dashed px-6 py-8 text-center text-muted-foreground">
                No facts yet. Add a resume above — it takes about 20 seconds.
              </p>
            )}
            {facts.length > 0 && (
              <ul className="divide-y rounded-2xl border bg-card shadow-sm">
                {facts.map((fact) => (
                  <li key={fact.id} className="flex items-start gap-4 px-5 py-4">
                    <span className="mt-0.5 shrink-0 rounded-md bg-accent px-2 py-0.5 text-xs font-semibold text-accent-foreground">
                      {fact.category}
                    </span>
                    <span className="leading-relaxed">{fact.achievement}</span>
                  </li>
                ))}
              </ul>
            )}
          </section>
        </div>
      )}
    </AppShell>
  );
}
