"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { api, Match } from "@/lib/api";
import { getToken } from "@/lib/auth";
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
    <Card>
      <CardHeader className="flex flex-row items-start justify-between gap-4">
        <div>
          <CardTitle>{job.title}</CardTitle>
          <p className="text-sm text-muted-foreground">
            {job.company}
            {job.location ? ` · ${job.location}` : ""}
            {job.remote ? " · Remote" : ""}
          </p>
        </div>
        <div className="flex flex-col items-end gap-1">
          <span className="text-2xl font-semibold tabular-nums">{match.score.toFixed(0)}</span>
          <Badge variant={stateVariant(state)}>{state}</Badge>
        </div>
      </CardHeader>
      <CardContent className="space-y-3">
        <p className="text-xs text-muted-foreground">
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
          <p className="text-xs text-muted-foreground">
            Missing: {breakdown.missing_skills.join(", ")}
          </p>
        )}

        <Button asChild size="sm">
          <a href={job.apply_url} target="_blank" rel="noreferrer">
            View listing
          </a>
        </Button>
      </CardContent>
    </Card>
  );
}

export default function MatchesPage() {
  const router = useRouter();
  const [ready, setReady] = useState(false);

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

  const matchesQuery = useQuery({
    queryKey: ["matches", profile?.id],
    queryFn: () => api.listMatches(profile!.id),
    enabled: !!profile,
  });

  if (!ready) return null;

  return (
    <main className="mx-auto max-w-3xl px-4 py-10">
      <h1 className="text-2xl font-semibold">Matches</h1>
      <p className="mb-6 text-sm text-muted-foreground">
        Jobs scored against your resume facts (F6 — semantic similarity, skill coverage, recency).
      </p>

      {matchesQuery.isLoading && (
        <div className="space-y-4">
          <Skeleton className="h-32 w-full" />
          <Skeleton className="h-32 w-full" />
          <Skeleton className="h-32 w-full" />
        </div>
      )}

      {matchesQuery.isSuccess && matchesQuery.data.length === 0 && (
        <p className="text-sm text-muted-foreground">
          No matches yet. This needs a confirmed resume-facts KB and embedded jobs in the database first.
        </p>
      )}

      <div className="space-y-4">
        {matchesQuery.data?.map((m) => (
          <MatchCard key={m.id} match={m} />
        ))}
      </div>
    </main>
  );
}
