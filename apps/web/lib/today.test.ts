import { afterAll, afterEach, beforeAll, describe, expect, it } from "vitest";
import { http, HttpResponse } from "msw";
import { setupServer } from "msw/node";
import { api } from "./api";
import {
  activityHref,
  activityLink,
  dailyLimitCaption,
  unconfirmedAction,
  formatWhen,
  greeting,
  homeState,
  maggieLabel,
  parseUtc,
  splitToday,
  summaryLine,
} from "./today";

const API_URL = "http://localhost:8000";
const server = setupServer();
beforeAll(() => server.listen({ onUnhandledRequest: "error" }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

describe("parseUtc", () => {
  it("reads an offset-less server timestamp as UTC, not local time", () => {
    expect(parseUtc("2026-09-27T14:14:00").toISOString()).toBe("2026-09-27T14:14:00.000Z");
    expect(parseUtc("2026-09-27T14:14:00Z").toISOString()).toBe("2026-09-27T14:14:00.000Z");
    expect(parseUtc("2026-09-27T14:14:00+00:00").toISOString()).toBe("2026-09-27T14:14:00.000Z");
  });
});

describe("formatWhen", () => {
  const now = new Date("2026-09-27T18:00:00Z");
  it("shows a plain clock time for today", () => {
    expect(formatWhen("2026-09-27T14:14:00Z", now, "UTC")).toBe("2:14 PM");
  });
  it("adds the date for an earlier day", () => {
    expect(formatWhen("2026-09-25T09:05:00Z", now, "UTC")).toBe("Sep 25, 9:05 AM");
  });
  it("uses the given time zone's day, not UTC's", () => {
    // 20:00 UTC on the 26th is already the 27th in Kolkata (+5:30).
    expect(formatWhen("2026-09-26T20:00:00Z", now, "Asia/Kolkata")).toBe("1:30 AM");
  });
});

describe("splitToday", () => {
  it("separates today's rows from earlier ones in the viewer's time zone, keeping order", () => {
    const now = new Date("2026-09-27T18:00:00Z");
    const rows = [
      { at: "2026-09-27T17:00:00Z", n: 1 },
      { at: "2026-09-26T20:00:00", n: 2 }, // 27th in Kolkata
      { at: "2026-09-26T10:00:00Z", n: 3 },
    ];
    const { today, earlier } = splitToday(rows, now, "Asia/Kolkata");
    expect(today.map((r) => r.n)).toEqual([1, 2]);
    expect(earlier.map((r) => r.n)).toEqual([3]);
  });
});

describe("greeting", () => {
  it("follows the hour", () => {
    expect(greeting(new Date(2026, 8, 27, 8))).toBe("Good morning");
    expect(greeting(new Date(2026, 8, 27, 13))).toBe("Good afternoon");
    expect(greeting(new Date(2026, 8, 27, 19))).toBe("Good evening");
    expect(greeting(new Date(2026, 8, 27, 2))).toBe("Good evening");
  });
});

describe("activityHref", () => {
  it("links each row to where the user can act on it", () => {
    expect(activityHref("match.new")).toBe("/matches");
    expect(activityHref("application.ready_for_review")).toBe("/review");
    expect(activityHref("application.needs_human")).toBe("/review");
    expect(activityHref("application.submitted")).toBe("/campaign");
    expect(activityHref("application.failed")).toBe("/campaign");
    expect(activityHref("application.approved")).toBe("/campaign");
    expect(activityHref("something.unknown")).toBe("/campaign");
    // Skips are campaign settings (score, limit, roles): change them there.
    expect(activityHref("campaign.skipped")).toBe("/campaign");
  });
});

describe("dailyLimitCaption", () => {
  const now = new Date("2026-09-27T18:00:00Z");
  it("says when the UTC-day limit resets, in the viewer's own clock", () => {
    expect(dailyLimitCaption(10, now, "Asia/Kolkata")).toBe("Daily limit 10 · resets 5:30 AM your time");
    expect(dailyLimitCaption(3, now, "UTC")).toBe("Daily limit 3 · resets 12:00 AM your time");
  });
});

describe("homeState", () => {
  it("is honest about why nothing is happening", () => {
    expect(homeState(undefined, 0)).toBe("no-campaign");
    expect(homeState("draft", 0)).toBe("not-started");
    expect(homeState("paused", 5)).toBe("paused");
    expect(homeState("active", 0)).toBe("waiting");
    expect(homeState("active", 3)).toBe("active");
  });
});

describe("maggieLabel", () => {
  it("names what Maggie is doing", () => {
    expect(maggieLabel("active")).toBe("Applying");
    expect(maggieLabel("paused")).toBe("Paused");
    expect(maggieLabel("draft")).toBe("Not started");
  });
});

describe("summaryLine", () => {
  const t = { sent_today: 0, needs_you: 0, new_matches_today: 0 };
  it("says so when nothing is set up", () => {
    expect(summaryLine(t, undefined)).toBe("Set up a campaign and Maggie starts looking for you.");
  });
  it("says nothing goes out while paused", () => {
    expect(summaryLine({ ...t, needs_you: 2 }, "paused")).toBe("Maggie is paused. 2 applications need you.");
  });
  it("counts with correct plurals", () => {
    expect(summaryLine(t, "active")).toBe("Nothing sent yet today.");
    expect(summaryLine({ ...t, sent_today: 1, needs_you: 1 }, "active")).toBe(
      "1 application sent today. 1 application needs you.",
    );
    expect(summaryLine({ ...t, sent_today: 3 }, "active")).toBe("3 applications sent today.");
  });
  it("never lets an unconfirmed send read as a plain success", () => {
    expect(summaryLine({ ...t, sent_today: 3, unconfirmed_today: 1 }, "active")).toBe(
      "3 applications sent today, 1 not confirmed yet.",
    );
    expect(summaryLine({ ...t, sent_today: 2, unconfirmed_today: 2, needs_you: 1 }, "active")).toBe(
      "2 applications sent today, 2 not confirmed yet. 1 application needs you.",
    );
  });
});

describe("unconfirmed sends", () => {
  const row = {
    id: 1,
    type: "application.unconfirmed",
    at: "2026-09-27T14:00:00Z",
    title: "Sent to Stripe — couldn't confirm it went through",
    job: { title: "SRE", company: "Stripe" },
    apply_url: "https://jobs.lever.co/stripe/1",
  };
  it("tells the user what to do, naming the company", () => {
    expect(unconfirmedAction("Stripe")).toBe("Check your email for a confirmation from Stripe, or open the form.");
    expect(unconfirmedAction(undefined)).toBe("Check your email for a confirmation, or open the form.");
  });
  it("links the row to the form itself, in a new tab", () => {
    expect(activityLink(row)).toEqual({ href: "https://jobs.lever.co/stripe/1", external: true });
    expect(activityLink({ ...row, apply_url: null })).toEqual({ href: "/campaign", external: false });
    expect(activityLink({ ...row, type: "application.needs_human", apply_url: null })).toEqual({
      href: "/review",
      external: false,
    });
  });
  it("never offers a non-http link", () => {
    expect(activityLink({ ...row, apply_url: "javascript:alert(1)" })).toEqual({ href: "/campaign", external: false });
  });
});

describe("GET /activity and /today", () => {
  it("asks for a bounded page of activity and returns it as-is", async () => {
    let url = "";
    server.use(
      http.get(`${API_URL}/activity`, ({ request }) => {
        url = request.url;
        return HttpResponse.json([{ id: 1, type: "match.new", at: "2026-09-27T10:00:00Z", title: "New match" }]);
      }),
    );
    const items = await api.getActivity(20);
    expect(new URL(url).searchParams.get("limit")).toBe("20");
    expect(items[0].title).toBe("New match");
  });

  it("reads the three counters over the viewer's local day", async () => {
    const tzs: (string | null)[] = [];
    server.use(
      http.get(`${API_URL}/today`, ({ request }) => {
        tzs.push(new URL(request.url).searchParams.get("tz"));
        return HttpResponse.json({ sent_today: 1, needs_you: 2, new_matches_today: 3 });
      }),
    );
    expect(await api.getToday()).toEqual({ sent_today: 1, needs_you: 2, new_matches_today: 3 });
    await api.getToday("Asia/Kolkata");
    expect(tzs).toEqual([Intl.DateTimeFormat().resolvedOptions().timeZone, "Asia/Kolkata"]);
  });
});
