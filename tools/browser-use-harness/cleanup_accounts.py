"""Delete harness throwaway accounts. Runs with the API's venv (owner role, bypasses RLS):

  D:\\job-copilot\\apps\\api\\.venv\\Scripts\\python.exe cleanup_accounts.py [--email X]

No --email: deletes every user whose email starts with EMAIL_PREFIX and ends @example.com.
users -> profiles/events/notifications and profiles -> everything else are ON DELETE CASCADE.
"""

import argparse
import os
import sys
from pathlib import Path

EMAIL_PREFIX = "bu-harness-"
API_DIR = Path(os.environ.get("APPLYSCOUT_MAIN", r"D:\job-copilot")) / "apps" / "api"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--email", help="delete only this harness account")
    args = ap.parse_args()
    if args.email and not (args.email.startswith(EMAIL_PREFIX) and args.email.endswith("@example.com")):
        sys.exit(f"refusing: {args.email!r} is not a harness account")

    os.chdir(API_DIR)  # core.config reads .env relative to CWD
    sys.path.insert(0, str(API_DIR))
    from sqlalchemy import text

    from database import session_scope

    with session_scope() as db:
        if args.email:
            rows = db.execute(text("DELETE FROM users WHERE email = :e RETURNING email"), {"e": args.email})
        else:
            rows = db.execute(
                text("DELETE FROM users WHERE email LIKE :p AND email LIKE '%@example.com' RETURNING email"),
                {"p": EMAIL_PREFIX + "%"},
            )
        deleted = [r[0] for r in rows]
    print(f"deleted {len(deleted)}: {', '.join(deleted) or '-'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
