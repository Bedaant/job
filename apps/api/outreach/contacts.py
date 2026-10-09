"""REACH-B — where a referral contact comes from (`docs/PLAN-OUTREACH.md`).

One interface, several adapters, because the cheap sources have narrow coverage and the
broad source costs money. The engine asks for contacts and does not care which adapter
answered; that is what lets the paid adapter be added, swapped or removed without the
send lock, the cap, suppression or verification changing.

MEASURED 2026-10-09, before writing this, because an adapter is only worth having if its
yield is real:

| org      | public org members | has a public email | bio names product/head |
|----------|--------------------|--------------------|------------------------|
| razorpay | 25                 | 12                 | 1                      |
| zerodha  | 14                 | 7                  | 0                      |
| meesho   | 2                  | -                  | -                      |
| Swiggy   | 0                  | -                  | -                      |

Two conclusions that shape the design:

1. **GitHub is a real source for engineers.** Roughly half the people it exposes publish
   an address themselves — no vendor, no pattern guessing, no bounce risk, and the
   address is public by the owner's own choice. `gh` is already a dependency.
2. **GitHub is not a source for product roles.** One product-adjacent person across 39,
   and `Swiggy` exposes nobody at all. A PM search returning nothing here is the EXPECTED
   outcome and must not be logged or surfaced as a failure.

So GitHub is tried first and the paid adapter covers what it cannot reach. There is no
fallback chain hardcoded here — the engine composes the sources it was given, in order.
"""
import logging
import os
import httpx
from dataclasses import dataclass, field
from typing import Protocol

logger = logging.getLogger(__name__)

TIMEOUT = 20
_GITHUB_API = "https://api.github.com"

# Deliverable to nobody. GitHub hands these out by default for web-UI commits and to
# anyone who hides their address, so it is the common case rather than an edge one.
_UNDELIVERABLE_DOMAINS = ("users.noreply.github.com", "noreply.github.com")

# Seniority and filler words carry no signal about WHAT someone does, and matching on
# them would make every bio containing "senior" a hit.
_TITLE_NOISE = {
    "senior", "sr", "junior", "jr", "staff", "principal", "lead", "associate",
    "head", "chief", "director", "vp", "of", "the", "and", "i", "ii", "iii",
}


def _title_tokens(titles: list[str]) -> set[str]:
    """Significant words from a job title.

    A title is matched by TOKEN, not as a phrase: "Product Manager" does not appear
    verbatim in a bio reading "Head of Product", which is exactly the kind of person the
    search wants. Phrase matching looks stricter and is simply wrong here.
    """
    words = (w.strip(".,/()-").casefold() for t in titles if t for w in t.split())
    return {w for w in words if len(w) > 2 and w not in _TITLE_NOISE}


@dataclass
class ContactCandidate:
    """A person who might be worth asking for a referral.

    `email` is optional on purpose: an adapter can know who someone is before it knows
    how to reach them, and the engine decides what to do about that (it verifies, and it
    never auto-sends to an address it could not confirm).
    """
    full_name: str
    company: str
    title: str | None = None
    email: str | None = None
    source: str = "unknown"
    source_ref: str | None = None
    # What the adapter knew about this person, which differs sharply BY adapter and is
    # what makes warm-signal ranking degrade rather than fail:
    #
    #   signal                | needs            | GitHub | Apify
    #   same_former_employer  | work history     | no     | yes
    #   same_role             | current title    | weak   | yes
    #   same_university       | education        | no     | yes
    #   same_city             | location         | no     | yes
    #
    # A GitHub candidate therefore usually reaches `same_role` or `none`. That is correct
    # for the data available, not a gap to paper over by guessing.
    past_companies: list[str] = field(default_factory=list)
    schools: list[str] = field(default_factory=list)
    location: str | None = None
    # Raw adapter observations. The RANKER, not the adapter, decides the final signal —
    # an adapter only reports what it saw.
    evidence: dict = field(default_factory=dict)
    # Set by `outreach.signals.rank_contacts`. The email asserts this out loud, so a
    # signal about the user carries the `ResumeFact` id that justifies it.
    warm_signal: dict | None = None


class ContactSource(Protocol):
    name: str

    def find(self, company: str, titles: list[str], limit: int) -> list[ContactCandidate]:
        """Return at most `limit` candidates. An empty list is a valid answer and means
        "this source cannot reach this company", never an error."""
        ...


class ManualContactSource:
    """The user typed the contact in themselves.

    Permanently useful, not scaffolding: every automated source has partial coverage, and
    this is the only one that can reach a company none of them cover. It is also what
    exercises the whole engine end to end with no vendor and no credential.
    """

    name = "manual"

    def __init__(self, candidates: list[ContactCandidate] | None = None):
        self._candidates = candidates or []

    def find(self, company: str, titles: list[str], limit: int) -> list[ContactCandidate]:
        hits = [c for c in self._candidates if c.company.casefold() == company.casefold()]
        for c in hits:
            c.source = self.name
        return hits[:limit]


class GitHubContactSource:
    """Public GitHub org members who publish an email on their profile.

    The address is published by its owner, on a profile they control, for the stated
    purpose of being contactable — which is a materially better position than any
    constructed or enriched address, and it costs nothing.

    Cost is one `gh api users/{login}` call per member, so `max_profile_lookups` bounds
    it; `limit` alone would not, since we must look at a profile to learn whether it has
    an email at all.
    """

    name = "github"

    def __init__(self, max_profile_lookups: int = 30):
        self.max_profile_lookups = max_profile_lookups

    def _gh_json(self, path: str):
        """One GitHub REST call. **httpx, not the `gh` CLI** (DEPLOY-A.2).

        This shelled out to `gh api`, which made the CLI a RUNTIME dependency rather than
        a developer convenience. A container has neither the binary nor an authenticated
        account, so on the first deploy every lookup would have returned None — and the
        engine correctly reads that as "nobody found", which is indistinguishable from a
        company genuinely having no public members. That is the measured normal case for
        a product role, so it would have looked like correct behaviour indefinitely.

        Direct HTTP also removes a second auth mechanism: one `GITHUB_TOKEN` instead of
        `gh auth login` state on the box. Unauthenticated works too, at GitHub's 60
        requests/hour anonymous limit — fine for a handful of lookups, and the token
        raises it to 5,000.
        """
        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "ApplyScout/0.1",
        }
        token = self._github_token()
        if token:
            headers["Authorization"] = f"Bearer {token}"
        try:
            r = httpx.get(f"{_GITHUB_API}/{path.lstrip('/')}", headers=headers, timeout=TIMEOUT)
        except Exception as exc:
            # Type only — a response body can echo a token in an error path.
            logger.warning("github lookup failed for %s: %s", path, type(exc).__name__)
            return None
        if r.status_code == 404:
            # An org that does not exist. Expected and quiet: the slug is guessed from a
            # company name, so misses are the common case.
            return None
        if r.status_code in (401, 403, 429):
            # Rate limit or a bad token. NOT the same as "nobody there", and the whole
            # point of this rewrite is that the difference is visible.
            logger.warning(
                "github lookup refused for %s: HTTP %s (rate limit or token) — this is "
                "not an empty result", path, r.status_code,
            )
            return None
        if r.status_code != 200:
            logger.warning("github lookup for %s returned HTTP %s", path, r.status_code)
            return None
        try:
            return r.json()
        except ValueError:
            return None

    @staticmethod
    def _github_token() -> str | None:
        """Settings first, then the environment — the same order and the same reason as
        `ApifyContactSource._resolve_token`: every other credential here lives in
        `apps/api/.env`, and an undeclared key is silently dropped by `extra="ignore"`."""
        try:
            from core.config import get_settings

            configured = get_settings().github_token
        except Exception:
            configured = None
        return configured or os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")

    def find(self, company: str, titles: list[str], limit: int) -> list[ContactCandidate]:
        # A GITHUB_TOKEN IS NOT OPTIONAL, measured 2026-10-09: anonymously
        # `GET /users/{login}` returns `email: None` for EVERY user, including those who
        # publish one. The field is only populated for authenticated requests. So without
        # a token this adapter returns zero candidates every time — and the engine
        # correctly reads that as "nobody found", which is indistinguishable from a
        # company genuinely having no public members.
        #
        # That is the third time today that shape of bug has appeared (the Apify token,
        # JobSpy's 403s, this), so it is said out loud rather than left to be discovered:
        # the earlier measurement of 12-of-25 razorpay members with a public address was
        # taken through an AUTHENTICATED `gh`, not anonymously.
        if not self._github_token():
            logger.warning(
                "GitHubContactSource has no GITHUB_TOKEN: GitHub omits the email field "
                "on anonymous requests, so this will find nobody — that is a missing "
                "credential, not an empty company"
            )
            return []

        # The org slug is guessed from the company name, so a miss is the common case and
        # a clean empty result (GitHub answers 404). No slug cleverness is warranted.
        org = company.strip().casefold().replace(" ", "")
        members = self._gh_json(f"orgs/{org}/members?per_page=100")
        if not isinstance(members, list):
            return []

        wanted = _title_tokens(titles)
        out: list[ContactCandidate] = []
        for m in members[: self.max_profile_lookups]:
            login = (m or {}).get("login")
            if not login:
                continue
            prof = self._gh_json(f"users/{login}")
            if not isinstance(prof, dict):
                continue
            email = prof.get("email")
            if not email or email.endswith(_UNDELIVERABLE_DOMAINS):
                continue
            bio = " ".join(filter(None, [prof.get("bio"), prof.get("company")])).casefold()
            # GitHub has no title field, so a bio hit is a hint and nothing more. A miss
            # is still returned: discarding a reachable engineer over a blank bio would
            # throw away most of the measured yield.
            matched = any(w in bio for w in wanted) if wanted else False
            out.append(ContactCandidate(
                full_name=prof.get("name") or login,
                company=company,
                title=prof.get("bio") or None,
                email=email,
                source=self.name,
                source_ref=login,
                evidence={"bio_matched_title": matched, "login": login},
            ))

        # `login` is the tiebreaker, not list order: GAPS 6.6 was a real nondeterminism
        # bug from ranking with no tiebreaker, and with auto-send on the tiebreaker
        # decides who receives mail.
        out.sort(key=lambda c: (not c.evidence["bio_matched_title"], c.evidence["login"]))
        return out[:limit]
