# Benchmarks and reliability of AI web/browser agents for form filling (as of 2026-10-11)

Method note: WebFetch could not open any page (DNS failure: arxiv.org, hal.cs.princeton.edu, yutori.com all ENOTFOUND). Everything below comes from WebSearch result summaries only, so most numbers are SECONDARY (aggregators, news) and unverified against primary pages. No primary vendor posts were opened. About 17 search calls were made; several topics (Nova Act, Manus, Page Agent, Nanobrowser, Gemini computer use, Mind2Web-Live, Chromium autofill accuracy, constrained decoding, small-model/NIM costs) returned nothing and are listed under Gaps.

## 1. Benchmarks and leaderboards: what to trust

### Takeaway
General web benchmarks are near-saturated or vendor-reported and say little about job-application forms. The only form-specific academic benchmark found (FormFactory) reports very low whole-form accuracy for MLLM agents, and no public ATS/Workday benchmark exists. Human-evaluated Online-Mind2Web and the paper's own numbers are the most credible general data points.

### Cited Findings
- Online-Mind2Web: 300 tasks, 136 live websites; the authors report that, under human evaluation, most recent agents except Claude Computer Use 3.7 and Operator underperform the simple SeeAct baseline; Operator reached 61%; their WebJudge LLM judge agrees with humans about 85% of the time (so roughly 1 in 7 judgments differs) — [arXiv 2504.01382 via search](https://arxiv.org/html/2504.01382v4)
- Online-Mind2Web, automatic-judge board (HAL, Princeton): top entry GPT-5 medium 42.33%; Browser-Use with Claude-3.7 Sonnet 39.33%; HAL notes costs are computed without caching benefits — [benchmarklist.com HAL mirror](https://benchmarklist.com/benchmarks/hal_online_mind2web/), [HAL](https://hal.cs.princeton.edu/online_mind2web)
- Online-Mind2Web, human-eval board: Yutori lists "Hark" at 97.7% (updated 5 Aug 2026) and Navigator n1.5 at 97.3%; OpenAI Operator 61.3%; Claude Computer Use 3.7 56.3% on the OSU HF board. Sources disagree sharply with the HAL board (42%), because of judge/method differences; the 97% figures come from a vendor (Yutori) hosting its own leaderboard — [Yutori leaderboards](https://yutori.com/leaderboards.md), [careerflow snapshot](https://www.careerflow.ai/human-data/online-mind2web)
- OSWorld-Verified: aggregators report Qwen3.8 Max 86.1% (10 Sep 2026), Claude Fable 5 / Mythos 5 about 85-86%, and an agent system at 90.2% (Yutori board, 7 Aug 2026); top eight span only ~6 points, suggesting saturation; provider-reported rows are mixed in — [BenchLM](https://www.benchlm.ai/benchmarks/osworld-verified), [Yutori](https://yutori.com/leaderboards/osworld-verified.md)
- WebArena-Verified: only one or two rows exist (Qwen3.8-27B 64.8%; Muse Spark 1.1 69%, July-Aug 2026), no broad ranking — [LLM Stats](https://llm-stats.com/benchmarks/webarena-verified), [BenchLM](https://benchlm.ai/benchmarks/webarena-verified)
- WebChoreArena (532 tasks on WebArena sites): top overall 44.9% in a May 2026 snapshot; another board says 54.8% (Gemini 2.5 Pro) — conflicting — [benchmarklist](https://benchmarklist.com/benchmarks/webchorearena/), [Steel](https://leaderboard.steel.dev/registry/benchmarks/webchorearena)
- BrowseComp (information-seeking, not form filling): GPT-5.6 Sol 92.2%, Kimi K3 91.2%, Claude Opus 5 90.8% (22 Aug 2026, third-party tracker) — [BenchLM](https://www.benchlm.ai/benchmarks/browsecomp)
- Mind2Web 2: 130 long-horizon research tasks with citation-backed answers; no 2026 score table found — [alphaxiv](https://alphaxiv.org/benchmarks/the-ohio-state-university/mind2web-2)
- WebVoyager: Browser Use claims 89.1% (own Dec 2024 report); Skyvern claims 85.85% (own blog, "updated July 2026"); both vendor-run, and reviewers call them dated/self-measured — [Skyvern blog](https://www.skyvern.com/blog/skyvern-2-0-webvoyager-benchmark-results/), [comparison](https://www.agenticwire.news/article/browser-use-vs-stagehand)
- Web Bench (Halluminate/YC, 5,750 tasks, 452 live sites, covers login, form filling, file download, CAPTCHA): aggregator ranks rtrvr 79.9%, Operator HITL 76.5%, Anthropic Computer Use 66.0%, Skyvern 2.0 64.4%, OpenAI CUA 59.8%, browser-use 43.9%; no per-category form numbers found; YC launch text says agents struggle most with authentication, form filling and file downloads — [benchmarklist](https://benchmarklist.com/benchmarks/webbench_ai/), [YC launch](https://www.ycombinator.com/launches/NdK-web-bench-a-new-way-to-compare-ai-browser-agents)
- FormFactory (20-25 forms, 8 domains, text/dropdown/date picker/checkbox/file upload; Flask backend, ground-truth key-values): headline "no model surpasses 5% accuracy" (whole-form, mid-2025 MLLMs), blamed on layout reasoning and field-value alignment — [arXiv 2506.01520](https://arxiv.org/pdf/2506.01520)
- FormGym (document forms, not web): GUI agents score 10.6-68.0% with high cost/latency — [arXiv 2506.14079](https://arxiv.org/pdf/2506.14079)
- Job/ATS-specific: no independent public benchmark found. Vendor JobWizard claims "90%+ Workday fill rate", unpublished methodology (marketing) — [JobWizard](https://jobwizard.ai/compare/jobwizard-vs-simplify)

### Inferences
- Benchmark scores of 85-97% (OSWorld, WebVoyager, human-eval Online-Mind2Web) are largely vendor-hosted/saturating and are not evidence about multi-page ATS wizards; the same benchmark ranges 42% to 97% depending on judge and who runs it.
- The FormFactory <5% figure is from mid-2025 models on a synthetic suite with strict whole-form scoring; frontier 2026 models are likely better but no re-run was found. Treat as "whole-form exact correctness is hard", not a current rate.
- Realistic planning range for real multi-step forms (my estimate, not sourced): per-form fully-correct unattended fill well below the headline 60-90% numbers, hence human review is mandatory.

### Gaps
- No ATS (Workday, Greenhouse, Lever, iCIMS) agent evaluation; Mind2Web-Live, Form-NLU not found; no primary leaderboard page could be opened; WebArena/VisualWebArena classic scores not retrieved.

## 2. Production browser agents: cost, speed, failure modes

### Takeaway
No independent head-to-head of Browser Use, Stagehand and Skyvern exists; cost and success figures are vendor or comparison-blog estimates. Authentication, forms and file download are the known weak categories.

### Cited Findings
- No independent head-to-head found; numbers are self-reported — [search synthesis; aicoolies/futurepicker/agenticwire comparisons](https://www.agenticwire.news/article/browser-use-vs-stagehand)
- Blog cost estimates (unverified): Skyvern cloud ~$0.50 per 10-step task; Stagehand $0.01-$0.06 plus Browserbase session fees; Browser Use ~$0.07 per 10-step task — [aicoolies Skyvern review](https://aicoolies.com/reviews/skyvern-review)
- Stagehand v4 vs Playwright MCP with Claude Sonnet 5: median 6.9k input tokens per call vs 12.9-14.1k, but Stagehand context grew ~1.8k tokens/step vs ~0.55k over a 12-page flow (re-reads page after each submission) — [ITNEXT benchmark](https://itnext.io/why-does-playwright-mcp-use-so-many-tokens-da56b6dbd2db)
- Stagehand caching: cache miss if page structure changes, then LLM is called; locator-scoped act/observe/extract bypass server cache; Browserbase claims ~2x faster and ~30% cheaper on repeats (vendor) — [Stagehand docs](https://docs.stagehand.dev/v4/best-practices/caching), [Browserbase](https://browserbase.com/blog/playwright-to-stagehand-migration)

### Inferences
- A deterministic per-ATS mapping is effectively "perfect caching"; Stagehand-style caching only helps on stable pages and per-user values change anyway.

### Gaps
- No numbers found for Operator/ChatGPT agent, Claude in Chrome, Gemini computer use, Nova Act, Manus, Page Agent, Nanobrowser on forms; no per-failure-mode rates (dropdowns, date pickers, shadow DOM, iframes, CAPTCHA) beyond qualitative statements; no DOM-vs-screenshot token comparison; no small-model/NIM/constrained-decoding evidence.

## 3. Field mapping versus end-to-end agents; fabrication

### Takeaway
Classical field-type classification is well established; evidence on LLM fabrication in application answers is thin and synthetic, but shows grounding plus deterministic layers cuts it sharply.

### Cited Findings
- Browsers use heuristic rules for field labels; Microsoft research proposes ML replacement — [arXiv 1912.08809](https://arxiv.org/pdf/1912.08809)
- Formasaurus: two-stage classifier (form type then ~50 field types) — [docs](https://formasaurus.readthedocs.io/en/latest/howitworks.html)
- Microsoft patent claims multi-class decision forest up to 95% precision with sentence-transformer features (patent claim, not independent) — [USPTO 12688353](https://image-ppubs.uspto.gov/dirsearch-public/print/downloadPdf/12688353)
- Hobby model card: fine-tuned Qwen 96.5% vs keyword heuristic 72.3% on 260 fields (anecdotal) — [HF ProCreations/Zap](https://huggingface.co/ProCreations/Zap)
- Resume rewriting study (25 synthetic resumes): undefended baselines 2.5-5.4 detected hallucinations per resume; five-layer defence cut to ~0.04-0.24; prompt grounding alone reached zero only at low temperature with a capable model (preprint, not peer reviewed) — [arXiv 2607.01457](https://arxiv.org/pdf/2607.01457)
- Hiring pipeline study: fully automated baseline invented names/contact details that were deliberately omitted; fabrications propagate across stages; guardrails plus human checkpoints evaluated (arXiv ID 2608.26171 looks anomalous, verify) — [arXiv 2608.26171](https://arxiv.org/pdf/2608.26171)

### Inferences
- Supports: verified fact store, deterministic fill, LLM only to classify/choose among provided options, abstain-and-ask when no fact matches, user clicks Submit.

### Gaps
- No published accuracy for Simplify, Chromium autofill ML, or LLM-fallback pipelines; no measurement of fabrication on application screening questions (e.g., work authorization, years of experience).

## 4. Prompt injection against browser agents

### Takeaway
Vendors report single-digit to near-zero adaptive attack success for newest models, yet OpenAI says it may never be fully solved and results do not transfer across settings; treat all job-posting text as hostile.

### Cited Findings
- Anthropic Claude for Chrome preview (Aug 2025): 23.6% attack success across 123 tests/29 scenarios without mitigations, 11.2% with, vs 19.4% for older computer use; 4 browser-specific attacks 35.7% to 0% (vendor red team) — [Anthropic](https://www.anthropic.com/news/claude-for-chrome), [TechSpot](https://www.techspot.com/news/109252-claude-chrome-arrives-despite-11-prompt-injection-success.html)
- Anthropic Nov 2025: Opus 4.5 ~1% success vs adaptive Best-of-N attacker (100 attempts/environment); Anthropic itself says 1% is meaningful risk — [Anthropic](https://www.anthropic.com/research/prompt-injection-defenses)
- Opus 4.6 system card via WorkOS: GUI environment 78.6% without safeguards, 0% in constrained coding setting after 200 attempts — [WorkOS](https://workos.com/blog/ai-agent-governance-prompt-injection-surface-not-model)
- Independent June 2026 arXiv (793-episode CUA-HandCrafted): 0/140 multi-step attacks on Claude Sonnet 4.6 and GPT-5.4 (95% upper bound 2.6%), but same weights up to 100% on a coding-agent skill-injection benchmark; cites RL-Hammer 98% on GPT-4o / 26% Claude 3.5 Sonnet — [arXiv 2606.05233](https://arxiv.org/pdf/2606.05233)
- Secondary report: "Opus 5" 0% across 129 browser scenarios with Auto Mode, 3.7% without (unverified against system card) — [The Decoder](https://the-decoder.com/opus-5-may-have-solved-browser-based-prompt-injection-the-biggest-security-flaw-haunting-ai-agents/)
- Brave (Oct 2025): near-invisible text in screenshots (OCR) hijacked Comet; Fellou sends page content to LLM; called systemic across AI browsers — [Brave](https://brave.com/blog/unseeable-prompt-injections/)
- OpenAI (Dec 2025): prompt injection against Atlas "may never be fully solved" — [The Decoder](https://the-decoder.com/openai-admits-prompt-injection-may-never-be-fully-solved-casting-doubt-on-the-agentic-ai-vision/)
- WASP benchmark of web-agent injection exists — [alphaxiv](https://www.alphaxiv.org/abs/2504.18575v1)

### Inferences
- Safe design for a job-form filler: never give an agent page text with tool authority; LLM sees field labels/options only as data and returns a constrained choice (enum/index) or abstain; no navigation/submit/exfil actions available to the model; strip hidden/off-screen text; allow-listed domains; user click on Submit.

### Gaps
- No Brave/OpenAI quantitative rates; primary system cards not opened; no job-posting-specific injection study.
