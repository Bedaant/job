// The Today screen's decision logic, kept out of the page so it is testable
// without a DOM: time formatting, where each activity row leads, and the
// honest one-line summary.
import type { CampaignStatus, TodayCounts } from "./api";

/** Server timestamps are UTC; one without an offset must not be read as local time. */
export function parseUtc(iso: string): Date {
  return new Date(/(Z|[+-]\d\d:?\d\d)$/.test(iso) ? iso : `${iso}Z`);
}

// Intl emits a narrow no-break space before AM/PM in newer ICU builds.
const plain = (s: string) => s.replace(/ /g, " ");

const sameDay = (a: Date, b: Date, timeZone?: string) =>
  a.toLocaleDateString("en-CA", { timeZone }) === b.toLocaleDateString("en-CA", { timeZone });

/** Rows from the viewer's today vs earlier, order kept. */
export function splitToday<T extends { at: string }>(rows: T[], now = new Date(), timeZone?: string) {
  const today = rows.filter((r) => sameDay(parseUtc(r.at), now, timeZone));
  return { today, earlier: rows.filter((r) => !today.includes(r)) };
}

/** "2:14 PM" today, "Sep 25, 9:05 AM" on an earlier day. `timeZone` defaults to the browser's. */
export function formatWhen(iso: string, now = new Date(), timeZone?: string): string {
  const at = parseUtc(iso);
  const time = plain(at.toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit", timeZone }));
  if (sameDay(at, now, timeZone)) return time;
  return `${at.toLocaleDateString("en-US", { month: "short", day: "numeric", timeZone })}, ${time}`;
}

/** The daily limit counts per UTC day (a server-side rail), so say when that is locally. */
export function dailyLimitCaption(cap: number, now = new Date(), timeZone?: string): string {
  const nextUtcMidnight = new Date(Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), now.getUTCDate() + 1));
  const time = plain(nextUtcMidnight.toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit", timeZone }));
  return `Daily limit ${cap} · resets ${time} your time`;
}

export function greeting(now = new Date()): string {
  const h = now.getHours();
  if (h >= 5 && h < 12) return "Good morning";
  if (h >= 12 && h < 17) return "Good afternoon";
  return "Good evening";
}

export function activityHref(type: string): string {
  if (type === "match.new") return "/matches";
  if (type === "application.ready_for_review" || type === "application.needs_human") return "/review";
  return "/campaign";
}

export type HomeState = "no-campaign" | "not-started" | "paused" | "waiting" | "active";

export function homeState(status: CampaignStatus | undefined, activityCount: number): HomeState {
  if (!status || status === "archived") return "no-campaign";
  if (status === "draft") return "not-started";
  if (status === "paused") return "paused";
  return activityCount === 0 ? "waiting" : "active";
}

export function maggieLabel(status: CampaignStatus): string {
  return { active: "Applying", paused: "Paused", draft: "Not started", archived: "Finished" }[status];
}

const count = (n: number, one: string, many: string) => `${n} ${n === 1 ? one : many}`;
const needs = (n: number) => `${count(n, "application needs", "applications need")} you.`;

export function summaryLine(t: TodayCounts, status: CampaignStatus | undefined): string {
  if (!status || status === "archived") return "Set up a campaign and Maggie starts looking for you.";
  const tail = t.needs_you > 0 ? ` ${needs(t.needs_you)}` : "";
  if (status === "paused") return `Maggie is paused.${tail}`;
  if (status === "draft") return `Your campaign hasn't started yet.${tail}`;
  const sent = t.sent_today === 0 ? "Nothing sent yet today." : `${count(t.sent_today, "application", "applications")} sent today.`;
  return sent + tail;
}
