"use client";

import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { Loader2Icon } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { ApiError, api } from "@/lib/api";
import type { Campaign } from "@/lib/api";
import { ExtensionStatus } from "@/components/ExtensionStatus";
import { FailureNotice } from "./fields";

export function StepDone({ campaign, profileId, started }: { campaign: Campaign; profileId: string; started: boolean }) {
  const statsQuery = useQuery({
    queryKey: ["campaign-stats", campaign.id],
    queryFn: () => api.getCampaignStats(campaign.id),
    retry: false,
  });

  const matchesQuery = useQuery({
    queryKey: ["matches", profileId],
    queryFn: () => api.listMatches(profileId),
    retry: false,
  });

  return (
    <div className="space-y-6">
      <div className="rounded-md border border-input bg-secondary/40 p-4">
        <p className="text-sm font-medium">
          {started ? `“${campaign.name}” is on.` : `“${campaign.name}” is saved but didn't start.`}
        </p>
        {!started && (
          <p role="alert" className="mt-1 text-sm text-destructive">
            Maggie couldn&apos;t begin her first search. Open Campaign and press Start to try again.
          </p>
        )}
        <p className="mt-1 text-sm text-muted-foreground">
          Maggie checks {campaign.sources.length} {campaign.sources.length === 1 ? "source" : "sources"} for{" "}
          {campaign.roles.join(", ")}, keeping anything above {Math.round(campaign.min_match_score * 100)}%, up to{" "}
          {campaign.daily_cap} a day.{" "}
          {campaign.auto_submit
            ? "Applications will be submitted without asking you again."
            : "Everything waits in your review queue until you approve it."}
        </p>
      </div>

      <section aria-labelledby="extension-heading" className="space-y-3 rounded-md border border-input p-4">
        <h3 id="extension-heading" className="text-base font-medium">
          Let Maggie apply from your browser
        </h3>
        <p className="text-sm text-muted-foreground">
          Maggie finds and tailors from here, but she sends applications from <em>your</em> browser, signed in as
          you — never from a shared bot. Until the ApplyScout extension is running, nothing is sent.
        </p>
        <ol className="list-decimal space-y-2 pl-5 text-sm">
          <li>
            Install the extension. It isn&apos;t in the Chrome Web Store yet: open{" "}
            <code className="rounded bg-secondary px-1">chrome://extensions</code>, turn on Developer mode, choose{" "}
            <strong>Load unpacked</strong> and pick the <code className="rounded bg-secondary px-1">apps/extension/dist</code>{" "}
            folder.
          </li>
          <li>Click the ApplyScout icon in the toolbar and sign in with this account.</li>
          <li>
            Press <strong>Run apply queue</strong>. Keep the browser open while it works; it applies up to your daily
            cap.
          </li>
        </ol>
        <ExtensionStatus />
      </section>

      <section aria-labelledby="stats-heading" className="space-y-2">
        <h3 id="stats-heading" className="text-base font-medium">
          Today
        </h3>
        {statsQuery.isLoading && (
          <p className="flex items-center gap-2 text-sm text-muted-foreground">
            <Loader2Icon className="h-4 w-4 animate-spin" aria-hidden="true" />
            Checking…
          </p>
        )}
        {statsQuery.isError && (
          <FailureNotice
            title="Campaign stats are not available"
            detail={
              statsQuery.error instanceof ApiError && statsQuery.error.status === 404
                ? "Today's numbers aren't available right now. Your campaign is saved."
                : String(statsQuery.error)
            }
          />
        )}
        {statsQuery.data && (
          <dl className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            {[
              ["Applied today", statsQuery.data.applied_today],
              ["Remaining today", statsQuery.data.remaining_today],
              ["Daily cap", statsQuery.data.daily_cap],
              ["Applied in total", statsQuery.data.total_applied],
            ].map(([label, value]) => (
              <div key={String(label)} className="rounded-md border border-input p-3">
                <dt className="text-xs text-muted-foreground">{label}</dt>
                <dd className="text-xl font-medium tabular-nums">{value}</dd>
              </div>
            ))}
          </dl>
        )}
      </section>

      <section aria-labelledby="matches-heading" className="space-y-2">
        <h3 id="matches-heading" className="text-base font-medium">
          First matches
        </h3>
        {matchesQuery.isLoading && (
          <p className="flex items-center gap-2 text-sm text-muted-foreground">
            <Loader2Icon className="h-4 w-4 animate-spin" aria-hidden="true" />
            Looking…
          </p>
        )}
        {matchesQuery.isError && (
          <FailureNotice title="Could not load matches" detail={String(matchesQuery.error)} />
        )}
        {matchesQuery.isSuccess && matchesQuery.data.length === 0 && (
          <p className="text-sm text-muted-foreground">
            Nothing yet. The first pass takes a few minutes; matches appear on your matches page as they land —
            you do not need to sit here.
          </p>
        )}
        {matchesQuery.data && matchesQuery.data.length > 0 && (
          <ul className="divide-y divide-border rounded-md border border-input">
            {matchesQuery.data.slice(0, 5).map((match) => (
              <li key={match.id} className="flex items-center justify-between gap-4 p-3">
                <div className="min-w-0">
                  <p className="truncate text-sm font-medium">{match.job.title}</p>
                  <p className="truncate text-xs text-muted-foreground">
                    {match.job.company}
                    {match.job.location ? ` · ${match.job.location}` : ""}
                  </p>
                </div>
                <Badge variant="secondary" className="shrink-0 tabular-nums">
                  {Math.round(match.score)}%
                </Badge>
              </li>
            ))}
          </ul>
        )}
      </section>

      <nav aria-label="Where to go next" className="flex flex-wrap gap-2">
        <Link
          href="/matches"
          className="rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:opacity-90 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
        >
          See all matches
        </Link>
        <Link
          href="/review"
          className="rounded-md border border-input px-4 py-2 text-sm font-medium hover:bg-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
        >
          Review queue
        </Link>
        <Link
          href="/facts"
          className="rounded-md border border-input px-4 py-2 text-sm font-medium hover:bg-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
        >
          Add more facts
        </Link>
      </nav>
    </div>
  );
}
