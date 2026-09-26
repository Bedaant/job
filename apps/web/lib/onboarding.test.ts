import { describe, expect, it } from "vitest";
import {
  STEPS,
  buildCampaignBody,
  canAdvance,
  editFact,
  emptyCampaignDraft,
  emptyPreferences,
  validateBasics,
  validateCampaign,
  validateFacts,
  validatePreferences,
} from "./onboarding";
import type { FactDraft } from "./api";

const fact = (achievement: string): FactDraft => ({
  category: "impact",
  achievement,
  proof: null,
  metric: null,
  tags: [],
});

describe("step gating", () => {
  it("does not advance past resume with no parsed facts", () => {
    expect(canAdvance("resume", { facts: [], basics: {}, prefs: emptyPreferences(), campaign: emptyCampaignDraft() })).toBe(false);
  });

  it("advances past resume once at least one fact is parsed", () => {
    expect(
      canAdvance("resume", { facts: [fact("Cut p99 latency 40%")], basics: {}, prefs: emptyPreferences(), campaign: emptyCampaignDraft() }),
    ).toBe(true);
  });

  it("does not advance past facts when a fact was emptied", () => {
    expect(
      canAdvance("facts", { facts: [fact("   ")], basics: {}, prefs: emptyPreferences(), campaign: emptyCampaignDraft() }),
    ).toBe(false);
  });

  it("does not advance past preferences without a role", () => {
    const prefs = { ...emptyPreferences(), locations: ["Berlin"] };
    expect(canAdvance("preferences", { facts: [fact("x")], basics: {}, prefs, campaign: emptyCampaignDraft() })).toBe(false);
  });

  it("advances past preferences with a role and remote_only instead of a location", () => {
    const prefs = { ...emptyPreferences(), roles: ["Backend Engineer"], remote_only: true };
    expect(canAdvance("preferences", { facts: [fact("x")], basics: {}, prefs, campaign: emptyCampaignDraft() })).toBe(true);
  });

  it("has a linear, ordered step list ending on done", () => {
    expect(STEPS[0]).toBe("resume");
    expect(STEPS[STEPS.length - 1]).toBe("done");
  });
});

describe("facts editor round-trip", () => {
  it("replaces only the edited fact and keeps the rest identical", () => {
    const facts = [fact("first"), fact("second"), fact("third")];
    const next = editFact(facts, 1, { achievement: "second, corrected", metric: "12%" });

    expect(next[1].achievement).toBe("second, corrected");
    expect(next[1].metric).toBe("12%");
    expect(next[1].category).toBe("impact");
    expect(next[0]).toBe(facts[0]);
    expect(next[2]).toBe(facts[2]);
    expect(facts[1].achievement).toBe("second"); // original not mutated
  });

  it("reports the index of an emptied fact so the error can be shown inline", () => {
    expect(validateFacts([fact("ok"), fact("")])).toEqual({ 1: "A fact cannot be empty — correct it or remove it." });
    expect(validateFacts([fact("ok")])).toEqual({});
  });

  it("requires at least one fact", () => {
    expect(validateFacts([])).toHaveProperty("_");
  });
});

describe("basics validation mirrors the server's ApplicantBasics validators", () => {
  it("accepts an all-null basics (a resume genuinely may not state a phone)", () => {
    expect(validateBasics({})).toEqual({});
  });

  it("rejects placeholder names", () => {
    expect(validateBasics({ full_name: "John Doe" })).toHaveProperty("full_name");
  });

  it("rejects the reserved fictional 555-01XX phone range", () => {
    expect(validateBasics({ phone: "+1 (415) 555-0142" })).toHaveProperty("phone");
  });

  it("rejects a phone with too few digits", () => {
    expect(validateBasics({ phone: "12345" })).toHaveProperty("phone");
  });

  it("rejects a scheme-less website url", () => {
    expect(validateBasics({ website_url: "example.com" })).toHaveProperty("website_url");
    expect(validateBasics({ website_url: "https://example.com" })).toEqual({});
  });

  it("rejects a non-alpha2 country code", () => {
    expect(validateBasics({ country_code: "USA" })).toHaveProperty("country_code");
    expect(validateBasics({ country_code: "us" })).toEqual({});
  });
});

describe("campaign validation", () => {
  it("requires a name and at least one source", () => {
    expect(validateCampaign({ ...emptyCampaignDraft(), name: "" })).toHaveProperty("name");
    expect(validateCampaign({ ...emptyCampaignDraft(), sources: [] })).toHaveProperty("sources");
  });

  it("bounds min_match_score to 0..1 and daily_cap to 1..50", () => {
    expect(validateCampaign({ ...emptyCampaignDraft(), min_match_score: 1.4 })).toHaveProperty("min_match_score");
    expect(validateCampaign({ ...emptyCampaignDraft(), daily_cap: 0 })).toHaveProperty("daily_cap");
    expect(validateCampaign({ ...emptyCampaignDraft(), daily_cap: 999 })).toHaveProperty("daily_cap");
  });

  it("accepts the defaults", () => {
    expect(validateCampaign(emptyCampaignDraft())).toEqual({});
  });
});

describe("buildCampaignBody", () => {
  it("emits exactly the documented contract keys", () => {
    const body = buildCampaignBody(
      { roles: ["Backend Engineer"], locations: ["Berlin"], remote_only: false, min_salary: null },
      emptyCampaignDraft(),
    );
    expect(Object.keys(body).sort()).toEqual(
      [
        "auto_submit",
        "daily_cap",
        "locations",
        "min_match_score",
        "name",
        "remote_only",
        "roles",
        "sources",
      ].sort(),
    );
  });

  it("carries the salary floor through tailoring_notes, the only contract field that can hold it", () => {
    const body = buildCampaignBody(
      { roles: ["SRE"], locations: [], remote_only: true, min_salary: 120000 },
      emptyCampaignDraft(),
    );
    expect(body.tailoring_notes).toContain("120000");
  });

  it("trims and drops blank roles/locations", () => {
    const body = buildCampaignBody(
      { roles: ["  SRE  ", "", "  "], locations: ["  Berlin "], remote_only: false, min_salary: null },
      emptyCampaignDraft(),
    );
    expect(body.roles).toEqual(["SRE"]);
    expect(body.locations).toEqual(["Berlin"]);
  });
});
