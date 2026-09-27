"use client";

import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { api, Match } from "@/lib/api";
import { AppShell, useRequireAuth } from "@/components/AppShell";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { Button } from "@/components/ui/button";

function formatPostedAt(iso: string | null): string {
  if (!iso) return "date unknown";
  const days = Math.floor((Date.now() - new Date(iso).getTime()) / 86_400_000);
  if (days <= 0) return "today";
  if (days === 1) return "1 day ago";
  return `${days} days ago`;
}

function stateVariant(state: Match["state"]): "default" | "secondary" | "outline" {
  if (state === "saved") return "default";
  if (state === "dismissed") return "outline";
  return "secondary";
}

function MatchCard({ match }: { match: Match }) {
  const { job, breakdown, state } = match;
  return (
    <Card className="rounded-2xl transition-shadow hover:shadow-md">
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
          <span className="text-3xl font-bold tracking-tight tabular-nums" aria-label={`${match.score.toFixed(0)} percent match`}>
            {match.score.toFixed(0)}
            <span className="text-base font-semibold text-muted-foreground">%</span>
          </span>
          {state !== "new" && <Badge variant={stateVariant(state)}>{state}</Badge>}
        </div>
      </CardHeader>
      <CardContent className="space-y-3">
        <p className="text-sm text-muted-foreground">
          {formatPostedAt(job.posted_at)}
          {job.salary ? ` · ${job.salary}` : ""}
        </p>

        {breakdown.matched_skills.length > 0 && (
          <div className="flex flex-wrap gap-1">
            {breakdown.matched_skills.map((s) => (
              <Badge key={s} variant="secondary">{s}</Badge>
            ))}
          </div>
        )}
        {breakdown.missing_skills.length > 0 && (
          <p className="text-sm text-muted-foreground">
            Not in your facts: {breakdown.missing_skills.join(", ")}
          </p>
        )}

        <Button asChild variant="outline" size="sm">
          <a href={job.apply_url} target="_blank" rel="noreferrer">
            View listing<span className="sr-only"> (opens in a new tab)</span>
          </a>
        </Button>
      </CardContent>
    </Card>
  );
}

export default function MatchesPage() {
  const ready = useRequireAuth();

  const profilesQuery = useQuery({
    queryKey: ["profiles"],
    queryFn: api.listProfiles,
    enabled: ready,
  });
  const profile = profilesQuery.data?.[0];

  const matchesQuery = useQuery({
    queryKey: ["matches", profile?.id],
    queryFn: () => api.listMatches(profile!.id),
    enabled: !!profile,
  });

  if (!ready) return null;

  return (
    <AppShell
      title="Matches"
      description="Jobs Maggie found, ranked by how well your real experience fits — not keyword bingo."
    >
      {matchesQuery.isLoading && (
        <div className="space-y-4">
          <Skeleton className="h-40 w-full rounded-2xl" />
          <Skeleton className="h-40 w-full rounded-2xl" />
          <Skeleton className="h-40 w-full rounded-2xl" />
        </div>
      )}

      {matchesQuery.isSuccess && matchesQuery.data.length === 0 && (
        <div className="rounded-2xl border border-dashed px-6 py-12 text-center">
          <p className="text-lg font-semibold">No matches yet</p>
          <p className="mx-auto mt-1 max-w-md text-muted-foreground">
            Maggie ranks jobs against your confirmed facts. Add your facts first — matches appear once she&apos;s searched.
          </p>
          <Button asChild className="mt-5">
            <Link href="/facts">Add your facts</Link>
          </Button>
        </div>
      )}

      <div className="space-y-4">
        {matchesQuery.data?.map((m) => (
          <MatchCard key={m.id} match={m} />
        ))}
      </div>
    </AppShell>
  );
}
