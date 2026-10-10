# India Mobile and Job-Search UX Lessons for ApplyScout

Method note: Research done 10 Oct 2026 using web search only (~17 calls). No pages were opened directly with a fetch tool, so the findings below come from search-result summaries and snippets. Where a figure depends on one secondary or vendor source, it is flagged. Statistics are dated. Nothing here is invented. Gaps are listed explicitly.

## 1. Device and network realities in India (2024-2026)

### Takeaway
ApplyScout's users are on Android (about 93%). They have plenty of data volume (about 25 GB a month on average) and fast median speeds in cities. The real limits are cheap-device CPU and RAM (jank), entry-level tariffs that keep rising, very low computer ownership outside cities, and a language preference for Indic languages. Design for a mid-to-low-end Android phone, used in daylight, in English with a Hindi or regional option. Do not assume a laptop.

### Cited Findings
- **Android share:** StatCounter (snapshot labelled May 2026) puts Android at 93.09% and iOS at 6.81% of India's mobile and tablet OS market. — [StatCounter India mobile/tablet OS 2025 page](https://gs.statcounter.com/os-market-share/mobile-tablet/india/2025)
- **Android versions:** StatCounter (June 2026, mobile) shows Android 15 at about 24.1%, Android 16 at about 21.7% and Android 13 at about 13.9%. A long tail of older versions remains. — [StatCounter Android version share India](https://gs.statcounter.com/android-version-market-share/mobile/india)
- **Smartphone market in 2025 (Counterpoint):** Volume grew about 1% and value about 8%. The premium segment (above Rs 30,000) rose 11% to a record 22% of shipments. Entry-tier shipments (below Rs 15,000) were "under pressure due to rising memory and component costs". Counterpoint expects 2026 ASPs to rise 5-7% and a single-digit volume decline in 2026, concentrated below Rs 15,000. vivo led 2025 with 20% volume share and Samsung was second. — [FoneArena summarising Counterpoint 2025](https://www.fonearena.com/blog/474743/india-smartphone-market-2025-counterpoint.html); [Business Today, Feb 2026](https://www.businesstoday.in/amp/technology/news/story/over-1-in-5-smartphones-sold-in-india-cost-more-than-rs-30000-apple-sees-highest-ever-value-share-report-514235-2026-02-02)
- **IDC price bands (2025):** Sub-$100 entry share rose from 14% to 16%. The $100-200 "mass budget" share fell from 44% to 41%. 2025 ASP was about $282. This uses different price bands from Counterpoint. — [EE Times India on IDC](https://www.eetindia.co.in/idc-india-smartphone-market-flat-in-2025/)
- **Inference from both firms:** Roughly 57% of 2025 shipments were under about $200 (16% + 41%). Most phones sold are therefore still budget devices, even as the premium share grows.
- **Data consumption (TRAI):** Average monthly wireless data use per subscriber was 25.51 GB in FY2025-26, up from 21.53 GB. Wireless data users numbered 1,026.75 million. — [NewKerala on TRAI FY26](https://www.newkerala.com/news/a/wireless-data-use-jumps-25-fy26-data-revenue-214.htm)
- **Data consumption (Nokia MBiT 2026):** Over 31 GB a month per user in calendar 2025, up from 27.5 GB in 2024. The methodology differs from TRAI's. — [Storyboard18](https://storyboard18.com/digital/indias-monthly-mobile-data-use-crosses-31gb-5g-traffic-surges-70-yoy-nokia-report-ws-l-93902.htm); [ETV Bharat](https://www.etvbharat.com/en/technology/india-average-monthly-data-usage-crosses-31-gb-in-2025-grows-at-18-pc-cagr-enn26033103281)
- **Tariffs:** Private telcos raised prices 10-25% in July 2024. Jio's entry plan is now Rs 299 for 1.5 GB a day for 28 days, and Airtel and Vi start at Rs 349. Jio and Airtel dropped their 1 GB-a-day plans. Analysts expected a further 10-12% hike, but I found no confirmation that it has happened. — [The Ken](https://the-ken.com/long_and_short/jio-airtel-hike-entry-level-pricing-but-lose-cheapest-data-tag-in-emerging-markets/); [Digit](https://www.digit.in/news/telecom/telecom-tariff-hike-on-the-horizon-jio-airtel-vi-may-raise-plan-prices-by-up-to-10-pct.html)
- **Speeds (Ookla):** India's median mobile download speed was 96.38 Mbps in August 2024 (ranked 20th, against a global median of 55.80 Mbps). A TelecomTalk report gives 131.77 Mbps for August 2025, but does not clearly say whether that is mobile. The April 2023 figure was 36.35 Mbps. — [tele.net.in](https://tele.net.in/?p=158941); [TelecomTalk](https://telecomtalk.info/?p=1000573); [Eastern Mirror](https://www.easternmirrornagaland.com/india-sees-4-spot-jump-in-median-mobile-speeds-globally)
- **Internet users (IAMAI-Kantar):** 958 million active internet users in 2025 (report released January 2026). Rural users make up 57% (about 548 million), and 44% of users already use AI-enabled features. The 2024 edition found 886 million users, of whom 98% (870 million) accessed content in Indic languages, and 57% preferred regional-language content. The scope of that 57% is ambiguous: one outlet says it refers to urban users. — [tele.net.in on 2025 report](https://tele.net.in/indias-internet-user-base-crosses-950-million-in-2025-as-per-iamai-report/); [Business Today on 2024 report](https://www.businesstoday.in/amp/technology/news/story/indias-internet-revolution-key-insights-from-kantar-and-iamai-report-461043-2025-01-16); [The Week](https://www.theweek.in/wire-updates/business/2025/01/16/dcm51-biz-iamai-internet-usage-report.html)
- **Computer access:** Fewer than 10% of Indian households own a laptop or computer. In 2023, about 4% of rural households did, against about 1 in 5 urban households. — [DataForIndia](https://www.dataforindia.com/access-to-computers-and-their-use/)
- **Low-end device performance (Swiggy case):** Swiggy found that users on "mid to low-end devices" experienced jank on the Home → Menu → Cart path. Working with Google Android DevRel in H2 2021, it reduced the jank using Perfetto, gfxinfo and ViewStubs, and Google reports a 50% boost in user interaction. — [Android Developers: Swiggy story](https://developer.android.com/stories/apps/swiggy)
- **Facebook Lite approach:** The client is designed to minimise CPU, storage and RAM use, and avoids animations and heavy UI interactions. — [Engineering at Meta](https://engineering.fb.com/android/how-we-built-facebook-lite-for-every-android-phone-and-network/)
- **Dark vs light mode in daylight:** A lab study of contrast polarity found no significant effect in daytime. At night, light mode performed better, and small text was much harder to read in dark mode. The study was indoors, and I found no controlled sunlight study. Practitioner guidance says light mode at high brightness holds up better outdoors. — [SoluteLabs summary](https://solutelabs.com/blog/light-vs-dark-mode); [NextTools](https://nexttools.net/how-to-make-a-screen-easier-to-see-in-sunlight/)

### Inferences
- **Bandwidth vs device:** Average data volume is no longer the main constraint for a typical user. CPU, RAM, jank and JS parse time on budget Androids are the bigger risk, which is what Swiggy found. The performance budget should target JS execution and interaction latency, not only bytes.
- **Data cost:** A meaningful minority are still cost-sensitive. Entry plans now start at Rs 299, and rural users plus freshers on daily caps of 1.5 GB a day may hit their limit. Keep the first load light (a reasonable target is under about 200-300 KB of compressed JS for the core app shell). Avoid autoplay video, and lazy-load illustrations. This target is a heuristic, not a sourced number.
- **Theme:** Default to a light theme for a daylight, on-the-go audience and offer dark as an option. A dark-only "premium" look in the CRED style risks legibility outdoors.
- **No laptop assumed:** Desktop or laptop access is limited (fewer than 10% of households own one). Resume upload, editing and review must work fully on a phone, including picking a PDF from WhatsApp downloads or Google Drive. A Chrome-extension-only workflow (Simplify-style) would exclude many users.
- **Language:** With 98% of internet users consuming Indic-language content, plan for Hindi and regional UI copy and notifications. Resumes and JDs for white-collar roles will still be mostly English. Use Noto Sans Devanagari and similar fonts with system-font fallbacks, and test line height, since Devanagari needs taller line boxes.

### Gaps
- No credible 2025-2026 source on typical RAM or screen size of budget phones sold in India. Counterpoint and IDC results did not include spec distributions.
- No current figure for laptop ownership among college students or young professionals. Only household-level data (2023) and a 2016 survey of 12-18 year olds were found.
- No mobile-only 2025 Ookla median was confirmed, and no per-GB price for 2026 was found.
- No Google/BCG or Google India report on mobile web performance was surfaced in these searches.
- No sourced research on Devanagari font rendering on low-end Android was found.

## 2. Admired Indian product design (CRED, Zepto, Swiggy, PhonePe/Paytm, apna, Naukri)

### Takeaway
Indian design leaders teach two different lessons. CRED shows that a distinctive, design-led brand can signal premium quality and exclusivity, although even CRED has moved toward clarity in its "Charcoal" redesign. PhonePe, Swiggy and apna show that trust and reliability on cheap phones win the mass market: clear confirmations, fast flows and verified counterparties. For a job-search tool, the second set matters more.

### Cited Findings
- **CRED's design system:** CRED's NeoPOP design system (open-sourced on GitHub) was described as a "4th generation design system" inspired by the neo-pop art movement. Its principles include isometrics, linear motion and "pseudo-morphism". — [Homegrown](https://homegrown.co.in/article/806427/cred-s-new-design-philosophy-channels-the-unbridled-creative-spirit-of-the-neo-pop-art-movemen); [Analytics India Mag](https://analyticsindiamag.com/creds-design-philosophy)
- **CRED's stance and redesign:** Head of Design Harish Sivaramakrishnan has said it is "just as important to offer an aesthetic experience to members, as it is to be efficient and easy to use". CRED's design has evolved from NeoPOP to "Charcoal", which is described as a move toward clarity and streamlined navigation. — [Analytics India Mag](https://analyticsindiamag.com/agams-frontman-reimagines-fintech-design-at-cred/)
- **PhonePe design blog:** PhonePe published "Designing Connections on Top of Transactions" (August 2020). It started from a user error: someone typed "5000" as a chat message instead of sending money through the payment flow. This prompted research into combining chat and payments. — [PhonePe design blog](https://www.phonepe.com/blog/design/designing-connections-on-top-of-transactions/)
- **PhonePe SmartSpeaker / Sound Box:** The device gives merchants real-time audio confirmation of UPI payments, so they do not need to keep checking their phone. Reports say more than 14 million are in use. — [Benzinga India](https://in.benzinga.com/content/40436802/phonepe-signs-100-cr-contract-with-cwd-limited-for-sound-box-manufacturing)
- **Swiggy performance work:** Swiggy invested in reducing jank on low-end devices along its core conversion path. — [Android Developers](https://developer.android.com/stories/apps/swiggy)
- **apna onboarding:** Onboarding supports multiple local languages and builds a "virtual business card" from a name, age and skills, aimed at users who do not speak English (sources from 2021). — [TechCrunch 2021](https://techcrunch.com/2021/03/01/apple-alum-jobs-app-apna-for-india-workers-raises-12-5-million); [HRKatha](https://www.hrkatha.com/?p=24559)
- **"Apna Safety" (September 2025):** This AI tool verifies recruiters against GST, PAN and CIN records and domain checks, validates individual recruiters through Aadhaar, and assigns a credibility score. Candidates can look up a recruiter by phone number. It flags scam patterns such as registration fees, security deposits, training charges and salary transfers. apna claims a pilot verified more than 146,000 recruiters and cut scam exposure by 45%; this is a company claim. — [Business Today](https://www.businesstoday.in/amp/technology/news/story/apnaco-launches-ai-powered-tool-apna-safety-to-curb-job-scams-in-india-during-festive-hiring-495735-2025-09-25)
- **apna's help pages:** Recruiters must "prove they're real" before they can contact candidates, and apna keeps reviewing them on an ongoing basis. — [apna help article](https://apna.co/career-central/how-apna-detects-blocks-fake-recruiters/)
- **Naukri:** Info Edge said on its November 2024 call (Q2 FY25) that the mobile app's active base was rising "significantly, month-on-month", with about 22,000 new CVs a day (+12% YoY) and recruiter searches and CV views increasing. The Naukri app surfaces "profile performance, search appearances, and recruiter actions" to job seekers. — [AlphaStreet transcript summary](https://alphastreet.com/india/wp-json/wp/v2/posts/137158); [Naukri App Store listing](https://apps.apple.com/app/482877505)

### Inferences
- **Borrow from PhonePe:** Make every automated action produce an unmistakable confirmation receipt, such as "Applied to X at 10:42, here's what we sent". This is the job-application equivalent of the Sound Box.
- **Borrow from Naukri:** Its "recruiter actions / profile views" feed suits an Indian audience that wants proof something is happening. ApplyScout's tracker should show external signals where available, not only "submitted".
- **Borrow from apna:** Recruiter verification and fee-pattern scam flags are directly transferable. ApplyScout should never auto-apply to listings that ask for fees, and should show a verified-employer badge where it can.
- **Borrow from CRED with care:** A distinctive brand can set ApplyScout apart, but CRED targets affluent credit-card holders. Freshers on budget phones need clarity first, and heavy motion or 3D effects work against performance on low-end devices.

### Gaps
- No primary CRED, Zepto, Swiggy Bytes or apna design-blog posts were opened. The sandbox had search only, and no Zepto design material surfaced.
- No Paytm design writing was found.
- No current data on Naukri's mobile vs desktop traffic split was found. The only figures are very old ones (23% mobile in an early press release, and 72% total traffic share in FY18).

## 3. Job-search UX: onboarding, matching, tracking, notifications, trust, complaints

### Takeaway
Market leaders compete on two things: a single profile parsed from the resume that powers matching and autofill, and a Kanban-style tracker. The weakest point in the category is trust. Auto-apply tools are criticised for wrong form fills, spam flags, account bans on LinkedIn and Indeed, low callback rates, and billing or refund problems. Indian users also face widespread recruitment scams. ApplyScout's advantage should be transparent, high-precision applications with human review, plus active scam shielding.

### Cited Findings
- **Simplify:** Free job tracker plus a Chrome-extension autofill, where "a single profile powers the entire job search". Described as lighter on features. — [Careerflow comparison blog](https://www.careerflow.ai/blog/huntr-vs-teal-vs-careerflow); [CB Insights](https://www.cbinsights.com/company/simplify-jobs/alternatives-competitors)
- **Teal:** Kanban tracker with stages Saved → Applied → Interview → Offer → Rejected. A 0-100 match score compares the resume with a saved JD and flags missing keywords, but sits behind the Teal+ paywall (about $29 a month per an older review). — [Scoutify Teal review](https://scoutify.com/blog/teal-review); [Tools for Humans](https://www.toolsforhumans.ai/ai-tools/teal)
- **Careerflow:** Imports a LinkedIn profile or starts fresh, then does one-click optimisation against a JD. A reviewer said its match score "pointed out the actual gaps we knew were there", i.e. more realistic than competitors. This comes from a review site, so treat it with caution. — [Scoutify Careerflow review](https://scoutify.com/blog/careerflow-review)
- **Jobright:** The AI ranks every job with a match score (Jobright's own comparison page). Its agent "Orion" auto-applies to hundreds of roles a day. Competitor LoopCV rates its auto-apply as "partial / assisted". Reviews report billing and cancellation complaints, a 33% price hike, resume AI "hallucinations" and US-only coverage. One review site claims the score is about 70-80% accurate, with no stated method. — [Jobright vs Simplify](https://jobright.ai/compare/simplify); [LoopCV](https://www.loopcv.pro/directory/jobright/); [ZPlatform](https://zplatform.ai/ai-reviews/jobright-ai/); [Trustpilot](https://www.trustpilot.com/review/jobright.ai?page=5)
- **LazyApply complaints:** Emails sent by the tool were flagged as spam, and accounts were blocked. Mass-applying violates the terms of service of LinkedIn and Indeed, and users report flagged or banned accounts. Users saw it fill applications with wrong information, report low callback rates, and cite ignored refund requests. One review site gives Trustpilot as 2.4/5 with 56% one-star reviews. A minority of reviews are positive ("15 plus interviews"). Many of these sources are competitors. — [Scoutify LazyApply review](https://scoutify.com/blog/lazyapply-review); [Trustpilot](https://ca.trustpilot.com/review/lazyapply.com?page=3); [Resumly](https://resumly.ai/answers/lazyapply-review)
- **Bot detection:** One review argues that high-volume auto-apply may be detected by modern Workday and Greenhouse configurations. This is a claim, not verified. — [atsverification.com Jobright review 2026](https://atsverification.com/blog/jobright-ai-review-2026/)
- **LinkedIn Job Search Safety Pulse (March 2026 fieldwork, 8,512 respondents across 5 countries including India):**
  - Over 82% of Indian professionals check whether a role is genuine before applying.
  - 53% are more likely to question whether an opportunity is a scam than a year ago.
  - 49% of Indian Gen Z said they had nearly fallen for a job scam, against 36% of Gen X.
  - 54% of Gen Z ignored warning signs when an opportunity "felt too important".
  - 90% of reported scam messages involve moving the conversation to private messages.
  - Sources: [People Matters](https://www.peoplematters.in/news/talent-management/82percent-indian-professionals-now-check-if-jobs-are-scams-before-applying-linkedin-49585); [Outlook Money](https://www.outlookmoney.com/news/54-per-cent-gen-z-ignore-potential-scam-signs-while-job-hunting-report); [IANS](https://ianslive.in/eight-in-ten-indian-job-seekers-now-vet-roles-for-scams-before-applying-report--20260506124903)
- **Indeed survey (India, reported July 2026):** 93% had encountered suspected recruitment scams and 51% were not confident telling genuine recruiters from fraudsters. Only 3% reported financial loss; the bigger damage was to trust. — [Business Today](https://www.businesstoday.in/amp/jobs/story/more-than-9-in-10-job-seekers-encounter-fake-job-offers-542006-2026-07-09); [Madhyamam](https://originen.madhyamam.com/india/93-of-indian-job-seekers-encounter-recruitment-scams-1538091)
- **India scam cases and advisories:**
  - **AICTE (February 2025):** Warned about fake appointment letters sent from look-alike domains and told people to trust only aicte-india.org and aicte.gov.in. — [Careers360](https://news.careers360.com/aicte-alerts-students-teachers-fake-job-offers-citing-council-education-ministry)
  - **Delhi Police (June 2025):** Busted a fake placement racket, linked in reports to the "Job Hai" app. The victim lost Rs 9,000 in "registration, verification and processing" fees, and police recovered more than 100 resumes and Aadhaar cards. — [IANS](https://ianslive.in/fake-job-racket-busted-in-delhi-police-recover-100-resumes-aadhaar-cards--20250624184853)
  - **Haryana (2025):** A fake HSSC website collected CET fees through QR codes and UPI. — [Careers360](https://news.careers360.com/haryana-gang-behind-fake-hssc-website-busted-main-conspirator-arrested-from-gorakhpur/amp)
  - **CERT-In:** General guidance warns about fake documents and fake company sites used to lure people with job offers. The source is a news summary, not the advisory itself. — [Vikaspedia on CERT-In advisory](https://en.vikaspedia.in/education/digital-litercy/information-security/preventing-online-scams-cert-in-advisory)

### Inferences
- **Onboarding:** Upload a resume (PDF from phone storage, Drive or WhatsApp), let the AI parse it, then show an editable confirmation screen of the parsed fields. Wrong form fills are the top complaint against auto-apply, so the user must check the parsed data once before any application is sent.
- **Match explanations:** Show why a job matches ("Matches 6 of 8 required skills; missing: Docker, AWS") rather than a bare 0-100 score. Careerflow's "realistic gaps" is praised, while Teal's paywalled score is a friction point. Keep at least a basic explanation free.
- **Auto-apply guardrails:** Set daily caps, apply only to verified employers, never touch listings that ask for fees, and never automate LinkedIn or Indeed where their terms of service prohibit it. Provide a clear per-application receipt showing what was sent, where and when. Position the product as quality over spray-and-pray, to stand apart from LazyApply's reputation.
- **Tracking:** A Kanban tracker with Saved, Applied, Interview, Offer and Rejected stages is the category standard. On a phone, render it as a stage-filtered list or tabs rather than a horizontal Kanban board, to avoid horizontal scrolling on a 360-dp-wide screen.
- **Scam shield as a feature:** Indian Gen Z is the most scam-exposed group. Add in-product warnings such as "Real employers never ask for fees", "Be careful if a recruiter moves you to WhatsApp or Telegram" and "Check the email domain". Link to cybercrime.gov.in and the 1930 helpline. The 1930 number is from general knowledge and should be verified before use.
- **Pricing trust:** Billing and refund complaints recur across Jobright and LazyApply. Use transparent pricing in INR, pay with UPI, make cancellation one tap, and state a refund policy up front.

### Gaps
- No primary-source material on how LinkedIn, Indeed, Naukri or Wellfound design resume-parsing onboarding or match explanations was retrieved.
- No independent data on recruiter attitudes to AI auto-applied candidates was found. Evidence is anecdotal or from competitor reviews.
- No Indian AI auto-apply tool reviews were found.

## 4. WhatsApp vs email for transactional updates

### Takeaway
WhatsApp is the dominant messaging channel in India, with an estimated 535-600 million users, and is read far more than email. However, the widely cited "98% open rate vs 20% email" figure is a vendor estimate. The most defensible measured benchmark found is about 68% average read rate for opt-in marketing broadcasts. Treat WhatsApp as the primary channel for time-sensitive updates such as interview invites, with email as the record.

### Cited Findings
- **WhatsApp users in India:** Estimates range from 535.8 million to 596.6 million MAU (2024), and they disagree with each other. Global WhatsApp MAU passed 3 billion by mid-2025 (Meta). — [Rasayel](https://learn.rasayel.io/en/blog/whatsapp-user-statistics/); [Sociallyin](https://sociallyin.com/?p=12769)
- **Open rates:** The 90-98% open-rate figure is "an estimate, not a Meta-published figure", against about 21% for email. About 68% is the average read rate reported for opt-in marketing broadcasts. — [Go4whatsup 2026 guide](https://www.go4whatsup.com/guides/whatsapp-marketing-statistics/)
- **India-specific vendor claim:** About 98% open rate vs 22% for email and a 45% response rate, presented as an industry estimate. — [Hyperleap](https://hyperleap.ai/blog/whatsapp-statistics-india-2026)
- **Scam pattern:** Scammers move victims to private messages: 90% of reported scam messages on LinkedIn involve moving off-platform. — [People Matters](https://www.peoplematters.in/news/talent-management/82percent-indian-professionals-now-check-if-jobs-are-scams-before-applying-linkedin-49585)

### Inferences
- **Use the official API:** Send only through the WhatsApp Business API from a verified business account (green tick if available), using fixed templates.
- **Tell users how you will contact them:** Say clearly in the product: "ApplyScout will only message you from [number]; we never ask for money or OTPs." Fraudsters use WhatsApp heavily, so a legitimate WhatsApp presence must stand apart from them.
- **Opt-in and frequency:** Keep messages opt-in and low-frequency. Event-driven messages work best: interview invites, status changes and a daily digest. Batching avoids being reported as spam.

### Gaps
- No credible independent (non-vendor) data on WhatsApp vs email engagement for young Indians specifically was found.
- No survey of Indian user preference for business updates on WhatsApp was found.

## 5. Accessibility and readability: sunlight contrast, touch targets, font sizes

### Takeaway
Use Material's 48dp touch targets (above the WCAG 2.2 AA floor of 24×24 CSS px), use light-mode high-contrast text, and use body text of at least 16px. These choices suit outdoor use on small, low-brightness budget screens.

### Cited Findings
- **WCAG 2.2 SC 2.5.8 (AA):** Targets must be at least 24×24 CSS px, or have enough spacing (an undisturbed 24px circle). Inline links are exempt. SC 2.5.5 (AAA) asks for 44×44. — [Deque axe rule](https://dequeuniversity.com/rules/axe/4.8/target-size); [TestParty](https://testparty.ai/blog/wcag-target-size-guide)
- **Platform guidance:** Material Design recommends 48dp touch targets and Apple HIG recommends 44pt. — [EZUD](https://ezud.com/touch-target-sizes-mobile-accessibility/)
- **Polarity study:** Light mode outperformed dark at night, small text in dark mode was much harder to read, and there was no significant difference in daytime. — [SoluteLabs summary](https://solutelabs.com/blog/light-vs-dark-mode)

### Inferences
- **Contrast:** Aim for WCAG AA contrast of 4.5:1 as a minimum and closer to 7:1 for body text. Budget LCD panels have lower peak brightness and are often used outdoors.
- **Type size:** Use 16px minimum for body text and 14px for secondary text. Avoid thin font weights; they render poorly on low-DPI screens and in Devanagari.
- **Layout:** Put primary actions in the thumb zone at the bottom, with 48dp targets. Avoid relying on colour alone for status; pair colour with icon and label.

### Gaps
- No India-specific accessibility or readability research was found.
- No measured data on screen brightness or resolution of budget phones in India was found.
- The W3C source text was not opened directly; the figures above are from secondary sources.
