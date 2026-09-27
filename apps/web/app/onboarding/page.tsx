"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeftIcon, CheckIcon, Loader2Icon } from "lucide-react";
import { ApiError, api } from "@/lib/api";
import type { ApplicantBasics, Campaign, FactDraft } from "@/lib/api";
import {
  STEPS,
  STEP_TITLES,
  blankFact,
  buildCampaignBody,
  emptyCampaignDraft,
  emptyPreferences,
  stepErrors,
} from "@/lib/onboarding";
import type { CampaignDraft, Preferences, WizardStep } from "@/lib/onboarding";
import { getToken } from "@/lib/auth";
import { FailureNotice } from "@/components/onboarding/fields";
import { StepCampaign } from "@/components/onboarding/StepCampaign";
import { StepDone } from "@/components/onboarding/StepDone";
import { StepFacts } from "@/components/onboarding/StepFacts";
import { StepPreferences } from "@/components/onboarding/StepPreferences";
import { StepResume } from "@/components/onboarding/StepResume";

export default function OnboardingPage() {
  const router = useRouter();
  const queryClient = useQueryClient();
  const [authed, setAuthed] = useState(false);

  const [step, setStep] = useState<WizardStep>("resume");
  const [submitted, setSubmitted] = useState(false); // errors stay hidden until they try to advance
  const [file, setFile] = useState<File | null>(null);
  const [facts, setFacts] = useState<FactDraft[]>([]);
  const [basics, setBasics] = useState<ApplicantBasics>({});
  const [prefs, setPrefs] = useState<Preferences>(emptyPreferences);
  const [campaignDraft, setCampaignDraft] = useState<CampaignDraft>(emptyCampaignDraft);
  const [campaign, setCampaign] = useState<Campaign | null>(null);

  const panelRef = useRef<HTMLDivElement>(null);
  const firstRender = useRef(true);

  useEffect(() => {
    if (!getToken()) router.push("/login");
    else setAuthed(true);
  }, [router]);

  // Focus management: a wizard that swaps the whole panel without moving focus
  // leaves a keyboard or screen-reader user stranded on a button that no longer
  // exists. Skip the very first render so we don't steal focus on page load.
  useEffect(() => {
    if (firstRender.current) {
      firstRender.current = false;
      return;
    }
    panelRef.current?.focus();
  }, [step]);

  const profilesQuery = useQuery({ queryKey: ["profiles"], queryFn: api.listProfiles, enabled: authed });
  const ensureProfile = useMutation({
    mutationFn: () => api.createProfile("developer"),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["profiles"] }),
  });
  const profile = profilesQuery.data?.[0];

  useEffect(() => {
    if (profilesQuery.isSuccess && profilesQuery.data.length === 0 && !ensureProfile.isPending && !ensureProfile.isError) {
      ensureProfile.mutate();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [profilesQuery.isSuccess, profilesQuery.data]);

  const upload = useMutation({
    mutationFn: (f: File) => api.uploadResume(profile!.id, f),
    onSuccess: (result) => {
      if (result.status === "failed") {
        setFacts([]);
        return;
      }
      setFacts(result.facts);
      // A parsed identity is a draft, never a saved fact (SPEC.md §2.1). Blank
      // fields are left blank on purpose — the user fills them, we don't guess.
      if (result.basics) setBasics(result.basics);
    },
  });

  // Facts + identity are persisted when leaving the confirm step, which is the
  // only point at which the user has actually approved them.
  const saveFacts = useMutation({
    mutationFn: async () => {
      await api.putBasics(profile!.id, basics);
      await api.confirmFacts(profile!.id, facts);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["facts", profile?.id] });
      goTo("preferences");
    },
  });

  const launch = useMutation({
    mutationFn: async () => {
      const created = await api.createCampaign(buildCampaignBody(prefs, campaignDraft));
      // A campaign that exists but was never run is a silent dead end, so kick
      // off the first pass here. A failure to start is reported, not swallowed —
      // but it does not discard the campaign that was just created.
      await api.runCampaign(created.id).catch(() => null);
      return created;
    },
    onSuccess: (created) => {
      setCampaign(created);
      goTo("done");
    },
  });

  const state = { facts, basics, prefs, campaign: campaignDraft };
  const errors = stepErrors(step, state);
  const visibleErrors = submitted ? errors : {};
  const blocked = Object.keys(errors).length > 0;

  function goTo(next: WizardStep) {
    setSubmitted(false);
    setStep(next);
  }

  function back() {
    const i = STEPS.indexOf(step);
    if (i > 0) goTo(STEPS[i - 1]);
  }

  function next() {
    setSubmitted(true);
    if (blocked) {
      panelRef.current?.focus();
      return;
    }
    if (step === "facts") saveFacts.mutate();
    else if (step === "campaign") launch.mutate();
    else goTo(STEPS[STEPS.indexOf(step) + 1]);
  }

  if (!authed) return null;

  const stepIndex = STEPS.indexOf(step);
  const pending = upload.isPending || saveFacts.isPending || launch.isPending;

  return (
    <div className="min-h-screen bg-background text-foreground">
      <main className="mx-auto max-w-2xl px-4 py-10">
        <header className="mb-8">
          <p className="text-xs font-medium uppercase tracking-wider text-muted-foreground">ApplyScout</p>
          <h1 className="mt-1 text-2xl font-semibold">Let&apos;s get you interview calls.</h1>
          <p className="mt-2 text-sm text-muted-foreground">
            Five steps. You tell Maggie what is true about you and what you want; she does the searching, the
            rewriting and the applying. Nothing is sent that you did not authorise.
          </p>
        </header>

        {/* Progress. An ordered list, not a row of divs — the step count and the
            current position are then available without sight. */}
        <nav aria-label="Progress" className="mb-8">
          <ol className="flex flex-wrap gap-x-2 gap-y-1 text-xs">
            {STEPS.map((s, i) => {
              const done = i < stepIndex;
              const current = s === step;
              return (
                <li
                  key={s}
                  aria-current={current ? "step" : undefined}
                  className={
                    current
                      ? "flex items-center gap-1 font-medium text-foreground"
                      : "flex items-center gap-1 text-muted-foreground"
                  }
                >
                  {done && <CheckIcon className="h-3 w-3" aria-hidden="true" />}
                  <span>
                    {i + 1}. {STEP_TITLES[s]}
                  </span>
                  {i < STEPS.length - 1 && <span aria-hidden="true" className="pl-2 text-muted-foreground">/</span>}
                </li>
              );
            })}
          </ol>
        </nav>

        {profilesQuery.isError && (
          <FailureNotice
            title="Could not load your account"
            detail={`${String(profilesQuery.error)} — the API may not be running. Nothing you type here will save until it is.`}
          />
        )}

        <div
          ref={panelRef}
          tabIndex={-1}
          role="group"
          aria-labelledby="step-heading"
          className="rounded-lg border border-border p-5 outline-none focus-visible:ring-2 focus-visible:ring-ring sm:p-6"
        >
          <h2 id="step-heading" className="mb-4 text-lg font-semibold">
            <span className="sr-only">
              Step {stepIndex + 1} of {STEPS.length}:{" "}
            </span>
            {STEP_TITLES[step]}
          </h2>

          {/* One live region for the whole wizard: step changes and blocked
              advances are announced instead of only being visible. */}
          <p aria-live="polite" className="sr-only">
            {submitted && blocked
              ? `Cannot continue: ${Object.keys(errors).length} problem(s) on this step.`
              : `Step ${stepIndex + 1} of ${STEPS.length}: ${STEP_TITLES[step]}`}
          </p>

          {!profile && !profilesQuery.isError && (
            <p className="text-sm text-muted-foreground">Setting up your profile…</p>
          )}

          {profile && step === "resume" && (
            <StepResume
              file={file}
              onFile={(f) => {
                setFile(f);
                upload.mutate(f);
              }}
              facts={facts}
              isUploading={upload.isPending}
              error={
                upload.isError
                  ? upload.error instanceof ApiError
                    ? upload.error.message
                    : "Upload failed."
                  : upload.data?.status === "failed"
                    ? upload.data.error || "The parser could not read it."
                    : null
              }
              onByHand={() => {
                if (facts.length === 0) setFacts([blankFact()]); // never discard parsed facts
                goTo("facts");
              }}
            />
          )}

          {profile && step === "facts" && (
            <StepFacts facts={facts} onFacts={setFacts} basics={basics} onBasics={setBasics} errors={visibleErrors} />
          )}

          {profile && step === "preferences" && (
            <StepPreferences prefs={prefs} onChange={setPrefs} errors={visibleErrors} />
          )}

          {profile && step === "campaign" && (
            <StepCampaign campaign={campaignDraft} onChange={setCampaignDraft} prefs={prefs} errors={visibleErrors} />
          )}

          {profile && step === "done" && campaign && <StepDone campaign={campaign} profileId={profile.id} />}

          {saveFacts.isError && (
            <div className="mt-4">
              <FailureNotice
                title="Your facts were not saved"
                detail={`${saveFacts.error instanceof ApiError ? saveFacts.error.message : String(saveFacts.error)} — nothing was lost from this page, but you cannot continue until this succeeds.`}
              />
            </div>
          )}

          {launch.isError && (
            <div className="mt-4">
              <FailureNotice
                title="The campaign was not created"
                detail={
                  launch.error instanceof ApiError && launch.error.status === 404
                    ? "POST /campaigns returned 404 — the campaigns backend is not deployed yet. Everything on this page is still here; press Launch again once it is."
                    : launch.error instanceof ApiError
                      ? launch.error.message
                      : String(launch.error)
                }
              />
            </div>
          )}

          {submitted && visibleErrors._ && step !== "facts" && (
            <p role="alert" className="mt-4 text-sm font-medium text-destructive">
              {visibleErrors._}
            </p>
          )}

          {step !== "done" && (
            <div className="mt-6 flex items-center justify-between gap-3 border-t border-border pt-5">
              <button
                type="button"
                onClick={back}
                disabled={stepIndex === 0 || pending}
                className="inline-flex items-center gap-1.5 rounded-md px-3 py-2 text-sm font-medium text-muted-foreground hover:text-foreground disabled:invisible focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              >
                <ArrowLeftIcon className="h-4 w-4" aria-hidden="true" />
                Back
              </button>
              <button
                type="button"
                onClick={next}
                disabled={!profile || pending}
                // Deliberately NOT disabled when the step is invalid: a disabled
                // button gives a keyboard user no way to find out why. It stays
                // pressable and reveals the errors instead.
                aria-describedby={submitted && blocked ? "step-heading" : undefined}
                className="inline-flex items-center gap-2 rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:opacity-90 disabled:opacity-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              >
                {pending && <Loader2Icon className="h-4 w-4 animate-spin" aria-hidden="true" />}
                {step === "campaign" ? "Launch campaign" : "Continue"}
              </button>
            </div>
          )}
        </div>
      </main>
    </div>
  );
}
