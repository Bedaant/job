import { afterAll, afterEach, beforeAll, describe, expect, it } from "vitest";
import { http, HttpResponse } from "msw";
import { setupServer } from "msw/node";
import { api } from "./api";

const API_URL = "http://localhost:8000";
const server = setupServer();

beforeAll(() => server.listen({ onUnhandledRequest: "error" }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

describe("similar roles", () => {
  it("lists near misses for the profile", async () => {
    let url = "";
    server.use(
      http.get(`${API_URL}/similar-jobs`, ({ request }) => {
        url = request.url;
        return HttpResponse.json([{ role: "Brand Head", job: { id: "j1", title: "Head of Marketing" } }]);
      }),
    );
    const rows = await api.listSimilarJobs("p1");
    expect(new URL(url).searchParams.get("profile_id")).toBe("p1");
    expect(rows[0].role).toBe("Brand Head");
  });

  it("saves one into applications by job id", async () => {
    let body: unknown = null;
    server.use(
      http.post(`${API_URL}/applications`, async ({ request }) => {
        body = await request.json();
        return HttpResponse.json({ id: "a1" });
      }),
    );
    await api.saveJob("p1", "j1");
    expect(body).toEqual({ profile_id: "p1", job_id: "j1" });
  });
});
