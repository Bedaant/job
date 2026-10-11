# Legal, ToS, platform-policy and licensing risks of AI job-application form filling (ApplyScout; India, later UAE/Singapore) - state as of 2026-10-11

Scope note: research, not legal advice (stated once). Coverage is PARTIAL: developer.chrome.com, linkedin.com (fetch) and other primary domains failed DNS in this sandbox (WebFetch ENOTFOUND), so most findings come from WebSearch result summaries (secondary). Items tagged [UNVERIFIED-BACKGROUND] come from the researcher's own prior knowledge, have no source here, and must be checked before use. No verbatim primary-source quotations were obtained; none are presented.

## 1. Open-source licence implications (MIT, Apache-2.0, GPL-3.0, AGPL-3.0; distribution; SaaS loophole)

### Takeaway
Licence text/FSF pages could not be fetched; only AGPL s.13 mechanics were confirmed via secondary summary. Working rule for ApplyScout: do not bundle or link GPL/AGPL agent code (WebBrain GPL-3.0, Skyvern AGPL-3.0) into the closed-source extension or a modified hosted backend; MIT/Apache-2.0 are safe with notice preservation.

### Cited Findings
- AGPL s.13 trigger: the extra source-offer duty applies when you MODIFY the Program; hosting an unmodified copy does not by itself create it. Modified versions must prominently offer all remote network users the Corresponding Source at no charge. — [AGPL summary search result set](https://thebuild.com/blog/the-agpl-radioactive-by-design/) (secondary)
- Internal-organisation copying/running is not distribution; FSF FAQ treats web apps/servers accepting network requests as in scope of the network clause. — same result set (secondary, via search summary)
- The network clause is described as untested in court; edges uncertain. — same (secondary)

### Inferences
- A Chrome extension is shipped as code to each user's machine, so it is almost certainly "conveying/distribution" under GPL-3.0 and AGPL-3.0: embedding or statically/dynamically combining such code in the extension would require releasing the whole combined work under that licence, incompatible with closed source.
- "SaaS loophole" applies to GPL-3.0 (server-side use without distributing is not conveying) but is closed by AGPL s.13 only if you modify the AGPL program. Running Skyvern unmodified as a separate service and talking to it over HTTP is lower risk than forking it, but whether an extension front-end "interacting remotely" creates a combined work is untested; ask a lawyer. Safest: do not use Skyvern in the product path.
- [UNVERIFIED-BACKGROUND] Apache-2.0 includes an express patent grant that terminates if you sue over the work, and requires NOTICE/attribution; MIT only needs copyright+licence notice; GPL-3.0 also has patent-licence terms and anti-tivoisation language; GPL-3.0 vs Apache-2.0 are one-way compatible (Apache code into GPL-3.0, not the reverse). Verify against SPDX/FSF text.
- Dependencies matter: audit transitive licences (e.g. via licence scanner) in the extension bundle and Python backend; "source-available"/BSL/Commons-Clause/SSPL tools are NOT open source and need separate review.

### Gaps
- Could not open gnu.org, apache.org, spdx.org licence texts or FSF FAQ; no confirmation of WebBrain's and Skyvern's current licences/CLA/dual-licensing (Skyvern may offer a commercial licence - unverified). Check each repo's LICENSE at the pinned commit.
- No sourced treatment of whether a browser extension talking to an AGPL server forms a derivative work.

## 2. Chrome Web Store policies for AI agent / automation extensions (as of Oct 2026)

### Takeaway
A policy update effective 1 Aug 2026 tightened Limited Use/disclosure and added a ban on extensions designed to circumvent safety guardrails or usage restrictions of AI services. MV3 remote-code ban could not be re-verified; keep all logic bundled, send only data (prompts/JSON) remotely.

### Cited Findings
- Google's July 2026 developer blog: updated Developer Program Policies take effect 1 Aug 2026. Data collected must be strictly necessary to the disclosed single purpose; all data collection must be prominently disclosed, even if closely related to the single purpose; developers must proactively tell users if data handling changes after install. — [Chrome for Developers blog](https://developer.chrome.com/blog/cws-policy-updates-2026) (surfaced via search; page not opened) and [CyberInsider](https://cyberinsider.com/google-chrome-extensions-must-meet-new-privacy-standards-by-august-1/)
- New Malicious/Prohibited Products language bans extensions designed to get around safety guardrails or usage restrictions on AI-powered services. — same sources
- A secondary source says CWS forbids loading remote code but allows remote prompt updates (no policy citation). — [Bushe blog](https://bushe.co/blog/how-ai-is-transforming-browser-extensions-in-2026-what-changed-under-the-hood/) (low confidence)

### Inferences
- Single-purpose: define ApplyScout's single purpose narrowly ("fill job application forms with the user's own verified profile data, for user review"); avoid bundling job scraping, analytics, or resume-marketing features in the same extension.
- Limited Use: résumé/profile data sent to your server and then to NVIDIA NIM/Claude must be used only to provide the user-facing feature; no ad use, no sale, no training of your own models on it, no human reading except consent/security/legal. Disclose LLM subprocessors in the privacy policy and the CWS privacy-practices tab.
- Permissions: prefer activeTab + optional host permissions requested per ATS domain over `<all_urls>`; avoid `debugger` permission (high review friction, alarming install warning) unless indispensable; scripting + declared hosts is easier to justify.
- [UNVERIFIED-BACKGROUND] MV3 forbids executing remotely hosted code (including eval of fetched JS); LLM output must be treated as data (structured field->value), never executed as script. Reviews of "agent" extensions that run LLM-generated JS are a rejection risk.

### Gaps
- developer.chrome.com policy pages (Limited Use, Impermissible Behavior, Spam/Quality, MV3 remote code) not opened; no verbatim text.
- No sourced evidence found of specific CWS rejections/takedowns of auto-apply extensions; unknown (not "none"). Many auto-apply extensions exist on the store (not verified here).

## 3. ToS of job platforms / ATS; case law; Indian law

### Takeaway
LinkedIn explicitly bans third-party software/extensions that scrape, modify or automate its site and actively litigates; Indeed reportedly prohibits automating Indeed Apply (secondary source). ATS (Workday/Greenhouse/Lever) terms and Naukri terms were not retrieved. Case law favours scrapers on public data in contract terms but not for logged-in use; none squarely covers a user-side form filler.

### Cited Findings
- LinkedIn Help "Prohibited software and extensions": bans third-party software/extensions that scrape, alter the look of, or automate activity on LinkedIn; cites User Agreement s.8.2; restricted accounts are re-enabled after disabling the extension. — [LinkedIn Help a1341387](https://www.linkedin.com/help/linkedin/answer/a1341387) and [Automated activity on LinkedIn](https://www.linkedin.com/help/linkedin/answer/90586) (search-result summaries; pages not opened)
- LinkedIn v. Proxycurl (filed Jan 2025): resolved with permanent injunction and deletion of LinkedIn data; Proxycurl shut down July 2025. LinkedIn sued ProAPIs in Oct 2025 (fake-account scraping); no ruling found. — [LinkedIn news](https://news.linkedin.com/2025/LinkedInWinsLegalBattleToProtectMemberData)
- hiQ v. LinkedIn ended in 2022 consent judgment (one source says hiQ paid $500,000 and destroyed code/data); contract claims survived the CFAA ruling. — [Unipile summary](https://www.unipile.com/de/ist-linkedin-scraping-legal/) (vendor source, treat cautiously)
- Meta v. Bright Data (N.D. Cal.): summary judgment for Bright Data on breach of contract because terms govern "your use" and logged-off public scraping is not use; Meta later dropped the suit and waived appeal. Contract ruling only; CFAA not reached. — [Farella Braun + Martel](https://www.fbm.com/data-analytics/publications/major-decision-affects-law-of-scraping-and-online-data-collection-meta-platforms-v-bright-data/), [MediaPost](https://www.mediapost.com/publications/article/393996/meta-abandons-lawsuit-against-bright-data-over-scraping)
- Indeed (via third-party tracker ConductAtlas, unverified against Indeed's own text): prohibits automation/scripts/bots for Indeed Apply outside Indeed's official tooling; separate scraping/bot clause; July 2026 terms update. — [ConductAtlas Indeed provision](https://conductatlas.com/platform/indeed/indeed-terms-of-service/provision/CA-P-028259/automation-of-indeed-apply-process-prohibited/)
- One auto-apply vendor says it does not support Workday sites or any platform whose terms prohibit/do not clearly permit third-party automated submission; some employers may require the applicant to personally complete forms. Workable publishes anti-bot safeguards and lets employers disable job-board traffic. — [Workable help](https://help.workable.com/hc/en-us/articles/35293126257815-Managing-AI-generated-and-automated-job-applications) (vendor policy, not ATS ToS)

### Inferences
- Distinction that matters: (a) a user-operated extension that pre-fills a form the user is viewing and who clicks Submit is closest to a password manager/autofill and a "user's own use"; (b) a server-side bot logging in or submitting at scale for the user resembles the scraping/automation targeted in LinkedIn/Indeed actions. Platforms' ToS often treat both as "automated" regardless; enforcement risk (account bans for user, C&D to you) differs from litigation risk.
- Bright Data supports "ToS doesn't bind non-users/logged-off", which does NOT help for logged-in users who accepted ToS; ApplyScout users are typically logged in on LinkedIn/Naukri/Indeed, so contract exposure (user breach, possible inducement/tortious-interference theory against you) is real. Safest: no LinkedIn/Indeed/Naukri automation on their own sites at launch; target employer-hosted ATS pages (Greenhouse/Lever/Ashby etc.) where application is a public form addressed to the employer, after reading each ToS.
- [UNVERIFIED-BACKGROUND] Indian law: IT Act 2000 s.43 (compensation for unauthorised access/damage; s.43(a) access without permission of owner) and s.66 (criminal if dishonest/fraudulent); Copyright Act 1957 s.63 re database/compilation copying; Indian courts generally enforce click-wrap contracts under the Contract Act 1872. Not verified here; no Indian case on auto-apply tools identified.

### Gaps
- Not retrieved: LinkedIn User Agreement text (s.8.2), Naukri/Info Edge ToS, Glassdoor, Workday, Greenhouse, Lever (Employ) terms. Need direct reading; Greenhouse ToS at conductatlas.com surfaced but not opened.
- No sourced Indian authority on s.43 applied to automation; no Van Buren/CFAA application sourced (Van Buren v. US, 2021 is background knowledge only).
- Whether LinkedIn has sued an auto-apply tool: not found.

## 4. DPDP Act 2023 and Rules; UAE PDPL; Singapore PDPA

### Takeaway
DPDP Rules notified Nov 2025 with phased commencement: core fiduciary duties (notice, consent, safeguards, breach notification) apply ~18 months later, i.e. ~13 May 2027 - not yet in force in Oct 2026, but ApplyScout should build for it now. UAE PDPL is in force with implementing regulations reportedly still pending.

### Cited Findings
- DPDP Rules 2025 notified 13 or 14 Nov 2025 (sources differ); Rules 1, 2, 17-21 (Board establishment) effective on publication; Rule 4 (consent managers) at 12 months (~13 Nov 2026); Rules 3, 5-16, 22, 23 at 18 months (~13 May 2027). One source suggests consent-manager registration may depend on a further notification. — [Deccan Herald](https://www.deccanherald.com/amp/story/india%2Fcentre-notifies-dpdp-rules-implementation-planned-in-phases-spread-over-12-18-months-3798465), [JSA Prism](https://www.jsalaw.com/?p=55573), [Sansa Legal](https://www.sansalegal.com/post/how-to-comply-with-the-dpdp-act-2023-before-the-may-2027-enforcement-deadline)
- Child = under 18; verifiable parental consent required before processing a child's data, with limited exceptions. — [S.S. Rana](https://ssrana.in/articles/ensuring-child-safety-under-the-dpdpa/)
- Cross-border (s.16): transfers allowed unless the Central Government restricts notified countries (blacklist model). — [dpdpa.com s.16](https://dpdpa.com/dpdpa2023/chapter-4/section16.html)
- Penalty cap Rs 250 crore for security-safeguard failure; sources conflict on the children's-data cap (Rs 150 vs 200 crore) - check the Schedule. — [Taxmann](https://taxmann.com/post/blog/obligations-of-data-fiduciaries-under-dpdp-act/), [TCSA](https://www.tcsa.in/frameworks/dpdp/advanced-topics)
- UAE PDPL (Federal Decree-Law 45/2021) in force since 2 Jan 2022, UAE Data Office regulator; Chambers 2026 and DLA Piper say implementing regulations not yet issued (further 6 months to comply after issue); a vendor blog claims otherwise (low reliability). — [Global Legal Post](https://www.globallegalpost.com/lawoverborders/data-protection-1072382791/united-arab-emirates-1827256483), [Simmons & Simmons](https://www.simmons-simmons.com/en/publications/ckwugz8lu16rs0a44qvbqcbz9/uae-personal-data-protection-law-faqs)

### Inferences
- ApplyScout is a Data Fiduciary (decides purpose) for user profiles/résumés; NVIDIA NIM / Anthropic are Data Processors under a contract (DPA) - needs written processor agreements, no-training/zero-retention terms where available, and a disclosed processor list. Cross-border to US is currently permitted subject to any notified restriction, but monitor.
- Consent must be free, specific, informed, unambiguous, with itemised notice and easy withdrawal; sending résumé data to third-party agent vendors needs explicit notice. Avoid ingesting under-18 users (age gate) or build parental consent.
- Résumés include sensitive-ish data (caste/religion/disability if user types it; EEO answers) - minimise, keep EEO blank by default.
- [UNVERIFIED-BACKGROUND] Singapore PDPA: consent-based with deemed-consent and business-improvement exceptions (2020 amendments), penalties up to 10% of Singapore turnover or S$1m, mandatory breach notification, DPO required, transfer-limitation obligation. Not sourced here.

### Gaps
- Official DPDP Act/Rules gazette text and exact commencement notification not opened; Rule numbers for cross-border vary across sources. Singapore PDPA and UAE PDPL specifics beyond status not retrieved.

## 5. Consumer-protection and advertising rules

### Takeaway
CCPA (India) dark-pattern guidelines are actively enforced in 2026 on renewal/cancellation and pre-ticked boxes; make cancel as easy as subscribe and substantiate every marketing claim.

### Cited Findings
- 2023 Guidelines define dark patterns as deceptive UX practices; enforceable under the Consumer Protection Act 2019 (secondary source cites imprisonment up to 2 years / fine up to Rs 10 lakh). Subscription trap = cumbersome cancellation after free trial with auto-debit. — [Mondaq overview](https://www.mondaq.com/ccpas-guidelines-on-dark-patterns-an-overview/1844140)
- 5 June 2025 CCPA advisory required e-commerce platforms to self-audit for dark patterns. — [Bar & Bench](https://www.barandbench.com/law-firms/view-point/dark-patterns-in-india-from-hidden-practices-to-regulatory-spotlight)
- May 2026 enforcement: McAfee fined Rs 1 lakh (renewal prompt far more prominent than decline option); PhysicsWallah Rs 5 lakh (pre-ticked donation box). — [Mondaq overview](https://www.mondaq.com/ccpas-guidelines-on-dark-patterns-an-overview/1844140) (search summary; verify)

### Inferences
- Avoid: pre-ticked add-ons, confirm-shaming, hidden auto-renew, drip pricing, "limited seats" urgency. Provide one-click cancel, reminder before renewal, clear price in INR incl. GST.
- Claims such as "every line true" or any interview/shortlist uplift must be substantiated or phrased as design intent ("answers are drawn only from your verified profile"); never promise outcomes. [UNVERIFIED-BACKGROUND] Misleading ads: CPA 2019 s.2(28), CCPA Guidelines for Prevention of Misleading Advertisements 2022 (substantiation, disclaimers); RBI e-mandate rules for recurring card debits (Rs 15,000 AFA threshold) - verify.

### Gaps
- Guidelines text not opened; the "13 patterns" count not confirmed. No auto-renewal-specific Indian rule text verified beyond the dark-pattern subscription-trap item.

## 6. Liability for fabricated or wrong answers; safeguards

### Takeaway
No sourced case law found. Risk is mostly user-misrepresentation (employer can reject/terminate) with potential claims against ApplyScout if the tool invents facts; mitigate by grounding, review and logs.

### Cited Findings
- Workable documents managing AI-generated/automated applications and lets employers disable job-board traffic - indicates employers actively filter automated submissions. — [Workable help](https://help.workable.com/hc/en-us/articles/35293126257815-Managing-AI-generated-and-automated-job-applications)

### Inferences
- [UNVERIFIED-BACKGROUND] Indian angle: false statements on applications can support termination for misrepresentation and, in extreme cases, cheating (BNS s.318, formerly IPC s.420) / forgery of documents; in US-linked employers, EEO self-ID must be voluntary and accurate. Not sourced.
- Safeguards that reduce risk: fact-grounded answers from a user-verified profile with provenance per field; unknown -> leave blank/flag, never guess; mandatory preview/diff and explicit user Submit; EEO/disability/caste/religion/gender fields left blank (or user-only); per-application receipt (page URL, field values, timestamp, model version) stored for user; audit log; ToS making user responsible for accuracy and attesting before submit; disclaimers not substituting for design.

### Gaps
- No court judgments or law-firm alerts found on tool-induced false application statements; need counsel.

## 7. Anti-bot / CAPTCHA circumvention

### Takeaway
Do not bypass; hand off to the user. Circumvention aggravates ToS, IT Act and CWS risk.

### Cited Findings
- Chrome's 2026 policy update bans extensions designed to circumvent guardrails/usage restrictions of AI services (not specific to CAPTCHA). — [Chrome blog](https://developer.chrome.com/blog/cws-policy-updates-2026)
- Indeed reportedly prohibits bot/scraping activity (secondary). — [ConductAtlas](https://conductatlas.com/platform/indeed/indeed-terms-of-service/provision/CA-P-028619/prohibition-on-scraping-automated-access-and-bot-activity/)

### Inferences
- Red line: no CAPTCHA solving services, no fingerprint spoofing, no proxy rotation, no headless stealth. On challenge detection pause, highlight, and let the user solve in their own tab. Rate-limit to human-like per-user volume and cap daily submissions.
- [UNVERIFIED-BACKGROUND] Circumvention of technical measures can be framed as unauthorised access (CFAA in US; IT Act s.43/66 in India).

### Gaps
- No sourced Indian or US case specific to CAPTCHA circumvention in this session.

## Red lines, design choices, tools, lawyer questions (synthesis, inferential)

### Takeaway
Red lines: server-side submission, CAPTCHA/anti-bot evasion, credential storage, embedding GPL/AGPL code, fabricating or guessing answers, auto-answering EEO, automating LinkedIn/Indeed/Naukri on-site flows, hidden auto-renewal, using résumé data for model training or ads.

### Inferences
- Risk-lowering choices: user's own browser session; user presses Submit; no credentials stored; fact-grounded answers with provenance; EEO blank; per-ATS allow-list after ToS review; LLM treated as data only (MV3); DPAs with NIM/Anthropic; DPDP-ready notice/consent/deletion before May 2027; narrow single-purpose + minimal permissions.
- Legally unsafe to embed in closed-source: WebBrain (GPL-3.0) and Skyvern (AGPL-3.0) - copyleft triggered by extension distribution (GPL/AGPL) and network clause (AGPL if modified); also any tool of unknown/ no licence, source-available, or non-commercial licences. Skyvern also is a server-side autonomous agent, the higher-risk ToS category. Use MIT/Apache-2.0 components only, with NOTICE retained. (Licence labels for these two come from the task brief; not re-verified.)
- Ask a lawyer: (1) does an extension calling an unmodified AGPL service create a combined work; (2) ToS exposure for assisting users on LinkedIn/Naukri/Indeed and Workday/Greenhouse/Lever, and tortious-interference risk; (3) DPDP fiduciary/processor structuring, cross-border and consent-manager implications, and retention of audit logs vs minimisation; (4) CWS single-purpose and Limited Use drafting; (5) CCPA/advertising claim review and recurring-payment compliance; (6) liability allocation/indemnity and disclaimers for wrong answers, EEO handling in UAE/Singapore; (7) UAE PDPL and Singapore PDPA transfer/DPO obligations.

### Gaps
- Everything here depends on primary texts not opened; re-verify the cited items against official pages before relying on them.
