// P0 #7: consent at signup, account deletion, and the privacy notice.
import { afterAll, afterEach, beforeAll, describe, expect, it } from "vitest";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { http, HttpResponse } from "msw";
import { setupServer } from "msw/node";
import { api } from "./api";
import PrivacyPage from "@/app/privacy/page";

const API_URL = "http://localhost:8000";
const server = setupServer();

beforeAll(() => server.listen({ onUnhandledRequest: "error" }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

describe("account API", () => {
  it("sends the consent checkbox with signup", async () => {
    let body: unknown;
    server.use(
      http.post(`${API_URL}/auth/signup`, async ({ request }) => {
        body = await request.json();
        return HttpResponse.json({ id: "u1", email: "a@b.in" }, { status: 201 });
      }),
    );
    await api.signup("a@b.in", "long enough", true);
    expect(body).toEqual({ email: "a@b.in", password: "long enough", privacy_consent: true });
  });

  it("deletes the account with DELETE /account", async () => {
    let hit = false;
    server.use(
      http.delete(`${API_URL}/account`, () => {
        hit = true;
        return new HttpResponse(null, { status: 204 });
      }),
    );
    await api.deleteAccount();
    expect(hit).toBe(true);
  });
});

describe("privacy notice", () => {
  const html = renderToStaticMarkup(createElement(PrivacyPage));

  it("is marked as a draft pending legal review", () => {
    expect(html).toContain("Draft — pending legal review");
  });

  it("names every processor that receives personal data, and how to delete", () => {
    for (const name of ["Anthropic", "NVIDIA", "Voyage AI", "Langfuse", "Apify", "Google", "Neon", "Redis"]) {
      expect(html).toContain(name);
    }
    expect(html).toContain("Delete my account");
  });
});
