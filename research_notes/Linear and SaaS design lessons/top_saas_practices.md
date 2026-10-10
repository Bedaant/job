# Design practices behind admired SaaS and AI products (beyond Linear): Stripe, Notion, Superhuman, Vercel, Figma, Raycast, Arc, Wispr Flow, Perplexity, Cursor

Research date: 2026-10-10. **Method note:** every direct fetch of company sites (stripe.com, blog.superhuman.com, vercel.com, blogdumoderateur.com) failed with DNS errors (ENOTFOUND) from this sandbox. All findings below come from web-search result snippets and summaries, so read them as secondary. URLs are the pages the search engine returned. Quotes are only those that appeared in search results. They have not been checked against the full original pages.

## 1. Process and culture: how these companies run design

### Takeaway
Leaders at the best-regarded companies describe "craft" and "beauty" as a business lever, not decoration. They protect quality from "good enough" pressure, and they rely on people who both design and code (design engineers). Figma's founder also argues for shipping early: you can't max out quality, features and deadline at once.

### Cited Findings
- **Stripe (Katie Dill, Head of Design):** she frames quality as three levels: utility, usability and beauty. Beauty means the details are executed well enough that the product is enjoyable. — [Creator Economy interview](https://creatoreconomy.so/p/how-stripe-crafts-quality-products-katie-dill)
- Dill on resisting "good enough" (quoted by Peter Yang): "It's just way too easy to ship something that's just 'good enough' for many reasons — we've got to get it out fast, we don't have the resources, we'll come back to it later…" — [Peter Yang Substack note](https://substack.com/@petergyang/note/c-71603425)
- At Stripe Sessions 2024 ("Craft and beauty: The business value of form in function"), Dill said Stripe prioritises craft partly because quality matters for growth. Her reasons were enjoyment, pride, and the fact that other businesses depend on Stripe's financial infrastructure. Figma's blog recapped the session, which included Linear and Figma speakers. — [Stripe Sessions 2024](https://stripe.com/gb/sessions/2024/craft-and-beauty-the-business-value-of-form-in-function); [Figma blog recap](https://www.figma.com/blog/stripe-sessions-linear-figma/)
- For AI-assisted work, a case study on the Stripe design team reports Dill's test: "Would I still be proud of this if it took me two weeks to build?" Stripe also has an internal prototyping tool (ProtoDash) that uses the real design system. This came via search summary only; the original was a LinkedIn case study whose URL the search did not return. See also [Lenny's Newsletter, How I AI on Stripe's internal AI tool](https://www.lennysnewsletter.com/p/this-week-on-how-i-ai-the-internal) and [Designer Fund: How Stripe creates room for good ideas to spread](https://designerfund.com/blog/ai-design-stripe)
- **Vercel / design engineering:** Rauno Freiberg, Staff Design Engineer at Vercel and formerly at The Browser Company working on Arc, publishes "Web Interface Guidelines". He calls them "a non-exhaustive list of details that make a good (web) interface", a living document. Example rule: toggles should take effect immediately, without confirmation. Vercel's design page links to the guidelines. — [GitHub raunofreiberg/interfaces](https://github.com/raunofreiberg/interfaces); [Vercel Design](https://vercel.com/design); [Sebastian De Deyne summary](https://sebastiandedeyne.com/rauno-web-interface-guidelines/)
- Freiberg also wrote "Devouring Details", an interactive reference on interaction design, and the essay "Invisible Details of Interaction Design" (2023). — [Devouring Details](https://devouringdetails.com/); [designengineering resource list](https://designengineering.arun.is/)
- **Notion (Ivan Zhao):** "beauty isn't decoration… it's fundamental to how the tool works". He says hierarchy, whitespace and typography decide whether a tool feels effortless. — [Founderboat interview, 2025-08-15](https://founderboat.com/interviews/2025-08-15-ivan-zhao-notion/)
- Zhao says designers spend too much time on edge cases, and that "the dumbest path" (the most common path) is what should be made great. In this account Notion optimises for exploration over up-front polish. — [Designer Founders: Ivan Zhao](https://designerfounders.substack.com/p/ivan-zhao-notion)
- Sequoia's podcast with Zhao covers Notion hiring designers who can code. — [Sequoia: Notion's Ivan Zhao, The Refounder](https://sequoiacap.com/podcast/notions-ivan-zhao-the-refounder)
- **Figma (Dylan Field):** Figma's Config 2025 book *Practice* was themed around craft ("making with intention"). Field is quoted in it saying the bar is *how* something works, not just whether it works. — [Figma: The making of Practice](https://www.figma.com/blog/the-making-of-practice/)
- Field said Figma's 3.5 years before launch was too long. He advises shipping early, and says you can pick two of quality, features and deadline. — [Lenny's Newsletter: Dylan Field live at Config](https://www.lennysnewsletter.com/p/dylan-field-live-at-config)
- **Superhuman:** Rahul Vohra's product-market-fit engine segments survey respondents ("how would you feel if you could no longer use the product?", with a 40% "very disappointed" benchmark from Sean Ellis). The roadmap then splits between doubling down on what fans love (speed) and fixing what holds back the near-fans. — [First Round Review](https://review.firstround.com/how-superhuman-built-an-engine-to-find-product-market-fit/); [Superhuman blog](https://blog.superhuman.com/how-superhuman-built-an-engine-to-find-product-market-fit/)

### Inferences
- The shared pattern is quality defined in public by a senior leader (Dill, Zhao, Field), plus a role that bridges design and code (Vercel design engineers, Notion's designers who code, Stripe's prototyping in the real system). That makes detail work cheap to do and hard to skip.
- "Craft" is pitched as an ROI argument (Stripe Sessions 2024), which is useful framing for a small team that has to justify polish time.

### Gaps
- I found no sourced material on formal "polish weeks" or quality-bar rituals at these companies in this pass. Linear's "quality weeks" are outside scope. Figma dogfooding practices also weren't found.
- Raycast's own design writing (raycast.com/blog) did not appear in search results.

## 2. Design systems, tokens and accessibility

### Takeaway
Stripe's public contribution is accessibility-first colour built with perceptual colour models. Its component system, Sail, is internal. Vercel publishes Geist as both an open font family and a design system. Notion's "system" is mostly restraint: a near-monochrome UI with a warm off-white.

### Cited Findings
- Stripe's blog post "Designing accessible color systems" (2019, credited by Matthew Strom to Daryl Koopersmith and Wilson Miner) says it was hard to build a colour system that allowed "great colors while ensuring accessibility". The team rejected hand-picking plus contrast-checking as trial and error. They also found that generating tints from base colours gave muted results. They built an internal tool that uses perceptually uniform colour models to give real-time accessibility feedback. — [Stripe blog](https://stripe.com/it-ca/blog/accessible-color-systems); [Matthew Strom, Generating color palettes](https://matthewstrom.com/writing/generating-color-palettes/); [Gigazine summary, 2019-10-17](https://gigazine.net/gsc_news/en/20191017-stripe-designing-accessible-color-systems)
- Strom (a later Stripe designer) writes that in the four years after that post, Stripe "stretched those colors to the limit". He then built his own palette-generation approach. — [Matthew Strom](https://matthewstrom.com/writing/generating-color-palettes/)
- **Sail** is Stripe's UI platform and design system: "the design system and component library that all of Stripe's products are built on" (job listing). A 2026 Lenny's Newsletter feature describes an internal AI prototyping tool that bundles Sail components and exposes Sail through an MCP server. — [Stripe Careers listing](https://stripe.com/careers/listing/product-designer-design-systems/7983076); [Lenny's Newsletter](https://www.lennysnewsletter.com/p/this-week-on-how-i-ai-the-internal). Sail itself is not public, according to an unofficial catalogue. — [designsystems.one](https://www.designsystems.one/design-systems/stripe-design)
- **Vercel Geist:** an open-source font family (Sans, Mono, and later Pixel) "created by Vercel in collaboration with Basement Studio", under the SIL Open Font License, installable via npm `geist`. — [npm geist](https://www.npmjs.com/package/geist?activeTab=readme). Vercel's font page says the family started from a monospace focused on readability and draws on the Swiss design movement (summarised from search). — [vercel.com/font](https://vercel.com/font?type=pixel). Geist Pixel is a bitmap-style addition with five variants (Square, Grid, Circle, Triangle, Line). — [Introducing Geist Pixel (feed mirror)](https://drss.io/feed/npub10vuuzme78zazljpt5new8mltdrn30rm9wf9a3ytf5k247vuf5t6qus2wgk/introducing-geist-pixel)
- Geist's release is described as "late 2023". Sources disagree on designer credits; some name Andrés Briganti, Mateo Zaragoza and Guido Ferreyra. — [Geist font review](https://fontcompressor.com/blog/geist-font-guide); [FontAlternatives](https://fontalternatives.com/fonts/geist/)
- The many "Vercel-style" token sets online (e.g. display tracking −0.05em) are community-made, not official. — [open-design.ai](https://open-design.ai/plugins/design-system-vercel/)
- **Notion:** a profile notes the "barely perceptible brown tint" in Notion's white background as a deliberate choice. It cites Bauhaus, Japanese minimalism and Christopher Alexander as influences. This is a secondary profile. — [Techy Ryter](https://techyryter.com/notions-ivan-zhao/)

### Inferences
- For a small product, the transferable lesson from Stripe is to generate the colour scale in a perceptual space (OKLCH/CIELAB) with contrast built into the steps, instead of hand-tuning hex values. From Vercel, the lesson is that one open font family plus strict tokens gives a recognisable identity.

### Gaps
- I could not open the full Stripe colour post to extract exact contrast targets or step counts.
- The search did not confirm Notion's UI typeface or official tokens.

## 3. Typography and colour choices

### Takeaway
Each brand commits to one distinctive type family: Stripe licenses Klim's Söhne, Vercel commissioned Geist, and Notion relies on calm, restrained typography. Colour is used sparingly and governed by accessibility.

### Cited Findings
- Stripe's 2020 redesign replaced Camphor with Klim Type Foundry's Söhne (a grotesque released in 2019, with Schmal, Breit and Mono variants). Klim lists Stripe as an in-use customer. — [Fonts In Use: Stripe website (2020)](https://fontsinuse.com/uses/35338/stripe-website-2020); [Klim: Stripe in use](https://klim.co.nz/in-use/stripe/); [Klim: Söhne](https://klim.co.nz/fonts/soehne/)
- An older snapshot shows Stripe's CSS using `sohne-var` with Helvetica Neue/Arial fallbacks. — [typ.io](https://typ.io/s/59wr)
- Vercel: Geist Sans/Mono, open-source, Swiss-influenced (see section 2). — [npm geist](https://www.npmjs.com/package/geist?activeTab=readme)
- Notion: "minimal, calm interface with thoughtful typography", whitespace, and minimal ornament (profiles). — [Startupik](https://startupik.com/ivan-zhao-the-notion-founder-who-built-one-of-the-most-loved-productivity-tools/); [Techy Ryter](https://techyryter.com/notions-ivan-zhao/)
- Arc: commentary credits Arc with rethinking browser chrome (sidebar, Spaces, a command bar replacing the URL bar). — [Blake Crosley design guide: Arc](https://blakecrosley.com/guides/design/arc)

### Inferences
- A distinctive but highly legible typeface does much of the brand work. An open option such as Geist or Inter is a credible zero-cost route; licensing a Söhne-class face is the premium route.
- Dark defaults are linked to dev-tool and "Linear-style" marketing (section 4). Notion and Stripe's product UIs are light-first. Choose by audience: job seekers aren't developers.

### Gaps
- I found no sourced statements in this pass from these companies explaining light vs dark default choices.

## 4. Landing pages: showing the product, and what's now cliché

### Takeaway
The dark, glowing-border, bento-grid look spread from Linear and Vercel around 2023. By 2024–26 it was so widely templated that sources describe it as *the* default layout. Copying it now signals "template", not quality.

### Cited Findings
- One source says the bento grid "that ate SaaS whole came from Linear and Vercel circa 2023". It adds that by mid-2024 "bento was no longer a layout choice, it was the layout". — [designmd.app: Bento Grids](https://designmd.app/library/bento-grids)
- Linear's page is called the "gold standard" for dark mode, glowing borders and bento feature grids, "influencing thousands of startups". — [framiq.app, 2026](https://framiq.app/blog/best-saas-landing-pages-2026); see also [Landdding bento guide](https://landdding.com/blog/blog-bento-grid-design-guide)
- Template marketplaces openly sell "grainy gradients and modern dark aesthetics inspired by Linear and Vercel". — [Design Drastic template](https://www.designdrastic.com/template/premium-saas-bento-landing)
- Caveat: these are vendor or template sources. I found no named designer explicitly calling it a "cliché" in this pass.
- Katie Dill has given an interview walking through Stripe's new website (podcast description only seen). — [Apple Podcasts: Stripe Head of Design Katie Dill Breaks Down Their New Website](https://podcasts.apple.com/us/podcast/stripe-head-of-design-katie-dill-breaks-down-their/id1236907421?i=1000763073781)
- Wispr Flow's onboarding (product, not landing page) was praised for having users practise with their own words instead of sample content. It later steered users to dictate into the apps they already use, which a teardown says removes the "demo sandbox" effect. — [Kristen Berman, 8 lessons](https://kristenberman.substack.com/p/wispr-flow-8-lessons-from-the-best); [Product Growth teardown](https://www.productgrowth.blog/p/wispr-flow-growth-teardown); [Growth Dives](https://www.growthdives.com/p/how-wispr-nails-onboarding)

### Inferences
- Showing the real product working on the user's own material beats decorative glow. For a job-application product, that means a real application being drafted and reviewed, not abstract gradient cards.

### Gaps
- No primary designer commentary was found that uses the word "cliché" for this look. I could not open the Stripe homepage to describe its current hero treatment.

## 5. Speed as UX

### Takeaway
Superhuman made speed a headline product pillar: UI responses within 100 ms, later pushed below 50 ms, with keyboard-driven everything. Arc and Raycast build on command bars and keyboard-first flows.

### Cited Findings
- Vohra: the UI responds within 100 ms, search is faster than Gmail, and the team pushed further to response times under 50 ms. — [First Round Review](https://review.firstround.com/how-superhuman-built-an-engine-to-find-product-market-fit/); [Superhuman blog (2018)](https://blog.superhuman.com/how-superhuman-built-an-engine-to-find-product-market-fit/)
- Vohra describes the original vision as "every interaction is 100 milliseconds or less". — [churn.fm episode](https://www.churn.fm/episode/how-superhuman-avoids-churn-by-systematically-increasing-product-market-fit)
- Superhuman deck pillars: "Blazingly Fast 100ms", keyboard-driven, offline. — [SlideShare deck](https://www.slideshare.net/slideshow/rahul-vohra-founderceo-superhuman-the-productmarket-fit-engine-122102118/122102118)
- Arc: keyboard-first navigation and a command bar in place of the URL bar (secondary commentary). — [Blake Crosley: Arc](https://blakecrosley.com/guides/design/arc). Raycast positions itself as "Your shortcut to everything". — [raycast.com](https://www.raycast.com/)
- Freiberg's guideline that toggles take effect immediately, without a confirm step, is a perceived-speed principle. — [GitHub interfaces](https://github.com/raunofreiberg/interfaces)

### Inferences
- A number-based speed budget (e.g. 100 ms for UI feedback) gives engineers a testable bar. Optimistic updates and immediate feedback, then slower background work (e.g. AI generation) with visible progress, follow from that.

### Gaps
- I found no source in this pass tying Superhuman's speed to specific optimistic-UI techniques.
- Raycast's own performance/design writing wasn't retrieved.

## 6. AI trust patterns: sources, review-before-act, undo, errors

### Takeaway
Perplexity shows its evidence inline (numbered citations plus a sources panel). Cursor shows its work as a diff that must be accepted or rejected per file or hunk. Its users push back hard when it auto-applies. Common agent practice is to gate irreversible actions (sends, submissions, payments) behind explicit approval, and to give reversible ones an undo window. That maps directly onto submitting a job application.

### Cited Findings
- Perplexity: inline numbered citations on factual claims, with a sources panel beside the answer. — [Blake Crosley: Perplexity design](https://blakecrosley.com/guides/design/perplexity). A design teardown argues that showing sources "every single time" is its central trust mechanism (the author's analysis, not Perplexity's). — [925 Studios](https://www.925studios.co/blog/perplexity-design-breakdown)
- Limits: a citation shows that a document informed the answer, not that it verifies that exact sentence, and synthesis can still hallucinate. Sources disagree on whether retrieval happens before generation. — [FutureAGI review](https://futureagi.com/blog/perplexity-ai-review-citations/); [LLM Pulse](https://llmpulse.ai/blog/how-perplexity-works/). A 2023 study cited there gives Perplexity citation recall of 68.7 vs Bing Chat's 58.7 (secondary report). — [FutureAGI](https://futureagi.com/blog/perplexity-ai-review-citations/)
- Henry Modisett (Head of Design, Perplexity) has given talks (Config 2024; Design MBA podcast, Jan 2024; a FirstMark Guild chat, Feb 2025) on AI design. No transcript on citations/trust was available. — [FirstMark Guild event](https://guilds.firstmark.com/events/perplexity-ai-designing-building-the-future-of-search); [Design MBA episode](https://pt.player.fm/series/design-mba/designing-for-ai)
- Cursor: agent edits appear as diffs with Accept/Reject per file or hunk. A forum bug report complains that an update applied edits without the review panel; the user said changes "should not be finalized without explicit user approval". — [Cursor forum](https://forum.cursor.com/t/agent-mode-no-longer-shows-review-accept-interface-and-applies-file-changes-automatically-after-recent-update/152581)
- The review panel shows diffs but doesn't run tests or linting before approval. — [theneuralbase guide](https://theneuralbase.com/cursor/learn/intermediate/reviewing-agent-actions-before-applying/). One take: "the win is not trust without review; it is a workflow where review has handles". — [Cursor Workshop](https://www.cursorworkshop.com/research/a-cursor-workshop-on-agent-prs)
- General human-in-the-loop guidance:
  - Put approval in front of hard-to-undo actions. — [DEV Community](https://dev.to/forrestzhang/human-in-the-loop-for-ai-agents-which-actions-need-approval-and-which-dont-547l)
  - Tier actions as act-and-log, act-and-notify with an undo window, or approve-before. — [OpusJake](https://opusjake.ai/blog/human-in-the-loop-ai-agent)
  - A universal undo is often infeasible for sent emails and payments. — [Atlassian HITL guide](https://www.atlassian.com/software/jira/guides/agentic-engineering/human-in-the-loop)
- A September 2026 paper ("Loopjacking") shows that approvals can be subverted if what the reviewer sees differs from what executes. It recommends exact rendering of the approved action and an execution-time check. — [arXiv 2609.21081](https://arxiv.org/pdf/2609.21081)

### Inferences
- For a product that submits job applications on the user's behalf:
  - Submission is irreversible, so it belongs behind an explicit approve step. That step should show the exact payload that will be sent (answers, attached CV version, target URL), as Loopjacking advises.
  - Drafting can be optimistic and editable.
  - Each generated answer should be traced to its source (CV line or job-post requirement), in the Perplexity manner.
  - Edits should appear as Cursor-style diffs against the user's master CV.
  - Keep a full log of what was submitted, where, and when.

### Gaps
- I couldn't retrieve primary docs on OpenAI Operator's confirmation and "takeover" UX or on Notion agent undo. From memory only, unverified: Operator asks for confirmation before consequential actions and hands control back for logins and payments. Verify before citing.
- No first-party Perplexity or Cursor design writing on trust was retrieved.

## 7. Commercial impact (dated, attributed)

### Takeaway
These products have strong commercial results, but no source shows that design *caused* them. The only causal claims are self-described (e.g. Stripe's "craft drives growth" argument).

### Cited Findings
- Grammarly announced the acquisition of Superhuman on 2025-07-01 (price undisclosed). — [SiliconANGLE, 2025-07-01](https://siliconangle.com/2025/07/01/grammarly-acquires-email-client-developer-superhuman/). Grammarly later renamed its parent company "Superhuman" (Oct 2025) and kept the Grammarly product name. — [Wikipedia: Superhuman](https://en.wikipedia.org/wiki/Superhuman_(email_client))
- Cursor (Anysphere): about $1B annualised revenue and a $29.3B post-money valuation at its Series D (Nov 2025). — [Wikipedia: Anysphere](https://en.wikipedia.org/wiki/Anysphere). Over $4B annualised by June 2026 (aggregator). — [Dealroom note](https://app.dealroom.co/news/note/cursor-tops-4b-annualized-revenue-june-2026). Some sites claim an acquisition by SpaceX at $60B; this is from aggregators only and conflicts with other sources, so treat it as unverified. — [tech-insider.org](https://tech-insider.org/cursor-60-billion-valuation-anysphere-ai-coding-2026/)
- Arc: The Register (2025-05-27) reported Arc in maintenance mode, saying it "never quite hit the mainstream". The Browser Company moved to Dia. — [The Register](https://www.theregister.com/2025/05/27/arc_browser_development_ends/). This is a counter-example: critically admired design did not guarantee mass adoption.
- Stripe's view of craft as a business driver is self-described. — [Stripe Sessions 2024](https://stripe.com/gb/sessions/2024/craft-and-beauty-the-business-value-of-form-in-function)

### Inferences
- Arc's outcome suggests craft has to serve a mainstream job-to-be-done. Superhuman's and Cursor's results tie design to a measurable core value (speed, trustworthy AI edits).

### Gaps
- No reliable 2025–26 figures retrieved for Notion, Perplexity, Wispr Flow funding/revenue, Raycast, or Vercel. Searches for Wispr Flow funding returned nothing usable.
