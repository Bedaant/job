# Apply Scout — architecture audit

Checked 18 October 2026. Companion to `Burner.md`, which covers provider prices, monthly burn, and unit economics. No product code was changed to produce this.

This repository is already a working job-search product, Apply Scout, not a blank app. The older name in the docs is Job Copilot. The README states it is a personal project for the owner and about five to seven friends, and that nothing is deployed: the API, worker, and scheduler run on the owner’s machine. Neon and Redis Cloud are already in use.

The intended product in this review is narrower than the code: a user-supplied job description, a truthful tailored resume, contact discovery, email checks, and an approved send. The repo already has the resume, review, and send machinery, plus a large job-collection system that does not have to be turned on.

## Verified tech stack

| Layer | What the source uses |
|---|---|
| Web | Next.js 15 App Router, React 19, TypeScript, Tailwind, shadcn/Radix, TanStack Query. No separate client store. |
| API | FastAPI, Pydantic v2, SQLAlchemy 2, Python 3.11. Routes in `apps/api/routes/`. |
| Data | Postgres 16 with pgvector. Alembic through revision 0040. SQLite for the fast test lane. |
| Queue | Redis, RQ, rq-scheduler. Queues: `default`, `background`, `effects`. |
| Auth | argon2id passwords and HS256 JWTs in `auth/router.py`. `better-auth` is an unused web devDependency. |
| LLM | NVIDIA NIM, model `nvidia/nemotron-3-super-120b-a12b`, through the OpenAI client and `instructor`. Free endpoint deprecated 19 October 2026. |
| Embeddings | Voyage `voyage-3-lite`, 512 dimensions. |
| Files | pdfplumber and python-docx parse an upload, then the file is discarded. Tailored output is DOCX rendered on demand. |
| Mail | Gmail OAuth per user, token encrypted with Fernet. One global SMTP account for digest, password reset, and outreach fallback. |
| Contacts | GitHub public profiles, then Apify actor `harvestapi~linkedin-profile-search`. |
| Extension | Chrome MV3, Vite. The server does not submit forms. |
| Tests | README reports API 1513 passed, web 159, extension 144. CI has four jobs. |

Required settings, by name only: `DATABASE_URL`, `JWT_SECRET`, `ANTHROPIC_API_KEY` (required by Settings even when the live provider is NVIDIA), `REDIS_URL`. Needed for the real loop: `APP_DATABASE_URL`, `LLM_PROVIDER`, `NVIDIA_API_KEY`, `NVIDIA_MODEL`, `VOYAGE_API_KEY`, `ENCRYPTION_KEY`, `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `APIFY_TOKEN`. Optional: `GITHUB_TOKEN`, `REED_API_KEY`, `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `SMTP_FROM`, `ALERT_EMAIL`, `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`, `DAILY_USD_CAP_APIFY`, `DAILY_USD_CAP_VOYAGE`, `DAILY_USD_CAP_LLM`.

**Dependency map.** The browser and the extension talk only to FastAPI. FastAPI and the workers talk to Postgres and Redis. Workers call NVIDIA, Voyage, job-board APIs, Apify, GitHub, Gmail, and SMTP. The web app does not call those providers. There is no object store.

```text
Browser ──▶ Next.js ──REST/SSE──▶ FastAPI ──▶ Postgres + pgvector
Chrome extension ──────────────▶ FastAPI ──▶ Redis (RQ + scheduler)
                                      │
                                      ├── NVIDIA NIM (tailor, truth-check)
                                      ├── Voyage (embeddings, optional)
                                      ├── Job-board connectors (optional)
                                      ├── GitHub + Apify (contacts)
                                      └── Gmail OAuth or SMTP (send)
```

## Existing implementation map

**VERIFIED, and exercised at least once on the real stack (owner, 10 Oct 2026):** signup, resume PDF to facts, confirm, campaign, match, tailor plus truth-check, approve, and an application email to the owner’s own address with a DOCX attached. Postgres row-level security is on Neon at migration 0040.

**VERIFIED in code and tests, not live:**

- Profile, contact details, work authorisation, network links, facts with proof and metrics, campaigns for role, location, and salary prefs.
- Job collection from Greenhouse, Lever, Ashby, Workday, Remotive, Reed, several remote feeds, Glassdoor via JobSpy, and LinkedIn guest jobs via Apify. India board scraping was explicitly rejected.
- Two-pass tailoring. Bullets must cite fact ids. The truth-check does not see the job description. A separate number check does not trust the model.
- DOCX render and a parse-back check. Review queue, diff, daily send cap, global and per-user pause, `sent_log`, duplicate-application uniqueness, outreach idempotency, two cold notes per address per day, suppression, and an HMAC unsubscribe link.
- Gmail send as the user. Prompt fencing in `untrusted.py`. PII redaction exists, but company research is not wired to an endpoint.
- Provider guard: retries, rate limit, circuit breaker, daily USD caps (defaults Apify $2, Voyage $1, LLM $5). It fails open if Redis is down.

**PARTIAL:**

- Outreach orchestration, Apify mapping, and Gmail send are built. Live Apify and Google OAuth for outreach are still waiting on credentials. Company research (`research/company_research.py`) shells out to `gh` and Jina Reader and has no caller.
- Extension autofill is built. No owner-watched submission to a real employer form has happened. Workday is incomplete. The extension does not yet upload the tailored resume.
- Email verification is a schema field and a written policy (`valid`, `invalid`, `accept_all`, `unknown`). No verifier runs.
- ClamAV client is installed. No daemon is connected, and uploads are not scanned.
- Encryption is a local Fernet key, not a KMS.

**MISSING:** paste, URL, or document intake of a single job description; PDF generation; per-user SMTP or Outlook credentials; billing; a hosted deployment.

**UNVERIFIED from this pass:** current Neon row counts, whether Redis is still on the 30-connection free tier, and whether `APIFY_TOKEN` is set. Environment files were not read.

## Product workflow

1. **Profile.** Reuse facts, contact fields, and documents-as-facts. The raw resume is not kept, which is the right isolation boundary.
2. **Job intake.** Today a job arrives from a connector into a shared `jobs` table. A pasted description needs a new path that stores the text on the user’s application, not in the global board inventory.
3. **Resume.** Already: compare facts to the description, generate from confirmed facts only, truth-check, preview, regenerate, download DOCX. PDF is a conversion step on top of that DOCX, not a second generator. Do not promise an ATS score. The code does not.
4. **Contacts.** GitHub first when the person published an address. Apify when they did not. Coverage is explicitly not guaranteed, and the actor does not read email off LinkedIn.
5. **Verification.** Still to build. Finding an address, checking syntax or MX, and proving the person owns the mailbox are three different results. The plan already says catch-all domains, which include most Google Workspace and Microsoft 365 tenants, must not be treated as proof.
6. **Draft and send.** Draft from facts, user approves, send through that user’s Gmail, record the result, suppress bounces and opt-outs. Follow-up drafts exist in `outreach/draft.py`.

Keep user approval on send. Auto-send exists as an opt-in in the outreach plan and should stay off until drafts have been measured. Job collection, embeddings, and the extension can stay off for a first version that only tailors and emails.

## Architecture proposal

Keep the current shape: one Next.js app, one FastAPI process, one Postgres, one Redis, one worker. The architecture doc already rejected microservices, and the code matches that. Do not add a vector database, a queue product, or an object store.

Build only these additions:

- A user-owned job record for pasted text, an allowed URL fetch, or an uploaded description.
- PDF by converting the existing DOCX locally. LibreOffice was considered and never installed.
- Per-user mail credentials encrypted with the same Fernet path as Gmail tokens, never placed in a prompt.
- One verification API call after an address is found, storing the status the schema already has.
- Raise the daily USD caps before any paid contact volume. The default Apify cap is $2 a day, which is about 16 lookups.

Leave Voyage off if you are not ranking a shared job corpus. Leave the extension off if the user applies by email or by hand.

What can be reused without a new stack: accounts, facts, tailoring, truth-check, DOCX, review, send gate, Gmail OAuth, outreach drafts, suppression, and the worker. What must be new is single-job intake, PDF, per-user SMTP, a real verifier, deployment, and payments.

## Security and compliance risks

Implemented: tenant filters plus forced row-level security, argon2id, a 32-character JWT secret check, Fernet for Gmail refresh tokens with no plaintext fallback, send gate, quotas, suppression, unsubscribe, fact-grounded generation, job text fenced as data, daily spend caps, and account deletion that fails tests if a new user table is forgotten.

Gaps that matter before other people use it:

- SMTP today is one shared secret in the environment. User mailbox passwords need the same encryption as Gmail tokens, and they must never be logged or sent to the model.
- The Fernet key lives beside the database URL. Anyone with the environment can decrypt every token.
- Uploaded files are not scanned. A malicious PDF is a parser risk even though the bytes are discarded after extraction.
- A job description can try to instruct the model. The truth-check is blind to the description, which is the right control, and it is not a guarantee. The golden-set run still found real fabrication in cover letters.
- Apify returns personal data about people who are not users. Storing it needs a purpose limit, a retention window, and a way to delete it. The README already names DPDP, GDPR, and CAN-SPAM as work before a wider release.
- Sending from the user’s account can get that account limited. The existing caps are the mitigation. Uncontrolled retries are already blocked for applications and outreach. Keep it that way.
- `APP_DATABASE_URL` falling back to the owner URL silently disables row-level security.
- The README says a secret-bearing `facts.json` remains in git history.
- Spend caps fail open when Redis fails, and the defaults are $2 / $1 / $5 per day. A bug at larger scale would otherwise be an Apify invoice.

## Implementation roadmap

1. Point tailoring at a paid OpenAI-compatible endpoint before 19 October 2026, and raise the LLM spend cap deliberately.
2. Add pasted and uploaded job descriptions on the existing application and tailor path. Skip the crawler.
3. Add PDF as a conversion of the current DOCX.
4. Deploy the existing image so the worker is not the laptop. Neon is already the database.
5. Wire a verifier into the status column, and show `accept_all` as uncertain.
6. Encrypt per-user SMTP next to Gmail OAuth. Keep approval on every send.
7. Turn on Apify only behind a credit balance and a cap you can afford. GitHub stays first.
8. Add payments only after the lookup cap exists.

The extension, shared job index, and embeddings are later, and only if board-scale discovery is still wanted.

## Open questions

These change the architecture or the bill. Numbers are in `Burner.md`.

- Is the first version pasted descriptions and email, or the existing board crawler and browser autofill? The first matches the cost model. The second adds a standing crawler and a deployment that does not exist yet.
- Will contact lookup be in the default action? If it is off, the monthly bill collapses to hosting plus LLM.
- Is a LinkedIn search actor acceptable, given this repo already refused unlicensed India job boards? The actor’s terms put the account holder at risk.
- Google OAuth stays in Testing mode until about 80 users, which the Gmail plan already flags. A public launch needs verification.
