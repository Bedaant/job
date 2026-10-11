# Server-side browser agents, cloud browser infrastructure and vendor computer-use APIs for AI form filling (state as of 2026-10-11)

Method note: research budget was ~15 tool calls. Primary vendor domains (browserbase.com, docs.browserbase.com, browser-use.com, skyvern.com) returned DNS errors (ENOTFOUND) from WebFetch; the GitHub pages for Skyvern, browser-use and Stagehand WERE read directly. Most pricing/benchmark numbers below come from WebSearch result summaries of vendor docs or third-party pages and are labelled accordingly. Candidates NOT researched in depth (no data found): Induced AI, Multion, Director, Airtop, Apify, Bright Data, Browserless, Perplexity Comet, Microsoft, Project Mariner, Hyperbrowser licence. Do not treat their absence as evidence of anything.

## Licence, maturity, pricing, India region

### Takeaway
Open-source cores are permissive (Browser Use, Stagehand: MIT) except Skyvern (AGPL-3.0, with anti-bot/CAPTCHA kept cloud-only). Cloud browser pricing clusters around $0.02-$0.12 per browser-hour plus proxy GB; no vendor found lists an India region (Browserbase: Oregon, Virginia, Frankfurt, Singapore). Many figures conflict between sources; verify on live pricing pages before budgeting.

### Cited Findings
- Skyvern: licence AGPL-3.0; repo README says core is open source "with the exception of anti-bot measures available in our managed cloud offering"; 23.2k stars, 6,981 commits; anti-bot, proxy network and CAPTCHA solvers are Skyvern Cloud only; TOTP/email/SMS 2FA support listed. No ee/ directory mentioned on the page. Releases section empty in capture, so last release date NOT verified. — [Skyvern GitHub](https://github.com/Skyvern-AI/skyvern) (read directly)
- Skyvern Cloud pricing (search-summary of vendor pricing/blog pages): Free 5,000 credits; Hobby $29/mo for 30,000 credits; Pro $149/mo for 150,000 credits; vendor says not charged per page/step but per workflow execution; previously $0.05/step. Third-party estimate of ~170/1,200/6,200 actions per tier; reviewers warn credits burn fast. — [Skyvern pricing blog](https://www.skyvern.com/blog/launch-week-day-5-simpler-pricing-model/), [Skyvern pricing](https://skyvern.com/pricing), [third-party review](https://dailyaifixs.com/blog/skyvern-pricing-2026-what-credits-really-buy) (pages not opened by me; summary only)
- Browser Use (open source): licence MIT; 117.6k stars, 10,345 commits; cloud advertised at $0.02/browser-hour, stealth browsers, CAPTCHA solving, residential proxies, profiles, recordings; $15 credit for new signups; page itself cautions no config guarantees every CAPTCHA is avoided/solved. Last release date not shown. — [browser-use GitHub](https://github.com/browser-use/browser-use) (read directly)
- Browser Use Cloud pricing is inconsistent across sources: docs example 10-step task on Browser Use 2.0 = $0.01 init + 10 x $0.006 = $0.07; Browser Use LLM $0.002/step; Claude Sonnet 4.5 $0.05/step; main page says steps from $0.002 ($0.0015 on Business); machine-readable page (verified 2026-07-27 per page) says sessions $0.02/hr, docs say $0.06/hr PAYG; tiers Dev $29/mo, Business $299/mo, Scaleup $999/mo. — [Browser Use docs pricing](https://docs.cloud.browser-use.com/pricing), [Models and pricing](https://docs.cloud.browser-use.com/get-started/models-and-pricing), [pricing.md](https://browser-use.com/pricing.md) (search summaries)
- Stagehand: licence MIT (trademark held by Browserbase, Inc.; "Copyright 2026 Browserbase"); 25.6k stars; TypeScript, Python, Go; act/observe/extract with self-healing; works with local Playwright or Browserbase; Browserbase add-ons include residential proxies, persistent contexts, session recordings. Release date not shown. Only quantified claim: "2x faster than Playwright cloud equivalents" (vendor, no data). — [Stagehand GitHub](https://github.com/browserbase/stagehand) (read directly)
- Browserbase plans (docs summary): Free $0 with 1 browser hour, 3 concurrent; Developer $20/mo with 100 hours then $0.12/hr; Startup $99/mo with 500 hours then $0.10/hr, 250 concurrent, 6h session limit; Scale custom; billed per minute (first minute rounded up per official guide). — [Browserbase plans docs](https://docs.browserbase.com/guides/plans-and-pricing) (via search summary; page not opened)
- Browserbase regions: us-west-2 (default), us-east-1, eu-central-1, ap-southeast-1 (Singapore). No Mumbai. — [Browserbase multi-region docs](https://docs.browserbase.com/guides/multi-region) (search summary)
- Steel.dev (per a third-party comparison, not vendor page; flagged possibly competitor-maintained): plans reportedly changed June 2026 to Launch ($0.10/browser-hr, $10/GB proxy, CAPTCHA $3/1,000) and Scale ($0.08/hr, $6/GB); older tiers $29/$99/$499 quoted for Anchor/Steel-like vendors. — [Steel vs Kernel (Steel blog)](https://steel.dev/blog/steel-vs-kernel), [Notte comparison](https://ai.notte.cc/answers/anchor-browser-vs-steel)
- Hyperbrowser: reportedly ~100 credits/hr (~$0.10/hr), proxy $10/GB, free 5,000 credits; Startup $30/mo. Kernel: per-second usage billing, idle time excluded, ~$0.50/hr basic per one review. Anchor: bills split across browser hours, bandwidth, AI steps, session init. All from third-party comparisons. — [agentdeals comparison](https://agentdeals.dev/compare/hyperbrowser-vs-steel), [Notte Anchor vs Kernel](https://ai.notte.cc/answers/anchor-browser-vs-kernel)
- Amazon Nova Act: $4.75 per agent-hour (real elapsed time; human-in-the-loop wait time excluded). GA status unclear in sources. — [AWS Nova pricing](https://aws.amazon.com/nova/pricing)
- Claude in Chrome: reported generally available to paid Claude plans (Aug 2026 signal, low-quality source); earlier April 2026 review said beta, Pro limited to Haiku 4.5. Consumer plans, not an API for embedding in a SaaS. — [Autobound signal](https://www.autobound.ai/signals/live/bdf652d4-7a41-8c8c-ef49-e6cce873ea1c), [Composite review](https://composite.com/blog/claude-chrome-reviews-pricing-alternatives)
- Computer-use API pricing (secondary blog, unverified): OpenAI computer-use-preview $3/$12 per M tokens; Gemini 2.5 Computer Use at Gemini 2.5 Pro rates $1.25/$10. — [ecorpit comparison](https://ecorpit.com/gemini-vs-claude-vs-openai-computer-use-browser-agent-2026/)
- Open GUI models: UI-TARS-1.5 README reports OSWorld 42.5 (100 steps), WebVoyager 84.8, ScreenSpot-Pro 61.6; licence reported Apache-2.0 by a Japanese blog (not confirmed on model card). — [UI-TARS mirror](https://www.gitlink.org.cn/mirrors/UI-TARS), [lilting.ch](https://lilting.ch/en/articles/ui-tars-gui-agent)

### Inferences
- INR conversion (at roughly Rs 85-88 per USD, my assumption, not sourced): Browserbase Developer $20 ~ Rs 1,700-1,760/mo; Skyvern Hobby $29 ~ Rs 2,500; Browser Use 10-step task $0.07 ~ Rs 6; Nova Act $4.75/hr ~ Rs 410/hr. Compute cost of the browser is small; LLM tokens and proxies dominate.
- For an India-focused product, nearest region is Singapore (Browserbase); latency to Indian job portals is not benchmarked anywhere I found.
- Per-user-per-application cost at $0.05-0.50 is plausible for a paid SaaS but is a recurring COGS the extension approach avoids (user's browser and, if BYO, user's LLM).

### Gaps
- Funding amounts, valuations, last-release dates for all vendors: not retrieved (primary sites blocked; funding search returned nothing).
- Pricing for Airtop, Apify, Bright Data, Browserless, Induced, Multion, Director: not found.
- Data residency/DPDP Act statements for any vendor: not found.
- Official, current pricing pages for Browserbase, Steel, Hyperbrowser, Anchor, Kernel could not be opened.

## Reliability and benchmarks

### Takeaway
Vendor-reported scores (WebVoyager ~85%) are far higher than independent/harder evals (Online-Mind2Web automatic eval ~40% on a 2026-05 HAL snapshot). No form-filling-specific or ATS-specific independent benchmark was found. Expect materially lower success than headline numbers on multi-page ATS flows.

### Cited Findings
- Skyvern reports 85.8% on WebVoyager (vendor); README states WebBench 64.4%; Skyvern built Web Bench (5,750 tasks, 1,000 sites) for write actions but no published form-filling breakdown found. — [Skyvern GitHub](https://github.com/Skyvern-AI/skyvern), [AI Agent Index](https://theaiagentindex.com/agents/skyvern)
- Online-Mind2Web (300 tasks, 136 sites): original paper found Operator ~61% human-evaluated and argued earlier agent progress was overstated ("An Illusion of Progress?"). — [arXiv 2504.01382](https://arxiv.org/html/2504.01382v4)
- HAL snapshot dated 2026-05-27 (automatic eval): top entry SeeAct + GPT-5 Medium 42.3% at ~$171 total; Claude-based Browser-Use entries ~39-40%. Yutori (vendor, Nov 2025) claims 78.7% human-eval for its Navigator vs Gemini 2.5 69.0%, Operator 61.3%, Claude 4.0 61.0%. Different judges/scaffolds so not comparable. — [Holistic Agent Leaderboard](https://arxiv.org/pdf/2510.11977), [Yutori](https://yutori.com/blog/introducing-navigator), [benchmarklist HAL](https://benchmarklist.com/benchmarks/hal_online_mind2web/)
- Google claims Gemini 2.5 Computer Use leads Online-Mind2Web/WebVoyager at >70% and ~225 s latency on Browserbase harness (vendor, via secondary blog). — [ecorpit](https://ecorpit.com/gemini-vs-claude-vs-openai-computer-use-browser-agent-2026/)
- OSWorld (desktop, not web forms): Claude Sonnet 4.6 72.7% (Feb 2026), later posts claim higher; every OSWorld score is vendor-self-reported with no independent verification as of June 2026. — [Towards AI](https://pub.towardsai.net/gemini-3-6-flash-hit-83-on-computer-use-a-cheap-flash-model-shouldnt-beat-gpt-5-6-and-grok-5b47fb2f71fc), [ecorpit](https://ecorpit.com/gemini-vs-claude-vs-openai-computer-use-browser-agent-2026/)
- Browser Use publishes BU Bench V2 (60-task subset) results as an image only; no numbers extractable. — [browser-use GitHub](https://github.com/browser-use/browser-use)
- Nova Act "90% reliability" appears only in a secondary review, no methodology. — [vpsranking](https://vpsranking.com/ai/amazon-nova-act/)
- Cost per task: Browser Use docs example $0.07 for 10 steps (vendor-model); HAL run ~$171 total for the 300-task set (~$0.57/task, my arithmetic).

### Inferences
- Realistic ATS multi-page forms (login, uploads, custom dropdowns, required-field validation) are the weak spot; treat 40-85% as the plausible band and measure on your own corpus.
- Seconds per task: only the ~225 s Gemini figure found; DIY agent loops typically take minutes per application (unverified).

### Gaps
- No independent form-filling or ATS benchmark; no per-task seconds for most vendors; Online-Mind2Web live leaderboard not opened.

## Human-in-the-loop (fill, stop before Submit, hand over) and anti-bot/ToS

### Takeaway
Browserbase, Anchor and Steel offer embeddable live views that can be interactive, so a "fill then hand control to user" flow is technically feasible (agent stops by your own logic; stopping before Submit is a prompt/code choice, not a vendor feature). Vendor consumer agents say they confirm before high-risk actions. LinkedIn explicitly bans bots and extensions that automate its site, so server-side bots on job sites carry higher account/ToS risk, and extensions are not exempt either.

### Cited Findings
- Browserbase Live View: iframe-embeddable debugger URL; docs list human-in-the-loop uses (take control, iframes, delegating credentials); `pointer-events: none` makes it view-only. — [Browserbase live view](https://docs.browserbase.com/features/session-live-view)
- Anchor Browser: embedded live UI, same pointer-events pattern; moving to headful-only. Steel: live sessions with `interactive` flag; anyone with the debug URL can view/interact. Cloudflare Browser Run and Firecrawl also offer handoff URLs. — [Anchor docs](https://docs.anchorbrowser.io/llms-full.txt), [Steel live sessions](https://docs.steel.dev/overview/sessions-api/embed-sessions/live-sessions)
- Kernel live view: not found. Nova Act excludes human-wait time from billing, implying built-in HITL. — [AWS Nova pricing](https://aws.amazon.com/nova/pricing)
- Claude in Chrome: asks confirmation before high-risk actions (publish, purchase, share personal data); Aug 2025 pilot prompt-injection success rate cut from 23.6% to 11.2% (123 cases) - Simon Willison called 11.2% still catastrophic; figures from 2025, may be stale. — [The Register](https://www.theregister.com/2025/08/26/anthropic_claude_chrome_warnings/), [Willison](https://simonwillison.net/b/8975)
- LinkedIn: does not permit third-party crawlers, bots, browser plug-ins or extensions that scrape or automate activity; risks account restriction (User Agreement s8.2). — [LinkedIn Help](https://www.linkedin.com/help/linkedin/answer/a1341387)
- Skyvern/Browser Use CAPTCHA and stealth are cloud-paid features; Browser Use cautions CAPTCHAs cannot be guaranteed solved. — GitHub pages above.
- Session persistence: Browserbase persistent contexts, Browser Use profiles (GitHub pages above).

### Inferences
- A server browser logging into a user's LinkedIn/Naukri account from datacenter IPs will likely trip anti-bot and account-risk systems and requires storing user credentials/cookies server-side (security/DPDP liability); a user's own browser avoids both.
- Live-view handoff means the user types into a remote browser, so MFA/OTP and CAPTCHA become the user's job; poor UX versus their own logged-in Chrome.
- Prompt injection from job-description text into a server agent holding sessions is a real risk.

### Gaps
- Greenhouse, Lever, Workday, Naukri, Indeed ToS on automated applications: not retrieved. Airtop/Kernel/Hyperbrowser HITL: not verified.

## AGPL/GPL implications and verdict for ApplyScout

### Takeaway
Do not embed or modify Skyvern (AGPL-3.0) inside the closed-source backend; running it unmodified as a separate internal service is lower risk but needs legal review. MIT options (Browser Use, Stagehand) are safe to embed. Server-side agents fit offline testing/regression, not the production fill-then-Submit flow.

### Cited Findings
- AGPL s13 network clause: triggered when you modify the AGPL program and let users interact with it over a network; a separate application merely calling it generally does not trigger it, but combining code into the AGPL work does, and direct user interaction via API may count. Secondary sources, not legal advice. — [St-Hakky](https://book.st-hakky.com/en/data-science/agpl-3.0-concat-saas-license-considerations), [FOSSA](https://fossa.com/resources/license-compliance-tools/license-compatibility-checker/gpl-3-0-vs-agpl-3-0/), [BearingPoint](https://bearingpoint.services/foss/en/newsblogs/understanding-network-copyleft-in-saas/)
- Skyvern exact SPDX AGPL-3.0; commercial/enterprise licence terms not found. — [Skyvern GitHub](https://github.com/Skyvern-AI/skyvern)

### Inferences
- Importing Skyvern as a Python library into FastAPI = combined work = must open-source the backend (or buy a commercial licence). Modifying it and exposing it to users = must publish modifications. Unmodified, isolated, internal-only (e.g. QA harness not exposed to users) is the safe lane. GPL (non-A) would only matter on distribution, e.g. shipping GPL code in the extension; none of the candidates is GPL.
- Where server agents add value: (1) nightly regression runs of the extension's form filler against real/staged ATS forms using Browserbase or local Playwright + Stagehand/Browser Use (MIT) with synthetic profiles; (2) generating/validating field-mapping selectors offline; (3) possible opt-in fallback for hard forms, but only with live-view handoff and cost cap. Wrong architecture for: the primary user flow (credential custody, anti-bot, ToS, per-application COGS, no India region, slower than in-page DOM fill) given the extension already runs in the user's authenticated browser and the user clicks Submit.
- A cheap hybrid: keep LLM mapping (NIM/Claude) server-side as a text API; keep DOM actuation in the extension.

### Gaps
- No lawyer-grade AGPL analysis; Skyvern commercial licence unseen; stale-risk: all pricing and benchmark numbers date from mid-2026 summaries and should be re-checked.
