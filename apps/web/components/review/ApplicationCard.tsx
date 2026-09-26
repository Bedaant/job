"use client";

import { diffWords } from "diff";
import { AlertTriangleIcon, FileTextIcon } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import type { ResumeFact, ReviewApplication, TailoredBullet } from "@/lib/api";

function scoreVariant(score: number | null): "default" | "secondary" | "outline" {
  if (score === null) return "outline";
  if (score >= 75) return "default";
  return "secondary";
}

/**
 * Renders a bullet's tailored text against its source fact(s).
 *
 * If we have real fact text for every source_fact_id, we diff word-by-word
 * (jsdiff) against the concatenated source achievements — a real diff, not a
 * fake one. If a bullet cites no facts, or a cited fact id isn't in the
 * profile's confirmed facts (e.g. it was edited/deleted after tailoring ran),
 * we fall back to plain text with a "grounded in N fact(s)" affordance
 * instead of guessing.
 */
function BulletDiff({ bullet, factsById }: { bullet: TailoredBullet; factsById: Map<string, ResumeFact> }) {
  const sourceFacts = bullet.source_fact_ids.map((id) => factsById.get(id)).filter((f): f is ResumeFact => !!f);
  const hasFullSourceText = bullet.source_fact_ids.length > 0 && sourceFacts.length === bullet.source_fact_ids.length;

  if (!hasFullSourceText) {
    // TODO: this bullet cites fact ids we couldn't resolve against this profile's
    // current /resume-facts (deleted/edited fact, or the facts fetch failed/is still
    // loading). Real diff-against-source-fact-text (below) is the correct view once
    // every cited fact resolves — don't fake a diff with a missing second string.
    return (
      <li className="flex items-start gap-2 text-sm">
        <span>{bullet.text}</span>
        {bullet.source_fact_ids.length > 0 && (
          <span
            className="mt-0.5 inline-flex shrink-0 items-center gap-1 text-xs text-muted-foreground"
            title={`Grounded in ${bullet.source_fact_ids.length} fact(s) — source text not loaded, showing tailored text as-is`}
          >
            <FileTextIcon className="size-3" />
            {bullet.source_fact_ids.length}
          </span>
        )}
      </li>
    );
  }

  const sourceText = sourceFacts.map((f) => f.achievement).join(" ");
  const parts = diffWords(sourceText, bullet.text);

  return (
    <li className="text-sm">
      <span
        className="mr-1.5 inline-flex items-center gap-1 align-middle text-xs text-muted-foreground"
        title={`Diffed against ${sourceFacts.length} source fact(s)`}
      >
        <FileTextIcon className="size-3" />
        {sourceFacts.length}
      </span>
      {parts.map((part, i) => (
        <span
          key={i}
          className={
            part.added
              ? "bg-emerald-500/15 text-emerald-700 dark:text-emerald-400"
              : part.removed
                ? "text-muted-foreground/60 line-through"
                : undefined
          }
        >
          {part.value}
        </span>
      ))}
    </li>
  );
}

export function ApplicationCard({
  application,
  facts,
  selected,
  onToggleSelected,
  onDismiss,
  isDismissing,
  resumeUrl,
}: {
  application: ReviewApplication;
  facts: ResumeFact[];
  selected: boolean;
  onToggleSelected: (checked: boolean) => void;
  onDismiss: () => void;
  isDismissing: boolean;
  resumeUrl: string;
}) {
  const { job, match_score, tailored_summary, tailored_bullets, flagged_unsupported_claims } = application;
  const factsById = new Map(facts.map((f) => [f.id, f]));

  return (
    <Card>
      <CardHeader className="flex flex-row items-start justify-between gap-4">
        <div className="flex items-start gap-3">
          <Checkbox
            checked={selected}
            onCheckedChange={(checked) => onToggleSelected(checked === true)}
            aria-label={`Select ${job.title} at ${job.company}`}
            className="mt-1"
          />
          <div>
            <CardTitle>{job.title}</CardTitle>
            <p className="text-sm text-muted-foreground">
              {job.company}
              {job.location ? ` · ${job.location}` : ""}
              {job.remote ? " · Remote" : ""}
            </p>
          </div>
        </div>
        <Badge variant={scoreVariant(match_score)}>
          {match_score === null ? "unscored" : `${match_score.toFixed(0)} match`}
        </Badge>
      </CardHeader>

      <CardContent className="space-y-3">
        {tailored_summary && <p className="text-sm">{tailored_summary}</p>}

        {tailored_bullets.length > 0 && (
          <ul className="list-disc space-y-1.5 pl-5">
            {tailored_bullets.map((bullet, i) => (
              <BulletDiff key={i} bullet={bullet} factsById={factsById} />
            ))}
          </ul>
        )}

        {flagged_unsupported_claims.length > 0 && (
          <div className="flex items-start gap-2 rounded-md border border-amber-500/30 bg-amber-500/10 p-3 text-sm text-amber-800 dark:text-amber-300">
            <AlertTriangleIcon className="mt-0.5 size-4 shrink-0" />
            <div>
              <p className="font-medium">Flagged as possibly unsupported by your facts — review before approving</p>
              <ul className="mt-1 list-disc pl-4">
                {flagged_unsupported_claims.map((claim, i) => (
                  <li key={i}>{claim}</li>
                ))}
              </ul>
            </div>
          </div>
        )}

        <div className="flex items-center gap-2 pt-1">
          <Button asChild size="sm" variant="outline">
            <a href={resumeUrl} target="_blank" rel="noreferrer">
              Download resume
            </a>
          </Button>
          <Button asChild size="sm" variant="outline">
            <a href={job.apply_url} target="_blank" rel="noreferrer">
              View listing
            </a>
          </Button>
          <Button size="sm" variant="ghost" onClick={onDismiss} disabled={isDismissing}>
            {isDismissing ? "Dismissing…" : "Not interested"}
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}
