"use client";

import { PlusIcon, ShieldCheckIcon, Trash2Icon } from "lucide-react";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import type { ApplicantBasics, FactDraft } from "@/lib/api";
import type { Errors } from "@/lib/onboarding";
import { Chips, Field } from "./fields";

/**
 * ADR-009: the Facts KB is the only thing generation may draw on. This screen is
 * where the user fixes what the parser got wrong, so it has to make the stakes
 * legible rather than look like a tidy-up chore.
 */
export function StepFacts({
  facts,
  onFacts,
  basics,
  onBasics,
  errors,
}: {
  facts: FactDraft[];
  onFacts: (facts: FactDraft[]) => void;
  basics: ApplicantBasics;
  onBasics: (basics: ApplicantBasics) => void;
  errors: Errors;
}) {
  const set = (patch: Partial<ApplicantBasics>) => onBasics({ ...basics, ...patch });
  const orNull = (v: string) => (v.trim() === "" ? null : v);

  return (
    <div className="space-y-8">
      <div className="flex gap-3 rounded-md border border-input bg-secondary/40 p-4">
        <ShieldCheckIcon className="mt-0.5 h-5 w-5 shrink-0" aria-hidden="true" />
        <p className="text-sm text-muted-foreground">
          <span className="font-medium text-foreground">This list is the whole truth we work from.</span>{" "}
          Every resume and cover letter we write is assembled only from what is on this page. Anything you
          delete here can never appear in an application; anything wrong here can. If a field is blank
          because your resume never said it, leave it blank — we will not invent a value for it.
        </p>
      </div>

      <section aria-labelledby="basics-heading" className="space-y-4">
        <div>
          <h3 id="basics-heading" className="text-base font-medium">
            You
          </h3>
          <p className="text-sm text-muted-foreground">What an application form asks for before anything else.</p>
        </div>

        <div className="grid gap-4 sm:grid-cols-2">
          <Field
            label="Full name"
            value={basics.full_name ?? ""}
            onChange={(v) => set({ full_name: orNull(v) })}
            error={errors.full_name}
          />
          <Field
            label="Phone"
            type="tel"
            inputMode="tel"
            value={basics.phone ?? ""}
            onChange={(v) => set({ phone: orNull(v) })}
            error={errors.phone}
            hint="Leave blank rather than guess — a wrong number costs you the callback."
          />
          <Field
            label="Website"
            type="url"
            inputMode="url"
            placeholder="https://"
            value={basics.website_url ?? ""}
            onChange={(v) => set({ website_url: orNull(v) })}
            error={errors.website_url}
          />
          <Field
            label="City"
            value={basics.city ?? ""}
            onChange={(v) => set({ city: orNull(v) })}
            error={errors.city}
          />
          <Field
            label="Region / state"
            value={basics.region ?? ""}
            onChange={(v) => set({ region: orNull(v) })}
            error={errors.region}
          />
          <Field
            label="Country code"
            value={basics.country_code ?? ""}
            onChange={(v) => set({ country_code: orNull(v) })}
            error={errors.country_code}
            hint="Two letters, e.g. US, IN, DE."
          />
          <Field
            label="Street address"
            value={basics.street_address ?? ""}
            onChange={(v) => set({ street_address: orNull(v) })}
            error={errors.street_address}
          />
          <Field
            label="Postal code"
            value={basics.postal_code ?? ""}
            onChange={(v) => set({ postal_code: orNull(v) })}
            error={errors.postal_code}
          />
        </div>

        <Chips
          label="Work authorisation"
          values={basics.work_auth ?? []}
          onChange={(work_auth) => set({ work_auth })}
          hint="e.g. “EU citizen”, “US H-1B”, “UK right to work”. Forms ask; we will only answer what you put here."
          placeholder="Add an authorisation"
        />
      </section>

      <section aria-labelledby="facts-heading" className="space-y-3">
        <div className="flex items-end justify-between gap-4">
          <div>
            <h3 id="facts-heading" className="text-base font-medium">
              Your facts ({facts.length})
            </h3>
            <p className="text-sm text-muted-foreground">Correct anything the parser mangled. Delete anything untrue.</p>
          </div>
          <button
            type="button"
            onClick={() =>
              onFacts([...facts, { category: "experience", achievement: "", proof: null, metric: null, tags: [] }])
            }
            className="inline-flex shrink-0 items-center gap-1.5 rounded-md border border-input px-3 py-1.5 text-sm font-medium hover:bg-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          >
            <PlusIcon className="h-4 w-4" aria-hidden="true" />
            Add a fact
          </button>
        </div>

        {errors._ && (
          <p role="alert" className="text-sm font-medium text-destructive">
            {errors._}
          </p>
        )}

        <ul className="space-y-3">
          {facts.map((fact, i) => (
            <li key={i} className="rounded-md border border-input p-3">
              <Label htmlFor={`fact-${i}`} className="text-xs text-muted-foreground">
                Fact {i + 1} · {fact.category}
              </Label>
              <Textarea
                id={`fact-${i}`}
                rows={2}
                value={fact.achievement}
                onChange={(e) =>
                  onFacts(facts.map((f, j) => (j === i ? { ...f, achievement: e.target.value } : f)))
                }
                aria-invalid={errors[i] ? true : undefined}
                aria-describedby={errors[i] ? `fact-${i}-error` : undefined}
                className="mt-1"
              />
              {errors[i] && (
                <p id={`fact-${i}-error`} role="alert" className="mt-1 text-xs font-medium text-destructive">
                  {errors[i]}
                </p>
              )}

              <div className="mt-2 grid gap-2 sm:grid-cols-2">
                <Field
                  label="Metric"
                  value={fact.metric ?? ""}
                  onChange={(v) =>
                    onFacts(facts.map((f, j) => (j === i ? { ...f, metric: v.trim() === "" ? null : v } : f)))
                  }
                  hint="A number makes this fact land. Blank is fine if there genuinely isn't one."
                />
                <Field
                  label="Proof"
                  value={fact.proof ?? ""}
                  onChange={(v) =>
                    onFacts(facts.map((f, j) => (j === i ? { ...f, proof: v.trim() === "" ? null : v } : f)))
                  }
                  hint="Where this is verifiable — a link, a repo, a reference."
                />
              </div>

              <button
                type="button"
                onClick={() => onFacts(facts.filter((_, j) => j !== i))}
                className="mt-2 inline-flex items-center gap-1.5 rounded-md px-2 py-1 text-xs font-medium text-muted-foreground hover:text-destructive focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              >
                <Trash2Icon className="h-3.5 w-3.5" aria-hidden="true" />
                Remove fact {i + 1}
              </button>
            </li>
          ))}
        </ul>
      </section>
    </div>
  );
}
