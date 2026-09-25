# Job Copilot

> **The code below is the single-user MVP.** The product being built is multi-tenant and
> much larger. Start with [`docs/WORKLOG.md`](docs/WORKLOG.md) for current state, then
> [`docs/PRD.md`](docs/PRD.md) · [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) ·
> [`docs/SPEC.md`](docs/SPEC.md) · [`docs/DECISIONS.md`](docs/DECISIONS.md) ·
> [`docs/DEPENDENCIES.md`](docs/DEPENDENCIES.md) · [`docs/CODE-REVIEW.md`](docs/CODE-REVIEW.md).

A self-hosted job search dashboard: pulls fresh listings from **legitimate public APIs**
(Remotive, Greenhouse, Lever, Ashby), stores them in Postgres, tailors your resume/cover
letter per job using a **truth-checked** AI pipeline (never invents achievements —
everything is traced back to your resume-facts KB), and gives you a tracker dashboard.

## What's in scope (built here)
- ✅ Job discovery via public APIs (Remotive, Greenhouse, Lever, Ashby) — no scraping, no ToS risk
- ✅ Postgres schema + FastAPI backend
- ✅ Resume-facts knowledge base (structured, not a raw resume blob)
- ✅ AI tailoring engine with a truth-checker pass (rejects unsupported claims)
- ✅ Application tracker (Saved → Applied → OA → Interview → Offer → Rejected)
- ✅ Next.js dashboard

## Deliberately NOT in scope
- ❌ Wellfound/LinkedIn scraping or login automation — these platforms actively fight this,
  and it risks your account. Log in and browse those yourself; paste the JD into the
  tailoring tool instead.
- ❌ Auto-submitting applications on your behalf without review — every tailored
  application is meant to be reviewed by you before sending. This is what keeps your
  applications from looking like spam.
- ❌ Sending unsolicited emails to random employees — not built, on purpose.

## Stack
| Layer | Tech |
|---|---|
| Frontend | Next.js 14 (App Router-free, pages dir for simplicity) |
| Backend | FastAPI |
| DB | PostgreSQL |
| Cache/Queue (optional, stubbed) | Redis + a simple cron script (swap for BullMQ/Temporal later if you scale) |
| AI | Anthropic API (Claude) |

## Running it locally

```bash
cp .env.example .env
# fill in ANTHROPIC_API_KEY in .env

docker compose up -d db redis     # Postgres + Redis
cd apps/api
pip install -r requirements.txt --break-system-packages
uvicorn main:app --reload --port 8000

# in a second terminal
cd apps/web
npm install
npm run dev
```

Dashboard: http://localhost:3000
API docs: http://localhost:8000/docs

## Pulling jobs

```
POST http://localhost:8000/discover/run
```
This hits Remotive + Greenhouse + Lever + Ashby for the companies/keywords in
`apps/api/connectors/config.py` and upserts new jobs into Postgres, deduped by
(company, title, source).

## Honest notes for scaling this up
- This is a real MVP skeleton, not the full 20-layer blueprint (no Temporal, no pgvector
  semantic search, no Playwright autofill) — those are legitimate next steps but are
  weeks of additional work each, not something to bolt on in one sitting.
- Before you hand this to friends: check the license on any third-party repo code you
  paste in here. MIT/Apache = fine to reuse. Repos with no LICENSE file, or that say
  "for educational purposes only," aren't safe to redistribute or commercialize.
- Add auth (Clerk/Better Auth) before deploying anywhere public — right now the API has
  no auth layer, it's single-user/local by design.
