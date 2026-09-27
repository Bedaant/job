import { afterAll, afterEach, beforeAll, describe, expect, it } from "vitest";
import { http, HttpResponse } from "msw";
import { setupServer } from "msw/node";
import { api } from "./api";
import { EXTENSION_POLL_MS, extensionStatusView } from "./extension";

const API_URL = "http://localhost:8000";
const server = setupServer();

beforeAll(() => server.listen({ onUnhandledRequest: "error" }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

describe("extensionStatusView", () => {
  it("says it is checking before the first answer", () => {
    expect(extensionStatusView(undefined, false)).toEqual({ connected: false, text: "Checking for the extension…" });
  });

  it("says it is waiting when the extension has never called in", () => {
    const view = extensionStatusView({ connected: false, last_seen_at: null, approved_waiting: 0 }, false);
    expect(view).toEqual({ connected: false, text: "Waiting for the extension…" });
  });

  it("tells a returning user how to reconnect when the last check-in is stale", () => {
    const view = extensionStatusView(
      { connected: false, last_seen_at: "2026-09-27T10:00:00", approved_waiting: 0 },
      false,
    );
    expect(view.connected).toBe(false);
    expect(view.text).toMatch(/open the ApplyScout extension/i);
  });

  it("says connected, and how much work is waiting for it", () => {
    const base = { connected: true, last_seen_at: "2026-09-27T12:00:00" };
    expect(extensionStatusView({ ...base, approved_waiting: 0 }, false)).toEqual({ connected: true, text: "Connected ✓" });
    expect(extensionStatusView({ ...base, approved_waiting: 1 }, false).text).toBe(
      "Connected ✓ · 1 application ready to send",
    );
    expect(extensionStatusView({ ...base, approved_waiting: 3 }, false).text).toBe(
      "Connected ✓ · 3 applications ready to send",
    );
  });

  it("never claims connected when the check itself failed", () => {
    const view = extensionStatusView({ connected: true, last_seen_at: null, approved_waiting: 0 }, true);
    expect(view.connected).toBe(false);
    expect(view.text).toMatch(/couldn.t check/i);
  });

  it("polls every few seconds", () => {
    expect(EXTENSION_POLL_MS).toBeGreaterThanOrEqual(2000);
    expect(EXTENSION_POLL_MS).toBeLessThanOrEqual(10000);
  });
});

describe("GET /extension/status", () => {
  it("returns the server's status as-is", async () => {
    const body = { connected: true, last_seen_at: "2026-09-27T12:00:00", approved_waiting: 2 };
    server.use(http.get(`${API_URL}/extension/status`, () => HttpResponse.json(body)));
    expect(await api.getExtensionStatus()).toEqual(body);
  });
});
