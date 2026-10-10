"use client";

import { useId, useState } from "react";
import Link from "next/link";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { MinusIcon, PlusIcon } from "lucide-react";
import { api, ApiError, type Campaign } from "@/lib/api";
import { buildCampaignPatch, formFromCampaign, statusView, validateCampaignForm, type CampaignForm } from "@/lib/campaign-form";
import { DAILY_CAP_MAX, type Errors } from "@/lib/onboarding";
import { AppShell, useRequireAuth } from "@/components/AppShell";
import { useCampaignStatus } from "@/components/useCampaignStatus";
import { SubmitModeChoice } from "@/components/SubmitModeChoice";
import { submitModeLine } from "@/lib/assisted";
import { Chips, Field } from "@/components/onboarding/fields";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { Textarea } from "@/components/ui/textarea";
import { cn } from "@/lib/utils";

const errorText = (err: unknown) => (err instanceof ApiError ? err.message : "Something went wrong. Try again.");

const TONE = {
  success: "border-success/40 bg-success-soft text-success",
  warning: "border-warning/40 bg-warning-soft text-warning",
  muted: "border-border bg-muted text-muted-foreground",
};

/** A labelled on/off switch. role="switch" + aria-checked, not aria-pressed. */
function Switch({
  label,
  checked,
  onChange,
  description,
}: {
  label: string;
  checked: boolean;
  onChange: (checked: boolean) => void;
  description: string;
}) {
  const id = useId();
  return (
    <div className="flex items-start justify-between gap-4">
      <div className="space-y-1">
        <Label id={`${id}-label`}>{label}</Label>
        <p id={`${id}-desc`} className="text-sm text-muted-foreground">
          {description}
        </p>
      </div>
      <button
        type="button"
        role="switch"
        aria-checked={checked}
        aria-labelledby={`${id}-label`}
        aria-describedby={`${id}-desc`}
        onClick={() => onChange(!checked)}
        className={cn(
          "relative inline-flex h-11 w-[72px] shrink-0 items-center rounded-full border-2 border-transparent p-1 transition-colors",
          checked ? "bg-primary" : "bg-input"
        )}
      >
        <span
          aria-hidden="true"
          className={cn("size-8 rounded-full bg-card shadow transition-transform", checked && "translate-x-7")}
        />
      </button>
    </div>
  );
}

function DailyCapStepper({ value, onChange, error }: { value: number; onChange: (v: number) => void; error?: string }) {
  const id = useId();
  const valid = Number.isFinite(value);
  return (
    <div className="space-y-1.5">
      <Label htmlFor={id}>Daily cap</Label>
      <div className="flex items-center gap-2">
        <Button
          type="button"
          variant="outline"
          size="icon-lg"
          aria-label="Decrease daily cap"
          disabled={valid && value <= 1}
          onClick={() => onChange(valid ? value - 1 : 1)}
        >
          <MinusIcon aria-hidden="true" />
        </Button>
        <Input
          id={id}
          type="number"
          inputMode="numeric"
          min={1}
          max={DAILY_CAP_MAX}
          value={valid ? String(value) : ""}
          onChange={(e) => onChange(e.target.value.trim() === "" ? NaN : Number(e.target.value))}
          aria-invalid={error ? true : undefined}
          aria-describedby={`${id}-hint${error ? ` ${id}-error` : ""}`}
          className={cn("w-24 text-center tabular-nums", error && "border-destructive")}
        />
        <Button
          type="button"
          variant="outline"
          size="icon-lg"
          aria-label="Increase daily cap"
          disabled={valid && value >= DAILY_CAP_MAX}
          onClick={() => onChange(valid ? value + 1 : 1)}
        >
          <PlusIcon aria-hidden="true" />
        </Button>
      </div>
      <p id={`${id}-hint`} className="text-xs text-muted-foreground">
        The most applications Maggie starts in one day, up to {DAILY_CAP_MAX}. A hard stop, not a target.
      </p>
      {error && (
        <p id={`${id}-error`} role="alert" className="text-xs font-medium text-destructive">
          {error}
        </p>
      )}
    </div>
  );
}

function StatusCard({ campaign }: { campaign: Campaign }) {
  const { setStatus, error } = useCampaignStatus(campaign);
  const view = statusView(campaign.status);

  const statsQuery = useQuery({
    queryKey: ["campaign-stats", campaign.id],
    queryFn: () => api.getCampaignStats(campaign.id),
  });
  const stats = statsQuery.data;

  return (
    <section aria-labelledby="status-heading" className="rounded-2xl border bg-card p-6 shadow-sm">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="space-y-2" aria-live="polite">
          <span className={cn("inline-flex items-center rounded-full border px-3 py-1 text-sm font-semibold", TONE[view.tone])}>
            {view.label}
          </span>
          <h2 id="status-heading" className="text-2xl font-bold tracking-tight">
            {view.headline}
          </h2>
          {campaign.status === "active" && (
            <p className="text-muted-foreground">
              {submitModeLine(campaign.auto_submit)}
            </p>
          )}
        </div>
        {view.action && (
          <Button size="lg" className="min-w-32" onClick={() => setStatus(view.action!.next)}>
            {view.action.label}
          </Button>
        )}
      </div>

      {error && (
        <p role="alert" className="mt-4 rounded-xl bg-destructive/10 px-4 py-3 text-sm font-medium text-destructive">
          {error}
        </p>
      )}

      <div className="mt-6 border-t pt-5">
        <h3 className="text-sm font-medium text-muted-foreground">Today</h3>
        {statsQuery.isLoading && <Skeleton className="mt-2 h-6 w-48" />}
        {statsQuery.isError && (
          <p role="alert" className="mt-1 text-sm text-destructive">
            Couldn&apos;t load today&apos;s numbers: {errorText(statsQuery.error)}
          </p>
        )}
        {stats && (
          <>
            <p className="mt-1 text-lg">
              <span className="font-semibold tabular-nums">{stats.applied_today}</span> of{" "}
              <span className="tabular-nums">{stats.daily_cap}</span> applications started today
              <span className="text-muted-foreground"> · {stats.total_applied} in total</span>
            </p>
            <div aria-hidden="true" className="mt-2 h-2 overflow-hidden rounded-full bg-muted">
              <div
                className="h-full rounded-full bg-primary"
                style={{ width: `${Math.min(100, (stats.applied_today / Math.max(1, stats.daily_cap)) * 100)}%` }}
              />
            </div>
          </>
        )}
      </div>
    </section>
  );
}

function SettingsForm({ campaign }: { campaign: Campaign }) {
  const queryClient = useQueryClient();
  const baseline = formFromCampaign(campaign);
  const [form, setForm] = useState<CampaignForm>(baseline);
  const [errors, setErrors] = useState<Errors>({});
  const [notice, setNotice] = useState("");

  const patch = buildCampaignPatch(baseline, form);
  const dirty = Object.keys(patch).length > 0;

  function set(change: Partial<CampaignForm>) {
    setForm((f) => ({ ...f, ...change }));
    setNotice("");
  }

  const mutation = useMutation({
    mutationFn: () => api.updateCampaign(campaign.id, patch),
    onSuccess: (saved) => {
      queryClient.setQueryData<Campaign[]>(["campaigns"], (old) => old?.map((c) => (c.id === saved.id ? saved : c)));
      queryClient.invalidateQueries({ queryKey: ["campaign-stats", saved.id] });
      setForm(formFromCampaign(saved));
      setErrors({});
      setNotice("Saved. Maggie uses these settings from her next run.");
    },
    onError: (err) => {
      // request() flattens a 422's per-field detail into one message, so a
      // server-side rejection lands here as a form-level error.
      setErrors({ _: `Not saved: ${errorText(err)}` });
    },
  });

  function save(e: React.FormEvent) {
    e.preventDefault();
    const found = validateCampaignForm(form);
    setErrors(found);
    if (Object.keys(found).length === 0) mutation.mutate();
  }

  return (
    <form onSubmit={save} aria-labelledby="settings-heading" className="space-y-7 rounded-2xl border bg-card p-6 shadow-sm" noValidate>
      <div className="space-y-1">
        <h2 id="settings-heading" className="text-xl font-semibold tracking-tight">
          What you approved
        </h2>
        <p className="text-sm text-muted-foreground">Change anything here; it takes effect from Maggie&apos;s next run.</p>
      </div>

      <Chips label="Roles" values={form.roles} onChange={(roles) => set({ roles })} error={errors.roles} placeholder="e.g. Backend Engineer" />
      <Chips
        label="Locations"
        values={form.locations}
        onChange={(locations) => set({ locations })}
        error={errors.locations}
        placeholder="e.g. Berlin"
      />
      <Switch
        label="Remote only"
        checked={form.remote_only}
        onChange={(remote_only) => set({ remote_only })}
        description={form.remote_only ? "On: only remote roles." : "Off: remote and on-site roles in your locations."}
      />
      <Switch
        label="Include older postings"
        checked={form.include_older_postings}
        onChange={(include_older_postings) => set({ include_older_postings })}
        description={form.include_older_postings ? "On: postings of any age." : "Off: skips postings older than 60 days — they are usually filled."}
      />
      <DailyCapStepper value={form.daily_cap} onChange={(daily_cap) => set({ daily_cap })} error={errors.daily_cap} />
      <Field
        label="Minimum match score (%)"
        type="number"
        inputMode="numeric"
        value={Number.isFinite(form.min_match_score) ? String(Math.round(form.min_match_score * 100)) : ""}
        onChange={(v) => set({ min_match_score: v.trim() === "" ? NaN : Number(v) / 100 })}
        error={errors.min_match_score}
        hint="Maggie skips jobs that fit less well than this."
      />
      <SubmitModeChoice autoSubmit={form.auto_submit} onChange={(auto_submit) => set({ auto_submit })} />
      <div className="space-y-1.5">
        <Label htmlFor="tailoring-notes">Notes for writing applications</Label>
        <Textarea
          id="tailoring-notes"
          value={form.tailoring_notes}
          onChange={(e) => set({ tailoring_notes: e.target.value })}
          aria-describedby="tailoring-notes-hint"
          rows={3}
        />
        <p id="tailoring-notes-hint" className="text-xs text-muted-foreground">
          How to write, e.g. &quot;keep cover letters short&quot;. Never used as a source of facts about you.
        </p>
      </div>

      {errors._ && (
        <p role="alert" className="rounded-xl bg-destructive/10 px-4 py-3 text-sm font-medium text-destructive">
          {errors._}
        </p>
      )}

      <div className="flex flex-wrap items-center gap-4">
        <Button type="submit" size="lg" disabled={!dirty || mutation.isPending}>
          {mutation.isPending ? "Saving…" : "Save changes"}
        </Button>
        <p aria-live="polite" className="text-sm font-medium text-success">
          {notice}
        </p>
      </div>
    </form>
  );
}

export default function CampaignPage() {
  const ready = useRequireAuth();
  const [selectedId, setSelectedId] = useState<string | null>(null);

  const campaignsQuery = useQuery({ queryKey: ["campaigns"], queryFn: api.listCampaigns, enabled: ready });
  // Archived campaigns are history — nothing to pause or change.
  const campaigns = (campaignsQuery.data ?? []).filter((c) => c.status !== "archived");
  const campaign = campaigns.find((c) => c.id === selectedId) ?? campaigns[0];

  if (!ready) return null;

  return (
    <AppShell title="Campaign" description="What Maggie is doing for you, and the limits you set. Pause it any time.">
      {campaignsQuery.isLoading && (
        <div className="space-y-4">
          <Skeleton className="h-48 w-full rounded-2xl" />
          <Skeleton className="h-96 w-full rounded-2xl" />
        </div>
      )}

      {campaignsQuery.isError && (
        <p role="alert" className="rounded-xl bg-destructive/10 px-4 py-3 text-sm font-medium text-destructive">
          Couldn&apos;t load your campaign: {errorText(campaignsQuery.error)}
        </p>
      )}

      {campaignsQuery.isSuccess && !campaign && (
        <div className="rounded-2xl border border-dashed px-6 py-12 text-center">
          <p className="text-lg font-semibold">No campaign yet</p>
          <p className="mx-auto mt-1 max-w-md text-muted-foreground">
            A campaign tells Maggie which roles to look for and how many applications a day are fine. Setup takes a few
            minutes.
          </p>
          <Button asChild className="mt-5">
            <Link href="/onboarding">Set up a campaign</Link>
          </Button>
        </div>
      )}

      {campaign && (
        <div className="space-y-6">
          {campaigns.length > 1 && (
            <nav aria-label="Your campaigns" className="flex flex-wrap gap-2">
              {campaigns.map((c) => (
                <Button
                  key={c.id}
                  variant={c.id === campaign.id ? "secondary" : "ghost"}
                  className="h-11"
                  aria-pressed={c.id === campaign.id}
                  onClick={() => setSelectedId(c.id)}
                >
                  {c.name} · {statusView(c.status).label}
                </Button>
              ))}
            </nav>
          )}
          <StatusCard campaign={campaign} />
          {/* key: switching campaigns resets the form instead of carrying edits across. */}
          <SettingsForm key={campaign.id} campaign={campaign} />
        </div>
      )}
    </AppShell>
  );
}
