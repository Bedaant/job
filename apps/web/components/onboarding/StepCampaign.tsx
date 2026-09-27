"use client";

import { AlertTriangleIcon } from "lucide-react";
import { Checkbox } from "@/components/ui/checkbox";
import { Label } from "@/components/ui/label";
import { AVAILABLE_SOURCES, DAILY_CAP_MAX } from "@/lib/onboarding";
import type { CampaignDraft, Errors, Preferences } from "@/lib/onboarding";
import { Field } from "./fields";
import { SubmitModeChoice } from "@/components/SubmitModeChoice";

/**
 * ADR-015: approval happens once, here, at campaign level — not per application.
 * That is the whole reason this screen has to be blunt. The user is not
 * configuring a search; in Automatic mode they are authorising a machine to
 * send things to real employers under their name while they are not watching.
 * Assisted (auto_submit=false) is the default: Maggie prepares, the user sends.
 */
export function StepCampaign({
  campaign,
  onChange,
  prefs,
  errors,
}: {
  campaign: CampaignDraft;
  onChange: (campaign: CampaignDraft) => void;
  prefs: Preferences;
  errors: Errors;
}) {
  const set = (patch: Partial<CampaignDraft>) => onChange({ ...campaign, ...patch });

  function toggleSource(id: string, on: boolean) {
    set({ sources: on ? [...campaign.sources, id] : campaign.sources.filter((s) => s !== id) });
  }

  return (
    <div className="space-y-7">
      <p className="text-sm text-muted-foreground">
        A campaign is a standing instruction: keep looking for{" "}
        <span className="font-medium text-foreground">{prefs.roles.join(", ") || "these roles"}</span>
        {prefs.remote_only ? " (remote only)" : prefs.locations.length ? ` in ${prefs.locations.join(", ")}` : ""}, and
        act on what turns up. You approve it once, here — not one application at a time.
      </p>

      <Field label="Campaign name" value={campaign.name} onChange={(name) => set({ name })} error={errors.name} />

      <fieldset className="space-y-2">
        <legend className="text-sm font-medium">Where to look</legend>
        {errors.sources && (
          <p role="alert" className="text-xs font-medium text-destructive">
            {errors.sources}
          </p>
        )}
        <div className="grid gap-2 sm:grid-cols-2">
          {AVAILABLE_SOURCES.map((source) => (
            <div key={source.id} className="flex items-start gap-3 rounded-md border border-input p-3">
              <Checkbox
                id={`source-${source.id}`}
                checked={campaign.sources.includes(source.id)}
                onCheckedChange={(checked) => toggleSource(source.id, checked === true)}
              />
              <div>
                <Label htmlFor={`source-${source.id}`}>{source.label}</Label>
                <p className="text-xs text-muted-foreground">{source.note}</p>
              </div>
            </div>
          ))}
        </div>
      </fieldset>

      <Field
        label="Minimum match score (%)"
        type="number"
        inputMode="numeric"
        value={String(Math.round(campaign.min_match_score * 100))}
        onChange={(v) => set({ min_match_score: v.trim() === "" ? NaN : Number(v) / 100 })}
        error={errors.min_match_score}
        hint="Below this, we do not bother you. 70% is the default: high enough to skip the obvious mismatches, low enough that you still see roles you would not have searched for."
      />

      <Field
        label="Daily cap"
        type="number"
        inputMode="numeric"
        value={Number.isFinite(campaign.daily_cap) ? String(campaign.daily_cap) : ""}
        onChange={(v) => set({ daily_cap: v.trim() === "" ? NaN : Number(v) })}
        error={errors.daily_cap}
        hint={`The most applications this campaign will produce in one day, up to ${DAILY_CAP_MAX}. This is a hard stop, not a target — it exists so a bad match score or a flood of new postings cannot spend your whole search in an afternoon.`}
      />

      <SubmitModeChoice autoSubmit={campaign.auto_submit} onChange={(auto_submit) => set({ auto_submit })}>
        {campaign.auto_submit && (
          <div role="alert" className="flex gap-3 rounded-md border border-destructive/50 bg-destructive/5 p-3">
            <AlertTriangleIcon className="mt-0.5 h-4 w-4 shrink-0 text-destructive" aria-hidden="true" />
            <div className="space-y-1 text-xs text-muted-foreground">
              <p className="text-sm font-medium text-destructive">You are authorising autonomous submission.</p>
              <p>
                Up to {Number.isFinite(campaign.daily_cap) ? campaign.daily_cap : "—"} applications a day will
                go to real employers under your name, with no further prompt. Nothing outside the facts you
                confirmed will be written, but a bad fit sent to a company you wanted to approach carefully is
                not something we can take back. You can switch this off at any time; anything already sent
                stays sent.
              </p>
            </div>
          </div>
        )}
      </SubmitModeChoice>
    </div>
  );
}
