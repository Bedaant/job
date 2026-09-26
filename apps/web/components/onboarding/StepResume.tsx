"use client";

import { FileTextIcon, Loader2Icon } from "lucide-react";
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
}: {
  file: File | null;
  onFile: (file: File) => void;
  facts: FactDraft[];
  isUploading: boolean;
  error: string | null;
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
        maxSize={MAX_RESUME_BYTES}
        src={file ? [file] : undefined}
        disabled={isUploading}
        onDrop={(accepted) => {
          if (accepted[0]) onFile(accepted[0]);
        }}
      >
        <DropzoneEmptyState />
        <DropzoneContent />
      </Dropzone>

      {isUploading && (
        <p className="flex items-center gap-2 text-sm text-muted-foreground" aria-live="polite">
          <Loader2Icon className="h-4 w-4 animate-spin" aria-hidden="true" />
          Reading your resume…
        </p>
      )}

      {error && (
        <FailureNotice
          title="We could not read that file"
          detail={`${error} Try the other format (.pdf or .docx), or a version exported straight from your editor rather than a scan.`}
        />
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
