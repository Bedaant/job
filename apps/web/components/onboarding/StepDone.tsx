"use client";

import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { Loader2Icon } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { ApiError, api } from "@/lib/api";
import type { Campaign } from "@/lib/api";
import { errorText, firstMatchesState, SEARCH_POLL_MS } from "@/lib/onboarding";
import { ExtensionStatus } from "@/components/ExtensionStatus";
import { submitModeLine } from "@/lib/assisted";
import { FailureNotice } from "./fields";

export function StepDone({ campaign, profileId, started }: { campaign: Campaign; profileId: string; started: boolean }) {
  const statsQuery = useQuery({
    queryKey: ["campaign-stats", campaign.id],
    queryFn: () => api.getCampaignStats(campaign.id),
    retry: false,
    // Poll until the first run stamps last_run_at.
    refetchInterval: (q) => (started && q.state.data?.last_run_at === null ? SEARCH_POLL_MS : false),
  });

  const matchesQuery = useQuery({
    queryKey: ["matches", profileId],
    queryFn: () => api.listMatches(profileId),
    retry: false,
    refetchInterval: started && statsQuery.data?.last_run_at === null ? SEARCH_POLL_MS : false,
  });
  const matchesState = firstMatchesState(started, matchesQuery.data?.length, statsQuery.data?.last_run_at);

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
          {submitModeLine(campaign.auto_submit)}
        </p>
      </div>

      <section aria-labelledby="assisted-heading" className="space-y-3 rounded-md border border-input p-4">
        <h3 id="assisted-heading" className="text-base font-medium">
          Send applications from any device
        </h3>
        <p className="text-sm text-muted-foreground">
          Works on your phone, no extension needed. Maggie prepares each application; in <strong>Ready to send</strong>{" "}
          you download the tailored resume, open the employer&apos;s form and press Submit yourself.
          {campaign.auto_submit && " Automatic sending needs the ApplyScout extension on a computer; until it's connected, nothing is sent automatically."}
        </p>
        <Link
          href="/review#ready-to-send"
          className="inline-flex min-h-11 items-center rounded-md border border-input px-4 text-sm font-medium hover:bg-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
        >
          Open Ready to send
        </Link>
      </section>

      {/* Browser extensions don't run on phones, so this is for computers only. */}
      <section aria-labelledby="extension-heading" className="hidden space-y-3 rounded-md border border-input p-4 md:block">
        <h3 id="extension-heading" className="text-base font-medium">
          On a computer: the ApplyScout extension (optional)
        </h3>
        <p className="text-sm text-muted-foreground">
          If you have the extension, it fills in the employer&apos;s form from <em>your</em> browser, signed in as
          you. Click the ApplyScout icon, sign in with this account and press <strong>Run apply queue</strong>.
        </p>
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
                : errorText(statsQuery.error)
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
          <FailureNotice title="Could not load matches" detail={errorText(matchesQuery.error)} />
        )}
        {matchesState === "searching" && (
          <p role="status" className="flex items-center gap-2 text-sm text-muted-foreground">
            <Loader2Icon className="h-4 w-4 animate-spin" aria-hidden="true" />
            Searching for your matches. This takes a few minutes; you don&apos;t need to stay on this page.
          </p>
        )}
        {matchesState === "none" && (
          <p className="text-sm text-muted-foreground">
            Nothing yet. Matches appear on your matches page as Maggie finds them — you do not need to sit here.
          </p>
        )}
        {matchesQuery.data && matchesState === "found" && (
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
          href="/today"
          className="inline-flex min-h-11 items-center rounded-md bg-primary px-4 text-sm font-medium text-primary-foreground hover:opacity-90 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
        >
          Go to Today
        </Link>
        <Link
          href="/applications/matches"
          className="inline-flex min-h-11 items-center rounded-md border border-input px-4 text-sm font-medium hover:bg-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
        >
          See all matches
        </Link>
        <Link
          href="/facts"
          className="inline-flex min-h-11 items-center rounded-md border border-input px-4 text-sm font-medium hover:bg-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
        >
          Add more facts
        </Link>
      </nav>
    </div>
  );
}
