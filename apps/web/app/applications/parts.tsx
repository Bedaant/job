"use client";

// Shared by the Applications pages (not a route: no page.tsx here).
import Link from "next/link";
import { useId } from "react";
import { usePathname } from "next/navigation";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { MailQuestionIcon } from "lucide-react";
import { api, type ApplicationRow } from "@/lib/api";
import { moveOptions, statusLabel } from "@/lib/applications";
import { cn } from "@/lib/utils";

const SECTIONS = [
  { href: "/applications", label: "Pipeline" },
  { href: "/applications/matches", label: "Matches" },
];

/** Pipeline vs Matches: two links (real URLs, so back/refresh/share work), not JS tabs. */
export function SectionTabs() {
  const pathname = usePathname();
  return (
    <nav aria-label="Applications" className="mb-6 inline-flex rounded-full bg-muted p-1">
      {SECTIONS.map((s) => {
        const current = pathname === s.href;
        return (
          <Link
            key={s.href}
            href={s.href}
            aria-current={current ? "page" : undefined}
            className={cn(
              "inline-flex h-11 items-center rounded-full px-5 text-[15px] font-medium text-muted-foreground transition-colors hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
              current && "bg-background text-foreground shadow-sm"
            )}
          >
            {s.label}
          </Link>
        );
      })}
    </nav>
  );
}

export function useProfile(enabled: boolean) {
  const q = useQuery({ queryKey: ["profiles"], queryFn: api.listProfiles, enabled });
  return { profile: q.data?.[0], isLoading: q.isLoading };
}

/** "Couldn't confirm" gets its own look: sent, but the employer never said so. */
export function StatusPill({ status }: { status: string }) {
  const unconfirmed = status === "submitted_unconfirmed";
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 rounded-full px-2.5 py-0.5 text-xs font-medium",
        unconfirmed ? "bg-warning-soft text-foreground ring-1 ring-warning/40" : "bg-muted text-muted-foreground"
      )}
    >
      {unconfirmed && <MailQuestionIcon aria-hidden="true" className="size-3.5 text-warning" />}
      {statusLabel(status)}
    </span>
  );
}

/**
 * Moving a card = PATCH its status. A native <select> is the menu: keyboard and
 * screen-reader support for free, no drag needed. Optimistic on the list cache,
 * rolled back on failure; `onDone` lets the page announce the result.
 */
export function MoveMenu({
  application,
  profileId,
  onDone,
}: {
  application: Pick<ApplicationRow, "id" | "status" | "job">;
  profileId: string | undefined;
  onDone: (message: string, failed?: boolean) => void;
}) {
  const id = useId();
  const qc = useQueryClient();
  const key = ["applications", profileId];
  const move = useMutation({
    mutationFn: (status: string) => api.setApplicationStatus(application.id, status),
    onMutate: async (status) => {
      await qc.cancelQueries({ queryKey: key });
      const before = qc.getQueryData<ApplicationRow[]>(key);
      qc.setQueryData<ApplicationRow[]>(key, (rows) => rows?.map((r) => (r.id === application.id ? { ...r, status } : r)));
      return { before };
    },
    onError: (_e, _s, ctx) => {
      qc.setQueryData(key, ctx?.before);
      onDone(`Couldn't move ${application.job.title} at ${application.job.company}. Nothing changed — try again.`, true);
    },
    onSuccess: (_d, status) => onDone(`Moved ${application.job.title} at ${application.job.company} to ${statusLabel(status)}.`),
    onSettled: () => {
      qc.invalidateQueries({ queryKey: key });
      qc.invalidateQueries({ queryKey: ["application", application.id] });
    },
  });

  return (
    <div className="flex items-center gap-2">
      <label htmlFor={id} className="text-sm text-muted-foreground">
        Move to<span className="sr-only">: {application.job.title} at {application.job.company}</span>
      </label>
      <select
        id={id}
        value=""
        disabled={move.isPending}
        onChange={(e) => e.target.value && move.mutate(e.target.value)}
        className="h-11 min-w-0 flex-1 rounded-lg border border-input bg-background px-3 text-[15px] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:opacity-50"
      >
        <option value="">Choose…</option>
        {moveOptions(application.status).map((o) => (
          <option key={o.status} value={o.status}>
            {o.label}
          </option>
        ))}
      </select>
    </div>
  );
}
