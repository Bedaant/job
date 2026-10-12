// P0 #5: StepDone works without the extension. No jsdom here (vitest.config.mts),
// so the component is rendered to static HTML with react-dom/server and inspected as text.
import { describe, expect, it } from "vitest";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { StepDone } from "@/components/onboarding/StepDone";
import { firstMatchesState } from "./onboarding";
import type { Campaign, CampaignStats, Match } from "./api";

const campaign = {
  id: "c1",
  profile_id: "p1",
  name: "My job search",
  roles: ["Data Analyst"],
  locations: ["Bengaluru"],
  remote_only: false,
  sources: ["remotive"],
  min_match_score: 0.7,
  daily_cap: 10,
  auto_submit: false,
  status: "active",
  created_at: "2026-10-12T00:00:00",
  updated_at: "2026-10-12T00:00:00",
  last_run_at: null,
} as Campaign;

const stats = (last_run_at: string | null): CampaignStats => ({
  applied_today: 0,
  daily_cap: 10,
  remaining_today: 10,
  total_applied: 0,
  last_run_at,
});

function render({ statsData, matches }: { statsData?: CampaignStats; matches?: Match[] } = {}) {
  const client = new QueryClient();
  if (statsData) client.setQueryData(["campaign-stats", campaign.id], statsData);
  if (matches) client.setQueryData(["matches", "p1"], matches);
  return renderToStaticMarkup(
    createElement(QueryClientProvider, { client }, createElement(StepDone, { campaign, profileId: "p1", started: true })),
  );
}

/** The opening tag of the <section> labelled by `id`. */
const sectionTag = (html: string, id: string) => html.match(new RegExp(`<section[^>]*aria-labelledby="${id}"[^>]*>`))?.[0];

describe("StepDone without the extension", () => {
  it("shows the Assisted send path at every width, phone included", () => {
    const html = render();
    const assisted = sectionTag(html, "assisted-heading");
    expect(assisted).toBeDefined();
    expect(assisted).not.toMatch(/\bhidden\b/); // no breakpoint hides it at 390px
    expect(html).toContain('href="/review#ready-to-send"');
  });

  it("keeps the extension to computers and gives no developer install steps", () => {
    const html = render();
    const extension = sectionTag(html, "extension-heading");
    expect(extension).toMatch(/[" ]hidden[" ]/); // not shown below md (phones)
    expect(extension).toMatch(/[" ]md:block[" ]/);
    for (const banned of ["chrome://", "Developer mode", "developer mode", "Load unpacked", "apps/extension/dist"]) {
      expect(html).not.toContain(banned);
    }
  });

  it("says Maggie is searching while the first run is in flight", () => {
    const html = render({ statsData: stats(null), matches: [] });
    expect(html).toContain("Searching for your matches");
  });

  it("lists the first matches once they land", () => {
    const match = {
      id: "m1",
      job: { title: "Data Analyst", company: "Acme", location: "Bengaluru" },
      score: 82,
    } as unknown as Match;
    const html = render({ statsData: stats("2026-10-12T00:00:00"), matches: [match] });
    expect(html).toContain("Data Analyst");
    expect(html).not.toContain("Searching for your matches");
  });
});

describe("firstMatchesState", () => {
  it("is loading until matches load", () => expect(firstMatchesState(true, undefined, null)).toBe("loading"));
  it("is found once there is a match", () => expect(firstMatchesState(true, 1, null)).toBe("found"));
  it("is searching while a started campaign has never finished a run", () =>
    expect(firstMatchesState(true, 0, null)).toBe("searching"));
  it("is none after the first run, or when the run never started", () => {
    expect(firstMatchesState(true, 0, "2026-10-12T00:00:00")).toBe("none");
    expect(firstMatchesState(false, 0, null)).toBe("none");
  });
});
