"use client";

import { FileTextIcon, Loader2Icon, PencilLineIcon, UploadIcon } from "lucide-react";
import { Dropzone, DropzoneContent, DropzoneEmptyState } from "@/components/kibo-ui/dropzone";
import type { FactDraft } from "@/lib/api";
import { FailureNotice } from "./fields";

const MAX_RESUME_BYTES = 5 * 1024 * 1024; // mirrors MAX_RESUME_UPLOAD_BYTES in apps/api/main.py

export function StepResume({
  file,
  onFile,
  facts,
  isUploading,
  error,
  onByHand,
}: {
  file: File | null;
  onFile: (file: File) => void;
  facts: FactDraft[];
  isUploading: boolean;
  error: string | null;
  /** The way forward when the parser can't help: the user writes the facts. */
  onByHand: () => void;
}) {
  return (
    <div className="space-y-5">
      <p className="text-sm text-muted-foreground">
        Drop in whatever you have. It does not need to be tidy and it does not need to be ATS-friendly — that
        is the part we do. A PDF or Word file under 5MB.
      </p>

      <Dropzone
        accept={{
          "application/pdf": [".pdf"],
          "application/vnd.openxmlformats-officedocument.wordprocessingml.document": [".docx"],
        }}
        maxFiles={1}
        multiple={false}
        maxSize={MAX_RESUME_BYTES}
        src={file ? [file] : undefined}
        disabled={isUploading}
        onDrop={(accepted) => {
          if (accepted[0]) onFile(accepted[0]);
        }}
      >
        {/* Own caption: the kit's default lists raw MIME types. */}
        <DropzoneEmptyState>
          <div className="flex flex-col items-center justify-center">
            <div className="flex size-8 items-center justify-center rounded-md bg-muted text-muted-foreground">
              <UploadIcon className="h-4 w-4" aria-hidden="true" />
            </div>
            <p className="my-2 text-sm font-medium">Upload your resume</p>
            <p className="text-xs text-muted-foreground">Drag and drop or click to choose a file</p>
            <p className="text-xs text-muted-foreground">PDF or Word (.docx), up to 5 MB</p>
          </div>
        </DropzoneEmptyState>
        <DropzoneContent />
      </Dropzone>

      {isUploading && (
        <p className="flex items-center gap-2 text-sm text-muted-foreground" aria-live="polite">
          <Loader2Icon className="h-4 w-4 animate-spin" aria-hidden="true" />
          Reading your resume…
        </p>
      )}

      {error ? (
        <div className="space-y-3">
          <FailureNotice
            title="We could not read that file"
            detail={error}
          />
          <button
            type="button"
            onClick={onByHand}
            className="inline-flex min-h-11 items-center gap-2 rounded-md bg-primary px-4 text-sm font-medium text-primary-foreground hover:opacity-90 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          >
            <PencilLineIcon className="h-4 w-4" aria-hidden="true" />
            Add your facts by hand
          </button>
        </div>
      ) : (
        !isUploading && (
          <p className="text-sm text-muted-foreground">
            No resume to hand?{" "}
            <button
              type="button"
              onClick={onByHand}
              className="inline-flex min-h-11 items-center rounded-md font-medium text-primary hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            >
              Add your facts by hand
            </button>
          </p>
        )
      )}

      {facts.length > 0 && !isUploading && (
        <div className="rounded-md border border-input bg-secondary/40 p-4">
          <p className="flex items-center gap-2 text-sm font-medium">
            <FileTextIcon className="h-4 w-4" aria-hidden="true" />
            {facts.length} {facts.length === 1 ? "fact" : "facts"} pulled out
          </p>
          <p className="mt-1 text-xs text-muted-foreground">
            Nothing has been saved yet. The next step is you checking every one of them.
          </p>
          <ul className="mt-3 space-y-1 text-sm">
            {facts.slice(0, 3).map((f, i) => (
              <li key={i} className="truncate text-muted-foreground">
                · {f.achievement}
              </li>
            ))}
            {facts.length > 3 && (
              <li className="text-xs text-muted-foreground">…and {facts.length - 3} more.</li>
            )}
          </ul>
        </div>
      )}
    </div>
  );
}
