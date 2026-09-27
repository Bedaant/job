"use client";

import Link from "next/link";
import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api, type ApplicationRow } from "@/lib/api";
import { COLUMNS, groupPipeline } from "@/lib/applications";
import { formatWhen } from "@/lib/today";
import { AppShell, useRequireAuth } from "@/components/AppShell";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { MoveMenu, SectionTabs, StatusPill, useProfile } from "./parts";

function TrackerCard({
  application,
  profileId,
  onDone,
}: {
  application: ApplicationRow;
  profileId: string | undefined;
  onDone: (m: string, failed?: boolean) => void;
}) {
  const { job } = application;
  return (
    <li className="space-y-3 rounded-2xl border bg-card p-4 shadow-sm">
      <div className="space-y-1">
        <Link
          href={`/applications/${application.id}`}
          className="block rounded font-semibold leading-snug hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
        >
          {job.title}
        </Link>
        <p className="text-sm text-muted-foreground">{job.company}</p>
      </div>
      <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
        <StatusPill status={application.status} />
        {application.applied_at && <span>Sent {formatWhen(application.applied_at)}</span>}
      </div>
      <MoveMenu application={application} profileId={profileId} onDone={onDone} />
    </li>
  );
}

export default function ApplicationsPage() {
  const ready = useRequireAuth();
  const { profile } = useProfile(ready);
  const [announce, setAnnounce] = useState<{ text: string; failed?: boolean } | null>(null);
  const onDone = (text: string, failed?: boolean) => setAnnounce({ text, failed });

  const list = useQuery({
    queryKey: ["applications", profile?.id],
    queryFn: () => api.listApplications(profile!.id),
    enabled: !!profile,
  });

  if (!ready) return null;
  const { columns, notSent } = groupPipeline(list.data ?? []);
  const open = COLUMNS.filter((c) => c.id !== "closed");
  const sentCount = COLUMNS.reduce((n, c) => n + columns[c.id].length, 0);

  return (
    <AppShell title="Applications" description="Everything you've sent, and where each one stands.">
      <SectionTabs />

      {/* One live region for every move, so a screen reader hears the result. */}
      <p
        role={announce?.failed ? "alert" : "status"}
        aria-live={announce?.failed ? "assertive" : "polite"}
        className={announce ? "mb-4 rounded-lg bg-muted px-4 py-2 text-sm" : "sr-only"}
      >
        {announce?.text}
      </p>

      {list.isLoading && (
        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
          {open.map((c) => <Skeleton key={c.id} className="h-48 rounded-2xl" />)}
        </div>
      )}

      {list.isError && (
        <div role="alert" className="flex flex-wrap items-center gap-3 rounded-2xl border px-4 py-3">
          <span>Couldn&apos;t load your applications.</span>
          <Button variant="outline" className="h-11" onClick={() => list.refetch()}>Retry</Button>
        </div>
      )}

      {list.isSuccess && (
        <>
          {notSent > 0 && (
            <p className="mb-5 text-[15px] text-muted-foreground">
              {notSent} {notSent === 1 ? "application is" : "applications are"} being prepared or waiting for you in{" "}
              <Link href="/review" className="font-medium text-foreground underline underline-offset-4">Review</Link>.
            </p>
          )}

          {sentCount === 0 ? (
            <div className="rounded-2xl border border-dashed px-6 py-12 text-center">
              <p className="text-lg font-semibold">Nothing sent yet</p>
              <p className="mx-auto mt-1 max-w-md text-muted-foreground">
                Once an application goes out, it shows up here so you can track replies, interviews and offers.
              </p>
              <Button asChild className="mt-5 h-11">
                <Link href="/applications/matches">See your matches</Link>
              </Button>
            </div>
          ) : (
            <>
              <div className="grid gap-6 md:grid-cols-2 lg:grid-cols-4">
                {open.map((c) => (
                  <section key={c.id} aria-labelledby={`col-${c.id}`} className="space-y-3">
                    <h2 id={`col-${c.id}`} className="flex items-baseline gap-2 text-base font-semibold">
                      {c.title}
                      <span className="text-sm font-normal text-muted-foreground tabular-nums">{columns[c.id].length}</span>
                    </h2>
                    {columns[c.id].length === 0 ? (
                      <p className="rounded-2xl border border-dashed px-4 py-6 text-center text-sm text-muted-foreground">None yet</p>
                    ) : (
                      <ul className="space-y-3">
                        {columns[c.id].map((a) => (
                          <TrackerCard key={a.id} application={a} profileId={profile?.id} onDone={onDone} />
                        ))}
                      </ul>
                    )}
                  </section>
                ))}
              </div>

              {columns.closed.length > 0 && (
                <details className="group mt-8 rounded-2xl border">
                  <summary className="flex min-h-11 cursor-pointer items-center gap-2 rounded-2xl px-4 font-semibold focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring">
                    Closed
                    <span className="text-sm font-normal text-muted-foreground tabular-nums">{columns.closed.length}</span>
                    <span className="text-sm font-normal text-muted-foreground">· rejected or withdrawn</span>
                  </summary>
                  <ul className="grid gap-3 p-4 pt-0 md:grid-cols-2 lg:grid-cols-4">
                    {columns.closed.map((a) => (
                      <TrackerCard key={a.id} application={a} profileId={profile?.id} onDone={onDone} />
                    ))}
                  </ul>
                </details>
              )}
            </>
          )}
        </>
      )}
    </AppShell>
  );
}
