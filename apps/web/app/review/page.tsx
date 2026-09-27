"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, ApiError } from "@/lib/api";
import { getToken } from "@/lib/auth";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Skeleton } from "@/components/ui/skeleton";
import { ApplicationCard } from "@/components/review/ApplicationCard";

export default function ReviewPage() {
  const router = useRouter();
  const queryClient = useQueryClient();
  const [ready, setReady] = useState(false);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [approveError, setApproveError] = useState<string | null>(null);

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
  const profile = profilesQuery.data?.[0];

  const queueQuery = useQuery({
    queryKey: ["review-queue", profile?.id],
    queryFn: () => api.listReviewQueue(profile!.id),
    enabled: !!profile,
  });

  // Real per-bullet diffs need the source fact text — reuse the same query key
  // the facts page uses so this doesn't cost a second round-trip if that page
  // was already visited this session.
  const factsQuery = useQuery({
    queryKey: ["facts", profile?.id],
    queryFn: () => api.listFacts(profile!.id),
    enabled: !!profile,
  });

  const approveMutation = useMutation({
    mutationFn: (ids: string[]) => api.batchApprove(ids),
    onSuccess: (result) => {
      setApproveError(null);
      setSelected(new Set());
      queryClient.setQueryData(
        ["review-queue", profile?.id],
        (old: typeof queueQuery.data) => old?.filter((a) => !result.approved.includes(a.id))
      );
    },
    onError: (err) => {
      // 404 = at least one selected id wasn't found/owned (all-or-nothing) — surface
      // it clearly rather than silently dropping the batch.
      setApproveError(err instanceof ApiError ? err.message : "Approval failed. Nothing was approved.");
    },
  });

  const dismissMutation = useMutation({
    mutationFn: (id: string) => api.dismissApplication(id),
    onSuccess: (_updated, id) => {
      queryClient.setQueryData(
        ["review-queue", profile?.id],
        (old: typeof queueQuery.data) => old?.filter((a) => a.id !== id)
      );
      setSelected((prev) => {
        const next = new Set(prev);
        next.delete(id);
        return next;
      });
    },
  });

  if (!ready) return null;

  const queue = queueQuery.data ?? [];
  const allSelected = queue.length > 0 && selected.size === queue.length;

  function toggleAll(checked: boolean) {
    setSelected(checked ? new Set(queue.map((a) => a.id)) : new Set());
  }

  function toggleOne(id: string, checked: boolean) {
    setSelected((prev) => {
      const next = new Set(prev);
      if (checked) next.add(id);
      else next.delete(id);
      return next;
    });
  }

  return (
    <main className="mx-auto max-w-3xl px-4 py-10">
      <h1 className="text-2xl font-semibold">Review queue</h1>
      <p className="mb-6 text-sm text-muted-foreground">
        Tailored and truth-checked applications, ready for your sign-off. Nothing is submitted
        until you approve it (ADR-001).
      </p>

      {(profilesQuery.isLoading || (!!profile && queueQuery.isLoading)) && (
        <div className="space-y-4">
          <Skeleton className="h-40 w-full" />
          <Skeleton className="h-40 w-full" />
          <Skeleton className="h-40 w-full" />
        </div>
      )}

      {profilesQuery.isSuccess && !profile && (
        <p className="text-sm text-muted-foreground">
          No profile yet — set one up on the{" "}
          <a href="/facts" className="underline">
            facts
          </a>{" "}
          page first.
        </p>
      )}

      {queueQuery.isSuccess && queue.length === 0 && (
        <div className="rounded-md border border-dashed p-6 text-center">
          <p className="text-sm font-medium">You&apos;re all caught up</p>
          <p className="mt-1 text-sm text-muted-foreground">
            Nothing is waiting for review right now. New matches get tailored and truth-checked
            automatically, then land here.
          </p>
          <Button asChild size="sm" className="mt-3">
            <a href="/matches">Browse matches</a>
          </Button>
        </div>
      )}

      {queueQuery.isError && (
        <p className="text-sm text-destructive">
          Couldn&apos;t load the review queue: {queueQuery.error instanceof ApiError ? queueQuery.error.message : "unknown error"}
        </p>
      )}

      {queue.length > 0 && (
        <>
          <div className="mb-4 flex items-center gap-3 rounded-md border p-3">
            <Checkbox checked={allSelected} onCheckedChange={(c) => toggleAll(c === true)} aria-label="Select all" />
            <span className="text-sm text-muted-foreground">
              {selected.size} of {queue.length} selected
            </span>
            <Button
              size="sm"
              className="ml-auto"
              disabled={selected.size === 0 || approveMutation.isPending}
              onClick={() => approveMutation.mutate(Array.from(selected))}
            >
              {approveMutation.isPending ? "Approving…" : `Approve ${selected.size}`}
            </Button>
          </div>

          {approveError && (
            <p className="mb-4 text-sm text-destructive">
              Approval failed: {approveError} — nothing was submitted. Check your selection and retry.
            </p>
          )}

          <div className="space-y-4">
            {queue.map((application) => (
              <ApplicationCard
                key={application.id}
                application={application}
                facts={factsQuery.data ?? []}
                selected={selected.has(application.id)}
                onToggleSelected={(checked) => toggleOne(application.id, checked)}
                onDismiss={() => dismissMutation.mutate(application.id)}
                isDismissing={dismissMutation.isPending && dismissMutation.variables === application.id}
                resumeUrl={api.resumeDocxUrl(profile!.id)}
                onSaveAnswer={async (question, answer) => {
                  await api.saveAnswer(profile!.id, question, answer);
                  // The backend derives pending_questions from the bank, so a
                  // refetch is what removes the answered one.
                  await queryClient.invalidateQueries({ queryKey: ["review-queue", profile?.id] });
                }}
              />
            ))}
          </div>
        </>
      )}
    </main>
  );
}
