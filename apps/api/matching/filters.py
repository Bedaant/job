"""F6 hard filters (PRD.md §"Hard filters (SQL, free): work authorization,
location/remote policy, seniority" — run in Python here, not SQL, matching
the ponytail shortcut already taken in matching/service.py's in-process scan).

ponytail: the actual MVP schema (models.py) never got `Job.seniority` or a
work-authorization field the way SPEC.md's aspirational full schema has them
(no connector — Remotive/Greenhouse/Lever/Ashby/Reed — exposes either).
Seniority is inferred from the title with a keyword regex at ingestion time;
visa sponsorship is a description-text heuristic, not a real signal. Missing
data never excludes a job — a false "no match" hides a real opportunity,
which is worse than an imperfect filter letting one through. Upgrade path:
a real seniority/sponsorship field once a connector or LLM extraction pass
actually provides one.
"""
import re

_SENIORITY_PATTERNS = [
    ("intern", re.compile(r"\bintern(ship)?\b", re.I)),
    ("junior", re.compile(r"\b(junior|jr\.?|entry.level|associate)\b", re.I)),
    ("lead", re.compile(r"\b(lead|principal)\b", re.I)),
    ("staff", re.compile(r"\bstaff\b", re.I)),
    ("senior", re.compile(r"\b(senior|sr\.?)\b", re.I)),
]

_NO_SPONSORSHIP_PATTERN = re.compile(
    r"(no|not|unable to|cannot|won'?t|will not)\s+(?:\w+\s+){0,4}sponsor"
    r"|sponsorship\s+(?:is\s+)?(not|unavailable)"
    r"|without\s+sponsorship"
    r"|u\.?s\.?\s*citizens?\s+only",
    re.I,
)


# A country also matches its main cities: postings say "Bangalore, Karnataka" or
# "Gurugram", not "India". ponytail: India only; add a country when users target it.
LOCATION_ALIASES = {
    "india": ["bengaluru", "bangalore", "pune", "gurugram", "gurgaon", "hyderabad", "mumbai",
              "delhi", "noida", "chennai", "kolkata", "ahmedabad"],
    # Both spellings are live (2026-10-10: 304 "Bengaluru", 247 "Bangalore").
    "bengaluru": ["bangalore"], "bangalore": ["bengaluru"],
    "gurugram": ["gurgaon"], "gurgaon": ["gurugram"],
    "mumbai": ["bombay"], "bombay": ["mumbai"],
    "delhi ncr": ["delhi", "noida", "gurugram", "gurgaon"],
}
_COUNTRY_NAMES = {"IN": "india"}
_COUNTRY_REGIONS = {"IN": ["apac", "asia"]}
# Words a remote job's location uses when it names no place ("Anywhere in the World").
_OPEN_WORDS = re.compile(
    r"\b(anywhere|in|the|world|worldwide|global|globally|remote|job|home ?office|remoto|work|from|home|"
    r"wfh|fully|international|internationally|location|flexible)\b|[^a-z]+", re.I)


def remote_open_to(job, country_code: str | None) -> bool:
    """A remote role restricted to somewhere else ("USA", "Europe", "Time zone: CET")
    isn't one this user can take. Open = no place named, or the user's country or
    region named. Unknown country: no filter (a false "no match" hides a real job)."""
    name = _COUNTRY_NAMES.get((country_code or "").upper())
    if not job.remote or not name:
        return True
    loc = (job.location or "").lower()
    terms = [name, *LOCATION_ALIASES.get(name, []), *_COUNTRY_REGIONS.get(country_code.upper(), [])]
    if any(re.search(rf"\b{re.escape(t)}\b", loc) for t in terms):
        return True
    return not _OPEN_WORDS.sub("", loc).strip()


def infer_seniority(title: str) -> str | None:
    for level, pattern in _SENIORITY_PATTERNS:
        if pattern.search(title):
            return level
    return None


def blocks_visa_sponsorship(description: str) -> bool:
    return bool(_NO_SPONSORSHIP_PATTERN.search(description or ""))


def _passes_location(prefs: dict, job) -> bool:
    locations = prefs.get("locations") or []
    remote_types = prefs.get("remote_types") or []
    if not locations and not remote_types:
        return True
    if job.remote:
        return not remote_types or "remote" in remote_types
    if not job.location:
        return True
    return not locations or any(loc.lower() in job.location.lower() for loc in locations)


def _passes_seniority(prefs: dict, job) -> bool:
    wanted = prefs.get("seniority")
    if not wanted or not job.seniority:
        return True
    return job.seniority in wanted


def _passes_visa(prefs: dict, job) -> bool:
    if not prefs.get("visa_sponsorship_required"):
        return True
    return not blocks_visa_sponsorship(job.description or "")


def passes_hard_filters(prefs: dict, job, country_code: str | None = None) -> bool:
    # delisted_at is the one exception to "missing data never excludes a job"
    # (module docstring above): NULL means still listed and must pass, but a
    # set timestamp is a real signal the job is gone, not missing data.
    if getattr(job, "delisted_at", None) is not None:
        return False
    return (_passes_location(prefs, job) and _passes_seniority(prefs, job) and _passes_visa(prefs, job)
            and remote_open_to(job, country_code))
