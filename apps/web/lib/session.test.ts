import { afterAll, afterEach, beforeAll, describe, expect, it, vi } from "vitest";
import { http, HttpResponse } from "msw";
import { setupServer } from "msw/node";
import { ApiError, api } from "./api";
import { isSessionExpiry, safeNext } from "./auth";

const API_URL = "http://localhost:8000";
const server = setupServer();

beforeAll(() => server.listen({ onUnhandledRequest: "error" }));
afterEach(() => {
  server.resetHandlers();
  vi.unstubAllGlobals();
});
afterAll(() => server.close());

describe("isSessionExpiry", () => {
  it("treats a 401 from an authed endpoint as an ended session", () => {
    expect(isSessionExpiry(401, "/profiles")).toBe(true);
    expect(isSessionExpiry(401, "/resume-facts?profile_id=p1")).toBe(true);
  });

  it("keeps a 401 from login/signup as a wrong-password error, not a logout", () => {
    expect(isSessionExpiry(401, "/auth/login")).toBe(false);
    expect(isSessionExpiry(401, "/auth/signup")).toBe(false);
  });

  it("ignores every other status", () => {
    expect(isSessionExpiry(403, "/profiles")).toBe(false);
    expect(isSessionExpiry(500, "/profiles")).toBe(false);
  });
});

describe("safeNext", () => {
  it("accepts same-origin relative paths", () => {
    expect(safeNext("/facts")).toBe("/facts");
    expect(safeNext("/review?tab=2#top")).toBe("/review?tab=2#top");
  });

  it("rejects anything that could leave the site (open redirect)", () => {
    for (const bad of [
      "//evil.com",
      "/\\evil.com",
      "\\\\evil.com",
      "/\t/evil.com",
      "https://evil.com",
      "javascript:alert(1)",
      "facts",
      "",
      null,
      undefined,
    ]) {
      expect(safeNext(bad), String(bad)).toBeNull();
    }
  });

  it("does not bounce back to /login", () => {
    expect(safeNext("/login?next=/facts")).toBeNull();
  });
});

describe("request() on 401", () => {
  function stubBrowser(path: string) {
    const storage = new Map([["job_copilot_token", "stale"]]);
    const replace = vi.fn();
    vi.stubGlobal("window", {
      localStorage: {
        getItem: (k: string) => storage.get(k) ?? null,
        setItem: (k: string, v: string) => storage.set(k, v),
        removeItem: (k: string) => storage.delete(k),
      },
      location: { pathname: path.split("?")[0], search: path.includes("?") ? `?${path.split("?")[1]}` : "", replace },
    });
    return { storage, replace };
  }

  it("clears the token and sends the user to /login with where they were", async () => {
    const { storage, replace } = stubBrowser("/facts?x=1");
    server.use(http.get(`${API_URL}/profiles`, () => HttpResponse.json({ detail: "Could not validate credentials" }, { status: 401 })));

    await expect(api.listProfiles()).rejects.toBeInstanceOf(ApiError);
    expect(storage.has("job_copilot_token")).toBe(false);
    expect(replace).toHaveBeenCalledWith("/login?expired=1&next=%2Ffacts%3Fx%3D1");
  });

  it("leaves a wrong password on /auth/login as an ApiError the form shows", async () => {
    const { storage, replace } = stubBrowser("/login");
    server.use(http.post(`${API_URL}/auth/login`, () => HttpResponse.json({ detail: "Incorrect email or password" }, { status: 401 })));

    await expect(api.login("a@b.co", "wrongpass")).rejects.toThrow("Incorrect email or password");
    expect(storage.has("job_copilot_token")).toBe(true);
    expect(replace).not.toHaveBeenCalled();
  });
});
