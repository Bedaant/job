"use client";

import { Checkbox } from "@/components/ui/checkbox";
import { Label } from "@/components/ui/label";
import type { Errors, Preferences } from "@/lib/onboarding";
import { Chips, Field } from "./fields";

export function StepPreferences({
  prefs,
  onChange,
  errors,
}: {
  prefs: Preferences;
  onChange: (prefs: Preferences) => void;
  errors: Errors;
}) {
  const set = (patch: Partial<Preferences>) => onChange({ ...prefs, ...patch });

  return (
    <div className="space-y-6">
      <p className="text-sm text-muted-foreground">
        This is what we go looking for. Two or three roles works better than one — the same background often
        reads as several different job titles.
      </p>

      <Chips
        label="Roles"
        values={prefs.roles}
        onChange={(roles) => set({ roles })}
        error={errors.roles}
        placeholder="e.g. Backend Engineer"
        hint="Type a title and press Enter. Add every variant you would accept."
      />

      <Chips
        label="Locations"
        values={prefs.locations}
        onChange={(locations) => set({ locations })}
        error={errors.locations}
        placeholder="e.g. Berlin"
        hint="Cities, regions, or countries. Skip this if you only want remote work."
      />

      <div className="flex items-start gap-3 rounded-md border border-input p-3">
        <Checkbox
          id="remote-only"
          checked={prefs.remote_only}
          onCheckedChange={(checked) => set({ remote_only: checked === true })}
        />
        <div className="space-y-1">
          <Label htmlFor="remote-only">Remote only</Label>
          <p className="text-xs text-muted-foreground">
            On, we discard anything that requires being on site — including hybrid roles.
          </p>
        </div>
      </div>

      <Field
        label="Salary floor (optional)"
        type="number"
        inputMode="numeric"
        value={prefs.min_salary === null ? "" : String(prefs.min_salary)}
        onChange={(v) => set({ min_salary: v.trim() === "" ? null : Number(v) })}
        error={errors.min_salary}
        hint="Annual base, in the currency of the role. Most postings do not state pay, so we pass this along as a note on the campaign rather than filter on it — it is not a hard cutoff yet."
      />
    </div>
  );
}
