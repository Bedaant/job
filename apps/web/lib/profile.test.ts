import { afterAll, afterEach, beforeAll, describe, expect, it, vi } from "vitest";
import { http, HttpResponse } from "msw";
import { setupServer } from "msw/node";
import { api, type ResumeFact } from "./api";
import { factChanges, undoableDeletes, UNDO_MS } from "./profile";

const API_URL = "http://localhost:8000";
const server = setupServer();

beforeAll(() => server.listen({ onUnhandledRequest: "error" }));
afterEach(() => {
  server.resetHandlers();
  vi.useRealTimers();
});
afterAll(() => server.close());

const fact: ResumeFact = {
  id: "f1",
  profile_id: "p1",
  category: "experience",
  achievement: "Cut deploy time by 40%",
  proof: null,
  metric: null,
  tags: [],
};

describe("factChanges", () => {
  it("returns only the fields the user changed", () => {
    expect(factChanges(fact, { ...fact, metric: "40%" })).toEqual({ metric: "40%" });
  });
  it("is empty when nothing changed, so no request is sent", () => {
    expect(factChanges(fact, { ...fact })).toEqual({});
  });
  it("sends a cleared optional field as null, not empty string", () => {
    expect(factChanges({ ...fact, proof: "Acme" }, { ...fact, proof: "" })).toEqual({ proof: null });
  });
  it("trims the achievement", () => {
    expect(factChanges(fact, { ...fact, achievement: "  New words " })).toEqual({ achievement: "New words" });
  });
});

describe("undoableDeletes", () => {
  it("waits five seconds before deleting", () => {
    vi.useFakeTimers();
    const commit = vi.fn();
    const d = undoableDeletes(commit);
    d.schedule("f1");
    vi.advanceTimersByTime(UNDO_MS - 1);
    expect(commit).not.toHaveBeenCalled();
    vi.advanceTimersByTime(1);
    expect(commit).toHaveBeenCalledWith("f1");
    expect(UNDO_MS).toBe(5000);
  });
  it("undo cancels the delete", () => {
    vi.useFakeTimers();
    const commit = vi.fn();
    const d = undoableDeletes(commit);
    d.schedule("f1");
    d.undo("f1");
    vi.advanceTimersByTime(UNDO_MS * 2);
    expect(commit).not.toHaveBeenCalled();
  });
  it("flush deletes everything pending now (leaving the page keeps the delete)", () => {
    vi.useFakeTimers();
    const commit = vi.fn();
    const d = undoableDeletes(commit);
    d.schedule("f1");
    d.schedule("f2");
    d.flush();
    expect(commit.mock.calls.map((c) => c[0])).toEqual(["f1", "f2"]);
    vi.advanceTimersByTime(UNDO_MS);
    expect(commit).toHaveBeenCalledTimes(2);
  });
});

describe("fact + answer endpoints", () => {
  it("PATCHes only the changed fields", async () => {
    let body: unknown = null;
    server.use(
      http.patch(`${API_URL}/resume-facts/f1`, async ({ request }) => {
        body = await request.json();
        return HttpResponse.json({ ...fact, metric: "40%" });
      })
    );
    const updated = await api.updateFact("f1", { metric: "40%" });
    expect(body).toEqual({ metric: "40%" });
    expect(updated.metric).toBe("40%");
  });

  it("DELETE handles the empty 204", async () => {
    server.use(http.delete(`${API_URL}/resume-facts/f1`, () => new HttpResponse(null, { status: 204 })));
    await expect(api.deleteFact("f1")).resolves.toBeUndefined();
  });

  it("lists and deletes saved answers", async () => {
    server.use(
      http.get(`${API_URL}/profiles/p1/answers`, () =>
        HttpResponse.json([{ id: "a1", question_text: "Notice period?", answer_text: "30 days", times_used: 3 }])
      ),
      http.delete(`${API_URL}/profiles/p1/answers/a1`, () => new HttpResponse(null, { status: 204 }))
    );
    const answers = await api.listAnswers("p1");
    expect(answers[0].times_used).toBe(3);
    await expect(api.deleteAnswer("p1", "a1")).resolves.toBeUndefined();
  });
});
