import { afterAll, afterEach, beforeAll, describe, expect, it } from "vitest";
import { http, HttpResponse } from "msw";
import { setupServer } from "msw/node";
import { api } from "./api";
import {
  COLUMNS,
  columnOf,
  groupPipeline,
  keywordRows,
  moveOptions,
  statusLabel,
} from "./applications";

const API_URL = "http://localhost:8000";
const server = setupServer();
beforeAll(() => server.listen({ onUnhandledRequest: "error" }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

const row = (id: string, status: string) => ({ id, status });

describe("columnOf", () => {
  it("puts every sent status in exactly one column", () => {
    expect(columnOf("applied")).toBe("applied");
    expect(columnOf("submitted_unconfirmed")).toBe("applied");
    expect(columnOf("submitting")).toBe("applied");
    expect(columnOf("recruiter")).toBe("heard_back");
    expect(columnOf("oa")).toBe("heard_back");
    expect(columnOf("interview")).toBe("interviewing");
    expect(columnOf("offer")).toBe("offer");
    expect(columnOf("rejected")).toBe("closed");
    expect(columnOf("withdrawn")).toBe("closed");
  });
  it("leaves not-yet-sent applications out of the pipeline (they live in Review)", () => {
    for (const s of ["saved", "ready_for_review", "approved", "dismissed"]) expect(columnOf(s)).toBeNull();
  });
});

describe("groupPipeline", () => {
  it("groups by column, keeps order, and counts what is still before sending", () => {
    const g = groupPipeline([
      row("a", "applied"), row("b", "interview"), row("c", "ready_for_review"),
      row("d", "applied"), row("e", "rejected"), row("f", "saved"),
    ]);
    expect(g.columns.applied.map((r) => r.id)).toEqual(["a", "d"]);
    expect(g.columns.interviewing.map((r) => r.id)).toEqual(["b"]);
    expect(g.columns.closed.map((r) => r.id)).toEqual(["e"]);
    expect(g.columns.offer).toEqual([]);
    expect(g.notSent).toBe(2);
  });
  it("names the columns the way the user thinks of them", () => {
    expect(COLUMNS.map((c) => c.title)).toEqual(["Applied", "Heard back", "Interviewing", "Offer", "Closed"]);
  });
});

describe("statusLabel", () => {
  it("says 'Couldn't confirm' for a send the employer never confirmed", () => {
    expect(statusLabel("submitted_unconfirmed")).toBe("Couldn't confirm");
    expect(statusLabel("oa")).toBe("Online assessment");
    expect(statusLabel("recruiter")).toBe("Recruiter reached out");
  });
});

describe("moveOptions", () => {
  it("offers every other tracker status, never the current one", () => {
    const opts = moveOptions("applied").map((o) => o.status);
    expect(opts).not.toContain("applied");
    expect(opts).toEqual(expect.arrayContaining(["recruiter", "oa", "interview", "offer", "rejected", "withdrawn"]));
  });
  it("lets an unconfirmed send be confirmed as applied", () => {
    expect(moveOptions("submitted_unconfirmed")[0]).toEqual({ status: "applied", label: "I've confirmed it was sent" });
  });
});

describe("keywordRows", () => {
  it("lists matched, reworded and left-out keywords with plain labels", () => {
    expect(keywordRows({ matched: ["python"], reworded: ["kubernetes"], missing: ["terraform"] })).toEqual([
      { kind: "matched", label: "Already in your facts", keywords: ["python"] },
      { kind: "reworded", label: "Reworded to the job's wording", keywords: ["kubernetes"] },
      { kind: "missing", label: "Not in your facts — left out", keywords: ["terraform"] },
    ]);
  });
  it("drops empty groups", () => {
    expect(keywordRows({ matched: [], reworded: [], missing: ["x"] }).map((r) => r.kind)).toEqual(["missing"]);
  });
});

describe("API contract", () => {
  it("lists applications with their job and fetches one application's detail", async () => {
    server.use(
      http.get(`${API_URL}/applications`, ({ request }) => {
        expect(new URL(request.url).searchParams.get("profile_id")).toBe("p1");
        return HttpResponse.json([{ id: "a1", status: "applied", job: { title: "SRE", company: "Stripe" } }]);
      }),
      http.get(`${API_URL}/applications/a1`, () => HttpResponse.json({ id: "a1", status: "applied" })),
    );
    expect((await api.listApplications("p1"))[0].job.company).toBe("Stripe");
    expect((await api.getApplication("a1")).id).toBe("a1");
  });

  it("moves a card with a PATCH of its status", async () => {
    let body: unknown;
    server.use(
      http.patch(`${API_URL}/applications/a1`, async ({ request }) => {
        body = await request.json();
        return HttpResponse.json({ id: "a1", status: "interview" });
      }),
    );
    await api.setApplicationStatus("a1", "interview");
    expect(body).toEqual({ status: "interview" });
  });

  it("saves / dismisses a match and prepares one", async () => {
    let patched: unknown;
    server.use(
      http.patch(`${API_URL}/matches/m1`, async ({ request }) => {
        patched = await request.json();
        return HttpResponse.json({ id: "m1", state: "dismissed" });
      }),
      http.post(`${API_URL}/matches/m1/prepare`, () =>
        HttpResponse.json({ application_id: "a9", status: "saved", queued: true }),
      ),
    );
    await api.setMatchState("m1", "dismissed");
    expect(patched).toEqual({ state: "dismissed" });
    expect(await api.prepareMatch("m1")).toEqual({ application_id: "a9", status: "saved", queued: true });
  });

  it("surfaces a queue outage as an error the page can show", async () => {
    server.use(
      http.post(`${API_URL}/matches/m1/prepare`, () =>
        HttpResponse.json({ detail: "Maggie couldn't start preparing this one right now." }, { status: 503 }),
      ),
    );
    await expect(api.prepareMatch("m1")).rejects.toThrow("couldn't start preparing");
  });
});
