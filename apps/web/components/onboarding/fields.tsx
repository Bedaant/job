"use client";

import { createContext, useContext, useId, useState } from "react";
import { XIcon } from "lucide-react";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { cn } from "@/lib/utils";

/** false = field errors are not each a role="alert"; the page announces one summary instead (onboarding). */
export const ErrorsAnnounced = createContext(true);

/**
 * One labelled input with its error wired up. Exists so the a11y plumbing
 * (`htmlFor`, `aria-invalid`, `aria-describedby`, `role="alert"`) is written once
 * instead of thirteen times across the wizard's forms — the version written
 * thirteen times is the version where three of them are wrong.
 */
export function Field({
  label,
  value,
  onChange,
  error,
  hint,
  type = "text",
  placeholder,
  inputMode,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  error?: string;
  hint?: string;
  type?: string;
  placeholder?: string;
  inputMode?: "text" | "numeric" | "tel" | "url";
}) {
  const id = useId();
  const announce = useContext(ErrorsAnnounced);
  const errorId = `${id}-error`;
  const hintId = `${id}-hint`;
  const describedBy = [error ? errorId : null, hint ? hintId : null].filter(Boolean).join(" ");

  return (
    <div className="space-y-1.5">
      <Label htmlFor={id}>{label}</Label>
      <Input
        id={id}
        type={type}
        inputMode={inputMode}
        value={value}
        placeholder={placeholder}
        onChange={(e) => onChange(e.target.value)}
        aria-invalid={error ? true : undefined}
        aria-describedby={describedBy || undefined}
        className={cn(error && "border-destructive")}
      />
      {hint && (
        <p id={hintId} className="text-xs text-muted-foreground">
          {hint}
        </p>
      )}
      {error && (
        <p id={errorId} role={announce ? "alert" : undefined} className="text-xs font-medium text-destructive">
          {error}
        </p>
      )}
    </div>
  );
}

/**
 * Free-text multi-value entry (roles, locations, work authorisations). A combobox
 * was the obvious reach — Kibo UI's is already installed — but it wants a fixed
 * option list and these are genuinely open-ended, so a plain input plus removable
 * chips is both smaller and more honest about what is accepted.
 */
export function Chips({
  label,
  values,
  onChange,
  error,
  hint,
  placeholder,
}: {
  label: string;
  values: string[];
  onChange: (values: string[]) => void;
  error?: string;
  hint?: string;
  placeholder?: string;
}) {
  const id = useId();
  const announce = useContext(ErrorsAnnounced);
  const errorId = `${id}-error`;
  const hintId = `${id}-hint`;
  const [draft, setDraft] = useState("");

  function add() {
    const v = draft.trim();
    if (!v || values.includes(v)) {
      setDraft("");
      return;
    }
    onChange([...values, v]);
    setDraft("");
  }

  return (
    <div className="space-y-1.5">
      <Label htmlFor={id}>{label}</Label>
      <div className="flex gap-2">
        <Input
          id={id}
          value={draft}
          placeholder={placeholder}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => {
            // Enter adds the chip; it must not submit the step, which is what an
            // un-prevented Enter inside a form does.
            if (e.key === "Enter" || e.key === ",") {
              e.preventDefault();
              add();
            }
          }}
          aria-invalid={error ? true : undefined}
          aria-describedby={[error ? errorId : null, hintId].filter(Boolean).join(" ")}
          className={cn(error && "border-destructive")}
        />
        <button
          type="button"
          onClick={add}
          className="shrink-0 rounded-md border border-input px-3 text-sm font-medium hover:bg-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
        >
          Add
        </button>
      </div>
      <p id={hintId} className="text-xs text-muted-foreground">
        {hint ?? "Type and press Enter."}
      </p>

      {values.length > 0 && (
        // gap-y-5 keeps neighbouring rows' 44px remove targets from overlapping.
        <ul className="flex flex-wrap gap-x-1.5 gap-y-5 pt-1">
          {values.map((v) => (
            <li key={v}>
              <span className="inline-flex items-center gap-1 rounded-full border border-input bg-secondary px-2.5 py-1 text-xs text-secondary-foreground">
                {v}
                {/* 44px hit area (WCAG 2.5.5) around a small ×; negative margins keep the chip small. */}
                <button
                  type="button"
                  onClick={() => onChange(values.filter((x) => x !== v))}
                  aria-label={`Remove ${v}`}
                  className="-my-3 -mr-3 inline-flex h-11 w-11 items-center justify-center rounded-full hover:text-destructive focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                >
                  <XIcon className="h-3 w-3" aria-hidden="true" />
                </button>
              </span>
            </li>
          ))}
        </ul>
      )}

      {error && (
        <p id={errorId} role={announce ? "alert" : undefined} className="text-xs font-medium text-destructive">
          {error}
        </p>
      )}
    </div>
  );
}

/** A visible, non-dismissable failure. The brief's rule: never a silent empty screen. */
export function FailureNotice({ title, detail }: { title: string; detail: string }) {
  return (
    <div role="alert" className="rounded-md border border-destructive/50 bg-destructive/5 p-3">
      <p className="text-sm font-medium text-destructive">{title}</p>
      <p className="mt-1 text-xs text-muted-foreground">{detail}</p>
    </div>
  );
}
