import { afterAll, afterEach, beforeAll, describe, expect, it } from "vitest";
import { http, HttpResponse } from "msw";
import { setupServer } from "msw/node";
import { ApiError, api } from "./api";

const API_URL = "http://localhost:8000";
const server = setupServer();

beforeAll(() => server.listen({ onUnhandledRequest: "error" }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

describe("PUT /profiles/{id}/answers", () => {
  it("sends the question verbatim with the user's answer", async () => {
    let received: unknown = null;
    server.use(
      http.put(`${API_URL}/profiles/p1/answers`, async ({ request }) => {
        received = await request.json();
        return HttpResponse.json({ id: "a1", question_text: "Why us?", answer_text: "The mission." });
      })
    );

    await api.saveAnswer("p1", "Why us?", "The mission.");

    expect(received).toEqual({ question_text: "Why us?", answer_text: "The mission." });
  });

  it("surfaces the backend's refusal of a demographic question", async () => {
    server.use(
      http.put(`${API_URL}/profiles/p1/answers`, () =>
        HttpResponse.json({ detail: "Demographic/EEO questions are never stored or auto-filled." }, { status: 400 })
      )
    );

    await expect(api.saveAnswer("p1", "Gender?", "x")).rejects.toBeInstanceOf(ApiError);
  });
});
