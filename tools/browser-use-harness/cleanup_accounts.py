"""Delete harness throwaway accounts. Runs with the API's venv (owner role, bypasses RLS):

  D:\\job-copilot\\apps\\api\\.venv\\Scripts\\python.exe cleanup_accounts.py [--email X]

No --email: deletes every user whose email starts with EMAIL_PREFIX and ends @example.com.
users -> profiles/events/notifications and profiles -> everything else are ON DELETE CASCADE.
Jobs are not user-owned, so harness jobs (source JOB_SOURCE) left without applications go too.
--add-job URL inserts one harness job (auto_apply.py: the API has no job-create route) and
prints its id.
"""

import argparse
import os
import secrets
import sys
from pathlib import Path

EMAIL_PREFIX = "bu-harness-"
JOB_SOURCE = "bu-harness"
API_DIR = Path(os.environ.get("APPLYSCOUT_MAIN", r"D:\job-copilot")) / "apps" / "api"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--email", help="delete only this harness account")
    ap.add_argument("--add-job", metavar="URL", help="insert a harness job with this apply_url; print its id")
    args = ap.parse_args()
    if args.email and not (args.email.startswith(EMAIL_PREFIX) and args.email.endswith("@example.com")):
        sys.exit(f"refusing: {args.email!r} is not a harness account")

    os.chdir(API_DIR)  # core.config reads .env relative to CWD
    sys.path.insert(0, str(API_DIR))
    from sqlalchemy import text

    from database import session_scope

    with session_scope() as db:
        if args.add_job:
            key = secrets.token_hex(8)
            job_id = db.execute(text(
                "INSERT INTO jobs (id, source, external_id, canonical_hash, title, company, apply_url, remote, "
                "tags, skills, fetched_at, last_seen_at) VALUES (gen_random_uuid(), :s, :k, :h, "
                "'Harness Engineer', 'Harness Co', :u, true, '[]', '[]', now(), now()) RETURNING id"),
                {"s": JOB_SOURCE, "k": key, "h": f"{JOB_SOURCE}-{key}", "u": args.add_job}).scalar()
            print(job_id)
            return 0
        if args.email:
            rows = db.execute(text("DELETE FROM users WHERE email = :e RETURNING email"), {"e": args.email})
        else:
            rows = db.execute(
                text("DELETE FROM users WHERE email LIKE :p AND email LIKE '%@example.com' RETURNING email"),
                {"p": EMAIL_PREFIX + "%"},
            )
        deleted = [r[0] for r in rows]
        jobs = db.execute(text("DELETE FROM jobs j WHERE source = :s AND NOT EXISTS "
                               "(SELECT 1 FROM applications a WHERE a.job_id = j.id)"), {"s": JOB_SOURCE}).rowcount
    print(f"deleted {len(deleted)}: {', '.join(deleted) or '-'}; harness jobs: {jobs}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
