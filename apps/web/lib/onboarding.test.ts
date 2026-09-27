import { describe, expect, it } from "vitest";
import {
  STEPS,
  blankFact,
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
  category: "experience",
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
    expect(next[1].category).toBe("experience");
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

  it("rejects a category the backend does not know, keyed so it shows inline", () => {
    expect(validateFacts([{ ...fact("Led a team"), category: "" }])).toHaveProperty("0.category");
    expect(validateFacts([{ ...fact("Led a team"), category: "impact" }])).toHaveProperty("0.category");
    expect(validateFacts([{ ...fact("AWS SA"), category: "certification" }])).toEqual({});
  });
});

describe("adding facts by hand (parser failed or no resume)", () => {
  it("starts from a blank row that cannot be saved until the user writes it", () => {
    const row = blankFact();
    expect(row).toEqual({ category: "experience", achievement: "", proof: null, metric: null, tags: [] });
    expect(canAdvance("facts", { facts: [row], basics: {}, prefs: emptyPreferences(), campaign: emptyCampaignDraft() })).toBe(false);
  });

  it("continues once every hand-written row has a category and an achievement", () => {
    const facts = [{ ...blankFact(), achievement: "Shipped the billing rewrite" }, { ...blankFact(), category: "skill", achievement: "Go" }];
    expect(canAdvance("facts", { facts, basics: {}, prefs: emptyPreferences(), campaign: emptyCampaignDraft() })).toBe(true);
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
      "p1",
    );
    expect(Object.keys(body).sort()).toEqual(
      [
        "auto_submit",
        "daily_cap",
        "locations",
        "min_match_score",
        "name",
        "profile_id",
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
      "p1",
    );
    expect(body.tailoring_notes).toContain("120000");
  });

  it("trims and drops blank roles/locations", () => {
    const body = buildCampaignBody(
      { roles: ["  SRE  ", "", "  "], locations: ["  Berlin "], remote_only: false, min_salary: null },
      emptyCampaignDraft(),
      "p1",
    );
    expect(body.roles).toEqual(["SRE"]);
    expect(body.locations).toEqual(["Berlin"]);
  });
});

describe("errorText", () => {
  it("shows the API's own message, never a raw exception", async () => {
    const { errorText } = await import("./onboarding");
    const { ApiError } = await import("./api");
    expect(errorText(new ApiError(422, "Daily cap must be at least 1"))).toBe("Daily cap must be at least 1");
    expect(errorText(new TypeError("Failed to fetch"))).toBe(
      "We couldn't reach ApplyScout. Check your connection and try again.",
    );
    expect(errorText(undefined)).not.toMatch(/undefined|Error/);
  });
});

describe("facts are never re-posted (Back then Continue duplicated them)", () => {
  it("posts only facts not already saved, ignoring case and spacing", async () => {
    const { factsToPost } = await import("./onboarding");
    const saved = [fact("Cut p99 latency 40%")];
    const drafts = [fact("  cut p99  LATENCY 40% "), fact("Shipped billing")];
    expect(factsToPost(drafts, saved).map((f) => f.achievement)).toEqual(["Shipped billing"]);
    expect(factsToPost(saved, saved)).toEqual([]);
  });

  it("treats a changed metric as a new fact", async () => {
    const { factsToPost } = await import("./onboarding");
    expect(factsToPost([{ ...fact("x"), metric: "5%" }], [fact("x")])).toHaveLength(1);
  });
});

describe("wizard draft survives a refresh (sessionStorage, per profile)", () => {
  function memoryStorage() {
    const m = new Map<string, string>();
    return {
      getItem: (k: string) => m.get(k) ?? null,
      setItem: (k: string, v: string) => void m.set(k, v),
      removeItem: (k: string) => void m.delete(k),
      dump: m,
    };
  }

  it("round-trips the draft under a per-profile key and never stores a token", async () => {
    const { saveDraft, loadDraft } = await import("./onboarding");
    const s = memoryStorage();
    const draft = { step: "preferences" as const, facts: [fact("a")], basics: {}, prefs: emptyPreferences(), campaign: emptyCampaignDraft() };
    saveDraft("p1", draft, s);
    expect(loadDraft("p1", s)).toEqual(draft);
    expect(loadDraft("p2", s)).toBeNull();
    expect([...s.dump.values()].join()).not.toMatch(/token|Bearer/i);
  });

  it("returns null on corrupt data or a throwing storage, and saving never throws", async () => {
    const { saveDraft, loadDraft, clearDraft } = await import("./onboarding");
    const s = memoryStorage();
    s.setItem("applyscout.onboarding.p1", "{not json");
    expect(loadDraft("p1", s)).toBeNull();
    const boom = () => {
      throw new Error("denied");
    };
    const broken = { getItem: boom, setItem: boom, removeItem: boom };
    expect(loadDraft("p1", broken)).toBeNull();
    expect(() =>
      saveDraft("p1", { step: "resume", facts: [], basics: {}, prefs: emptyPreferences(), campaign: emptyCampaignDraft() }, broken),
    ).not.toThrow();
    expect(() => clearDraft("p1", broken)).not.toThrow();
  });
});

describe("starting step comes from the server", () => {
  it("a campaign already exists → set up, never a second campaign", async () => {
    const { startingStep } = await import("./onboarding");
    expect(startingStep({ draftStep: "campaign", factCount: 3, campaignCount: 1 })).toBe("already-set-up");
  });

  it("saved facts skip to preferences; a later draft step wins; done is never restored", async () => {
    const { startingStep } = await import("./onboarding");
    expect(startingStep({ draftStep: null, factCount: 0, campaignCount: 0 })).toBe("resume");
    expect(startingStep({ draftStep: null, factCount: 2, campaignCount: 0 })).toBe("preferences");
    expect(startingStep({ draftStep: "facts", factCount: 0, campaignCount: 0 })).toBe("facts");
    expect(startingStep({ draftStep: "campaign", factCount: 2, campaignCount: 0 })).toBe("campaign");
    expect(startingStep({ draftStep: "done", factCount: 2, campaignCount: 0 })).toBe("preferences");
  });
});

describe("sources come from GET /sources", () => {
  it("defaults to every enabled source and keeps disabled ones out", async () => {
    const { defaultSources } = await import("./onboarding");
    const list = [
      { id: "remoteok", label: "Remote OK", note: "", enabled: true, reason: null, job_count: 3 },
      { id: "jobspy_google", label: "Google Jobs", note: "", enabled: false, reason: "Currently returns no results.", job_count: 0 },
    ];
    expect(defaultSources(list)).toEqual(["remoteok"]);
  });
});
