"use client";

import { useId } from "react";
import { ASSISTED, AUTOMATIC } from "@/lib/assisted";
import { cn } from "@/lib/utils";

/** auto_submit as a choice between two named modes (native radios: keyboard and screen readers for free). */
export function SubmitModeChoice({
  autoSubmit,
  onChange,
  children,
}: {
  autoSubmit: boolean;
  onChange: (autoSubmit: boolean) => void;
  /** Shown under the choice, e.g. a warning while Automatic is picked. */
  children?: React.ReactNode;
}) {
  const name = useId();
  const options = [
    { value: false, ...ASSISTED },
    { value: true, ...AUTOMATIC },
  ];
  return (
    <fieldset className="space-y-2">
      <legend className="mb-1 text-sm font-medium">How applications get sent</legend>
      {options.map((o) => (
        <label
          key={String(o.value)}
          className={cn(
            "flex min-h-11 cursor-pointer items-start gap-3 rounded-md border p-3",
            autoSubmit === o.value ? "border-primary bg-primary/5" : "border-input",
          )}
        >
          <input
            type="radio"
            name={name}
            checked={autoSubmit === o.value}
            onChange={() => onChange(o.value)}
            className="mt-0.5 size-5 shrink-0 accent-primary"
          />
          <span className="space-y-0.5">
            <span className="block text-sm font-medium">{o.label}</span>
            <span className="block text-sm text-muted-foreground">{o.description}</span>
          </span>
        </label>
      ))}
      {children}
    </fieldset>
  );
}
