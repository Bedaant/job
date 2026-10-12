from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

import ats_controls
from core.config import get_settings
import send_gate
from auth.router import router as auth_router
from account import router as account_router
from outreach import api as outreach_api
from outreach import gmail
from observability import router as ops_router
from routes import applications, campaigns, extension, feed, matches, profiles, resume_facts

settings = get_settings()

# Schema is owned by Alembic now (alembic/versions/0001_baseline.py) — run
# `alembic upgrade head` before starting the app. No create_all() here; that
# was CODE-REVIEW.md B2 (silently ignores schema changes in production).

app = FastAPI(title="Job Copilot API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)


@app.exception_handler(send_gate.InvalidTransition)
def _invalid_transition(_request: Request, exc: send_gate.InvalidTransition):
    return JSONResponse(status_code=409, content={"detail": str(exc)})

# Stage 8 (`docs/PLAN-OUTREACH.md`). Their own routers rather than another 200 lines
# here: `outreach.api` carries the review/approve/skip surface plus the PUBLIC
# unsubscribe route, and `outreach.gmail` the OAuth grant REACH-D's send path needs.
app.include_router(outreach_api.router)
app.include_router(gmail.router)
app.include_router(ats_controls.router)
app.include_router(ops_router)
app.include_router(account_router)
app.include_router(send_gate.router)

# Route groups. No path overlaps across groups, so order matters only inside
# routes/applications.py: `/applications/{application_id}` is registered after
# `/applications/review-queue` and `/ready-to-send` so it can't swallow them.
app.include_router(campaigns.router)
app.include_router(applications.router)
app.include_router(extension.router)
app.include_router(resume_facts.router)
app.include_router(profiles.router)
app.include_router(feed.router)
app.include_router(matches.router)


@app.get("/health")
def health():
    return {"status": "ok"}
