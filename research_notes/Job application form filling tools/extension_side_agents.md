# Extension-side / in-page AI agents and DOM/a11y libraries for AI-assisted form filling (ApplyScout)

Method note: ~19 tool calls. GitHub MCP was scoped to bedaant/job only, so repo data came from WebFetch of github.com pages (rendered, summarised by a small model; year is often omitted on release pages). developer.chrome.com did not resolve in WebFetch (ENOTFOUND); Chrome facts come from WebSearch snippets only. Today = 2026-10-11. NOT verified from primary pages: Playwright MCP licence, Chrome DevTools MCP release dates, Stagehand/browser-use release dates, AgentQL licence, Nanobrowser/Page Agent manifest permissions, any job-form accuracy numbers.

## 1. Licence, maturity, maintenance, and "embed vs learn" per candidate

### Takeaway
Only Page Agent (MIT) and Stagehand/browser-use (MIT) and Nanobrowser (Apache-2.0) are licence-safe to embed or fork in a closed-source product; WebBrain is GPL-3.0-or-later and must not be embedded. Page Agent is the closest architectural fit (in-page, text-DOM, BYO OpenAI-compatible endpoint) but is a general-purpose agent, not a job-form specialist.

### Cited Findings
- Alibaba Page Agent: MIT; 29.4k stars, 2.6k forks, 1,137 commits; reads page via text-based DOM ("No screenshots. No multi-modal LLMs or special permissions needed"); DOM processing derived from browser-use; BYO model incl. local, OpenAI-compatible endpoint; optional Chrome extension for multi-tab tasks; MCP server marked Beta; page describes no human-in-the-loop controls; "designed for client-side web enhancement, not server-side automation"; free demo LLM is evaluation-only — [GitHub](https://github.com/alibaba/page-agent)
- Page Agent releases: v1.12.4 (06 Sep, model list/badge), v1.12.3 (05 Sep, WXT upgrade, MCP SDK 1.29->1.30, Kimi K3, focus-preservation fix), v1.12.2 (16 Jul); year not shown on page but v1.12.4 is the newest, i.e. ~5 weeks before today if 2026 — [Releases](https://github.com/alibaba/page-agent/releases)
- Nanobrowser: Apache-2.0; ~14.1k stars, 1.5k forks, 376 commits, 49 open issues/33 PRs; Chrome/Edge only; Planner+Navigator agents; providers OpenAI, Anthropic, Gemini, DeepSeek, Grok, Azure, OpenRouter, Ollama, custom OpenAI-compatible; Web Store build may lag; cheaper models "less stable ... more iterations on complex tasks"; page does not explain how it reads the DOM; credits Browser Use — [GitHub](https://github.com/nanobrowser/nanobrowser)
- Nanobrowser releases: v0.2.0 "02 Oct" labelled Latest, v0.1.13 "22 Nov", v0.1.12 "03 Sep"; years not shown, ordering implies v0.2.0 is Oct 2026 and v0.1.13 Nov 2025 (inference, unconfirmed) — [Releases](https://github.com/nanobrowser/nanobrowser/releases)
- WebBrain: GPL-3.0-or-later (because it bundles GPL Xapian/libzim WASM); ~1.3k stars, 154 forks, 6,216 commits; latest commits 8-11 Oct 2026 (very active, tagged 40.1.0, many commits from an AI-assisted "Codex" workflow and release bots); reads page via accessibility tree; 112 provider cards; modes Ask (read-only) / Act (click, type, upload, fill) / Dev; plan-for-approval and per-site permission prompts; has a `/dangerously-skip-permissions` command; Firefox lacks shadow-DOM piercing; SPAs may not re-inject content script after client navigation — [GitHub](https://github.com/webbrain-one/webbrain), [commits](https://github.com/webbrain-one/webbrain/commits/main)
- Browser Use web-ui: MIT; 16.6k stars; NOT an extension (Gradio app on localhost:7788, Playwright); changelog newest entry 2025/01/26, 271 open issues -> stale/likely superseded — [GitHub](https://github.com/browser-use/web-ui)
- Browser Use library: MIT; ~117.6k stars; Python lib + CLI; no extension; cloud browsers $0.02/browser-hour, $15 credit for new signups; inference billed separately — [GitHub](https://github.com/browser-use/browser-use)
- Playwright MCP: licence not stated on releases page; v0.0.83 (28 Sep), v0.0.82 (18 Sep, WebMCP tools, 60fps video), v0.0.81 (14 Sep); has an "extension mode" that attaches to the user's real Chrome profile with token auth — [Releases](https://github.com/microsoft/playwright-mcp/releases)
- Chrome DevTools MCP: Apache-2.0; 53.3k stars; Puppeteer-based; usage statistics collected by default (opt out `--no-usage-statistics`); disclaimer that MCP clients can inspect/modify any data in the browser — [GitHub](https://github.com/ChromeDevTools/chrome-devtools-mcp)
- Stagehand: MIT (Browserbase, trademark); ~25.6k stars; v4 docs; hybrid accessibility-tree trimming; `act`/`observe`/`extract`; `observe` returns selectors so credentials can stay away from the model; server-side caching only on Browserbase; says it can run "as an extension next to the browser"; supports WebMCP — [GitHub](https://github.com/browserbase/stagehand)
- Claude in Chrome: Anthropic's own extension, paid plans only (Pro/Max/Team/Enterprise); permission modes Manually approve / Automatically approve / Skip all approvals; purchases and permanent deletes blocked in every mode; Pro limited to Haiku 4.5 per one support article. Closed source; cannot be embedded or pointed at our backend — [Support](https://support.claude.com/en/articles/12902446-claude-in-chrome-permissions-guide)
- AgentQL: hosted API + Python/JS SDKs + a Debugger Chrome extension; pricing per aggregators: Professional $99/mo (10,000 calls), per-call overage ~$0.015, free tier figures conflict (50 vs 300 calls); MIT licence claim is from a directory only — [aggregator](https://toolradar.com/tools/agentql/pricing); [AgentQL blog](https://agentql.com/blog/2024-pricing-update). Official pricing page not opened.

### Inferences
- GPL-3.0-or-later (WebBrain): shipping its code inside a closed-source extension distributed to users would require releasing ApplyScout's extension source under GPL; treat as "learn only" (reading the design is fine, copying code is not). AGPL candidates: none found. Legal review advised.
- Page Agent being derived from browser-use's DOM code means both share the same indexed-interactive-element approach; ApplyScout can reuse it without its own extension scaffolding, but must pin versions (releases are frequent, 1.12.x weekly-ish).
- Nanobrowser is a full side-panel agent product; embedding it as a dependency makes little sense, but forking (Apache-2.0, requires notice/NOTICE retention) is legally possible. Release cadence looks slower (roughly one release per quarter).
- Browser Use web-ui is effectively abandoned for our purpose.

### Gaps
- Exact last-commit dates for Page Agent, Nanobrowser, Stagehand, browser-use, Playwright MCP licence (not shown on fetched pages).
- Whether Page Agent / Nanobrowser have active named maintainers beyond Alibaba / the Nanobrowser org; Page Agent maintainer-note path guessed and 404'd.

## 2. How each reads the page, how actions are restricted, permissions, LLM endpoints, cost

### Takeaway
Text/a11y approaches (Page Agent, WebBrain, Stagehand, Playwright MCP, Chrome DevTools MCP) avoid screenshots and keep token cost lower; approval gates exist natively only in WebBrain and Claude in Chrome. For Page Agent/Nanobrowser, a "no-submit, user clicks Submit" rule would have to be implemented by ApplyScout (e.g., a blocklist in the action layer).

### Cited Findings
- Page Agent: text DOM, no screenshots, no special permissions for the in-page library; any OpenAI-compatible endpoint, so it can call our own backend/NIM — [GitHub](https://github.com/alibaba/page-agent)
- WebBrain: a11y tree; Act mode can click/type/upload/fill; plan approval and per-site prompts before consequential actions — [GitHub](https://github.com/webbrain-one/webbrain)
- Nanobrowser: custom OpenAI-compatible endpoints supported; Playwright/Puppeteer-style heritage; permissions not listed on README (manifest fetch 404) — [GitHub](https://github.com/nanobrowser/nanobrowser)
- Stagehand: a11y tree trimming; `observe` returns selectors for deterministic replay — [GitHub](https://github.com/browserbase/stagehand)
- Chrome DevTools MCP: exposes whole browser to MCP client; requires debugging port/CDP, not a store-friendly embed — [GitHub](https://github.com/ChromeDevTools/chrome-devtools-mcp)
- Playwright MCP extension mode connects to user's real Chrome; used by external MCP client (needs Node + desktop) — [Releases](https://github.com/microsoft/playwright-mcp/releases)
- Chrome built-in Prompt API (Gemini Nano): desktop only (Win10/11, macOS 13+, Linux, Chromebook Plus); needs >=22 GB free disk, GPU >4 GB VRAM or CPU with 16 GB RAM and 4+ cores; Android/iOS not supported per docs — [search snippet of Chrome docs](https://developer.chrome.com/docs/ai/prompt-api). A 2026 report says Pixel 10/Galaxy S26 Android support is coming (unverified) — [Ubergizmo](https://www.ubergizmo.com/2026/05/gemini-intelligence-min-req/)
- Chrome "Enhanced autofill"/"Find and Fill with Gemini": Canary only as of July 2026, triggered by "@@", pulls data from Gmail/Photos; page titles/URLs may be human-reviewed; not stable, no date — [Android Authority](https://androidauthority.com/find-and-fill-with-gemini-3689348), [Android Headlines](https://www.androidheadlines.com/2026/07/googles-new-chrome-autofill-upgrade-lets-gemini-fill-forms-for-you.html). Chromium agent fix: click target field first so autofill reparses stale form data — [Chrome Story](https://chromestory.com/2026/06/chromium-gemini-agent-form-filling-fix/)
- Chromium has an ML field-type prediction hook plus server predictions in `autofill_field.cc` and an Optimization Guide target; weights/model not confirmed open — [Chromium commit](https://chromium.googlesource.com/chromium/src/+/28d9ba710b275fcf49d01fe628e407ae27764554)

### Inferences
- Gemini Nano is unusable as a primary path for Indian budget laptops (disk/RAM requirements) and Chrome Android has no extensions anyway; at best an optional offline classifier for the rare capable device.
- Chrome's native Gemini autofill competes with ApplyScout's value for generic fields on stable Chrome; the answer bank (India-specific: notice period, CTC, PAN-linked data) remains differentiating.
- Per-form token cost was not found in any source; no published tokens/steps per form. Agent loops (observe-act per field) are inherently costlier than one-shot structured fill.

### Gaps
- No per-form cost figures for any tool; Page Agent / Nanobrowser manifest permissions; Chrome docs not opened directly.

## 3. Job-form testing, accuracy numbers, and failure modes

### Takeaway
No candidate publishes job-application accuracy numbers. Only generic web-agent benchmarks exist and show low reliability, so the safest design keeps deterministic mapping first and the LLM only for residual fields.

### Cited Findings
- Search for Workday/Greenhouse/Lever agent benchmarks found only vendor claims (no success rates) — [rtrvr.ai](https://rtrvr.ai/data), [FrogHire](https://www.froghire.ai/help/autofill)
- Online-Mind2Web (300 tasks, 136 live sites): Operator ~61% in the original study; HAL leaderboard top ~42.3% (SeeAct + GPT-5 Medium), verified 2026-05-27 — [arXiv 2504.01382](https://arxiv.org/pdf/2504.01382v4), [HAL](https://benchmarklist.com/benchmarks/hal_online_mind2web/)
- WebArena: Claude-3.7-Sonnet 45.4%, GPT-4o 37.6% in one paper (older models, possibly stale) — [arXiv 2506.03533](https://arxiv.org/pdf/2506.03533)
- TinyFish self-reports 83.2% on Mind2Web (vendor claim, different variant) — [TinyFish](https://www.tinyfish.ai/benchmarks)
- WebBrain Firefox lacks shadow-DOM piercing and trusted mouse events; SPAs may break content script injection — [GitHub](https://github.com/webbrain-one/webbrain)
- FUNSD (199 scanned forms, 2019) and FUNSD+ (1,113 docs) are scanned-document datasets, not HTML forms; no HTML web-form dataset or FormNet/LayoutLM licence info found — [FUNSD](https://arxiv.org/pdf/1905.13538)

### Inferences
- Known generic weak points (custom comboboxes, Workday's dynamic widgets, shadow DOM, iframes, file upload via hidden inputs) were NOT evidenced in primary sources for these tools; treat as risk, to be tested in-house on a fixture set of Workday/Greenhouse/Lever/Ashby/iCIMS pages.
- LayoutLM/FormNet-style models target scanned images and are the wrong modality for live DOM forms; label/attribute-based classification (as Chromium does) fits better.

### Gaps
- No ATS-specific failure reports from GitHub issues/HN/Reddit were retrieved; no accuracy numbers; LayoutLM/FormNet licences not checked.

## 4. Commercial versions, Indian-user and Chrome Web Store suitability, recommendation

### Takeaway
Recommendation: do not embed a full agent; build a hybrid where ApplyScout's deterministic mapper + answer bank fills first, and a small LLM call (own backend, NIM/Claude) resolves unmapped fields from a trimmed a11y/DOM snapshot, with user clicking Submit. Learn from Page Agent (DOM indexing, MIT, could vendor the DOM-distillation module with notice) and Stagehand (observe -> selector, then deterministic act).

### Cited Findings
- Paid/hosted: Browser Use cloud ($0.02/browser-hour) [GitHub](https://github.com/browser-use/browser-use); Browserbase caching [GitHub](https://github.com/browserbase/stagehand); AgentQL $99/mo [aggregator](https://toolradar.com/tools/agentql/pricing); Claude in Chrome via paid Claude plans [Support](https://support.claude.com/en/articles/12902446-claude-in-chrome-permissions-guide). No paid support plans found for Page Agent, Nanobrowser or WebBrain.
- Page Agent claims no special permissions needed for the library — [GitHub](https://github.com/alibaba/page-agent)

### Inferences
- Hybrid flow: (1) extension content script collects form fields with label/name/aria/autocomplete attributes; (2) deterministic mapper + answer bank fills known fields; (3) residual fields (open questions, unusual dropdowns) sent as a compact JSON of field descriptors to the backend LLM, returning values only (no click authority); (4) fill via native setters + dispatched events, with ARIA-aware combobox handlers; (5) highlight unresolved/low-confidence fields; (6) never invoke submit/Next, user clicks Submit. This keeps permissions to activeTab + scripting on ATS host patterns, simplifying Web Store review, and avoids `debugger`/all-URL permissions that CDP-based tools (Playwright/DevTools MCP) need.
- Hosted browser agents (Browser Use cloud, Browserbase, AgentQL) conflict with a "user's own session / user clicks Submit" model and add INR-unfriendly USD costs.
- Indian users: desktop Chrome only for extension; Android needs a separate path (PWA/share flow), which none of these tools solve.

### Gaps
- Web Store policy review specifics for AI-agent extensions not researched; Chrome Web Store listings for Nanobrowser/WebBrain/Page Agent not opened.
