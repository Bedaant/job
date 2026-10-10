# UI Discovery (uidiscovery.com) and user-journey design patterns: onboarding, activation, dashboards, upgrades and retention

Research date: 2026-10-10. Access note: uidiscovery.com could not be opened from this sandbox (WebFetch returned `getaddrinfo ENOTFOUND`, and direct curl was refused by the proxy with 403). lennysnewsletter.com, jonesday.com and legal500.com also failed DNS. Everything about UI Discovery below comes from **search-engine snippets and summaries of its homepage**, not from reading the site. Several benchmark figures come from search summaries of primary pages. Where I could not open the primary page, the finding says so.

## 1. What is uidiscovery.com: who runs it, what it catalogues, how it is organised, its Claude Code prompts or MCP, and pricing

### Takeaway
UI Discovery describes itself as "Real-world UI & UX design inspiration". It is a searchable library of real websites, iOS apps, web apps or dashboards, and their page sections. It also runs a remote MCP server so Claude Code can query the library and pull a design brief, design tokens and an "AI-ready build prompt" for each reference. Today it is organised by **site, app and section**, not by user journey. A journey-level product called "Flow Kits" is announced but marked as still in development. I found no owner or pricing information.

### Cited Findings
- The site title is "UI Discovery — Real-world UI & UX design inspiration". — [UI Discovery](https://uidiscovery.com/)
- Stated catalogue size per search snippets of the homepage: about **2,647+ websites, 3,836 iOS apps and 111,083+ real sections**, "including heroes, pricing tables, onboarding flows and more". These are counts as indexed by search, so the live numbers may differ. — [UI Discovery](https://uidiscovery.com/)
- How it is organised: the live library covers websites, iOS apps, web apps and dashboards, plus the sections inside them, "with search, compare and saved boards on top". — [UI Discovery](https://uidiscovery.com/)
- **Flow Kits** are described as a planned section "for multi-step product journeys" that is still in development. "Graphics, Templates, Motion and Flow Kits are in the works and will open in the nav when they're ready." — [UI Discovery](https://uidiscovery.com/)
- Each reference reportedly includes "its palette, fonts and an AI-ready build prompt". — [UI Discovery](https://uidiscovery.com/)
- Claude Code integration is a remote MCP server, added with: `claude mcp add --transport http uidiscovery https://uidiscovery.com/mcp` — [UI Discovery](https://uidiscovery.com/)
- Connected agents reportedly get seven MCP tools: `search_screens`, `search_sections`, `search_flows`, `search_sites`, `get_design_brief`, `get_image_plan`, `get_design_tokens`. — [UI Discovery](https://uidiscovery.com/), via search summary
- Comparable products exist. Mobbin also offers an MCP for Claude Code, marketed as "600,000+ design references". — [Griffin Wooldridge blog](https://griffinwooldridge.com/blog/mobbin-mcp-claude-code-design-references); [João Queirós blog](https://www.ai.joaoqueiros.com/blog/mobbin-mcp-claude-code-ui-reference-workflow)
- Name collision: "UI Discover" and "Product UI Discovery" are unrelated community Claude Code skills on skill registries (one inventories components and crawls routes with Playwright). Do not confuse them with uidiscovery.com. — [ClaudSkills](https://claudskills.com/skills/ui-discover/); [skills.sh](https://www.skills.sh/janpereira-dev/ngautopilot/product-ui-discovery)

### Inferences
- The intended workflow seems to be: connect the MCP in Claude Code, search for a real reference (for example, "pricing table" or "onboarding flow"), then call `get_design_brief` or `get_design_tokens` so the agent builds from real-world precedent instead of a blank prompt. A `search_flows` tool exists even though the "Flow Kits" browsing section is not live. That suggests some flow-level data can already be queried over MCP, but this is unverified.
- For an AI job-application SaaS, the most relevant queries would be onboarding flows, pricing tables or paywalls, and dashboard sections.

### Gaps
- **Owner or operator:** no search result named who runs uidiscovery.com.
- **Pricing and access:** no pricing page or plan details surfaced. I could not confirm whether the MCP or library is free, gated or paid.
- **Prompts:** I could not see an actual "AI-ready build prompt" or whether the site publishes a separate prompt library for Claude Code. Only the MCP command and tool names are confirmed via snippets.
- **Journey taxonomy:** I could not confirm whether references are tagged by journey stage (onboarding, paywall, retention and so on) beyond "onboarding flows" being mentioned as a section type.
- Site launch date and update cadence are unknown.

## 2. Onboarding and activation: what strong products do

### Takeaway
The best products define a measurable activation event tied to the core value: a team sending messages, a meeting booked, a first design made. They then strip everything between signup and that event. That means asking one or two personalisation questions, giving templates or sample data, using short checklists, and in high-touch cases running human onboarding. "Magic numbers" are useful heuristics, not laws.

### Cited Findings
**Benchmarks (dated)**
- Lenny Rachitsky's activation survey (about 2022–23, 500+ products): average activation **34%**, median **25%**. SaaS only: average **36%**, median **30%**. He treats the 60th percentile as "good" and the 80th as "great". About 6% of respondents had time-bound activation, with a median window of 10 days and a mode of 7. Figures are taken from a search summary because lennysnewsletter.com was unreachable. — [Lenny's Newsletter, "What is a good activation rate"](https://www.lennysnewsletter.com/p/what-is-a-good-activation-rate)
- Userpilot 2024: average activation **37.5%**, median **37%** (62 B2B companies on its activation dashboard). By industry: AI & ML 54.8%, CRM & Sales 42.6%, MarTech 24%, Healthcare 23.8%, HR 8.3%, FinTech & Insurance 5%. Average core feature adoption was 24.5% (median 16.5%, 181 companies). This is vendor data, and sample descriptions are inconsistent (62 vs 547 companies) across Userpilot materials. — [Userpilot Activation Benchmark 2024](https://userpilot.com/blog/user-activation-rate-benchmark-report-2024/); [Userpilot core feature adoption](https://userpilot.medium.com/core-feature-adoption-rate-benchmark-report-2024-ba96b1d02ca5)

**Aha moments and activation metrics**
- Facebook: "7 friends in 10 days" was named by Chamath Palihapitiya as the north star on the path to 1B users. Mode cautions that such numbers "shouldn't be viewed as scientific tipping points; they're often round numbers picked in the middle of a range". — [Mode](https://mode.com/blog/facebook-aha-moment-simpler-than-you-think/)
- Mixpanel makes the same point: it "could have been '10 friends in 12 days' or even 'five friends in one day'". — [Mixpanel, "Magic numbers are an illusion"](https://mixpanel.com/blog/magic-numbers-are-an-illusion/)
- Slack: teams that had sent about **2,000 messages** became long-term users. This is commonly attributed to Stewart Butterfield, and Appcues frames it as a team-level activation metric. A widely repeated "93% retention" figure is unverified. — [Appcues aha examples](https://www.appcues.com/blog/aha-moment-examples)

**Named product patterns**
- **Canva:** asks "What will you be using Canva for?" and tailors what it shows next. Appcues GoodUX calls it a tailored onboarding flow. A 2026 teardown found the personalisation was effectively one question, then a fairly generic templates page, with about 9 clicks to onboard. Early Canva (about 2014) used interactive "challenges" to give small wins. — [Appcues GoodUX](https://goodux.appcues.com/blog/canvas-user-tailored-onboarding-flow); [Meagan Glenn teardown (2026)](https://meaganglenn.beehiiv.com/p/the-teardown-canva); [UserTesting Canva case](https://www.usertesting.com/blog/canva-case-study)
- **Calendly:** the checklist uses a progress bar ("connect a calendar", "set up booking page"). Activation is commonly treated as booking the first meeting. The share-link pop-up appears right after an event type is created, though the link is harder to find again once dismissed. The welcome email has a single CTA. — [Digistorms (2026)](https://www.digistorms.ai/blog/saas-onboarding-email-sequence); [Zapier](https://zapier.com/blog/how-to-use-calendly/); [Val Geisler teardown (older)](https://www.valgeisler.com/email-onboarding-tear-down-calendly/)
- **Superhuman:** ran human, 1:1 onboarding for about five years. Early sessions lasted 1–1.5 hours, and later ones were 30-minute calls with a specialist. They covered shortcuts, settings and import, and collected Sean Ellis PMF survey data. Rahul Vohra says this was the best way to get users to a "wow" moment, not manufactured scarcity. At peak, about 20 people did manual onboarding. — [First Round Review](https://review.firstround.com/superhuman-onboarding-playbook/); [Lenny's Newsletter](https://www.lennysnewsletter.com/p/superhumans-secret-to-success-rahul-vohra)

**Checklists and progressive disclosure**
- Appcues split one long onboarding checklist into two short ones, and completion rose from **under 2% to about 25%** (vendor self-report). Their docs recommend 3–5 items and claim lists with more than 5 items see significantly lower completion. They also warn that completion is not success unless it ties to retention. — [Appcues bite-sized checklists](https://goodux.appcues.com/behind-the-experience/appcues-bite-sized-checklists); [Appcues docs](https://docs.appcues.com/best-practices/checklist-best-practices); [Appcues onboarding metrics](https://www.appcues.com/blog/user-onboarding-metrics-and-kpis)
- NN/g: progressive disclosure "defers advanced or rarely used features to a secondary screen, making applications easier to learn and less error-prone". It shows the few most important options first. For forms, show only what is relevant to the current task and add fields as users progress. — [NN/g Progressive Disclosure](https://www.nngroup.com/articles/progressive-disclosure/); [NN/g cognitive load in forms](https://www.nngroup.com/articles/4-principles-reduce-cognitive-load/)

### Inferences
- For an AI job-application SaaS, a candidate activation event is "first tailored application (CV plus cover letter) generated and submitted or exported within the first session". A team-level analogue of Slack's metric could be "N applications sent in the first 7 days". Validate any threshold against your own retention cohorts, as Mixpanel and Mode warn.
- Minimal info first: ask the target role or paste a job link, plus upload a CV (one question, like Canva). Defer preferences, integrations and profile completeness to later prompts, which is progressive disclosure.
- Use sample data or templates, for example a pre-filled demo job, so value shows before the user has done any setup work.

### Gaps
- No primary data source for Notion's, Duolingo's or Loom's onboarding-specific metrics was retrieved. Notion's template-gallery onboarding is widely discussed but was not sourced here.
- Reforge and Amplitude activation benchmarks were not retrieved. Their sites were not queried successfully in this session.
- No controlled study tying the Zeigarnik or endowed-progress effect to SaaS checklists was found. It appears only as vendor design advice.

## 3. Dashboards and home screens: what goes on the first screen after login

### Takeaway
The evidence base here is thin. The strongest guidance is NN/g's empty-state rules: show system status, teach the system, and give a direct path to key tasks. The consistent product pattern is a **next-best-action**-led first screen for new users, such as Calendly's checklist with progress bar. Metrics come later, once there is data to show.

### Cited Findings
- NN/g says empty dashboards and lists should not be left blank. Blank "creates confusion and decreases user confidence" and wastes learnability and discoverability. Its three guidelines are: **communicate system status, help users learn the system, provide direct pathways to key tasks**. — [NN/g, Designing Empty States in Complex Applications](https://www.nngroup.com/articles/empty-state-interface-design/)
- Calendly's new-user home centres on a progress-bar checklist (connect calendar, set up booking page) that leads to the first booked meeting. — [Digistorms (2026)](https://www.digistorms.ai/blog/saas-onboarding-email-sequence)
- UI Discovery explicitly catalogues "web apps and dashboards" as a category, so it can be a source of real dashboard references via `search_screens` or `search_sections`. — [UI Discovery](https://uidiscovery.com/)

### Inferences
- For a job-application SaaS, day-1 home could show one primary action ("Tailor your CV to a job: paste link"), a short 3–5 item checklist, and the status of anything in progress. After activation, switch to a pipeline view (applications by stage, follow-ups due, interviews) with the single next action at the top. Keep vanity metrics such as "applications sent" secondary to outcome signals such as responses and interviews.

### Gaps
- No credible quantitative study on "focus vs metrics" first-screen designs was found. Linear, Loom and Notion home-screen rationale was searched but not found in this session.

## 4. Upgrade and paywall patterns

### Takeaway
Free trials convert at roughly 2–3x the rate of freemium. The best freemium products show limits and premium value **inside the workflow at the moment of need**: Grammarly shows locked advanced suggestions inline, and Notion limits blocks only in shared workspaces. Pricing pages stay public and simple.

### Cited Findings
- Kyle Poyar and Lenny Rachitsky (2023, 1,000+ products): free trial "good" free-to-paid **8–12%**, "great" **15–25%**. Self-serve freemium "good" **3–5%**, "great" **8–12%**. About a fifth of freemium products converted below 2.5%, versus 7% of trial products. This comes from a search summary of the August 2023 Lenny piece "What is a good free-to-paid conversion rate?", which was not opened directly. — [Appcues summary citing the data](https://www.appcues.com/blog/free-to-paid-conversion-strategies)
- Opt-in (no card) vs opt-out (card required) trials: figures vary widely across secondary sources. One example is about 8.9% for no-card trials, attributed to a ChartMogul 2026 study, versus about 25–60% for card-required trials. Treat these as low-confidence. — [Kirro](https://kirro.io/free-trial-conversion-rate); [Pulseahead](https://www.pulseahead.com/blog/trial-to-paid-conversion-benchmarks-in-saas)
- **Grammarly:** the free plan includes spelling and grammar. The paid tier ("Pro", replacing "Premium") includes full-sentence rewrites and tone adjustment, at $12 per member per month billed annually per its plans page (as surfaced in search, 2026). Locked advanced suggestions appear inside the workflow as the upgrade hook. — [Grammarly plans](https://www.grammarly.com/plans); [Grammarly Pro](https://www.grammarly.com/pro); [How-To Geek](https://www.howtogeek.com/695344/grammarly-premium-review/); [Appcues freemium upgrade prompts](https://www.appcues.com/blog/best-freemium-upgrade-prompts)
- **Notion:** a solo Free workspace gets unlimited pages and blocks. In multi-member Free workspaces you can still read and edit existing blocks but cannot add new ones past the limit. Third parties cite about 1,000 blocks. So the paywall triggers at the collaboration moment, which is where team value appears. — [Notion pricing](https://www.notion.com/pricing)
- A paywall-CRO Claude Code skill advises against showing upgrade prompts during onboarding, because it is too early. — [aitmpl paywall-upgrade-cro](https://www.aitmpl.com/component/skills/business-marketing/paywall-upgrade-cro)

### Inferences
- For a job-application SaaS: offer a free tier with a visible usage meter (for example, N tailored applications per month). Put the upgrade prompt at the moment of value, such as after a user sees a tailored CV, or when they hit the limit mid-application, with their work preserved. Avoid prompts during the first-run flow. Publish transparent pricing.
- A no-card trial is the safer choice under dark-pattern rules (see section 5, India's "subscription trap" language on payment details for free trials).

### Gaps
- Duolingo and Spotify paywall specifics (Super or Max tiers, ad-supported free tier, shuffle limits) were not sourced in this session.
- The primary Lenny/Poyar conversion article and OpenView data were not opened directly.

## 5. Retention: notifications, streaks, re-engagement, dark patterns and regulation

### Takeaway
Duolingo is the canonical case. Its retention gains came from rigorously A/B-tested streaks, streak freezes, leaderboards and well-timed reminders, and an early gamification push was flat. Retention mechanics must stay clear of dark patterns. **India's CCPA 2023 guidelines** explicitly ban subscription traps, confirmshaming and nagging. The **US FTC "Click-to-Cancel" rule was vacated on 8 July 2025** and was not in effect as of May 2026, but about 30 US state regimes and ROSCA still apply.

### Cited Findings
**Duolingo** (primary source: Jorge Mazal's Lenny's Newsletter guest post, about 2023. The page itself was unreachable, so facts come from search summaries.)
- DAU grew **about 4.5x over four years**, driven by work on leaderboards, notifications and streaks. — [Lenny's Newsletter, Jorge Mazal](https://www.lennysnewsletter.com/p/how-duolingo-reignited-user-growth)
- The first gamification update was "completely neutral" for retention and DAU. **Leaderboards** then lifted learning time by **17%** and tripled the number of highly engaged learners. — [Lenny's Newsletter, Jorge Mazal](https://www.lennysnewsletter.com/p/how-duolingo-reignited-user-growth)
- Allowing two or three **streak freezes** instead of one "significantly improved" return rates and DAU. A late-night "streak saver" notification showed "considerable upside". — [Lenny's Newsletter, Jorge Mazal](https://www.lennysnewsletter.com/p/how-duolingo-reignited-user-growth)
- Duolingo's streak PM (Jackson Shuttleworth) reports a large retention jump from a 1- to 2-day streak, and that users who reach 7 days are more likely to stay. — [Recall summary of Lenny's Podcast](https://www.getrecall.ai/summary/lennys-podcast/behind-the-product-duolingo-streaks-or-jackson-shuttleworth-group-pm-retention-team)
- Secondary sources report Duolingo had 58.7M DAU in Q2 2026. This is unverified against an earnings release. — [Okara](https://okara.ai/blog/how-duolingo-grew)

**Dark patterns and regulation**
- **India:** the CCPA notified the *Guidelines for Prevention and Regulation of Dark Patterns, 2023* on **30 November 2023**, effective immediately. They apply to platforms offering goods or services in India, advertisers and sellers. Annexure I specifies **13** dark patterns. — [SCC Online](https://www.scconline.com/blog/post/2023/12/04/ccpa-notifies-guidelines-for-prevention-and-regulation-of-dark-patterns-2023-legal-news/); [Mondaq](https://www.mondaq.com/india/social-media/1409216/the-guidelines-for-prevention-and-regulations-of-dark-patterns-2023-an-analysis)
  - "**Subscription trap**" covers making cancellation of a paid subscription impossible or complex and lengthy, hiding the cancellation option, and, per one source, forcing payment details for free trials. — [exchange4media](https://www.exchange4media.com/marketing-news/ccpa-new-guidelines-to-target-dark-patterns-like-subscription-trapping-nagging-131246.html); [Ahlawat & Associates](https://www.ahlawatassociates.com/blog/guidelines-for-prevention-and-regulation-of-dark-patterns-2023)
  - "**Confirm shaming**" means using fear, shame, ridicule or guilt to push a purchase or continuation. The guidelines illustrate it with "I will stay unsecured". "**Nagging**" is also listed. — [SCC Online](https://www.scconline.com/blog/post/2023/12/04/ccpa-notifies-guidelines-for-prevention-and-regulation-of-dark-patterns-2023-legal-news/); [exchange4media](https://www.exchange4media.com/marketing-news/ccpa-new-guidelines-to-target-dark-patterns-like-subscription-trapping-nagging-131246.html)
  - On **5 June 2025** the CCPA issued an advisory asking e-commerce platforms to self-audit for dark patterns within three months. Enforcement has included fines, for example PhysicsWallah ₹5 lakh and McAfee ₹1 lakh, as reported. — [Chambers](https://chambers.com/articles/dark-patterns-and-the-limits-of-self-policing-a-critical-look-at-the-ccpa-s-june-2025-advisory); [PIB](https://www.pib.gov.in/PressReleasePage.aspx?PRID=2268302&reg=3&lang=1); [AZB & Partners](https://www.azbpartners.com/bank/regulatory-crackdown-on-dark-patterns-ccpas-enforcement-actions-and-emerging-compliance-landscape-in-indian-e-commerce/)
  - Critics argue the regime is still "soft law". — [IAPP](https://iapp.org/news/a/india-s-ccpa-guidelines-on-dark-patterns-welcome-signal-but-law-is-still-soft)
- **US FTC "Click-to-Cancel" (Negative Option Rule, 2024):** vacated in full by the 8th Circuit on **8 July 2025** (*Custom Communications, Inc. v. FTC*) on procedural grounds, because no preliminary regulatory analysis was done despite a projected cost above $100M per year. — [Crowell](https://www.crowell.com/en/insights/client-alerts/eighth-circuit-cancels-click-to-cancel); [WilmerHale](https://www.wilmerhale.com/en/insights/client-alerts/20250801-eighth-circuit-vacates-the-ftcs-click-to-cancel-rule-but-federal-and-state-regulators-likely-to-remain-active)
  - The FTC moved to revive it in early 2026 (Crowell, February 2026). Jones Day (May 2026) says the 2024 rule is **not in effect**. — [Crowell](https://www.crowell.com/en/insights/client-alerts/clicking-all-the-right-boxes-ftc-moves-to-revive-click-to-cancel-rule-following-eighth-circuit-vacatur); [Jones Day](https://www.jonesday.com/en/insights/2026/05/ftc-revives-clicktocancel-rule-new-risks-for-subscription-businesses)
  - About 30 US jurisdictions, including California, Colorado and New York, have similar auto-renewal and cancellation requirements. — [Dickinson Wright](https://www.dickinson-wright.com/news-alerts/rule-interrupted-click-to-cancel-is-click-to-gone)
- **California (CPPA, a separate regime from India's CCPA):** the updated privacy regulations, finalised in November 2025, give dark-pattern examples, such as making a "yes" button more prominent than "no". — [Inside Privacy](https://www.insideprivacy.com/state-privacy/california-finalizes-updates-to-existing-ccpa-regulations/)

### Inferences
- For a job-application SaaS, ethical retention levers include:
  - digests of new matching jobs
  - follow-up reminders on applications pending for more than 7 days
  - interview-prep nudges
  - weekly progress ("5 applications, 2 responses")
  - an optional "application streak" with freezes or forgiveness, following Duolingo, so users aren't punished for breaks

  Frequency caps and one-click notification controls help avoid "nagging".
- For compliance (India plus US states): cancellation as easy as signup and inside the app, no confirmshaming copy on cancel or downgrade screens, no card required for trials (or clear renewal reminders), and no pre-ticked add-ons or drip pricing. An AI job tool serving Indian users falls within the CCPA guidelines' scope as a platform offering services in India.

### Gaps
- I could not verify the full official list of all 13 Indian dark patterns from a primary source (gazette or consumeraffairs.nic.in) in this session. From prior knowledge it also includes false urgency, basket sneaking, forced action, interface interference, bait and switch, drip pricing, disguised advertisement, trick question, **SaaS billing** and rogue malware. This is unverified here, so confirm against the gazette text.
- Whether the FTC finalised a replacement rule after May 2026 is unknown.
- Mixpanel or Amplitude retention-curve benchmarks (for example, Amplitude's product benchmark data) were not retrieved.
- Spotify and Duolingo paywall-in-retention specifics were not sourced.
