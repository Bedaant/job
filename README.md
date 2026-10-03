# Job Copilot

**Upload your resume once. The app finds matching jobs, tailors your resume to each job's ATS, applies from your own browser, then emails people inside the company to ask for a referral. The goal is to get you interviews, not just applications.**

Job Copilot (the browser extension is called **ApplyScout**) is a personal project, built to run for the owner and about 5–7 friends. It is not a commercial product yet. This README is the blueprint: what the system does end to end, how the parts fit together, which repos and tools are used where and why, and what is built versus still to build.

> **Status in one line:** everything from resume upload through auto-apply is built and tested. The last step (referral outreach by email) is designed but **not built**. We make no promise of an interview. We aim to raise the chance of a reply, and we measure it.

---

## 1. The whole loop

```
 ┌──────────┐   ┌──────────┐   ┌──────────┐   ┌──────────┐   ┌──────────┐
 │ 1 Resume │──▶│ 2 Facts  │──▶│3 Campaign│──▶│ 4 Find   │──▶│ 5 Match  │
 │  upload  │   │ review   │   │ (roles,  │   │  jobs    │   │ & explain│
 └──────────┘   └──────────┘   │ places)  │   └──────────┘   └────┬─────┘
                               └──────────┘                       │
 ┌──────────┐   ┌──────────┐   ┌──────────┐   ┌──────────┐        │
 │ 9 Learn  │◀──│ 8 Refer- │◀──│ 7 Apply  │◀──│ 6 Tailor │◀───────┘
 │ & track  │   │ ral email│   │ in your  │   │ to the   │
 │          │   │ (PLANNED)│   │ browser  │   │ job's ATS│
 └──────────┘   └──────────┘   └──────────┘   └──────────┘
```

| # | Stage | What happens | Built? |
|---|---|---|---|
| 1 | **Resume upload** | You upload a PDF or DOCX. It is parsed. | ✅ |
| 2 | **Facts review** | The resume becomes 25–40 small, checkable claims (the **Facts KB**), such as *"Cut checkout API p99 latency from 1.4s to 180ms, Payments team, Q2 2025"*. You edit them. Everything written later can only use facts you confirmed. | ✅ |
| 3 | **Campaign** | You say what you want: job titles, locations, sources, caps, and whether each application waits for your review (assisted) or goes out on its own. | ✅ |
| 4 | **Find jobs** | Scheduled workers pull jobs from many public sources into one deduplicated table. | ✅ |
| 5 | **Match** | Every job is scored against your whole profile, not only the title. Each match says why: "7 of 9 required skills matched, missing Kubernetes". | ✅ |
| 6 | **Tailor to the ATS** | For each job the app rewrites your resume to the job's own wording, then truth-checks it. | ✅ built, quality not yet measured |
| 7 | **Apply** | The extension fills and submits the employer's form inside your own browser. | ✅ built, first real submission still to do |
| 8 | **Referral email** | After you apply, the app finds a suitable person at the company, verifies an email, writes a short note and sends it from your Gmail. | ❌ planned |
| 9 | **Track and learn** | A Kanban tracker, a daily digest, and reply and interview rates. | ✅ tracker and digest, 🟡 analytics |

### Stage 5 in more detail: how matching works
- **Semantic match:** your facts are compared to the job description with embeddings.
- **Skill coverage:** which required skills you have and which you lack (the keyword gap).
- **Hard filters:** location and remote policy, seniority, visa or work-authorisation text, and remote jobs that are limited to another country.
- **Near-duplicate removal:** the same role listed on three boards appears once.

### Stage 6 in more detail: tailoring to the ATS
Before each application the app reads the job description and rewrites your resume to match what that employer's ATS and recruiter look for:
- **Title alignment:** if you are a *Product Manager* and the job says *Technical Product Manager*, the app uses the job's wording where your real experience supports it.
- **Skill alignment:** it pulls the skills the job asks for and puts the ones you actually have into your skills section and bullets, in the job's wording.
- **ATS-safe layout:** single column, standard section names, no tables or text boxes.

Three steps do the work:
1. **Tailor:** reorder and reword your real facts for this job.
2. **Truth-check:** a second, independent model call checks the draft against your Facts KB. A claim your facts don't support blocks the application. So "Technical Product Manager" appears only when your facts back it up, and a skill you lack is flagged as a gap and never added.
3. **Voice:** strips the usual AI filler so the text sounds like you.

The result is an ATS-safe DOCX. The app re-parses its own output to confirm the content survives a parser.

### Stage 7 in more detail: auto-apply
- A server-side **planner** (Stagehand) studies each job's form once, read-only, and saves a fill plan. A network guard blocks every non-GET request, and the plan holds no personal data.
- The **ApplyScout extension** runs the plan in your browser, with your IP and your logins, using your real data. It checks each field after writing it. The server never submits an application.
- **Assisted mode:** the extension fills, you press Send. **Automatic mode:** it sends within your daily cap.
- It follows multi-page forms (Workday-style "Next" flows). At a sign-in wall it stops and tells you, and it never types a password.
- It never answers EEO or demographic questions. It never guesses essay questions or "How did you hear about us?". Those come from your saved answers, or it asks you.
- An application counts as *submitted* only when the employer's confirmation page says so.

### Stage 8 in more detail: referral email (planned)
Once an application is submitted:

1. **Pick who to contact.** At the same company, find 1–3 people who can help. If you applied as a Developer I, that means a Developer II or III, an Engineering Manager, or the hiring manager.
2. **Get an email.** Take a candidate address from a public source, a pattern guess (`first.last@company.com`), or a finder service.
3. **Verify it** (MX and SMTP checks) and send only when the result is safe.
4. **Write it.** At most 120 words: *"I applied for this role and I'm very interested. Here is my profile."* Every claim comes from your Facts KB.
5. **Send from your own Gmail** through OAuth, paced and capped.
6. **Watch.** A bounce, a reply or an opt-out stops all further mail to that person. A reply notifies you.

---

## 2. System architecture

```
                  ┌───────────────────────────────┐
  You ──────────▶ │ Web app (Next.js)             │   onboarding, facts, campaign,
                  │ dashboard                     │   matches, review, tracker
                  └──────────────┬────────────────┘
                                 │ REST + live events (SSE)
 ┌──────────────┐   ┌────────────▼────────────────┐        ┌─────────────────────────┐
 │ ApplyScout   │◀─▶│ API (FastAPI)               │◀──────▶│ PostgreSQL + pgvector   │
 │ Chrome ext.  │   │ auth, tenancy, campaigns,   │        │ (Neon). Row-level       │
 │ fills forms  │   │ matching, tailoring, plans  │        │ security per user       │
 └──────┬───────┘   └────────────┬────────────────┘        └─────────────────────────┘
        │                        │ jobs
        │              ┌─────────▼────────────┐   ┌──────────────────────────────────┐
        │              │ Redis + RQ workers   │──▶│ Job sources: Greenhouse, Lever,  │
        │              │ + scheduler          │   │ Ashby, Remotive, Reed, 6 feeds   │
        │              │ discover · embed ·   │   └──────────────────────────────────┘
        │              │ prepare · plan forms │   ┌──────────────────────────────────┐
        │              │ · (outreach, later)  │──▶│ AI: Claude (tailor + truth-check)│
        │              └─────────┬────────────┘   │ Voyage (embeddings)              │
        │                        │                │ Stagehand planner (form reading) │
        │              ┌─────────▼────────────┐   └──────────────────────────────────┘
        │              │ Planned: outreach    │   ┌──────────────────────────────────┐
        └─ page the    │ person finder, email │──▶│ agent-reach · email verifier ·   │
           user opens  │ verify, Gmail send   │   │ Gmail API (user's own account)   │
                       └──────────────────────┘   └──────────────────────────────────┘
```

**Design rules**
1. **One database, one API, one queue.** No microservices. A few friends fit comfortably on this.
2. **The server plans, your browser acts.** Submitting from the user's own browser avoids captchas on server IPs and keeps personal data off server browsers.
3. **Facts KB is the only source for generated text.** The resume file is never used to generate. That is what makes the truth-check possible.
4. **Every outbound action is capped and logged.** Applications and emails both have daily caps and show up in the digest.

---

## 3. Tools and repos: what we use, where and why

### 3.1 In use today

| Tool / repo | Where | Why |
|---|---|---|
| **FastAPI, SQLAlchemy, Alembic, Pydantic** | `apps/api` | The existing backend. Alembic for safe migrations. |
| **PostgreSQL + pgvector** (Neon) | database | One store for normal data and embeddings. |
| **Redis + RQ + rq-scheduler** (Redis Cloud) | `apps/api/workers` | Background discovery, embedding and preparation, plus scheduled runs. Simple and restart-safe. |
| **Next.js, TypeScript, Tailwind, shadcn/ui, Kibo UI** | `apps/web` | The dashboard. shadcn and Kibo UI save building a design system (Kibo supplies the Kanban tracker and dropzone). |
| **Chrome Manifest V3 + Vite** | `apps/extension` | Fills forms in the user's own browser. |
| **Anthropic Claude** | `tailoring/` | Tailor and truth-check. |
| **Voyage AI** | `matching/embeddings.py` | Embeddings for matching. The free tier is slow, so a backlog job fills them. |
| **Stagehand** (MIT) | `tools/stagehand-harness`, `formplans.py` | Reads a job form once, without clicking, and produces a fill plan. Measured as far faster and cheaper than browser-use on the same forms. |
| **browser-use** (MIT) | `tools/browser-use-harness` | A guarded test harness that fills real forms and can never submit. Used for testing, not production. |
| **agent-reach** (MIT) | `research/company_research.py` | Company research through GitHub and web pages. Installed in its own venv. |
| **JobSpy** (MIT) | `connectors/jobspy_connector.py` | Extra search sources, in an isolated venv because of a numpy conflict. Currently returns nothing, pending an upstream fix. |
| **Microsoft Presidio** (MIT) | `pii/redact.py` | Strips personal data from cached company dossiers and generation history. |
| **JSON Resume** schema (MIT) | `parsing/jsonresume_export.py` | The standard interchange format for resume facts. |
| **ats-scrapers URL→ATS mapping** (MIT) | `connectors/discovery.py` | Identifies which ATS a job link belongs to. We took the mapping data, not the code. |
| **pdfplumber, python-docx** | `parsing/`, `documents/` | Read resumes. Write the ATS-safe DOCX. |
| **Promptfoo, Langfuse** | `eval/` | Measure tailoring and truth-check quality, and trace model calls. Waiting on a production Anthropic key. |

### 3.2 Planned for the referral step

| Need | Plan | Why |
|---|---|---|
| Find who works there | **agent-reach** (web search and public pages), plus the extension reading a LinkedIn page the user opens themselves | Free, and low risk. Agent-reach reads public pages through Jina Reader, and its optional LinkedIn route uses a separate `mcp-server-linkedin`. It does not return a list of employees, so **this is the riskiest part and gets a spike first** (see section 6). |
| Find an email | Pattern guess (`first.last@domain`), then **Hunter** free tier (50 credits a month) as a top-up | Free to start. Pay only if it proves worth it. |
| Verify the email | **dnspython** for MX records, plus **AfterShip `email-verifier`** (MIT) or `email-validator-js` | Avoids bounces, which damage a sender's reputation. Many hosts block outbound port 25, so SMTP checks may need a different host or a provider's verifier. |
| Send the email | **Gmail API** (`gmail.send`) with `google-api-python-client` and `google-auth-oauthlib` | Sends as the user, so it looks like a normal email from a real person. |
| Suppression and caps | In-house tables | No suitable open-source tool was found (see `docs/DEPENDENCIES.md`). |

**Gmail setup for 5–7 friends:** Google's OAuth app verification is needed for public launch, but an app in testing mode allows up to 100 listed test users with no review. That fits a friends beta. One catch to check early: refresh tokens for apps in testing mode expire after about 7 days, so friends may have to reconnect Gmail weekly. `gmail.send` is a *sensitive* scope (verification needed, no security assessment), not the *restricted* one that `docs/DECISIONS.md` ADR-003 describes.

### 3.3 Studied, not used
Resume-Matcher (Apache-2.0, keyword-gap ideas), esco-skill-extractor, nanobrowser (extension agent design), pytector, pydantic-ai, career-ops, public-apis.

### 3.4 Rejected, so nobody re-proposes them
- **AGPL code:** AIHawk and its forks, open-resume, and `check-if-email-exists`. Copyleft would force opening our source.
- **No-licence repos** such as ats-resume-generator.
- **LinkedIn Easy-Apply bots** and any bulk LinkedIn scraper.
- **Stealth tooling:** fingerprint spoofing and rotating proxies. They add legal risk, break often, and are what platforms hunt for.

Full table with licences: [`docs/DEPENDENCIES.md`](docs/DEPENDENCIES.md).

---

## 4. Job sources

| Kind | Sources |
|---|---|
| Company ATS boards | Greenhouse, Lever, Ashby |
| Aggregator APIs | Remotive, Reed |
| Keyless feeds | RemoteOK, Himalayas, Working Nomads, Jobicy, Arbeitnow, We Work Remotely |
| Search scraper (isolated) | JobSpy: Google, ZipRecruiter, Glassdoor |

LinkedIn is not scraped by the server (ADR-015). The owner accepts some account risk from auto-apply, and the safety rules below keep it small.

---

## 5. Safety rules

The owner accepts some account risk. Nothing here guarantees no account is ever flagged. The rules keep volume low and keep the user's own session in charge.

**Applications:** a daily cap, a digest of what went out, no re-applying to the same job, and assisted mode for anyone who wants to press Send.

**Email (Gmail):**
- Start new accounts at 3–5 emails a day and rise slowly to 10.
- Spread sends across the day with random gaps, never in a burst.
- Never send the same text twice. Each email comes from the user's facts and that specific job.
- Verify every address first. Stop if bounces pass about 2–3%.
- A bounce, a reply or an opt-out stops all mail to that person. Keep a suppression list across all users.
- One follow-up at most, after about 6 days.
- Plain text, a real signature, no tracking pixels.

**LinkedIn:** the extension reads only pages the user opened, at human speed with a small daily limit. It never sends connection requests or messages, and it stores no passwords.

**Circuit breaker:** a captcha, a warning page, a bounce spike or a spam complaint pauses that user's sending and tells them why.

**Truth:** no claim in any resume or email may lack support in the user's Facts KB.

**Privacy:** resumes are personal data. The plan is encryption at rest, hard delete on request, personal data stripped from cached research, and no third-party analytics on profile pages.

---

## 6. What is left to close the loop

| Step | Task | Notes |
|---|---|---|
| 1 | **First real, owner-watched submission** through the extension | Proves the core loop. Nothing real has been sent yet. |
| 2 | **Spike: person-finder.** For 20 real jobs, can we name a suitable person and get a *verified* email? | Decides if stage 8 works at all. If under about 1 in 3 succeed, change the approach before building more. |
| 3 | **Build outreach as "draft, you press send"** | Gmail OAuth, draft, verify, caps, suppression list. Move to automatic only after real replies. |
| 4 | **SMTP credentials** | Digest and password-reset emails only log to the console until set. |
| 5 | **Production Anthropic key, then run the eval** | Gives real tailoring-quality numbers. |
| 6 | **Workday gaps** | Button-style dropdowns, multi-selects, date pickers and "Add another" sections still stop and ask the user. |
| 7 | **Friends beta** | 5–7 friends on the hosted app. See below. |

### Beta with 5–7 friends
- **What to measure:** applications sent, replies, referral emails sent, replies to them, interviews. Compare applications with and without a referral email. That is the number that says whether the idea works.
- **What it costs:** model and embedding calls for tailoring, plus hosting. Finder and verifier credits stay on free tiers to start. The target is $0.40 or less per prepared application. Check it against real usage.
- **What to watch:** bounce rate, any account warnings, and how often the extension hands a form back to the user.
- **Persona:** v1 is built around one persona at a time. The owner's own campaign is Product Manager roles in India or remote.

---

## 7. Where the code lives

```
apps/api/         FastAPI backend
  connectors/       job sources, normalise, dedupe, ATS detection
  matching/         filters, embeddings, scoring, skill gap, near-duplicate detection
  tailoring/        tailor and truth-check pipeline
  parsing/          resume PDF/DOCX to Facts KB
  documents/        ATS-safe DOCX export and parse-back check
  formfill/         field mapping, deterministic fills, per-ATS schemas
  formplans.py      per-job fill plans from the planner
  research/         company research (agent-reach)
  campaigns.py      campaign bounds and runs
  workers/          RQ worker and scheduler
  alembic/          database migrations
apps/web/         Next.js dashboard
apps/extension/   ApplyScout Chrome extension (Manifest V3)
eval/             Promptfoo eval harness for tailoring and the truth-checker
tools/            Stagehand form planner, guarded browser-use harness
docs/             product and engineering docs
```

Tests: about 737 API tests and 132 extension tests passed at the last logged run.

## 8. Running it locally

```bash
cp .env.example .env     # DATABASE_URL, REDIS_URL, JWT_SECRET, ANTHROPIC_API_KEY
                         # embeddings need a Voyage key (see docs/WORKLOG.md for free-tier limits)

docker compose up -d db redis

cd apps/api
pip install -r requirements.txt
alembic upgrade head
uvicorn main:app --port 8000

python -m workers.run_worker       # second terminal: discovery, campaign runs, embeddings
python -m workers.run_scheduler    # third terminal: periodic runs

cd apps/web && npm install && npm run dev            # http://localhost:3000
cd apps/extension && npm install && npm run build    # load dist/ as an unpacked extension
```

API docs: http://localhost:8000/docs. Tests: `pytest` in `apps/api`, `npm test` in `apps/web` and `apps/extension`. Without a running worker, **Run** and **Discover** return a 503 that says how to start one.

## 9. Docs

Start with [`docs/WORKLOG.md`](docs/WORKLOG.md). It is the running log, and its top section says where the project stands.

| Doc | What it is |
|---|---|
| [`docs/PRD.md`](docs/PRD.md) | What we are building and why: journeys, features, metrics, build order |
| [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) | System design and module boundaries |
| [`docs/SPEC.md`](docs/SPEC.md) | Module contracts and API surface |
| [`docs/DECISIONS.md`](docs/DECISIONS.md) | Decision records, including the pivot to auto-apply (ADR-015, ADR-016) |
| [`docs/DEPENDENCIES.md`](docs/DEPENDENCIES.md) | Every third-party tool and repo, with licences and reasons |
| [`docs/LIVE-FORM-TEST.md`](docs/LIVE-FORM-TEST.md) | How auto-apply is tested on real forms |
| [`docs/harness-reports/`](docs/harness-reports) | Measured results from the form planner |

## 10. Before you share this wider
- Check the licence of any third-party code you add. MIT and Apache are fine. AGPL and no-licence code are not.
- Auto-applying from a user's browser carries terms-of-service and account risk on job boards. That is an accepted decision (ADR-015). Caps and the digest bound it.
- If this ever goes beyond friends, Google's OAuth verification, email-law compliance (CAN-SPAM, GDPR) and a paid-provider plan all become required work.
