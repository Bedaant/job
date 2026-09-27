"use client";

import Link from "next/link";
import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { BookmarkIcon } from "lucide-react";
import { api, type Match } from "@/lib/api";
import { statusLabel } from "@/lib/applications";
import { AppShell, useRequireAuth } from "@/components/AppShell";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Button } from "@/components/ui/button";
import { SectionTabs, useProfile } from "../parts";

function formatPostedAt(iso: string | null): string {
  if (!iso) return "date unknown";
  const days = Math.floor((Date.now() - new Date(iso).getTime()) / 86_400_000);
  if (days <= 0) return "today";
  if (days === 1) return "1 day ago";
  return `${days} days ago`;
}

type Say = (text: string, failed?: boolean) => void;

function MatchCard({ match, profileId, say }: { match: Match; profileId: string; say: Say }) {
  const { job, breakdown, state } = match;
  const qc = useQueryClient();
  const key = ["matches", profileId];
  const what = `${job.title} at ${job.company}`;

  const setState = useMutation({
    mutationFn: (next: Match["state"]) => api.setMatchState(match.id, next),
    onMutate: async (next) => {
      await qc.cancelQueries({ queryKey: key });
      const before = qc.getQueryData<Match[]>(key);
      qc.setQueryData<Match[]>(key, (rows) =>
        next === "dismissed" ? rows?.filter((m) => m.id !== match.id) : rows?.map((m) => (m.id === match.id ? { ...m, state: next } : m))
      );
      return { before };
    },
    onError: (_e, _n, ctx) => {
      qc.setQueryData(key, ctx?.before);
      say(`Couldn't update ${what}. Try again.`, true);
    },
    onSuccess: (_d, next) =>
      say(next === "dismissed" ? `Hid ${what}.` : next === "saved" ? `Saved ${what}.` : `Unsaved ${what}.`),
  });

  const prepare = useMutation({
    mutationFn: () => api.prepareMatch(match.id),
    onSuccess: (r) => {
      say(r.queued ? `Maggie is preparing ${what}. It will show up in Review.` : `${what} is already prepared.`);
      qc.invalidateQueries({ queryKey: key });
      qc.invalidateQueries({ queryKey: ["applications"] });
    },
    onError: (e: Error) => say(e.message || `Couldn't start preparing ${what}.`, true),
  });

  return (
    <Card className="rounded-2xl">
      <CardHeader className="flex flex-row items-start justify-between gap-4">
        <div className="space-y-1">
          <CardTitle className="text-lg">{job.title}</CardTitle>
          <p className="text-sm text-muted-foreground">
            {job.company}
            {job.location ? ` · ${job.location}` : ""}
            {job.remote ? " · Remote" : ""}
          </p>
        </div>
        <div className="flex flex-col items-end gap-1">
          <span className="text-3xl font-bold tracking-tight tabular-nums">
            {match.score.toFixed(0)}
            <span className="text-base font-semibold text-muted-foreground">%</span>
            <span className="sr-only"> match</span>
          </span>
          {state === "saved" && (
            <span className="inline-flex items-center gap-1 text-xs font-medium text-primary">
              <BookmarkIcon aria-hidden="true" className="size-3.5" /> Saved
            </span>
          )}
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        <p className="text-sm text-muted-foreground">
          Posted {formatPostedAt(job.posted_at)}
          {job.salary ? ` · ${job.salary}` : ""}
        </p>
        {breakdown.matched_skills.length > 0 && (
          <p className="text-sm">
            <span className="font-medium">In your facts:</span> {breakdown.matched_skills.join(", ")}
          </p>
        )}
        {breakdown.missing_skills.length > 0 && (
          <p className="text-sm text-muted-foreground">Not in your facts: {breakdown.missing_skills.join(", ")}</p>
        )}

        <div className="flex flex-wrap gap-2">
          {match.application_id ? (
            <Button asChild className="h-11">
              <Link href={`/applications/${match.application_id}`}>
                {statusLabel(match.application_status ?? "saved")} — open
                <span className="sr-only"> {what}</span>
              </Link>
            </Button>
          ) : (
            <Button className="h-11" disabled={prepare.isPending} onClick={() => prepare.mutate()}>
              {prepare.isPending ? "Starting…" : "Prepare this one"}
            </Button>
          )}
          <Button
            variant="outline"
            className="h-11"
            aria-pressed={state === "saved"}
            onClick={() => setState.mutate(state === "saved" ? "new" : "saved")}
          >
            {state === "saved" ? "Saved" : "Save"}
            <span className="sr-only"> {what}</span>
          </Button>
          <Button variant="ghost" className="h-11" onClick={() => setState.mutate("dismissed")}>
            Not for me<span className="sr-only">: {what}</span>
          </Button>
          <Button asChild variant="ghost" className="h-11">
            <a href={job.apply_url} target="_blank" rel="noreferrer">
              View listing<span className="sr-only"> for {what} (opens in a new tab)</span>
            </a>
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}

export default function MatchesPage() {
  const ready = useRequireAuth();
  const { profile } = useProfile(ready);
  const [announce, setAnnounce] = useState<{ text: string; failed?: boolean } | null>(null);

  const matchesQuery = useQuery({
    queryKey: ["matches", profile?.id],
    queryFn: () => api.listMatches(profile!.id),
    enabled: !!profile,
  });

  if (!ready) return null;

  return (
    <AppShell
      title="Applications"
      pageTitle="Matches"
      description="Jobs Maggie found, ranked by how well your real experience fits. Prepare the ones you want."
    >
      <SectionTabs />
      <p
        role={announce?.failed ? "alert" : "status"}
        aria-live={announce?.failed ? "assertive" : "polite"}
        className={announce ? "mb-4 rounded-lg bg-muted px-4 py-2 text-sm" : "sr-only"}
      >
        {announce?.text}
      </p>

      {matchesQuery.isLoading && (
        <div className="space-y-4">
          <Skeleton className="h-40 w-full rounded-2xl" />
          <Skeleton className="h-40 w-full rounded-2xl" />
        </div>
      )}

      {matchesQuery.isError && (
        <div role="alert" className="flex flex-wrap items-center gap-3 rounded-2xl border px-4 py-3">
          <span>Couldn&apos;t load your matches.</span>
          <Button variant="outline" className="h-11" onClick={() => matchesQuery.refetch()}>Retry</Button>
        </div>
      )}

      {matchesQuery.isSuccess && matchesQuery.data.length === 0 && (
        <div className="rounded-2xl border border-dashed px-6 py-12 text-center">
          <p className="text-lg font-semibold">No matches yet</p>
          <p className="mx-auto mt-1 max-w-md text-muted-foreground">
            Maggie ranks jobs against your confirmed facts. Add your facts first — matches appear once she&apos;s searched.
          </p>
          <Button asChild className="mt-5 h-11">
            <Link href="/facts">Add your facts</Link>
          </Button>
        </div>
      )}

      <div className="space-y-4">
        {profile &&
          matchesQuery.data?.map((m) => (
            <MatchCard key={m.id} match={m} profileId={profile.id} say={(text, failed) => setAnnounce({ text, failed })} />
          ))}
      </div>
    </AppShell>
  );
}
