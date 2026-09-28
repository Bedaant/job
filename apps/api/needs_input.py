"""Why the driver stopped, read back from the `[outcome] reason` lines that
`POST /applications/{id}/submission-result` appends to `applications.notes`.

Derived, not stored: no migration, and the note line stays the single record.
Patterns mirror apps/extension/src/background/driverCore.mjs NEEDS_HUMAN_PATTERNS
and fieldDecision.mjs needsHumanReason (REASON_TEXT) for the blocking fields.
"""
import re

_STAMP = re.compile(r"^\[(submitted|unconfirmed|failed|needs_human)\] (.*)$")

# Order matters: a captcha or an account wall blocks the form whatever else it asks.
_KINDS = [
    ("captcha", re.compile(r"captcha|cloudflare.{0,20}challenge", re.I)),
    ("account", re.compile(r"\bsign ?in\b|\blog ?in\b|\blogged in\b|create an account|register.{0,20}to apply", re.I)),
    ("upload", re.compile(r"file_upload|file input|upload", re.I)),
    # Still a question once every one is answered (pending empty): retrying helps then.
    ("question", re.compile(r"low_confidence|essay|unanswered|no saved answer|not sure what to enter|why do you want|why are you interested", re.I)),
]
_DEMOGRAPHIC = re.compile(r"\bdemographic\b", re.I)


def _last_stamp(notes: str | None) -> tuple[str, str] | None:
    for line in reversed((notes or "").splitlines()):
        m = _STAMP.match(line.strip())
        if m:
            return m.group(1), m.group(2)
    return None


def attempt_history(notes: str | None) -> list[dict]:
    """Every `[outcome] reason` stamp, oldest first."""
    stamps = (_STAMP.match(line.strip()) for line in (notes or "").splitlines())
    return [{"outcome": m.group(1), "message": m.group(2)} for m in stamps if m]


def last_attempt(notes: str | None) -> dict | None:
    stamp = _last_stamp(notes)
    return {"outcome": stamp[0], "message": stamp[1]} if stamp else None


def needs_input(notes: str | None, pending_questions: list[str], consent_questions: list[str] = ()) -> dict | None:
    """None unless the most recent attempt ended in needs_human."""
    stamp = _last_stamp(notes)
    if not stamp or stamp[0] != "needs_human":
        return None
    reason = stamp[1]
    scan = _reasons_only(reason)
    kind = next((k for k, p in _KINDS if p.search(scan)), None)
    if kind is None:
        kind = "question" if pending_questions or consent_questions else "other"
    return {
        "kind": kind, "message": reason, "demographic_left_blank": bool(_DEMOGRAPHIC.search(scan)),
        # A required legal consent stops every retry: only the user may agree to it.
        "consent_required": bool(consent_questions),
    }


# "Needs you: <labels> (<reason>); ..." (fieldDecision.needsHumanReason) carries the
# form's own labels: "Upload your portfolio link" must not make it an upload. Only
# each group's trailing "(reason)" is read.
_GROUP_REASON = re.compile(r"\(([^()]*)\)\s*(?=;|$)")


def _reasons_only(reason: str) -> str:
    if not reason.startswith("Needs you:"):
        return reason
    return " ".join(_GROUP_REASON.findall(reason))
