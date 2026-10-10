import { describe, expect, it } from "vitest";
import type { Campaign } from "./api";
import { buildCampaignPatch, formFromCampaign, statusView, validateCampaignForm } from "./campaign-form";

const campaign: Campaign = {
  id: "c1",
  profile_id: "p1",
  name: "Autumn search",
  status: "active",
  roles: ["Backend Engineer"],
  locations: ["Berlin"],
  remote_only: false,
  sources: ["greenhouse"],
  min_match_score: 0.7,
  daily_cap: 10,
  auto_submit: false,
  include_older_postings: false,
  tailoring_notes: undefined,
  created_at: "2026-09-27T00:00:00Z",
  updated_at: "2026-09-27T00:00:00Z",
  last_run_at: null,
};

describe("formFromCampaign", () => {
  it("copies the editable settings and turns a missing/null note into an empty string", () => {
    expect(formFromCampaign({ ...campaign, tailoring_notes: null as unknown as string })).toEqual({
      roles: ["Backend Engineer"],
      locations: ["Berlin"],
      remote_only: false,
      min_match_score: 0.7,
      daily_cap: 10,
      auto_submit: false,
      include_older_postings: false,
      tailoring_notes: "",
    });
  });
});

describe("older postings switch", () => {
  it("is sent only when the user flips it", () => {
    const base = formFromCampaign(campaign);
    expect(buildCampaignPatch(base, { ...base, include_older_postings: true })).toEqual({ include_older_postings: true });
  });
});

describe("buildCampaignPatch", () => {
  const base = formFromCampaign(campaign);

  it("is empty when nothing changed — that is what keeps Save disabled", () => {
    expect(buildCampaignPatch(base, { ...base })).toEqual({});
  });

  it("contains only the fields that changed", () => {
    expect(buildCampaignPatch(base, { ...base, daily_cap: 5, auto_submit: true })).toEqual({
      daily_cap: 5,
      auto_submit: true,
    });
  });

  it("compares lists by value, not by reference", () => {
    expect(buildCampaignPatch(base, { ...base, roles: ["Backend Engineer"] })).toEqual({});
    expect(buildCampaignPatch(base, { ...base, roles: ["Backend Engineer", "SRE"] })).toEqual({
      roles: ["Backend Engineer", "SRE"],
    });
  });

  it("trims notes, treats whitespace-only edits as no change, and sends '' to clear a note", () => {
    expect(buildCampaignPatch(base, { ...base, tailoring_notes: "   " })).toEqual({});
    expect(buildCampaignPatch(base, { ...base, tailoring_notes: "  Keep it short " })).toEqual({
      tailoring_notes: "Keep it short",
    });
    const withNote = { ...base, tailoring_notes: "Keep it short" };
    // The API drops nulls (exclude_none), so clearing has to be an empty string.
    expect(buildCampaignPatch(withNote, { ...withNote, tailoring_notes: "" })).toEqual({ tailoring_notes: "" });
  });
});

describe("validateCampaignForm", () => {
  const base = formFromCampaign(campaign);

  it("accepts the campaign as approved", () => {
    expect(validateCampaignForm(base)).toEqual({});
  });

  it("flags each bad field by name so the error lands next to its input", () => {
    const errors = validateCampaignForm({ ...base, roles: [], locations: [], remote_only: false, daily_cap: 0, min_match_score: 1.5 });
    expect(Object.keys(errors).sort()).toEqual(["daily_cap", "locations", "min_match_score", "roles"]);
  });

  it("accepts remote-only in place of a location", () => {
    expect(validateCampaignForm({ ...base, locations: [], remote_only: true })).toEqual({});
  });
});

describe("statusView", () => {
  it("active: says Maggie is applying and offers Pause", () => {
    const v = statusView("active");
    expect(v.headline).toBe("Maggie is applying");
    expect(v.tone).toBe("success");
    expect(v.action).toEqual({ label: "Pause", next: "paused" });
  });

  it("paused: says nothing will be sent and offers Resume", () => {
    const v = statusView("paused");
    expect(v.headline).toBe("Nothing will be sent until you resume");
    expect(v.tone).toBe("warning");
    expect(v.action).toEqual({ label: "Resume", next: "active" });
  });

  it("draft: offers Start, which moves it to active", () => {
    expect(statusView("draft").action).toEqual({ label: "Start", next: "active" });
  });

  it("archived is terminal: no action", () => {
    expect(statusView("archived").action).toBeNull();
  });
});
