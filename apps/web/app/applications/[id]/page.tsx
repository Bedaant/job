"use client";

import Link from "next/link";
import { useState } from "react";
import { useParams } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { AlertTriangleIcon, ArrowLeftIcon } from "lucide-react";
import { api } from "@/lib/api";
import { columnOf, keywordRows } from "@/lib/applications";
import { coverageChange, isHttpUrl, resumeFilename } from "@/lib/assisted";
import { needsInputView } from "@/lib/needs-input";
import { formatWhen } from "@/lib/today";
import { AppShell, useRequireAuth } from "@/components/AppShell";
import { saveBlob } from "@/components/review/ApplicationCard";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";
import { MoveMenu, StatusPill, useProfile } from "../parts";

const OUTCOME: Record<string, string> = {
  submitted: "Sent and confirmed",
  unconfirmed: "Sent, couldn't confirm",
  failed: "Didn't go through",
  needs_human: "Stopped for you",
};

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="space-y-3 rounded-2xl border bg-card p-5">
      <h2 className="text-lg font-semibold">{title}</h2>
      {children}
    </section>
  );
}

export default function ApplicationDetailPage() {
  const ready = useRequireAuth();
  const { id } = useParams<{ id: string }>();
  const { profile } = useProfile(ready);
  const [announce, setAnnounce] = useState<{ text: string; failed?: boolean } | null>(null);
  const [downloadError, setDownloadError] = useState(false);

  const q = useQuery({ queryKey: ["application", id], queryFn: () => api.getApplication(id), enabled: ready && !!id });
  const a = q.data;

  async function download() {
    if (!a) return;
    setDownloadError(false);
    try {
      saveBlob(await api.downloadTailoredResumeDocx(a.id), resumeFilename(a.job.company));
    } catch {
      setDownloadError(true);
    }
  }

  if (!ready) return null;
  // Why Maggie stopped only matters until it's sent; after that it's history (below).
  const stopped = a && columnOf(a.status) === null ? needsInputView(a.needs_input, a.job.company, a.pending_questions.length) : null;
  const coverage = a ? coverageChange(a.keyword_gap) : null;

  return (
    <AppShell
      title={a ? a.job.title : "Application"}
      pageTitle={a ? `${a.job.title} · ${a.job.company}` : "Application"}
      description={a ? a.job.company : undefined}
      actions={
        <Button asChild variant="ghost" className="h-11">
          <Link href="/applications">
            <ArrowLeftIcon aria-hidden="true" /> All applications
          </Link>
        </Button>
      }
    >
      <p
        role={announce?.failed ? "alert" : "status"}
        aria-live={announce?.failed ? "assertive" : "polite"}
        className={announce ? "mb-4 rounded-lg bg-muted px-4 py-2 text-sm" : "sr-only"}
      >
        {announce?.text}
      </p>

      {q.isLoading && <Skeleton className="h-64 w-full rounded-2xl" />}
      {q.isError && (
        <div role="alert" className="flex flex-wrap items-center gap-3 rounded-2xl border px-4 py-3">
          <span>Couldn&apos;t load this application.</span>
          <Button variant="outline" className="h-11" onClick={() => q.refetch()}>Retry</Button>
        </div>
      )}

      {a && (
        <div className="space-y-6">
          <div className="flex flex-wrap items-center gap-x-4 gap-y-3">
            <StatusPill status={a.status} />
            {a.match_score !== null && <span className="text-sm text-muted-foreground">{Math.round(a.match_score)}% match</span>}
            {a.applied_at && <span className="text-sm text-muted-foreground">Sent {formatWhen(a.applied_at)}</span>}
            {a.created_at && <span className="text-sm text-muted-foreground">Found {formatWhen(a.created_at)}</span>}
            <div className="w-full sm:ml-auto sm:w-72">
              <MoveMenu application={a} profileId={profile?.id} onDone={(text, failed) => setAnnounce({ text, failed })} />
            </div>
          </div>

          {a.status === "submitted_unconfirmed" && (
            <p role="note" className="rounded-xl border border-warning/40 bg-warning-soft p-4 text-sm">
              Sent, but {a.job.company}&apos;s page never confirmed it. Check your email for a confirmation, then move it to
              &quot;I&apos;ve confirmed it was sent&quot;.
            </p>
          )}

          {stopped && (
            <div
              role="note"
              className={cn(
                "flex items-start gap-2 rounded-xl border p-4 text-sm",
                stopped.tone === "warning" ? "border-warning/40 bg-warning-soft" : "bg-muted"
              )}
            >
              {stopped.tone === "warning" && <AlertTriangleIcon aria-hidden="true" className="mt-0.5 size-4 shrink-0 text-warning" />}
              <div className="space-y-1">
                <p className="font-semibold">{stopped.title}</p>
                <p>{stopped.body}</p>
                {stopped.demographicNote && <p className="text-muted-foreground">{stopped.demographicNote}</p>}
              </div>
            </div>
          )}

          <div className="flex flex-wrap gap-2">
            {isHttpUrl(a.job.apply_url) && (
              <Button asChild variant="outline" className="h-11">
                <a href={a.job.apply_url} target="_blank" rel="noreferrer">
                  Open the job<span className="sr-only"> (opens in a new tab)</span>
                </a>
              </Button>
            )}
            {a.tailored_bullets.length > 0 && (
              <Button variant="outline" className="h-11" onClick={download}>Download tailored resume</Button>
            )}
          </div>
          {downloadError && (
            <p role="alert" className="text-sm text-destructive">Couldn&apos;t download the tailored resume. Try again.</p>
          )}

          <Section title="Keywords">
            {coverage && <p className="text-[15px] font-medium">{coverage}</p>}
            {keywordRows(a.keywords).length === 0 ? (
              <p className="text-sm text-muted-foreground">This job description didn&apos;t list keywords we could check.</p>
            ) : (
              <dl className="space-y-3">
                {keywordRows(a.keywords).map((r) => (
                  <div key={r.kind}>
                    <dt className="text-sm font-medium">{r.label}</dt>
                    <dd className="mt-1 flex flex-wrap gap-1.5">
                      {r.keywords.map((k) => (
                        <span
                          key={k}
                          className={cn(
                            "rounded-full px-2.5 py-0.5 text-xs",
                            r.kind === "missing" ? "border border-dashed text-muted-foreground" : "bg-muted"
                          )}
                        >
                          {k}
                        </span>
                      ))}
                    </dd>
                  </div>
                ))}
              </dl>
            )}
            {a.keywords.missing.length > 0 && (
              <p className="text-sm text-muted-foreground">
                Maggie only uses what&apos;s in your facts, so these weren&apos;t added. If you have that experience, add it to your profile.
              </p>
            )}
          </Section>

          <Section title="Tailored resume">
            {a.tailored_bullets.length === 0 ? (
              <p className="text-sm text-muted-foreground">Maggie hasn&apos;t tailored this one yet.</p>
            ) : (
              <>
                {a.tailored_summary && <p className="text-[15px]">{a.tailored_summary}</p>}
                <ul className="divide-y">
                  {a.tailored_bullets.map((b, i) => (
                    <li key={i} className="grid gap-2 py-3 md:grid-cols-2 md:gap-6">
                      <p className="text-[15px]">{b.text}</p>
                      <div className="text-sm text-muted-foreground">
                        {b.sources.length > 0 ? (
                          <>
                            <span className="font-medium text-foreground">From your fact: </span>
                            {b.sources.map((s) => s.achievement).join(" · ")}
                          </>
                        ) : (
                          <span className="text-destructive">No matching fact found — not used in your resume.</span>
                        )}
                      </div>
                    </li>
                  ))}
                </ul>
              </>
            )}
            {a.flagged_unsupported_claims.length > 0 && (
              <div role="note" className="rounded-xl border border-warning/40 bg-warning-soft p-3 text-sm">
                <p className="font-semibold">Flagged by the truth check</p>
                <ul className="mt-1 list-disc pl-5">
                  {a.flagged_unsupported_claims.map((c) => <li key={c}>{c}</li>)}
                </ul>
              </div>
            )}
          </Section>

          {a.tailored_cover_letter && (
            <Section title="Cover letter">
              <p className="whitespace-pre-wrap text-[15px] leading-relaxed">{a.tailored_cover_letter}</p>
            </Section>
          )}

          {a.history.length > 0 && (
            <Section title="What happened">
              <ol className="space-y-2">
                {a.history.map((h, i) => (
                  <li key={i} className="text-sm">
                    <span className="font-medium">{OUTCOME[h.outcome] ?? h.outcome}</span>
                    <span className="text-muted-foreground"> — {h.message}</span>
                  </li>
                ))}
              </ol>
            </Section>
          )}
        </div>
      )}
    </AppShell>
  );
}
