"use client";

import { useState } from "react";
import Link from "next/link";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, ApiError } from "@/lib/api";
import { AppShell, useRequireAuth } from "@/components/AppShell";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Skeleton } from "@/components/ui/skeleton";
import { ApplicationCard } from "@/components/review/ApplicationCard";

export default function ReviewPage() {
  const queryClient = useQueryClient();
  const ready = useRequireAuth();
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [approveError, setApproveError] = useState<string | null>(null);

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
    <AppShell
      title="Review"
      description="Applications Maggie tailored from your facts, plus anything a form asked that only you can answer. Approve to send."
    >
      {(profilesQuery.isLoading || (!!profile && queueQuery.isLoading)) && (
        <div className="space-y-4">
          <Skeleton className="h-48 w-full rounded-2xl" />
          <Skeleton className="h-48 w-full rounded-2xl" />
        </div>
      )}

      {profilesQuery.isSuccess && !profile && (
        <div className="rounded-2xl border border-dashed px-6 py-12 text-center">
          <p className="text-lg font-semibold">Let&apos;s set you up first</p>
          <p className="mx-auto mt-1 max-w-md text-muted-foreground">Two minutes: your resume, your facts, and what you&apos;re looking for.</p>
          <Button asChild className="mt-5">
            <Link href="/onboarding">Start setup</Link>
          </Button>
        </div>
      )}

      {queueQuery.isSuccess && queue.length === 0 && (
        <div className="rounded-2xl border border-dashed px-6 py-12 text-center">
          <p className="text-lg font-semibold">You&apos;re all caught up</p>
          <p className="mx-auto mt-1 max-w-md text-muted-foreground">
            Nothing needs you right now. New applications are tailored and truth-checked, then land here.
          </p>
          <Button asChild variant="outline" className="mt-5">
            <Link href="/matches">See matches</Link>
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
          <div className="sticky top-16 z-30 mb-5 flex items-center gap-3 rounded-2xl border bg-card/90 p-3 pl-4 shadow-sm backdrop-blur-xl">
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
            <p role="alert" className="mb-4 rounded-xl bg-destructive/10 px-4 py-3 text-sm font-medium text-destructive">
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
    </AppShell>
  );
}
