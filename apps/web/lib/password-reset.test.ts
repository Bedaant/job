import { afterAll, afterEach, beforeAll, describe, expect, it } from "vitest";
import { http, HttpResponse } from "msw";
import { setupServer } from "msw/node";
import { ApiError, api } from "./api";

const API_URL = "http://localhost:8000";
const server = setupServer();

beforeAll(() => server.listen({ onUnhandledRequest: "error" }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

describe("password reset", () => {
  it("asks for a reset link by email", async () => {
    let received: unknown = null;
    server.use(
      http.post(`${API_URL}/auth/forgot-password`, async ({ request }) => {
        received = await request.json();
        return HttpResponse.json({ ok: true }, { status: 202 });
      }),
    );
    await api.forgotPassword("me@example.com");
    expect(received).toEqual({ email: "me@example.com" });
  });

  it("sets the new password with the token, and surfaces an expired link", async () => {
    let received: unknown = null;
    server.use(
      http.post(`${API_URL}/auth/reset-password`, async ({ request }) => {
        received = await request.json();
        return HttpResponse.json({ ok: true });
      }),
    );
    await api.resetPassword("tok", "a new long password");
    expect(received).toEqual({ token: "tok", password: "a new long password" });

    server.use(
      http.post(`${API_URL}/auth/reset-password`, () =>
        HttpResponse.json({ detail: "This reset link is invalid or has expired. Ask for a new one." }, { status: 400 }),
      ),
    );
    const err = await api.resetPassword("old", "a new long password").catch((e) => e);
    expect(err).toBeInstanceOf(ApiError);
    expect(err.message).toContain("invalid or has expired");
  });
});
