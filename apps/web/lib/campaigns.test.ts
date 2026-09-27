import { afterAll, afterEach, beforeAll, describe, expect, it } from "vitest";
import { http, HttpResponse } from "msw";
import { setupServer } from "msw/node";
import { ApiError, api } from "./api";
import { buildCampaignBody, emptyCampaignDraft } from "./onboarding";

const API_URL = "http://localhost:8000";
const server = setupServer();

beforeAll(() => server.listen({ onUnhandledRequest: "error" }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

describe("POST /campaigns", () => {
  it("posts exactly the agreed contract body", async () => {
    let received: unknown = null;
    server.use(
      http.post(`${API_URL}/campaigns`, async ({ request }) => {
        received = await request.json();
        return HttpResponse.json({ id: "c1", status: "draft" }, { status: 201 });
      }),
    );

    const body = buildCampaignBody(
      { roles: ["Backend Engineer", "Platform Engineer"], locations: ["Berlin"], remote_only: true, min_salary: null },
      { name: "Autumn search", sources: ["greenhouse", "lever"], min_match_score: 0.75, daily_cap: 5, auto_submit: true },
    );
    await api.createCampaign(body);

    expect(received).toEqual({
      name: "Autumn search",
      roles: ["Backend Engineer", "Platform Engineer"],
      locations: ["Berlin"],
      remote_only: true,
      sources: ["greenhouse", "lever"],
      min_match_score: 0.75,
      daily_cap: 5,
      auto_submit: true,
    });
  });

  it("sends the documented defaults when the user changes nothing", async () => {
    let received: Record<string, unknown> = {};
    server.use(
      http.post(`${API_URL}/campaigns`, async ({ request }) => {
        received = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json({ id: "c1" }, { status: 201 });
      }),
    );

    await api.createCampaign(
      buildCampaignBody({ roles: ["SRE"], locations: [], remote_only: true, min_salary: null }, emptyCampaignDraft()),
    );

    expect(received.min_match_score).toBe(0.7);
    expect(received.daily_cap).toBe(10);
    expect(received.auto_submit).toBe(false);
  });

  it("surfaces a 404 as an ApiError rather than resolving empty — the backend may not be merged yet", async () => {
    server.use(http.post(`${API_URL}/campaigns`, () => HttpResponse.json({ detail: "Not Found" }, { status: 404 })));

    await expect(
      api.createCampaign(
        buildCampaignBody({ roles: ["SRE"], locations: [], remote_only: true, min_salary: null }, emptyCampaignDraft()),
      ),
    ).rejects.toBeInstanceOf(ApiError);
  });

  it("runs a campaign and reads back its stats", async () => {
    server.use(
      http.post(`${API_URL}/campaigns/c1/run`, () => HttpResponse.json({ job_id: "job-9" })),
      http.get(`${API_URL}/campaigns/c1/stats`, () =>
        HttpResponse.json({
          applied_today: 2,
          daily_cap: 10,
          remaining_today: 8,
          total_applied: 14,
          last_run_at: "2026-09-26T10:00:00Z",
        }),
      ),
    );

    expect(await api.runCampaign("c1")).toEqual({ job_id: "job-9" });
    expect((await api.getCampaignStats("c1")).remaining_today).toBe(8);
  });
});

describe("PATCH /campaigns/{id}", () => {
  it("sends exactly the given body and returns the updated campaign", async () => {
    let method = "";
    let received: unknown = null;
    server.use(
      http.patch(`${API_URL}/campaigns/c1`, async ({ request }) => {
        method = request.method;
        received = await request.json();
        return HttpResponse.json({ id: "c1", status: "paused" });
      }),
    );

    const updated = await api.updateCampaign("c1", { status: "paused" });

    expect(method).toBe("PATCH");
    expect(received).toEqual({ status: "paused" });
    expect(updated.status).toBe("paused");
  });

  it("surfaces a 422 (e.g. an illegal status move) as an ApiError with the server's message", async () => {
    server.use(
      http.patch(`${API_URL}/campaigns/c1`, () =>
        HttpResponse.json({ detail: "Cannot move a archived campaign to active" }, { status: 422 }),
      ),
    );

    const err = await api.updateCampaign("c1", { status: "active" }).catch((e) => e);
    expect(err).toBeInstanceOf(ApiError);
    expect(err.status).toBe(422);
    expect(err.message).toBe("Cannot move a archived campaign to active");
  });
});
