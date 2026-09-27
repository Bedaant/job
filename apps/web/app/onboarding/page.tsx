"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
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
  clearDraft,
  defaultSources,
  emptyCampaignDraft,
  emptyPreferences,
  factsToPost,
  loadDraft,
  saveDraft,
  startingStep,
  stepErrors,
} from "@/lib/onboarding";
import { errorText, launchCampaign } from "@/lib/onboarding";
import type { CampaignDraft, Preferences, WizardStep } from "@/lib/onboarding";
import { getToken } from "@/lib/auth";
import { ErrorsAnnounced, FailureNotice } from "@/components/onboarding/fields";
import { StepCampaign } from "@/components/onboarding/StepCampaign";
import { StepDone } from "@/components/onboarding/StepDone";
import { StepFacts } from "@/components/onboarding/StepFacts";
import { StepPreferences } from "@/components/onboarding/StepPreferences";
import { StepResume } from "@/components/onboarding/StepResume";

const toDraft = ({ category, achievement, proof, metric, tags }: FactDraft): FactDraft => ({
  category,
  achievement,
  proof,
  metric,
  tags,
});

export default function OnboardingPage() {
  const router = useRouter();
  const queryClient = useQueryClient();
  const [authed, setAuthed] = useState(false);

  // null until the starting step has been worked out from the server + saved draft.
  const [step, setStep] = useState<WizardStep | "already-set-up" | null>(null);
  const [existing, setExisting] = useState<Campaign | null>(null);
  const [submitted, setSubmitted] = useState(false); // errors stay hidden until they try to advance
  const [attempt, setAttempt] = useState(0); // bumps on each blocked Continue → focus the first invalid field
  const [file, setFile] = useState<File | null>(null);
  const [facts, setFacts] = useState<FactDraft[]>([]);
  const [savedFacts, setSavedFacts] = useState<FactDraft[]>([]); // what the server already has
  const [basics, setBasics] = useState<ApplicantBasics>({});
  const [prefs, setPrefs] = useState<Preferences>(emptyPreferences);
  const [campaignDraft, setCampaignDraft] = useState<CampaignDraft>(emptyCampaignDraft);
  const [restoredDraft, setRestoredDraft] = useState(false);
  const [campaign, setCampaign] = useState<Campaign | null>(null);
  const [started, setStarted] = useState(true);

  const panelRef = useRef<HTMLDivElement>(null);
  const firstStep = useRef(true);

  useEffect(() => {
    if (!getToken()) router.push("/login");
    else setAuthed(true);
  }, [router]);

  useEffect(() => {
    document.title = "Set up · ApplyScout";
  }, []);

  // Focus management: a wizard that swaps the whole panel without moving focus
  // leaves a keyboard or screen-reader user stranded on a button that no longer
  // exists. Skip the first step shown so we don't steal focus on page load.
  useEffect(() => {
    if (step === null) return;
    if (firstStep.current) {
      firstStep.current = false;
      return;
    }
    panelRef.current?.focus();
  }, [step]);

  // A blocked Continue: focus the first invalid field (after the errors render),
  // or the panel when the problem isn't tied to a field.
  useEffect(() => {
    if (attempt === 0) return;
    const invalid = panelRef.current?.querySelector<HTMLElement>('[aria-invalid="true"]');
    (invalid ?? panelRef.current)?.focus();
  }, [attempt]);

  const profilesQuery = useQuery({ queryKey: ["profiles"], queryFn: api.listProfiles, enabled: authed });
  const ensureProfile = useMutation({
    mutationFn: () => api.createProfile("developer"),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["profiles"] }),
  });
  const profile = profilesQuery.data?.[0];
  const sourcesQuery = useQuery({ queryKey: ["sources"], queryFn: api.listSources, enabled: authed, retry: false });

  useEffect(() => {
    if (profilesQuery.isSuccess && profilesQuery.data.length === 0 && !ensureProfile.isPending && !ensureProfile.isError) {
      ensureProfile.mutate();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [profilesQuery.isSuccess, profilesQuery.data]);

  // Where to start: the server decides (saved facts, an existing campaign), a
  // draft saved in this tab restores what was typed. Runs once per profile.
  const profileId = profile?.id;
  useEffect(() => {
    if (!profileId) return;
    let cancelled = false;
    (async () => {
      const [saved, campaigns] = await Promise.all([
        api.listFacts(profileId).catch(() => [] as FactDraft[]),
        api.listCampaigns().catch(() => [] as Campaign[]),
      ]);
      const live = campaigns.filter((c) => c.status !== "archived");
      const draft = loadDraft(profileId);
      if (cancelled) return;
      setSavedFacts(saved.map(toDraft));
      if (draft) {
        setFacts(draft.facts);
        setBasics(draft.basics);
        setPrefs(draft.prefs);
        setCampaignDraft(draft.campaign);
        setRestoredDraft(true);
      } else if (saved.length > 0) {
        setFacts(saved.map(toDraft));
        // Leaving the facts step re-saves basics — start from what's saved, never from blank.
        setBasics(await api.getBasics(profileId).catch(() => ({})));
      }
      const start = startingStep({ draftStep: draft?.step ?? null, factCount: saved.length, campaignCount: live.length });
      if (start === "already-set-up") setExisting(live[0]);
      setStep(start);
    })();
    return () => {
      cancelled = true;
    };
  }, [profileId]);

  // A new campaign searches every live source unless the user's draft already chose.
  useEffect(() => {
    if (sourcesQuery.data && !restoredDraft) {
      setCampaignDraft((d) => ({ ...d, sources: defaultSources(sourcesQuery.data) }));
    }
  }, [sourcesQuery.data, restoredDraft]);

  // Persist the in-progress wizard so a refresh doesn't lose it (no token, no file).
  useEffect(() => {
    if (!profileId || step === null || step === "already-set-up" || step === "done") return;
    saveDraft(profileId, { step, facts, basics, prefs, campaign: campaignDraft });
  }, [profileId, step, facts, basics, prefs, campaignDraft]);

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
  // only point at which the user has actually approved them. Only facts the
  // server doesn't already have are posted (Back → Continue used to duplicate).
  const saveFacts = useMutation({
    mutationFn: async () => {
      await api.putBasics(profile!.id, basics);
      const fresh = factsToPost(facts, savedFacts);
      return fresh.length ? api.confirmFacts(profile!.id, fresh) : [];
    },
    onSuccess: (created) => {
      setSavedFacts((s) => [...s, ...created.map(toDraft)]);
      queryClient.invalidateQueries({ queryKey: ["facts", profile?.id] });
      goTo("preferences");
    },
  });

  const liveSources = sourcesQuery.data;
  const launch = useMutation({
    mutationFn: () => {
      // Never send a source the server says is off (a restored draft may hold one).
      const sources = liveSources
        ? campaignDraft.sources.filter((id) => liveSources.some((s) => s.id === id && s.enabled))
        : campaignDraft.sources;
      return launchCampaign(buildCampaignBody(prefs, { ...campaignDraft, sources }, profile!.id));
    },
    onSuccess: ({ campaign, started }) => {
      setCampaign(campaign);
      setStarted(started);
      if (profileId) clearDraft(profileId);
      goTo("done");
    },
  });

  const wizardStep: WizardStep = step === null || step === "already-set-up" ? "resume" : step;
  const state = { facts, basics, prefs, campaign: campaignDraft };
  const errors = stepErrors(wizardStep, state);
  const visibleErrors = submitted ? errors : {};
  const errorCount = Object.keys(errors).length;
  const blocked = errorCount > 0;
  const pending = upload.isPending || saveFacts.isPending || launch.isPending;

  function goTo(next: WizardStep) {
    setSubmitted(false);
    setStep(next);
  }

  function back() {
    if (pending) return;
    const i = STEPS.indexOf(wizardStep);
    if (i > 0) goTo(STEPS[i - 1]);
  }

  function next() {
    // aria-disabled, not disabled: the button keeps focus while a step saves.
    if (!profile || pending) return;
    setSubmitted(true);
    if (blocked) {
      setAttempt((n) => n + 1);
      return;
    }
    if (wizardStep === "facts") saveFacts.mutate();
    else if (wizardStep === "campaign") launch.mutate();
    else goTo(STEPS[STEPS.indexOf(wizardStep) + 1]);
  }

  if (!authed) return null;

  const stepIndex = STEPS.indexOf(wizardStep);
  const firstError = Object.values(errors)[0];

  return (
    <div className="min-h-screen bg-background text-foreground">
      <main className="mx-auto max-w-2xl px-4 py-10">
        <header className="mb-8">
          <p className="text-xs font-medium uppercase tracking-wider text-muted-foreground">ApplyScout</p>
          <h1 className="mt-1 text-2xl font-semibold">Let&apos;s get you interview calls.</h1>
          <p className="mt-2 text-sm text-muted-foreground">
            Five steps. You tell Maggie what is true about you and what you want; she does the searching, the
            rewriting and the applying — from your own browser, through a small extension you add at the end. Nothing
            is sent that you did not authorise.
          </p>
        </header>

        {profilesQuery.isError && (
          <FailureNotice
            title="Could not load your account"
            detail={`${errorText(profilesQuery.error)} Nothing you type here will save until this works.`}
          />
        )}

        {step === "already-set-up" && existing ? (
          <section aria-labelledby="set-up-heading" className="rounded-lg border border-border p-5 sm:p-6">
            <h2 id="set-up-heading" className="text-lg font-semibold">
              You&apos;re already set up
            </h2>
            <p className="mt-2 text-sm text-muted-foreground">
              Maggie is working on “{existing.name}”. Running setup again would start a second campaign, so there is
              nothing to do here.
            </p>
            <div className="mt-5 flex flex-wrap gap-3">
              <Link
                href="/today"
                className="inline-flex min-h-11 items-center rounded-md bg-primary px-4 text-sm font-medium text-primary-foreground hover:opacity-90"
              >
                Go to Today
              </Link>
              <Link
                href="/campaign"
                className="inline-flex min-h-11 items-center rounded-md border border-input px-4 text-sm font-medium hover:bg-accent"
              >
                Change your campaign
              </Link>
              <Link
                href="/facts"
                className="inline-flex min-h-11 items-center rounded-md border border-input px-4 text-sm font-medium hover:bg-accent"
              >
                Add more facts
              </Link>
            </div>
          </section>
        ) : (
          <>
            {/* Progress. An ordered list, not a row of divs — the step count and the
                current position are then available without sight. */}
            <nav aria-label="Progress" className="mb-8">
              <ol className="flex flex-wrap gap-x-2 gap-y-1 text-xs">
                {STEPS.map((s, i) => {
                  const done = i < stepIndex;
                  const current = s === wizardStep;
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
                {STEP_TITLES[wizardStep]}
              </h2>

              {/* The one live region for the wizard: step changes, a blocked Continue
                  (one summary — field errors are not each an alert), and saving. */}
              <p id="step-status" aria-live="polite" className="sr-only">
                {pending
                  ? "Saving…"
                  : submitted && blocked
                    ? `Can't continue: ${errorCount} ${errorCount === 1 ? "problem" : "problems"} on this step. ${firstError}`
                    : `Step ${stepIndex + 1} of ${STEPS.length}: ${STEP_TITLES[wizardStep]}`}
              </p>

              {(!profile || step === null) && !profilesQuery.isError && (
                <p className="text-sm text-muted-foreground">Setting up your profile…</p>
              )}

              <ErrorsAnnounced.Provider value={false}>
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
                          ? upload.data.error || "We couldn't read this resume. You can add your facts by hand instead."
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
                  <StepCampaign
                    campaign={campaignDraft}
                    onChange={setCampaignDraft}
                    prefs={prefs}
                    errors={visibleErrors}
                    sources={sourcesQuery.data}
                    sourcesFailed={sourcesQuery.isError}
                  />
                )}
              </ErrorsAnnounced.Provider>

              {profile && step === "done" && campaign && (
                <StepDone campaign={campaign} profileId={profile.id} started={started} />
              )}

              {saveFacts.isError && (
                <div className="mt-4">
                  <FailureNotice
                    title="Your facts were not saved"
                    detail={`${errorText(saveFacts.error)} Nothing on this page was lost.`}
                  />
                </div>
              )}

              {launch.isError && (
                <div className="mt-4">
                  <FailureNotice
                    title="The campaign was not created"
                    detail="Your answers are all still here. Check your connection and press Launch again."
                  />
                </div>
              )}

              {submitted && visibleErrors._ && step !== "facts" && (
                <p className="mt-4 text-sm font-medium text-destructive">{visibleErrors._}</p>
              )}

              {step !== "done" && step !== null && (
                <div className="mt-6 flex items-center justify-between gap-3 border-t border-border pt-5">
                  <button
                    type="button"
                    onClick={back}
                    disabled={stepIndex === 0}
                    aria-disabled={pending || undefined}
                    className="inline-flex min-h-11 items-center gap-1.5 rounded-md px-3 text-sm font-medium text-muted-foreground hover:text-foreground disabled:invisible aria-disabled:opacity-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                  >
                    <ArrowLeftIcon className="h-4 w-4" aria-hidden="true" />
                    Back
                  </button>
                  {/* Never `disabled`: a disabled button drops focus to <body> mid-save,
                      and an invalid step must still be pressable to learn why. */}
                  <button
                    type="button"
                    onClick={next}
                    aria-disabled={!profile || pending || undefined}
                    aria-describedby={submitted && blocked ? "step-status" : undefined}
                    className="inline-flex min-h-11 items-center gap-2 rounded-md bg-primary px-4 text-sm font-medium text-primary-foreground hover:opacity-90 aria-disabled:opacity-60 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                  >
                    {pending && <Loader2Icon className="h-4 w-4 animate-spin" aria-hidden="true" />}
                    {pending ? "Saving…" : step === "campaign" ? "Launch campaign" : "Continue"}
                  </button>
                </div>
              )}
            </div>
          </>
        )}
      </main>
    </div>
  );
}
