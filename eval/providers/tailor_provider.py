"""promptfoo custom Python provider (ADR-014) wrapping the real two-pass
tailoring engine (apps/api/tailoring/engine.py) — the same code path the
API uses, not a reimplementation, so eval results reflect production
behavior. Config syntax verified against promptfoo's own docs
(https://www.promptfoo.dev/docs/providers/python/) before writing this,
per the standing "never guess APIs" rule.
"""
import json
import os
import sys

API_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "apps", "api")
sys.path.insert(0, API_DIR)

# core.config.Settings' env_file=".env" is resolved relative to the process's
# CWD, not this file's location — promptfoo runs this provider from eval/,
# not apps/api/, so every Settings()-backed lookup (this file's own, and
# tailoring/engine.py's internal get_settings() call) would silently fail
# (ValidationError: database_url/anthropic_api_key/jwt_secret all missing)
# without this. chdir once, here, fixes it for every consumer at once
# rather than patching each one's env-var reads individually.
os.chdir(API_DIR)

from tailoring.engine import tailor_application  # noqa: E402


def call_api(prompt, options, context):
    v = context["vars"]
    job = {"title": v["jd_title"], "company": v["jd_company"], "description": v["jd_description"]}
    facts = json.loads(v["facts_json"])

    try:
        result = tailor_application(job, facts)
    except Exception as exc:
        return {"output": "", "error": str(exc)}

    return {"output": json.dumps(result)}
