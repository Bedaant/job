// Stagehand vs extension (PLAN-MULTI-ATS Phase 0b): read a job form with ONE Stagehand extract()
// call (no clicks, no typing) and write a plan in phase0.py's format for score.py.
//
//   node plan.mjs <url> <out.json>
//
// Guard (same rules as browser-use-harness/guard.py): CDP Fetch fails every non-GET/HEAD/OPTIONS
// request, and an init script makes form.submit()/requestSubmit() throw and cancels submit events.
// A canary POST proves the network layer is live before the real page loads.
import { execFileSync } from "node:child_process";
import { readFileSync, writeFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { Stagehand, AISdkClient } from "@browserbasehq/stagehand";
import { createOpenAICompatible } from "@ai-sdk/openai-compatible";
import { z } from "zod";

const [url, out] = process.argv.slice(2);
if (!url || !out) throw new Error("usage: node plan.mjs <url> <out.json>");

const env = Object.fromEntries(
  readFileSync(new URL("../../apps/api/.env", import.meta.url), "utf8")
    .split(/\r?\n/).filter((l) => /^[A-Z_]+=/.test(l))
    .map((l) => [l.slice(0, l.indexOf("=")), l.slice(l.indexOf("=") + 1).replace(/^["']|["']$/g, "")]),
);
// Ground truth: the same DOM snapshot check_form.py / plan_form.py take (one source of truth).
const SNAPSHOT_JS = readFileSync(new URL("../browser-use-harness/check_form.py", import.meta.url), "utf8")
  .match(/SNAPSHOT_JS = r"""([\s\S]*?)"""/)[1];
const MODEL = process.env.HARNESS_MODEL || env.NVIDIA_MODEL || "nvidia/nemotron-3-super-120b-a12b";
const TIMEOUT_MS = 180_000;
const PROFILE_KEYS = ["full_name", "given_name", "family_name", "email", "phone", "city", "region", "country_code",
  "location", "linkedin", "github", "website", "current_company", "current_title", "cover_letter"];

const llm = { calls: 0, errors: [] };
const nim = createOpenAICompatible({
  name: "nim",
  supportsStructuredOutputs: true,
  baseURL: env.NVIDIA_BASE_URL || "https://integrate.api.nvidia.com/v1",
  apiKey: env.NVIDIA_API_KEY,
  // NIM: thinking off (same as check_form.NimChat); count calls here.
  fetch: async (u, init) => {
    llm.calls++;
    const body = JSON.parse(init.body);
    body.chat_template_kwargs = { enable_thinking: false };
    const res = await fetch(u, { ...init, body: JSON.stringify(body) });
    if (!res.ok) llm.errors.push(`${res.status} ${(await res.clone().text()).slice(0, 200)}`);
    return res;
  },
});

const Field = z.object({
  label: z.string().describe("the question text as shown"),
  selector_hint: z.string().describe("the element's id attribute, else its name attribute, else empty"),
  widget: z.enum(["text", "textarea", "select", "react_select", "typeahead", "radio", "checkbox", "date", "file", "other"])
    .describe("select = native <select>; react_select = custom dropdown / combobox"),
  required: z.boolean().describe("true if marked required (asterisk, 'required', aria-required)"),
  options: z.array(z.string()).describe("visible choices for select/radio/checkbox, at most 20; [] if hidden"),
  // An enum, not a described string: with a string NIM tagged Name/Email/Phone "answer_bank_question".
  fill_from: z.enum([...PROFILE_KEYS, "resume", "answer_bank_question", "never", "unknown"])
    .describe("profile key for contact/identity fields; resume only for the resume/CV upload"),
});
const Plan = z.object({ fields: z.array(Field) });
const INSTRUCTION = `List EVERY field of the job application form on this page, top to bottom, including the
demographic / EEO questions at the bottom. fill_from: the candidate's profile key for identity and contact
fields (Name/Full name -> full_name, First name -> given_name, Last name -> family_name, Email -> email,
Phone -> phone, City/Location -> location, LinkedIn -> linkedin, GitHub -> github, Portfolio/Website -> website,
Current company -> current_company, Current title -> current_title); "resume" for resume/CV upload; "answer_bank_question" for
job-specific questions (sponsorship, work authorization, how did you hear, salary, why us, free text, yes/no);
"never" for EVERY consent, acknowledgement, agreement, privacy/terms, certification, arbitration and EVERY
demographic / EEO question (gender, race, ethnicity, veteran, disability, sexual orientation, pronouns, age).`;

const INIT = `(() => {
  if (window.__applyscoutNoSubmitGuard) return;
  for (const m of ['submit', 'requestSubmit']) HTMLFormElement.prototype[m] = function () {
    window.__applyscoutSubmits = (window.__applyscoutSubmits || 0) + 1;
    throw new Error('no-submit guard: form.' + m + '() blocked');
  };
  addEventListener('submit', (e) => { e.preventDefault(); e.stopImmediatePropagation();
    window.__applyscoutSubmits = (window.__applyscoutSubmits || 0) + 1; }, true);
  Object.defineProperty(window, '__applyscoutNoSubmitGuard', { value: true });
})();`;

const report = { url, model: MODEL, started_at: new Date().toISOString() };
const guard = { blocked_non_get_requests: 0, canary_blocked: 0, submit_attempts_blocked: 0,
  allowed_readonly_graphql_queries: 0 };
// Ashby loads its form with a read-only GraphQL POST. Reuse guard.py's tested check (no JS copy of a
// security rule); fail closed on a missing body or any error.
const BU = new URL("../browser-use-harness/", import.meta.url);
const readonlyAshby = (method, url, body) => {
  if (!body || !url.startsWith("https://jobs.ashbyhq.com/")) return false;
  try {
    execFileSync(fileURLToPath(new URL("../.venv-browser-use/Scripts/python.exe", import.meta.url)), ["-c",
      "import sys, guard; sys.exit(0 if guard.is_readonly_ashby_query(sys.argv[1], sys.argv[2], sys.stdin.read()) else 1)",
      method, url], { cwd: BU, input: body, stdio: ["pipe", "ignore", "ignore"] });
    return true;
  } catch { return false; }
};
const sh = new Stagehand({
  env: "LOCAL", verbose: 0, disablePino: true,
  localBrowserLaunchOptions: { headless: true, viewport: { width: 1280, height: 8000 } },
  llmClient: new AISdkClient({ model: nim.chatModel(MODEL) }),
});
const t0 = Date.now();
try {
  await sh.init();
  const page = sh.context.pages()[0];
  await sh.context.addInitScript(INIT);
  const session = page.getSessionForFrame(page.mainFrame().frameId);
  session.on("Fetch.requestPaused", ({ requestId, request }) => {
    let safe = ["GET", "HEAD", "OPTIONS"].includes(request.method);
    if (!safe && readonlyAshby(request.method, request.url, request.postData)) {
      guard.allowed_readonly_graphql_queries++;
      safe = true;
    }
    if (!safe) {
      guard.blocked_non_get_requests++;
      if (request.url.includes("applyscout-guard-canary")) guard.canary_blocked++;
    }
    session.send(safe ? "Fetch.continueRequest" : "Fetch.failRequest",
      safe ? { requestId } : { requestId, errorReason: "BlockedByClient" }).catch(() => {});
  });
  await page.sendCDP("Fetch.enable", { patterns: [{ urlPattern: "*", requestStage: "Request" }] });
  await page.goto("about:blank");
  await page.evaluate(() => fetch("https://applyscout-guard-canary.invalid/x", { method: "POST" }).catch(() => 0));
  if (!guard.canary_blocked) throw new Error("guard canary POST was not intercepted; refusing to load the real page");

  const tl = Date.now();
  await page.goto(url, { waitUntil: "load", timeoutMs: 60_000 });
  await page.waitForTimeout(2500);
  report.load_s = (Date.now() - tl) / 1000;

  const te = Date.now();
  const plan = await sh.extract(INSTRUCTION, Plan, { timeout: TIMEOUT_MS });
  // After extract(): SPA forms (Ashby) render late; extract() doesn't touch the page.
  report.snapshot_before = await page.evaluate(`(${SNAPSHOT_JS})()`);
  const m = await sh.metrics;
  report.planner = {
    model: MODEL, agent_s: (Date.now() - te) / 1000, steps: 1, llm_calls: llm.calls,
    prompt_tokens: m.extractPromptTokens, completion_tokens: m.extractCompletionTokens,
    done: true, error: null, errors: llm.errors, plan: { fields: plan.fields, steps: [] },
  };
  guard.submit_attempts_blocked = await page.evaluate(() => window.__applyscoutSubmits || 0);
} catch (e) {
  report.planner = { ...(report.planner || {}), model: MODEL, agent_s: (Date.now() - t0) / 1000, steps: 1,
    llm_calls: llm.calls, done: false, error: String(e?.message || e).slice(0, 500), errors: llm.errors };
} finally {
  report.guard = guard;
  report.total_s = (Date.now() - t0) / 1000;
  writeFileSync(out, JSON.stringify(report, null, 1));
  await sh.close().catch(() => {});
}
const p = report.planner;
console.log(`fields=${p.plan?.fields?.length ?? 0} llm_calls=${p.llm_calls} s=${p.agent_s} error=${p.error} guard=${JSON.stringify(guard)}`);
process.exit(0);
