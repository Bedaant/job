"use client";

import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import {
  ChevronRightIcon,
  CircleCheckIcon,
  CircleHelpIcon,
  InboxIcon,
  MailQuestionMarkIcon,
  PauseIcon,
  PlayIcon,
  SendIcon,
  SkipForwardIcon,
  SparklesIcon,
  TriangleAlertIcon,
  type LucideIcon,
} from "lucide-react";
import { api, ApiError, type ActivityItem, type Campaign } from "@/lib/api";
import { statusView } from "@/lib/campaign-form";
import {
  activityLink,
  dailyLimitCaption,
  formatWhen,
  greeting,
  homeState,
  maggieLabel,
  splitToday,
  summaryLine,
  unconfirmedAction,
} from "@/lib/today";
import { AppShell, useRequireAuth } from "@/components/AppShell";
import { useCampaignStatus } from "@/components/useCampaignStatus";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";

const errorText = (err: unknown) => (err instanceof ApiError ? err.message : "We couldn't reach the server.");

const ROW_ICON: Record<string, { Icon: LucideIcon; tone: string }> = {
  "application.submitted": { Icon: CircleCheckIcon, tone: "text-success" },
  // Sent but not confirmed: never the success tick.
  "application.unconfirmed": { Icon: MailQuestionMarkIcon, tone: "text-warning" },
  "application.needs_human": { Icon: CircleHelpIcon, tone: "text-warning" },
  "application.failed": { Icon: TriangleAlertIcon, tone: "text-destructive" },
  "application.ready_for_review": { Icon: InboxIcon, tone: "text-primary" },
  "application.approved": { Icon: SendIcon, tone: "text-muted-foreground" },
  "match.new": { Icon: SparklesIcon, tone: "text-primary" },
  "campaign.skipped": { Icon: SkipForwardIcon, tone: "text-muted-foreground" },
};

const BADGE = {
  success: "border-success/40 bg-success-soft text-success",
  warning: "border-warning/40 bg-warning-soft text-warning",
  muted: "border-border bg-muted text-muted-foreground",
};

function MaggieStatus({ campaign }: { campaign: Campaign }) {
  const { setStatus, pending, error } = useCampaignStatus(campaign);
  const view = statusView(campaign.status);
  const ActionIcon = view.action?.next === "paused" ? PauseIcon : PlayIcon;

  return (
    <section aria-labelledby="maggie-heading" className="rounded-2xl border bg-card p-5 shadow-sm sm:p-6">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div className="space-y-1.5" aria-live="polite">
          <span className={cn("inline-flex items-center rounded-full border px-3 py-1 text-sm font-semibold", BADGE[view.tone])}>
            {maggieLabel(campaign.status)}
          </span>
          <h2 id="maggie-heading" className="text-xl font-semibold tracking-tight">
            {view.headline}
          </h2>
        </div>
        {view.action && (
          <Button size="lg" variant={view.action.next === "paused" ? "outline" : "default"} disabled={pending} onClick={() => setStatus(view.action!.next)}>
            <ActionIcon aria-hidden="true" />
            {view.action.label}
          </Button>
        )}
      </div>
      {error && (
        <p role="alert" className="mt-4 rounded-xl bg-destructive/10 px-4 py-3 text-sm font-medium text-destructive">
          {error}
        </p>
      )}
    </section>
  );
}

function Tile({ label, value, sub, href }: { label: string; value: number; sub: string; href?: string }) {
  const body = (
    <>
      <span className="text-sm font-medium text-muted-foreground">{label}</span>
      <span className="mt-1 block text-3xl font-bold tabular-nums tracking-tight">{value}</span>
      <span className="mt-1 flex items-center gap-1 text-sm text-muted-foreground">
        {sub}
        {href && <ChevronRightIcon aria-hidden="true" className="size-4" />}
      </span>
    </>
  );
  const cls = "block rounded-2xl border bg-card p-5 shadow-sm";
  return href ? (
    <Link href={href} className={cn(cls, "transition-colors hover:bg-muted")}>
      {body}
    </Link>
  ) : (
    <div className={cls}>{body}</div>
  );
}

function ActivityList({ items }: { items: ActivityItem[] }) {
  return (
    <ol className="divide-y rounded-2xl border bg-card shadow-sm">
      {items.map((item) => {
        const { Icon, tone } = ROW_ICON[item.type] ?? ROW_ICON["application.approved"];
        const link = activityLink(item);
        const unconfirmed = item.type === "application.unconfirmed";
        return (
          <li key={item.id}>
            <Link
              href={link.href}
              {...(link.external ? { target: "_blank", rel: "noopener noreferrer" } : {})}
              className="flex items-start gap-3 px-4 py-3.5 transition-colors hover:bg-muted sm:px-5"
            >
              <Icon aria-hidden="true" className={cn("mt-0.5 size-5 shrink-0", tone)} />
              <span className="min-w-0 flex-1">
                <span className="block font-medium">
                  {item.title}
                  {item.job && (
                    <span className="font-normal text-muted-foreground">
                      {" "}
                      · {item.job.title} at {item.job.company}
                    </span>
                  )}
                </span>
                {unconfirmed ? (
                  <span className="mt-0.5 block text-sm text-warning">
                    {unconfirmedAction(item.job?.company)}
                    {link.external && <span className="sr-only"> (opens the form in a new tab)</span>}
                  </span>
                ) : (
                  item.detail && <span className="mt-0.5 block text-sm text-muted-foreground">{item.detail}</span>
                )}
              </span>
              <time dateTime={item.at} className="shrink-0 whitespace-nowrap text-sm tabular-nums text-muted-foreground">
                {formatWhen(item.at)}
              </time>
            </Link>
          </li>
        );
      })}
    </ol>
  );
}

const EMPTY: Record<string, string> = {
  waiting:
    "Maggie is waiting on her first search. Sending applications also needs the ApplyScout browser extension connected.",
  paused: "Maggie is paused, so nothing new will happen until you resume.",
  "not-started": "Start your campaign and Maggie begins looking for roles.",
  active: "Nothing yet today.",
};

export default function TodayPage() {
  const ready = useRequireAuth();
  const campaignsQuery = useQuery({ queryKey: ["campaigns"], queryFn: api.listCampaigns, enabled: ready });
  const todayQuery = useQuery({ queryKey: ["today"], queryFn: () => api.getToday(), enabled: ready });
  const activityQuery = useQuery({ queryKey: ["activity"], queryFn: () => api.getActivity(50), enabled: ready });

  if (!ready) return null;

  const queries = [campaignsQuery, todayQuery, activityQuery];
  const failed = queries.filter((q) => q.isError);
  const loading = queries.some((q) => q.isLoading);
  // Same pick as /campaign: archived campaigns are history.
  const campaign = campaignsQuery.data?.find((c) => c.status !== "archived");
  const counts = todayQuery.data;
  const activity = activityQuery.data ?? [];
  const state = homeState(campaign?.status, activity.length);
  const { today, earlier } = splitToday(activity);

  return (
    <AppShell
      title={greeting()}
      pageTitle="Today"
      description={counts && campaignsQuery.isSuccess ? summaryLine(counts, campaign?.status) : undefined}
    >
      {failed.length > 0 && (
        <div role="alert" className="mb-6 flex flex-wrap items-center justify-between gap-3 rounded-xl bg-destructive/10 px-4 py-3">
          <p className="text-sm font-medium text-destructive">Couldn&apos;t load today: {errorText(failed[0].error)}</p>
          <Button variant="outline" onClick={() => failed.forEach((q) => q.refetch())}>
            Retry
          </Button>
        </div>
      )}

      {loading && (
        <div className="space-y-6" aria-busy="true" aria-label="Loading today">
          <Skeleton className="h-28 w-full rounded-2xl" />
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <Skeleton className="h-32 rounded-2xl" />
            <Skeleton className="h-32 rounded-2xl" />
            <Skeleton className="h-32 rounded-2xl" />
            <Skeleton className="h-32 rounded-2xl" />
          </div>
          <Skeleton className="h-48 w-full rounded-2xl" />
        </div>
      )}

      {!loading && campaignsQuery.isSuccess && !campaign && (
        <div className="rounded-2xl border border-dashed px-6 py-12 text-center">
          <p className="text-lg font-semibold">Maggie has nothing to do yet</p>
          <p className="mx-auto mt-1 max-w-md text-muted-foreground">
            Tell her which roles to look for and how many applications a day are fine. Setup takes a few minutes.
          </p>
          <Button asChild className="mt-5">
            <Link href="/onboarding">Set up a campaign</Link>
          </Button>
        </div>
      )}

      {!loading && campaign && (
        <div className="space-y-8">
          <MaggieStatus campaign={campaign} />

          {counts && (
            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
              <Tile label="Sent today" value={counts.sent_today} sub={dailyLimitCaption(campaign.daily_cap)} />
              <Tile label="Ready to send" value={counts.ready_to_send ?? 0} sub="Send them" href="/review#ready-to-send" />
              <Tile label="Needs you" value={counts.needs_you} sub="Open Review" href="/review" />
              <Tile label="New matches" value={counts.new_matches_today} sub="See matches" href="/applications/matches" />
            </div>
          )}

          {activityQuery.isSuccess && (
            <section aria-labelledby="activity-heading" className="space-y-3">
              <h2 id="activity-heading" className="text-xl font-semibold tracking-tight">
                What Maggie did today
              </h2>
              {today.length > 0 ? (
                <ActivityList items={today} />
              ) : (
                <p className="rounded-2xl border border-dashed px-5 py-6 text-muted-foreground">{EMPTY[state]}</p>
              )}
              {today.length === 0 && earlier.length > 0 && (
                <>
                  <h3 className="pt-3 text-sm font-medium text-muted-foreground">Earlier</h3>
                  <ActivityList items={earlier.slice(0, 10)} />
                </>
              )}
            </section>
          )}
        </div>
      )}
    </AppShell>
  );
}
