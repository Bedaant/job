"use client";

import { useState } from "react";
import { diffWords } from "diff";
import { AlertTriangleIcon, FileTextIcon, InfoIcon, MessageSquareIcon } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { Textarea } from "@/components/ui/textarea";
import type { ResumeFact, ReviewApplication, TailoredBullet } from "@/lib/api";
import { CONSENT_NOTE, needsInputView } from "@/lib/needs-input";

/** Save a fetched file: the endpoint needs the Bearer header, so a plain link would 401. */
export function saveBlob(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 0);
}

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

/**
 * One question an auto-apply run stopped on. Answering saves it to the answer
 * bank (ADR-015), which is what makes every later form asking it fill itself —
 * the backend then drops it from pending_questions, so it disappears on refetch.
 */
function PendingQuestion({
  question,
  options,
  onSave,
}: {
  question: string;
  /** A dropdown on the form: the answer must be one of these, so pick instead of type. */
  options?: string[];
  onSave: (answer: string) => Promise<void>;
}) {
  const [answer, setAnswer] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function save() {
    setSaving(true);
    setError(null);
    try {
      await onSave(answer.trim());
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not save the answer.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <li className="space-y-1.5">
      <p className="font-medium">{question}</p>
      {options?.length ? (
        <select
          value={answer}
          onChange={(e) => setAnswer(e.target.value)}
          aria-label={question}
          className="block h-11 w-full rounded-md border border-input bg-background px-3 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
        >
          <option value="">Choose…</option>
          {options.map((o) => (
            <option key={o} value={o}>
              {o}
            </option>
          ))}
        </select>
      ) : (
        <Textarea value={answer} onChange={(e) => setAnswer(e.target.value)} aria-label={question} rows={2} />
      )}
      {error && <p className="text-xs text-destructive">{error}</p>}
      <Button size="sm" onClick={save} disabled={saving || !answer.trim()}>
        {saving ? "Saving…" : "Save answer"}
      </Button>
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
  onDownloadResume,
  onSaveAnswer,
}: {
  application: ReviewApplication;
  facts: ResumeFact[];
  selected: boolean;
  onToggleSelected: (checked: boolean) => void;
  onDismiss: () => void;
  isDismissing: boolean;
  onDownloadResume: () => Promise<Blob>;
  onSaveAnswer: (question: string, answer: string) => Promise<void>;
}) {
  const { job, match_score, tailored_summary, tailored_bullets, flagged_unsupported_claims, pending_questions } =
    application;
  const factsById = new Map(facts.map((f) => [f.id, f]));
  const stopped = needsInputView(application.needs_input, job.company, pending_questions?.length ?? 0);
  const [downloading, setDownloading] = useState(false);
  const [downloadError, setDownloadError] = useState<string | null>(null);

  async function downloadResume() {
    setDownloading(true);
    setDownloadError(null);
    try {
      saveBlob(await onDownloadResume(), "base-resume.docx");
    } catch (err) {
      setDownloadError(err instanceof Error ? err.message : "Could not download the resume.");
    } finally {
      setDownloading(false);
    }
  }

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
        {stopped && (
          <div
            role="note"
            aria-label="Why Maggie stopped"
            className={
              stopped.tone === "warning"
                ? "flex items-start gap-2 rounded-md border border-warning/40 bg-warning-soft p-3 text-sm text-foreground"
                : "flex items-start gap-2 rounded-md border bg-muted p-3 text-sm text-foreground"
            }
          >
            {stopped.tone === "warning" ? (
              <AlertTriangleIcon aria-hidden="true" className="mt-0.5 size-4 shrink-0 text-warning" />
            ) : (
              <InfoIcon aria-hidden="true" className="mt-0.5 size-4 shrink-0 text-muted-foreground" />
            )}
            <div className="space-y-1">
              <p className="font-medium">{stopped.title}</p>
              <p>{stopped.body}</p>
              {stopped.demographicNote && <p className="text-muted-foreground">{stopped.demographicNote}</p>}
              {stopped.openForm && (
                <a
                  href={job.apply_url}
                  target="_blank"
                  rel="noreferrer"
                  className="inline-block font-medium text-primary underline underline-offset-4"
                >
                  Open the form<span className="sr-only"> (opens in a new tab)</span>
                </a>
              )}
            </div>
          </div>
        )}

        {tailored_summary &&<p className="text-sm">{tailored_summary}</p>}

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

        {pending_questions?.length > 0 && (
          <div className="flex items-start gap-2 rounded-md border p-3 text-sm">
            <MessageSquareIcon className="mt-0.5 size-4 shrink-0" />
            <div className="w-full">
              <p className="font-medium">The form asked something only you can answer</p>
              {!stopped && (
                <p className="text-xs text-muted-foreground">
                  Answer once. It&apos;s saved and reused on every later form that asks.
                </p>
              )}
              <ul className="mt-2 space-y-3">
                {pending_questions.map((q) => (
                  <PendingQuestion
                    key={q}
                    question={q}
                    options={application.question_options?.[q]}
                    onSave={(answer) => onSaveAnswer(q, answer)}
                  />
                ))}
              </ul>
            </div>
          </div>
        )}

        {/* Never answered or saved by us (answer_bank consent rail): the user's own act, on the form. */}
        {(application.consent_questions?.length ?? 0) > 0 && (
          <div className="flex items-start gap-2 rounded-md border border-warning/40 bg-warning-soft p-3 text-sm">
            <AlertTriangleIcon aria-hidden="true" className="mt-0.5 size-4 shrink-0 text-warning" />
            <div className="space-y-1">
              <p className="font-medium">{CONSENT_NOTE}</p>
              <ul className="list-disc pl-4">
                {application.consent_questions!.map((q) => (
                  <li key={q}>{q}</li>
                ))}
              </ul>
              <a
                href={job.apply_url}
                target="_blank"
                rel="noreferrer"
                className="inline-block font-medium text-primary underline underline-offset-4"
              >
                Open the form<span className="sr-only"> (opens in a new tab)</span>
              </a>
            </div>
          </div>
        )}

        <div className="flex flex-wrap items-center gap-2 pt-1">
          <Button size="sm" variant="outline" onClick={downloadResume} disabled={downloading}>
            {downloading ? "Downloading…" : "Download base resume"}
          </Button>
          <Button asChild size="sm" variant="outline">
            <a href={job.apply_url} target="_blank" rel="noreferrer">
              View listing<span className="sr-only"> (opens in a new tab)</span>
            </a>
          </Button>
          <Button size="sm" variant="ghost" onClick={onDismiss} disabled={isDismissing}>
            {isDismissing ? "Dismissing…" : "Not interested"}
          </Button>
        </div>
        {downloadError && (
          <p role="alert" className="text-xs text-destructive">
            Couldn&apos;t download your resume: {downloadError}
          </p>
        )}
      </CardContent>
    </Card>
  );
}
