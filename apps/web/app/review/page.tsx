"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, ApiError } from "@/lib/api";
import { AppShell, useRequireAuth } from "@/components/AppShell";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Skeleton } from "@/components/ui/skeleton";
import { ApplicationCard } from "@/components/review/ApplicationCard";
import { SendCard } from "@/components/review/SendCard";
import type { ReviewApplication } from "@/lib/api";
import { EXTENSION_NOTE, needsYouOnly, undoMessage, UNDO_MS, type SendAction } from "@/lib/assisted";

type Pending = { application: ReviewApplication; action: SendAction };

/**
 * "I've sent it" / "Not for me" hide the card at once and wait UNDO_MS before
 * telling the server, so Undo never has to reverse a write. Leaving the page
 * (or acting on another card) sends the waiting change immediately.
 */
function useUndoable(commit: (p: Pending) => void) {
  const [pending, setPending] = useState<Pending | null>(null);
  const ref = useRef<Pending | null>(null);
  const timer = useRef<ReturnType<typeof setTimeout>>(undefined);
  const commitRef = useRef(commit);
  commitRef.current = commit;

  const flush = useCallback(() => {
    clearTimeout(timer.current);
    if (ref.current) commitRef.current(ref.current);
    ref.current = null;
    setPending(null);
  }, []);

  useEffect(() => {
    window.addEventListener("pagehide", flush);
    return () => {
      window.removeEventListener("pagehide", flush);
      flush();
    };
  }, [flush]);

  function start(p: Pending) {
    flush();
    ref.current = p;
    setPending(p);
    timer.current = setTimeout(flush, UNDO_MS);
  }

  function undo() {
    clearTimeout(timer.current);
    ref.current = null;
    setPending(null);
  }

  return { pending, start, undo };
}

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

  const readyQuery = useQuery({
    queryKey: ["ready-to-send", profile?.id],
    queryFn: () => api.listReadyToSend(profile!.id),
    enabled: !!profile,
  });
  const [sendError, setSendError] = useState<string | null>(null);
  const undoButton = useRef<HTMLButtonElement>(null);

  const { pending, start, undo } = useUndoable(({ application, action }) => {
    const done = action === "sent" ? api.markApplied(application.id) : api.dismissApplication(application.id);
    done
      .then(() => {
        queryClient.setQueryData<ReviewApplication[]>(["ready-to-send", profile?.id], (old) =>
          old?.filter((a) => a.id !== application.id),
        );
        queryClient.invalidateQueries({ queryKey: ["today"] });
      })
      .catch((err) => {
        setSendError(
          `Couldn't save that for ${application.job.company}: ${err instanceof ApiError ? err.message : "network error"}. It's back in the list.`,
        );
        queryClient.invalidateQueries({ queryKey: ["ready-to-send", profile?.id] });
      });
  });

  // The card the user acted on is gone; keep keyboard focus somewhere useful.
  useEffect(() => {
    if (pending) undoButton.current?.focus();
  }, [pending]);

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

  const readyAll = readyQuery.data ?? [];
  const readyList = readyAll.filter((a) => a.id !== pending?.application.id);
  // A prepared application shows once, as ready to send — not again below.
  const queue = needsYouOnly(queueQuery.data ?? [], readyAll);
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
      description="Applications Maggie prepared from your facts. You send them; she never makes anything up."
    >
      {(readyList.length > 0 || pending) && (
        <section id="ready-to-send" aria-labelledby="ready-heading" className="mb-10 scroll-mt-20 space-y-4">
          <div className="space-y-1">
            <h2 id="ready-heading" className="text-xl font-semibold tracking-tight">
              Ready to send <span className="font-normal text-muted-foreground">({readyList.length})</span>
            </h2>
            <p className="text-sm text-muted-foreground">
              Everything is prepared. Download the resume, copy the text, open the form and press Submit. {EXTENSION_NOTE}
            </p>
          </div>

          <div role="status" aria-live="polite">
            {pending && (
              <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border bg-muted px-4 py-3">
                <p className="text-sm font-medium">{undoMessage(pending.action, pending.application.job)}</p>
                <Button ref={undoButton} type="button" variant="outline" className="min-h-11" onClick={undo}>
                  Undo
                </Button>
              </div>
            )}
          </div>

          {sendError && (
            <p role="alert" className="rounded-xl bg-destructive/10 px-4 py-3 text-sm font-medium text-destructive">
              {sendError}
            </p>
          )}

          {readyList.map((application) => (
            <SendCard
              key={application.id}
              application={application}
              onDownloadResume={() => api.downloadTailoredResumeDocx(application.id)}
              onSent={() => {
                setSendError(null);
                start({ application, action: "sent" });
              }}
              onDismiss={() => {
                setSendError(null);
                start({ application, action: "dismissed" });
              }}
            />
          ))}
        </section>
      )}

      {readyQuery.isError && (
        <p role="alert" className="mb-6 text-sm text-destructive">
          Couldn&apos;t load what&apos;s ready to send:{" "}
          {readyQuery.error instanceof ApiError ? readyQuery.error.message : "unknown error"}
        </p>
      )}

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

      {queue.length > 0 && readyList.length > 0 && (
        <h2 className="mb-4 text-xl font-semibold tracking-tight">Needs you first</h2>
      )}

      {queueQuery.isSuccess && queue.length === 0 && readyList.length === 0 && !pending && (
        <div className="rounded-2xl border border-dashed px-6 py-12 text-center">
          <p className="text-lg font-semibold">You&apos;re all caught up</p>
          <p className="mx-auto mt-1 max-w-md text-muted-foreground">
            Nothing needs you right now. New applications are tailored and truth-checked, then land here.
          </p>
          <Button asChild variant="outline" className="mt-5">
            <Link href="/applications/matches">See matches</Link>
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
                onDownloadResume={() => api.downloadResumeDocx(profile!.id)}
                onSaveAnswer={async (question, answer) => {
                  await api.saveAnswer(profile!.id, question, answer);
                  // The backend derives pending_questions from the bank, so a
                  // refetch is what removes the answered one.
                  await queryClient.invalidateQueries({ queryKey: ["review-queue", profile?.id] });
                  // Answering the last question can make it ready to send.
                  await queryClient.invalidateQueries({ queryKey: ["ready-to-send", profile?.id] });
                }}
              />
            ))}
          </div>
        </>
      )}
    </AppShell>
  );
}
