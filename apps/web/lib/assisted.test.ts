import { afterAll, afterEach, beforeAll, describe, expect, it, vi } from "vitest";
import { http, HttpResponse } from "msw";
import { setupServer } from "msw/node";
import { api } from "./api";
import {
  ASSISTED,
  AUTOMATIC,
  copyText,
  coverageChange,
  isHttpUrl,
  needsYouOnly,
  resumeFilename,
  submitModeLine,
  undoMessage,
} from "./assisted";

const API_URL = "http://localhost:8000";
const server = setupServer();
beforeAll(() => server.listen({ onUnhandledRequest: "error" }));
afterEach(() => {
  server.resetHandlers();
  vi.unstubAllGlobals();
});
afterAll(() => server.close());

describe("submit mode copy", () => {
  it("names both modes plainly, assisted as the recommended one", () => {
    expect(ASSISTED.label).toBe("Assisted — Maggie prepares, you send (recommended)");
    expect(AUTOMATIC.label).toBe("Automatic — Maggie sends within your daily limit");
  });
  it("describes what happens once the campaign is running", () => {
    expect(submitModeLine(false)).toBe("She prepares each application; you send it from Review, one tap at a time.");
    expect(submitModeLine(true)).toBe("She sends applications herself, within your daily limit.");
  });
});

describe("coverageChange", () => {
  it("shows keyword coverage before → after as whole percentages", () => {
    expect(coverageChange({ coverage_before: 0.5, coverage_after: 0.754 })).toBe("Job keywords covered: 50% → 75%");
  });
  it("says nothing when tailoring didn't record it", () => {
    expect(coverageChange(null)).toBeNull();
    expect(coverageChange({})).toBeNull();
    expect(coverageChange({ coverage_before: "x", coverage_after: 0.5 })).toBeNull();
  });
});

describe("copyText", () => {
  it("copies with the clipboard API when it works", async () => {
    let got = "";
    const clipboard = { writeText: async (t: string) => void (got = t) };
    expect(await copyText("Dear Acme", clipboard)).toBe("copied");
    expect(got).toBe("Dear Acme");
  });
  it("falls back to showing the text when there is no clipboard or it refuses", async () => {
    expect(await copyText("x", undefined)).toBe("show");
    const refusing = { writeText: async () => Promise.reject(new Error("NotAllowedError")) };
    expect(await copyText("x", refusing)).toBe("show");
  });
});

describe("isHttpUrl", () => {
  it("only lets real web links open", () => {
    expect(isHttpUrl("https://jobs.lever.co/acme/1")).toBe(true);
    expect(isHttpUrl("http://acme.example/apply")).toBe(true);
    expect(isHttpUrl("javascript:alert(1)")).toBe(false);
    expect(isHttpUrl("")).toBe(false);
  });
});

describe("resumeFilename", () => {
  it("names the file after the company, filesystem-safe", () => {
    expect(resumeFilename("Acme, Inc.")).toBe("resume-acme-inc.docx");
    expect(resumeFilename("  ")).toBe("resume.docx");
  });
});

describe("undoMessage", () => {
  const job = { title: "SRE", company: "Stripe" };
  it("says what just happened, in words", () => {
    expect(undoMessage("sent", job)).toBe("Marked as sent: SRE at Stripe.");
    expect(undoMessage("dismissed", job)).toBe("Removed: SRE at Stripe.");
  });
});

describe("needsYouOnly", () => {
  it("keeps a prepared application out of the needs-you list", () => {
    expect(needsYouOnly([{ id: "a" }, { id: "b" }, { id: "c" }], [{ id: "b" }])).toEqual([{ id: "a" }, { id: "c" }]);
  });
});

describe("assisted apply API", () => {
  it("lists ready-to-send for a profile", async () => {
    let url = "";
    server.use(
      http.get(`${API_URL}/applications/ready-to-send`, ({ request }) => {
        url = request.url;
        return HttpResponse.json([]);
      }),
    );
    expect(await api.listReadyToSend("p1")).toEqual([]);
    expect(new URL(url).searchParams.get("profile_id")).toBe("p1");
  });

  it("marks an application applied with a PATCH of exactly its status", async () => {
    let body: unknown = null;
    server.use(
      http.patch(`${API_URL}/applications/a1`, async ({ request }) => {
        body = await request.json();
        return HttpResponse.json({ id: "a1", status: "applied" });
      }),
    );
    await api.markApplied("a1");
    expect(body).toEqual({ status: "applied" });
  });

  it("fetches the tailored resume with the Bearer header, as a blob", async () => {
    let auth: string | null = null;
    server.use(
      http.get(`${API_URL}/applications/a1/resume.docx`, ({ request }) => {
        auth = request.headers.get("authorization");
        return new HttpResponse(new Uint8Array([80, 75]), { headers: { "Content-Type": "application/octet-stream" } });
      }),
    );
    vi.stubGlobal("window", { localStorage: { getItem: () => "tok" } });
    const blob = await api.downloadTailoredResumeDocx("a1");
    expect(blob.size).toBe(2);
    expect(auth).toBe("Bearer tok");
  });
});
