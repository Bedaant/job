"use client";

import { useId, useState } from "react";
import { CheckIcon, CopyIcon, DownloadIcon, ExternalLinkIcon } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Textarea } from "@/components/ui/textarea";
import type { ReviewApplication } from "@/lib/api";
import { copyText, coverageChange, isHttpUrl, resumeFilename } from "@/lib/assisted";
import { saveBlob } from "./ApplicationCard";

/** Copy with a visible, announced "Copied"; if the clipboard refuses, show the text to copy by hand. */
function CopyBlock({ label, text }: { label: string; text: string }) {
  const [state, setState] = useState<"idle" | "copied" | "show">("idle");
  const id = useId();

  async function copy() {
    const result = await copyText(text, typeof navigator !== "undefined" ? navigator.clipboard : undefined);
    setState(result);
    if (result === "copied") setTimeout(() => setState("idle"), 2500);
  }

  return (
    <div className="space-y-2">
      <div className="flex flex-wrap items-center gap-3">
        <Button type="button" variant="outline" className="min-h-11" onClick={copy}>
          {state === "copied" ? <CheckIcon aria-hidden="true" /> : <CopyIcon aria-hidden="true" />}
          {label}
        </Button>
        <span role="status" className="text-sm font-medium text-success">
          {state === "copied" ? "Copied" : ""}
        </span>
      </div>
      {state === "show" && (
        <div className="space-y-1">
          <label htmlFor={id} className="text-sm text-muted-foreground">
            Your browser blocked copying. Select the text below and copy it.
          </label>
          <Textarea id={id} readOnly value={text} rows={6} onFocus={(e) => e.currentTarget.select()} autoFocus />
        </div>
      )}
    </div>
  );
}

function Step({ n, title, children }: { n: number; title: string; children: React.ReactNode }) {
  return (
    <li className="flex gap-3">
      <span
        aria-hidden="true"
        className="flex size-7 shrink-0 items-center justify-center rounded-full bg-muted text-sm font-semibold"
      >
        {n}
      </span>
      <div className="min-w-0 flex-1 space-y-2">
        <h4 className="font-medium">
          <span className="sr-only">Step {n}: </span>
          {title}
        </h4>
        {children}
      </div>
    </li>
  );
}

export function SendCard({
  application,
  onSent,
  onDismiss,
  onDownloadResume,
}: {
  application: ReviewApplication;
  onSent: () => void;
  onDismiss: () => void;
  onDownloadResume: () => Promise<Blob>;
}) {
  const { job, match_score, tailored_cover_letter, prepared_answers = [] } = application;
  const coverage = coverageChange(application.keyword_gap);
  const [downloading, setDownloading] = useState(false);
  const [downloadError, setDownloadError] = useState<string | null>(null);

  async function download() {
    setDownloading(true);
    setDownloadError(null);
    try {
      saveBlob(await onDownloadResume(), resumeFilename(job.company));
    } catch (err) {
      setDownloadError(err instanceof Error ? err.message : "Could not download the resume.");
    } finally {
      setDownloading(false);
    }
  }

  return (
    <Card>
      <CardHeader className="flex flex-row items-start justify-between gap-4">
        <div className="min-w-0">
          <CardTitle>
            <h3 className="text-base font-semibold">
              {job.title} <span className="font-normal text-muted-foreground">at {job.company}</span>
            </h3>
          </CardTitle>
          {coverage && <p className="mt-1 text-sm text-muted-foreground">{coverage}</p>}
        </div>
        {match_score !== null && <Badge variant="secondary">{match_score.toFixed(0)}% match</Badge>}
      </CardHeader>

      <CardContent className="space-y-5">
        <ol className="space-y-5">
          <Step n={1} title="Download your tailored resume">
            <Button type="button" className="min-h-11" onClick={download} disabled={downloading}>
              <DownloadIcon aria-hidden="true" />
              {downloading ? "Downloading…" : "Download tailored resume"}
            </Button>
            {downloadError && (
              <p role="alert" className="text-sm text-destructive">
                Couldn&apos;t download it: {downloadError}
              </p>
            )}
          </Step>

          <Step n={2} title="Copy what the form asks for">
            {tailored_cover_letter ? (
              <CopyBlock label="Copy cover letter" text={tailored_cover_letter} />
            ) : (
              <p className="text-sm text-muted-foreground">No cover letter was prepared for this one.</p>
            )}
            {prepared_answers.length > 0 && (
              <ul className="space-y-3 border-t pt-3">
                {prepared_answers.map((a) => (
                  <li key={a.question} className="space-y-1.5">
                    <p className="text-sm font-medium">{a.question}</p>
                    <p className="text-sm text-muted-foreground">{a.answer}</p>
                    <CopyBlock label="Copy answer" text={a.answer} />
                  </li>
                ))}
              </ul>
            )}
          </Step>

          <Step n={3} title="Open the form and submit it">
            {isHttpUrl(job.apply_url) ? (
              <Button asChild variant="outline" className="min-h-11">
                <a href={job.apply_url} target="_blank" rel="noopener noreferrer">
                  <ExternalLinkIcon aria-hidden="true" />
                  Open application form<span className="sr-only"> (opens in a new tab)</span>
                </a>
              </Button>
            ) : (
              <p className="text-sm text-muted-foreground">This job has no application link.</p>
            )}
          </Step>
        </ol>

        <div className="flex flex-wrap items-center gap-2 border-t pt-4">
          <Button type="button" className="min-h-11" onClick={onSent}>
            <CheckIcon aria-hidden="true" />
            I&apos;ve sent it
          </Button>
          <Button type="button" variant="ghost" className="min-h-11" onClick={onDismiss}>
            Not for me
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}
