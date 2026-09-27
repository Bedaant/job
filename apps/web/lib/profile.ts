// Profile page logic, kept out of the component so it is testable without a DOM.
import type { FactDraft, ResumeFact } from "./api";

export const UNDO_MS = 5000;

const OPTIONAL = ["proof", "metric"] as const;

/** Only what the user changed — an unchanged achievement must not trigger a re-embed. */
export function factChanges(original: ResumeFact, edited: FactDraft): Partial<FactDraft> {
  const changes: Partial<FactDraft> = {};
  const achievement = edited.achievement.trim();
  if (achievement !== original.achievement) changes.achievement = achievement;
  if (edited.category !== original.category) changes.category = edited.category;
  for (const key of OPTIONAL) {
    const value = edited[key]?.trim() || null;
    if (value !== (original[key] || null)) changes[key] = value;
  }
  return changes;
}

/** Deletes wait UNDO_MS so Undo needs no restore endpoint; flush() on leaving the page. */
export function undoableDeletes(commit: (id: string) => void, ms = UNDO_MS) {
  const timers = new Map<string, ReturnType<typeof setTimeout>>();
  const run = (id: string) => {
    clearTimeout(timers.get(id));
    timers.delete(id);
    commit(id);
  };
  return {
    schedule: (id: string) => timers.set(id, setTimeout(() => run(id), ms)),
    undo: (id: string) => {
      clearTimeout(timers.get(id));
      timers.delete(id);
    },
    flush: () => [...timers.keys()].forEach(run),
  };
}
