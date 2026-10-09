# DEPLOY-B — one image, three services (docs/PLAN-DEPLOY.md).
#
# The API, the RQ worker and the scheduler differ only by command, so they share this
# image. Postgres is Neon and Redis is Redis Cloud, so nothing stateful runs here and the
# container is disposable.
#
# WHAT IS DELIBERATELY ABSENT, because it is what keeps this under ~1GB instead of ~3GB:
#
#   * Chromium and tools/stagehand-harness. Form planning stays on the owner's machine by
#     decision. Everything that must run UNATTENDED — discovery, embedding, matching,
#     tailoring, truth-check, outreach, the digest — is here.
#   * tools/browser-use-harness, same reason.
#   * spaCy's en_core_web_lg (~400MB). PLAN-DEPLOY first claimed the API could not start
#     without it; that was WRONG and measured so: nothing in the API or worker import
#     graph touches `pii`, `spacy` or `presidio` — only tests do, and GAPS 5.8 records
#     that `redact_pii` has no production callers at all. The presidio PACKAGES install
#     from requirements.txt regardless, so if F7 is ever wired the failure is a loud
#     missing-model error at import, not silent bad output. Add
#     `python -m spacy download en_core_web_lg` here at that point.
FROM python:3.11-slim AS base

# curl: used by research/company_research.py, and by the compose healthcheck.
# ca-certificates: httpx talks to Neon, Redis Cloud, Gmail, Apify and GitHub over TLS.
# `gh` is NOT installed — DEPLOY-A.2 replaced that subprocess with a direct httpx call
# precisely so the image would not need the binary or a second auth mechanism.
RUN apt-get update \
 && apt-get install -y --no-install-recommends curl ca-certificates \
 && rm -rf /var/lib/apt/lists/*

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Requirements first, so a code change does not reinstall the dependency tree.
COPY apps/api/requirements.txt /app/apps/api/requirements.txt
RUN pip install -r /app/apps/api/requirements.txt

# The second venv for JobSpy. It MUST be isolated: python-jobspy hard-pins
# numpy==1.26.3, which conflicts with pgvector/scikit-learn's numpy 2.x and broke a real
# test when installed in the main environment (WORKLOG 2026-08-16).
#
# Built at IMAGE time, not first use — a container should not pip-install on a scheduled
# run. `bin/python` here is why DEPLOY-A.1 had to stop hardcoding `Scripts/python.exe`:
# that path exists only on Windows, and the connector used to return [] on Linux, which
# is indistinguishable from a board with nothing matching.
#
# >=1.3.0 is not cosmetic: on the previously pinned 1.1.82, ZipRecruiter AND Glassdoor
# both answered HTTP 403. 1.3.0 is what makes Glassdoor work, and Glassdoor is the only
# site in JOBSPY_SITES.
RUN python -m venv /app/tools/.venv-jobspy \
 && /app/tools/.venv-jobspy/bin/pip install --no-cache-dir "python-jobspy>=1.3.0"

# Layout is load-bearing. `connectors/jobspy_connector.py` resolves tools/ as
# ../../../tools from apps/api/connectors/, and formplans.py does the same with
# parents[2]. Flattening this breaks both silently.
COPY apps/api /app/apps/api
COPY tools/ats_token_probe.py /app/tools/ats_token_probe.py

# Non-root. Nothing here needs to write to the image, and the only writable path the app
# wants is the log directory, mounted by compose.
RUN useradd --create-home --uid 10001 app \
 && chown -R app:app /app
USER app

WORKDIR /app/apps/api

# 0.0.0.0, not 127.0.0.1: the port has to be reachable from outside the container. Caddy
# is the only thing that should actually reach it — compose does not publish this port.
#
# No --reload, deliberately: GAPS 5.1 records it hanging and serving stale code, and a
# reloader has no business in a deployed image anyway.
EXPOSE 8000
CMD ["python", "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
