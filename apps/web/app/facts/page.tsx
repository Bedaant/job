"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { FileUpIcon, PlusIcon } from "lucide-react";
import { api, ApiError, type ApplicantBasics, type FactDraft, type ResumeFact, type SavedAnswer } from "@/lib/api";
import { FACT_CATEGORIES, blankFact, validateBasics } from "@/lib/onboarding";
import { factChanges, undoableDeletes } from "@/lib/profile";
import { AppShell, useRequireAuth } from "@/components/AppShell";
import { Chips, Field } from "@/components/onboarding/fields";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { Textarea } from "@/components/ui/textarea";

const errorText = (err: unknown, fallback: string) => (err instanceof ApiError ? err.message : fallback);

function Alert({ children }: { children: React.ReactNode }) {
  return <p role="alert" className="rounded-xl bg-destructive/10 px-4 py-3 text-sm font-medium text-destructive">{children}</p>;
}

function Saved({ children }: { children: React.ReactNode }) {
  return <p role="status" className="rounded-xl bg-success-soft px-4 py-3 text-sm font-medium text-success">{children}</p>;
}

export default function ProfilePage() {
  const queryClient = useQueryClient();
  const ready = useRequireAuth();

  const profilesQuery = useQuery({ queryKey: ["profiles"], queryFn: api.listProfiles, enabled: ready });
  const ensureProfile = useMutation({
    mutationFn: () => api.createProfile("developer"),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["profiles"] }),
  });
  const profile = profilesQuery.data?.[0];

  useEffect(() => {
    if (ready && profilesQuery.isSuccess && profilesQuery.data.length === 0 && !ensureProfile.isPending) {
      ensureProfile.mutate();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ready, profilesQuery.isSuccess, profilesQuery.data]);

  if (!ready) return null;

  return (
    <AppShell
      title="Profile"
      description="Everything Maggie knows about you, and everything she writes comes from here. Keep it true — changes apply to future applications."
    >
      {!profile && <Skeleton className="h-40 w-full rounded-2xl" />}
      {profile && (
        <div className="space-y-12">
          <nav aria-label="Profile sections" className="flex flex-wrap gap-2">
            {[["#facts", "Facts"], ["#about", "About you"], ["#answers", "Saved answers"]].map(([href, label]) => (
              <a
                key={href}
                href={href}
                className="inline-flex min-h-11 items-center rounded-lg border px-4 text-sm font-medium hover:bg-muted focus-visible:outline-none focus-visible:ring-[3px] focus-visible:ring-ring/50"
              >
                {label}
              </a>
            ))}
          </nav>
          <FactsSection profileId={profile.id} />
          <AboutSection profileId={profile.id} />
          <AnswersSection profileId={profile.id} />
        </div>
      )}
    </AppShell>
  );
}

// ---------------------------------------------------------------- Facts

function FactsSection({ profileId }: { profileId: string }) {
  const queryClient = useQueryClient();
  const fileInput = useRef<HTMLInputElement>(null);
  const [draftFacts, setDraftFacts] = useState<FactDraft[] | null>(null);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [adding, setAdding] = useState<FactDraft | null>(null);
  const [hidden, setHidden] = useState<string[]>([]);
  const factsKey = ["facts", profileId];

  const factsQuery = useQuery({ queryKey: factsKey, queryFn: () => api.listFacts(profileId) });

  const deletes = useMemo(
    () =>
      undoableDeletes((id) => {
        api
          .deleteFact(id)
          .catch((err) => {
            setHidden((h) => h.filter((x) => x !== id));
            setError(errorText(err, "Couldn't delete that fact. It's back in the list — try again."));
          })
          .finally(() => queryClient.invalidateQueries({ queryKey: ["facts", profileId] }));
      }),
    [profileId, queryClient]
  );
  // Leaving the page keeps a pending delete rather than silently dropping it.
  useEffect(() => () => deletes.flush(), [deletes]);

  const uploadMutation = useMutation({
    mutationFn: (file: File) => api.uploadResume(profileId, file),
    onSuccess: (result) => {
      setUploadError(null);
      setNotice(null);
      if (result.status === "failed") {
        setUploadError(result.error || "We couldn't read this resume. You can add your facts by hand instead.");
        setDraftFacts(null);
      } else {
        setDraftFacts(result.facts);
      }
    },
    onError: (err) => setUploadError(errorText(err, "We couldn't upload this file. Check your connection and try again.")),
  });

  const confirmMutation = useMutation({
    mutationFn: (facts: FactDraft[]) => api.confirmFacts(profileId, facts),
    onSuccess: (created) => {
      setNotice(`Saved ${created.length} fact${created.length === 1 ? "" : "s"}.`);
      setDraftFacts(null);
      setAdding(null);
      queryClient.invalidateQueries({ queryKey: factsKey });
    },
    onError: (err) => setError(errorText(err, "Couldn't save. Try again.")),
  });

  function remove(fact: ResumeFact) {
    setHidden((h) => [...h, fact.id]);
    setNotice(null);
    deletes.schedule(fact.id);
  }

  function undo(id: string) {
    deletes.undo(id);
    setHidden((h) => h.filter((x) => x !== id));
  }

  const all = factsQuery.data ?? [];
  const facts = all.filter((f) => !hidden.includes(f.id));
  const pending = all.filter((f) => hidden.includes(f.id));

  return (
    <section id="facts" aria-labelledby="facts-h" className="scroll-mt-24 space-y-6">
      <div className="space-y-1">
        <h2 id="facts-h" className="text-2xl font-semibold">Facts</h2>
        <p className="text-muted-foreground">
          One thing you did per fact, in your own words — Maggie tailors from these and nothing else. Edits apply to
          future applications; resumes already tailored keep their wording. A deleted fact is also left out of any
          prepared resume you download later.
        </p>
      </div>

      <div>
        <input ref={fileInput} id="resume-file" type="file" accept=".pdf,.docx" className="sr-only"
          disabled={uploadMutation.isPending}
          onChange={(e) => {
            const file = e.target.files?.[0];
            if (file) uploadMutation.mutate(file);
            e.target.value = "";
          }}
        />
        <button
          type="button"
          onClick={() => fileInput.current?.click()}
          disabled={uploadMutation.isPending}
          className="flex w-full flex-col items-center gap-2 rounded-2xl border-2 border-dashed border-input bg-card px-6 py-8 text-center transition-colors hover:border-primary hover:bg-accent disabled:cursor-wait disabled:opacity-70"
        >
          <FileUpIcon className="size-8 text-primary" aria-hidden="true" />
          <span className="font-semibold">{uploadMutation.isPending ? "Reading your resume…" : "Add facts from a resume"}</span>
          <span className="text-sm text-muted-foreground">PDF or Word, under 5 MB · nothing is saved until you confirm</span>
        </button>
      </div>

      <div aria-live="polite" className="space-y-2">
        {uploadError && <Alert>{uploadError}</Alert>}
        {error && <Alert>{error}</Alert>}
        {notice && <Saved>{notice}</Saved>}
        {pending.map((f) => (
          <div key={f.id} role="status" className="flex flex-wrap items-center justify-between gap-2 rounded-xl border bg-card px-4 py-2 text-sm">
            <span>Deleted “{f.achievement.slice(0, 60)}{f.achievement.length > 60 ? "…" : ""}”</span>
            <Button variant="outline" className="h-11" onClick={() => undo(f.id)}>Undo</Button>
          </div>
        ))}
      </div>

      {draftFacts && draftFacts.length > 0 && (
        <div className="space-y-4">
          <h3 className="text-lg font-semibold">Check {draftFacts.length} facts we found</h3>
          <p className="text-muted-foreground">Fix anything that&apos;s off and remove anything that isn&apos;t true.</p>
          <ul className="space-y-3">
            {draftFacts.map((fact, i) => (
              <li key={i} className="space-y-3 rounded-2xl border bg-card p-5 shadow-sm">
                <Label htmlFor={`draft-${i}`} className="text-xs uppercase text-muted-foreground">{fact.category}</Label>
                <Textarea id={`draft-${i}`} rows={2} value={fact.achievement}
                  onChange={(e) => setDraftFacts((p) => p && p.map((f, j) => (j === i ? { ...f, achievement: e.target.value } : f)))}
                />
                <Button variant="ghost" className="h-11" onClick={() => setDraftFacts((p) => p && p.filter((_, j) => j !== i))}>
                  Remove
                </Button>
              </li>
            ))}
          </ul>
          <Button size="lg"
            onClick={() => confirmMutation.mutate(draftFacts.filter((f) => f.achievement.trim()))}
            disabled={confirmMutation.isPending}
          >
            {confirmMutation.isPending ? "Saving…" : `Keep ${draftFacts.length} facts`}
          </Button>
        </div>
      )}

      <div className="space-y-3">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h3 className="text-lg font-semibold">
            Confirmed <span className="tabular-nums text-muted-foreground">{facts.length}</span>
          </h3>
          {!adding && (
            <Button variant="outline" className="h-11" onClick={() => setAdding(blankFact())}>
              <PlusIcon aria-hidden="true" /> Add a fact
            </Button>
          )}
        </div>

        {adding && (
          <FactForm
            idPrefix="new"
            value={adding}
            onChange={setAdding}
            saving={confirmMutation.isPending}
            saveLabel="Add fact"
            onSave={() => confirmMutation.mutate([{ ...adding, achievement: adding.achievement.trim() }])}
            onCancel={() => setAdding(null)}
          />
        )}

        {factsQuery.isLoading && <Skeleton className="h-24 w-full rounded-2xl" />}
        {factsQuery.isError && <Alert>{errorText(factsQuery.error, "Couldn't load your facts.")}</Alert>}
        {factsQuery.isSuccess && facts.length === 0 && !adding && (
          <p className="rounded-2xl border border-dashed px-6 py-8 text-center text-muted-foreground">
            No facts yet. Add a resume above, or add one by hand.
          </p>
        )}
        {facts.length > 0 && (
          <ul className="divide-y rounded-2xl border bg-card shadow-sm">
            {facts.map((fact) => (
              <FactRow key={fact.id} fact={fact} onDelete={() => remove(fact)} />
            ))}
          </ul>
        )}
      </div>
    </section>
  );
}

function FactForm({
  idPrefix, value, onChange, onSave, onCancel, saving, saveLabel, error,
}: {
  idPrefix: string;
  value: FactDraft;
  onChange: (v: FactDraft) => void;
  onSave: () => void;
  onCancel: () => void;
  saving: boolean;
  saveLabel: string;
  error?: string | null;
}) {
  const empty = !value.achievement.trim();
  return (
    <form
      className="space-y-3 rounded-2xl border bg-card p-5"
      onSubmit={(e) => {
        e.preventDefault();
        if (!empty) onSave();
      }}
    >
      <div className="space-y-1.5">
        <Label htmlFor={`${idPrefix}-category`}>Kind</Label>
        <select
          id={`${idPrefix}-category`}
          value={value.category}
          onChange={(e) => onChange({ ...value, category: e.target.value })}
          className="block h-11 w-full rounded-md border border-input bg-background px-3 text-sm capitalize focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring sm:w-56"
        >
          {!FACT_CATEGORIES.includes(value.category) && <option value={value.category}>{value.category}</option>}
          {FACT_CATEGORIES.map((c) => <option key={c} value={c}>{c}</option>)}
        </select>
      </div>
      <div className="space-y-1.5">
        <Label htmlFor={`${idPrefix}-achievement`}>What you did, in your own words</Label>
        <Textarea id={`${idPrefix}-achievement`} rows={2} value={value.achievement} required
          onChange={(e) => onChange({ ...value, achievement: e.target.value })}
        />
      </div>
      <div className="grid gap-3 sm:grid-cols-2">
        <div className="space-y-1.5">
          <Label htmlFor={`${idPrefix}-metric`}>Number (optional)</Label>
          <Input id={`${idPrefix}-metric`} value={value.metric ?? ""} placeholder="e.g. 40% faster"
            onChange={(e) => onChange({ ...value, metric: e.target.value })}
          />
        </div>
        <div className="space-y-1.5">
          <Label htmlFor={`${idPrefix}-proof`}>Where (optional)</Label>
          <Input id={`${idPrefix}-proof`} value={value.proof ?? ""} placeholder="Role, project or company"
            onChange={(e) => onChange({ ...value, proof: e.target.value })}
          />
        </div>
      </div>
      <p className="text-xs text-muted-foreground">Only add a number you can back up — Maggie never makes one up.</p>
      {error && <Alert>{error}</Alert>}
      <div className="flex flex-wrap gap-2">
        <Button type="submit" className="h-11" disabled={saving || empty}>{saving ? "Saving…" : saveLabel}</Button>
        <Button type="button" variant="ghost" className="h-11" onClick={onCancel}>Cancel</Button>
      </div>
    </form>
  );
}

function FactRow({ fact, onDelete }: { fact: ResumeFact; onDelete: () => void }) {
  const queryClient = useQueryClient();
  const [editing, setEditing] = useState<FactDraft | null>(null);
  const save = useMutation({
    mutationFn: (changes: Partial<FactDraft>) => api.updateFact(fact.id, changes),
    onSuccess: () => {
      setEditing(null);
      queryClient.invalidateQueries({ queryKey: ["facts", fact.profile_id] });
    },
  });

  if (editing) {
    return (
      <li className="p-3">
        <FactForm
          idPrefix={`fact-${fact.id}`}
          value={editing}
          onChange={setEditing}
          saving={save.isPending}
          saveLabel="Save"
          error={save.isError ? errorText(save.error, "Couldn't save. Try again.") : null}
          onSave={() => {
            const changes = factChanges(fact, editing);
            if (Object.keys(changes).length === 0) setEditing(null);
            else save.mutate(changes);
          }}
          onCancel={() => { save.reset(); setEditing(null); }}
        />
      </li>
    );
  }

  return (
    <li className="flex flex-wrap items-start gap-3 px-5 py-4 sm:flex-nowrap">
      <span className="mt-0.5 shrink-0 rounded-md bg-accent px-2 py-0.5 text-xs font-semibold capitalize text-accent-foreground">
        {fact.category}
      </span>
      <div className="min-w-0 flex-1 space-y-1">
        <p className="leading-relaxed">{fact.achievement}</p>
        {(fact.metric || fact.proof) && (
          <p className="text-sm text-muted-foreground">{[fact.metric, fact.proof].filter(Boolean).join(" · ")}</p>
        )}
      </div>
      <div className="flex shrink-0 gap-1">
        <Button variant="ghost" className="h-11" aria-label={`Edit: ${fact.achievement}`} onClick={() => setEditing({ ...fact })}>
          Edit
        </Button>
        <Button variant="ghost" className="h-11 text-destructive" aria-label={`Delete: ${fact.achievement}`} onClick={onDelete}>
          Delete
        </Button>
      </div>
    </li>
  );
}

// ---------------------------------------------------------------- About you

function AboutSection({ profileId }: { profileId: string }) {
  const basicsQuery = useQuery({ queryKey: ["basics", profileId], queryFn: () => api.getBasics(profileId) });
  const [basics, setBasics] = useState<ApplicantBasics | null>(null);
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    if (basicsQuery.data && basics === null) setBasics(basicsQuery.data);
  }, [basicsQuery.data, basics]);

  const save = useMutation({
    mutationFn: (b: ApplicantBasics) => api.putBasics(profileId, b),
    onSuccess: (b) => { setBasics(b); setSaved(true); },
  });

  const errors = basics ? validateBasics(basics) : {};
  const set = (patch: Partial<ApplicantBasics>) => { setSaved(false); setBasics((b) => ({ ...b, ...patch })); };
  const orNull = (v: string) => (v.trim() === "" ? null : v);
  const links = basics?.network_profiles ?? [];
  const setLink = (i: number, url: string, network?: string) =>
    set({ network_profiles: links.map((p, j) => (j === i ? { ...p, url: orNull(url), network: network ?? p.network } : p)) });

  return (
    <section id="about" aria-labelledby="about-h" className="scroll-mt-24 space-y-6">
      <div className="space-y-1">
        <h2 id="about-h" className="text-2xl font-semibold">About you</h2>
        <p className="text-muted-foreground">What application forms ask for first. Leave a field blank rather than guess.</p>
      </div>
      {basicsQuery.isLoading && <Skeleton className="h-40 w-full rounded-2xl" />}
      {basicsQuery.isError && <Alert>{errorText(basicsQuery.error, "Couldn't load your details.")}</Alert>}
      {basics && (
        <form
          className="space-y-5 rounded-2xl border bg-card p-5"
          onSubmit={(e) => {
            e.preventDefault();
            if (Object.keys(errors).length === 0) save.mutate({ ...basics, country_code: basics.country_code?.trim().toUpperCase() || null });
          }}
        >
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="Full name" value={basics.full_name ?? ""} onChange={(v) => set({ full_name: orNull(v) })} error={errors.full_name} />
            <Field label="Phone" type="tel" inputMode="tel" value={basics.phone ?? ""} onChange={(v) => set({ phone: orNull(v) })} error={errors.phone} />
            <Field label="First name" value={basics.given_name ?? ""} onChange={(v) => set({ given_name: orNull(v) })}
              hint="Forms often ask first and last name separately. We never split your full name for you." />
            <Field label="Last name" value={basics.family_name ?? ""} onChange={(v) => set({ family_name: orNull(v) })} />
            <Field label="City" value={basics.city ?? ""} onChange={(v) => set({ city: orNull(v) })} />
            <Field label="Region / state" value={basics.region ?? ""} onChange={(v) => set({ region: orNull(v) })} />
            <Field label="Country code" value={basics.country_code ?? ""} onChange={(v) => set({ country_code: orNull(v) })}
              error={errors.country_code} hint="Two letters, e.g. US, IN, DE." />
            <Field label="Postal code" value={basics.postal_code ?? ""} onChange={(v) => set({ postal_code: orNull(v) })} />
            <Field label="Street address" value={basics.street_address ?? ""} onChange={(v) => set({ street_address: orNull(v) })} />
            <Field label="Website" type="url" inputMode="url" placeholder="https://" value={basics.website_url ?? ""}
              onChange={(v) => set({ website_url: orNull(v) })} error={errors.website_url} />
          </div>

          <fieldset className="space-y-3">
            <legend className="text-sm font-medium">Links</legend>
            {links.map((p, i) => (
              <div key={i} className="grid gap-2 sm:grid-cols-[10rem_1fr_auto] sm:items-start">
                <Field label="Site" value={p.network} onChange={(v) => setLink(i, p.url ?? "", v)} error={errors[`network_profiles.${i}.network`]} />
                <Field label="URL" type="url" inputMode="url" placeholder="https://" value={p.url ?? ""}
                  onChange={(v) => setLink(i, v)} error={errors[`network_profiles.${i}`]} />
                <Button type="button" variant="ghost" className="h-11 sm:mt-6" aria-label={`Remove ${p.network || "link"}`}
                  onClick={() => set({ network_profiles: links.filter((_, j) => j !== i) })}>
                  Remove
                </Button>
              </div>
            ))}
            <Button type="button" variant="outline" className="h-11"
              onClick={() => set({ network_profiles: [...links, { network: "LinkedIn", username: null, url: null }] })}>
              <PlusIcon aria-hidden="true" /> Add a link
            </Button>
          </fieldset>

          <Chips label="Work authorisation" values={basics.work_auth ?? []} onChange={(work_auth) => set({ work_auth })}
            hint="e.g. “EU citizen”, “US H-1B”. Forms ask; Maggie only answers with what you put here." placeholder="Add an authorisation" />

          <div aria-live="polite">
            {save.isError && <Alert>{errorText(save.error, "Couldn't save. Try again.")}</Alert>}
            {saved && <Saved>Saved. Future applications use these details.</Saved>}
          </div>
          <Button type="submit" className="h-11" disabled={save.isPending || Object.keys(errors).length > 0}>
            {save.isPending ? "Saving…" : "Save details"}
          </Button>
        </form>
      )}
    </section>
  );
}

// ---------------------------------------------------------------- Saved answers

function AnswersSection({ profileId }: { profileId: string }) {
  const queryClient = useQueryClient();
  const key = ["answers", profileId];
  const answersQuery = useQuery({ queryKey: key, queryFn: () => api.listAnswers(profileId) });
  const [error, setError] = useState<string | null>(null);
  const del = useMutation({
    mutationFn: (id: string) => api.deleteAnswer(profileId, id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: key }),
    onError: (err) => setError(errorText(err, "Couldn't delete that answer. Try again.")),
  });
  const answers = answersQuery.data ?? [];

  return (
    <section id="answers" aria-labelledby="answers-h" className="scroll-mt-24 space-y-6">
      <div className="space-y-1">
        <h2 id="answers-h" className="text-2xl font-semibold">Saved answers</h2>
        <p className="text-muted-foreground">
          Answers you gave to form questions. Maggie reuses them on the same question next time — change or remove any
          that no longer hold.
        </p>
      </div>
      <div aria-live="polite">{error && <Alert>{error}</Alert>}</div>
      {answersQuery.isLoading && <Skeleton className="h-24 w-full rounded-2xl" />}
      {answersQuery.isError && <Alert>{errorText(answersQuery.error, "Couldn't load your answers.")}</Alert>}
      {answersQuery.isSuccess && answers.length === 0 && (
        <p className="rounded-2xl border border-dashed px-6 py-8 text-center text-muted-foreground">
          No saved answers yet. When a form asks something only you can answer, your reply is kept here.
        </p>
      )}
      {answers.length > 0 && (
        <ul className="divide-y rounded-2xl border bg-card shadow-sm">
          {answers.map((a) => (
            <AnswerRow key={a.id} profileId={profileId} answer={a} deleting={del.isPending && del.variables === a.id}
              onDelete={() => { setError(null); del.mutate(a.id); }} />
          ))}
        </ul>
      )}
    </section>
  );
}

function AnswerRow({ profileId, answer, onDelete, deleting }: {
  profileId: string; answer: SavedAnswer; onDelete: () => void; deleting: boolean;
}) {
  const queryClient = useQueryClient();
  const [draft, setDraft] = useState<string | null>(null);
  const save = useMutation({
    mutationFn: (text: string) => api.saveAnswer(profileId, answer.question_text, text),
    onSuccess: () => { setDraft(null); queryClient.invalidateQueries({ queryKey: ["answers", profileId] }); },
  });
  const inputId = `answer-${answer.id}`;

  return (
    <li className="space-y-2 px-5 py-4">
      <p className="font-medium">{answer.question_text}</p>
      {draft === null ? (
        <>
          <p className="whitespace-pre-wrap leading-relaxed">{answer.answer_text}</p>
          <div className="flex flex-wrap items-center justify-between gap-2">
            <span className="text-sm text-muted-foreground">
              Used {answer.times_used} time{answer.times_used === 1 ? "" : "s"}
            </span>
            <div className="flex gap-1">
              <Button variant="ghost" className="h-11" aria-label={`Edit answer to: ${answer.question_text}`}
                onClick={() => setDraft(answer.answer_text)}>Edit</Button>
              <Button variant="ghost" className="h-11 text-destructive" disabled={deleting}
                aria-label={`Delete answer to: ${answer.question_text}`} onClick={onDelete}>
                {deleting ? "Deleting…" : "Delete"}
              </Button>
            </div>
          </div>
        </>
      ) : (
        <form className="space-y-2" onSubmit={(e) => { e.preventDefault(); if (draft.trim()) save.mutate(draft.trim()); }}>
          <Label htmlFor={inputId}>Your answer</Label>
          <Textarea id={inputId} rows={3} value={draft} required onChange={(e) => setDraft(e.target.value)} />
          {save.isError && <Alert>{errorText(save.error, "Couldn't save. Try again.")}</Alert>}
          <div className="flex gap-2">
            <Button type="submit" className="h-11" disabled={save.isPending || !draft.trim()}>{save.isPending ? "Saving…" : "Save"}</Button>
            <Button type="button" variant="ghost" className="h-11" onClick={() => { save.reset(); setDraft(null); }}>Cancel</Button>
          </div>
        </form>
      )}
    </li>
  );
}
