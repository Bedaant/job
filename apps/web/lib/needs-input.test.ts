import { afterAll, afterEach, beforeAll, describe, expect, it, vi } from "vitest";
import { http, HttpResponse } from "msw";
import { setupServer } from "msw/node";
import { ApiError, api } from "./api";
import { DEMOGRAPHIC_NOTE, needsInputView } from "./needs-input";

const ni = (kind: "question" | "upload" | "captcha" | "account" | "other", demographic = false, message = "m") => ({
  kind,
  message,
  demographic_left_blank: demographic,
});

describe("needsInputView", () => {
  it("is null when Maggie did not stop", () => {
    expect(needsInputView(null, "Stripe", 0)).toBeNull();
  });

  it("captcha: say so, send the user to the form, no retry", () => {
    const v = needsInputView(ni("captcha"), "Stripe", 0)!;
    expect(v.title).toBe("Maggie stopped at a captcha on Stripe's form.");
    expect(v.body).toBe("Open the form, solve it, and submit it yourself.");
    expect(v).toMatchObject({ openForm: true, retryHelps: false, tone: "warning" });
  });

  it("account: names the company's site", () => {
    const v = needsInputView(ni("account"), "Workday Co", 0)!;
    expect(v.title).toContain("needs an account on Workday Co's site");
    expect(v).toMatchObject({ openForm: true, retryHelps: false });
  });

  it("upload: a file other than the resume, finish by hand", () => {
    const v = needsInputView(ni("upload"), "Acme", 0)!;
    expect(v.body).toMatch(/file/i);
    expect(v).toMatchObject({ openForm: true, retryHelps: false });
  });

  it("question with open questions: answer here, then approve to retry", () => {
    const v = needsInputView(ni("question"), "Acme", 2)!;
    expect(v.body).toMatch(/approve to retry/i);
    expect(v).toMatchObject({ openForm: false, retryHelps: true, demographicNote: null });
  });

  it("question, all answered: retry is the next step", () => {
    const v = needsInputView(ni("question"), "Acme", 0)!;
    expect(v.title).toMatch(/answered/i);
    expect(v.retryHelps).toBe(true);
  });

  it("demographic fields block every retry, so no retry framing and the note shows", () => {
    const v = needsInputView(ni("question", true), "Acme", 1)!;
    expect(v.retryHelps).toBe(false);
    expect(v.body).not.toMatch(/approve to retry/i);
    expect(v.openForm).toBe(true);
    expect(v.demographicNote).toBe(DEMOGRAPHIC_NOTE);
    expect(DEMOGRAPHIC_NOTE).toBe(
      "This form requires a self-identification question (gender, ethnicity, veteran or disability status). ApplyScout never answers these, so open the form and answer it yourself. Optional ones are left blank automatically."
    );
  });

  it("other: shows what the driver reported and sends the user to the form", () => {
    const v = needsInputView(ni("other", false, "no submit button"), "Acme", 0)!;
    expect(v.body).toContain("no submit button");
    expect(v).toMatchObject({ openForm: true, retryHelps: false });
  });
});

const API_URL = "http://localhost:8000";
const server = setupServer();
beforeAll(() => server.listen({ onUnhandledRequest: "error" }));
afterEach(() => {
  server.resetHandlers();
  vi.unstubAllGlobals();
});
afterAll(() => server.close());

describe("api.downloadResumeDocx", () => {
  it("sends the Bearer token and returns the file as a blob", async () => {
    vi.stubGlobal("window", { localStorage: { getItem: () => "tok" } });
    let auth: string | null = null;
    server.use(
      http.get(`${API_URL}/profiles/p1/resume.docx`, ({ request }) => {
        auth = request.headers.get("Authorization");
        return new HttpResponse("DOCX", { headers: { "Content-Type": "application/octet-stream" } });
      })
    );

    const blob = await api.downloadResumeDocx("p1");

    expect(auth).toBe("Bearer tok");
    expect(await blob.text()).toBe("DOCX");
  });

  it("rejects with the server's message", async () => {
    server.use(
      http.get(`${API_URL}/profiles/p1/resume.docx`, () =>
        HttpResponse.json({ detail: "No confirmed facts yet" }, { status: 404 })
      )
    );
    await expect(api.downloadResumeDocx("p1")).rejects.toBeInstanceOf(ApiError);
  });
});
