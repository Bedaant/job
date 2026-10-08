"""REACH-E — the paid `ContactSource`: Apify's LinkedIn profile search.

Covers what `GitHubContactSource` cannot. GitHub was measured at 12 reachable people of
25 public members for razorpay, of whom ONE was product-adjacent across two orgs — good
for engineers, useless for the product roles this product's own owner is searching for
(`outreach/contacts.py` carries the numbers). This adapter is what reaches those people.

WHY THIS IS A PLAIN HTTP CALL AND MUST STAY ONE. The actor runs on Apify's
infrastructure, so it needs no cookie, no session and no LinkedIn account from the user —
that was the deciding reason it was chosen over every other route. One authenticated POST
returns the dataset directly. **There is no browser here, no Patchright, no proxy
configuration and no anti-detection layer, and none of that belongs in this file.** If a
future change seems to need any of it, that is a signal to stop, not to add it.

The query is narrow by construction: one company, the job's own title, `limit` 2 by
default. A lookup, not a harvest.

COST, from the actor's published pricing: $0.10 per search page (up to 25 results) plus
$0.01 per profile in email mode, so roughly $0.12 per application at the default.

COVERAGE IS PARTIAL AND THE CODE MUST NOT PRETEND OTHERWISE. Email addresses are not on
LinkedIn profiles — the actor says so itself, performs a separate email search, and does
not guarantee a result. So a candidate with no email is a NORMAL return value here, the
engine's verification gate still applies, and `ManualContactSource` stays the permanent
fallback.
"""
import logging
import os

import httpx

from outreach.contacts import ContactCandidate

logger = logging.getLogger(__name__)

# `username/actor-name` is written with a tilde in the API path.
_ACTOR = "harvestapi~linkedin-profile-search"
_ENDPOINT = f"https://api.apify.com/v2/actors/{_ACTOR}/run-sync-get-dataset-items"

# ponytail: read straight from the environment rather than `core.config.Settings`,
# because REACH-A is adding Google OAuth settings to that same class concurrently and
# two appends to one Settings block is a merge conflict for no benefit. Upgrade path:
# declare `apify_token: str | None = None` on Settings and read it via `get_settings()`
# once REACH-A has landed — one line, one import, no behaviour change. Note `Settings`
# sets `extra="ignore"`, so APIFY_TOKEN in .env is silently dropped until then, which is
# exactly why this reads os.environ and not nothing.
_TOKEN_ENV = "APIFY_TOKEN"

# An actor run is not a simple GET. `_ACTOR_TIMEOUT` caps the run server-side so Apify
# stops billing and returns, and the client waits slightly longer so the cap is what
# fires rather than a local disconnect that leaves the run going.
_ACTOR_TIMEOUT = 90
_CLIENT_TIMEOUT = _ACTOR_TIMEOUT + 15


def _first_str(d: dict, *keys: str) -> str | None:
    """First non-blank string among `keys`.

    Several keys per field because the output schema below was read from the actor's
    published example and has NOT been verified against a live response — there is no
    token to run one with. The alternative to being lenient here is a silent all-None
    mapping the first time a key differs.
    """
    for k in keys:
        v = d.get(k)
        if isinstance(v, str) and v.strip():
            return v.strip()
    return None


def _names(d: dict, *keys: str) -> list[str]:
    """Names out of a list-of-objects field (`experience`, `education`), order kept and
    deduped."""
    out = []
    for item in d if isinstance(d, list) else []:
        if isinstance(item, dict):
            name = _first_str(item, *keys)
            if name:
                out.append(name)
    return list(dict.fromkeys(out))


def _location(item: dict) -> str | None:
    """`location` is a string in the published example, but LinkedIn-shaped payloads
    often nest it, so both are handled."""
    loc = item.get("location")
    if isinstance(loc, str):
        return loc.strip() or None
    if isinstance(loc, dict):
        return _first_str(loc, "linkedinText", "text", "name", "city")
    return None


def _email(item: dict) -> str | None:
    """Only present in "Full + email search" mode, and not guaranteed even then. Absence
    is normal and must never be filled in with a guess — a constructed address is exactly
    what the verification gate exists to keep out."""
    direct = _first_str(item, "email", "emailAddress", "workEmail")
    if direct:
        return direct
    emails = item.get("emails")
    if isinstance(emails, list):
        for e in emails:
            if isinstance(e, str) and e.strip():
                return e.strip()
            if isinstance(e, dict):
                got = _first_str(e, "email", "address", "value")
                if got:
                    return got
    return None


def _candidate(item: dict, company: str) -> ContactCandidate | None:
    full_name = " ".join(
        filter(None, [_first_str(item, "firstName"), _first_str(item, "lastName")])
    ) or _first_str(item, "name", "fullName", "publicIdentifier")
    if not full_name:
        # Nothing to address the email to. A greeting is not somewhere to improvise.
        return None
    return ContactCandidate(
        full_name=full_name,
        company=company,
        title=_first_str(item, "headline", "jobTitle", "title", "position"),
        email=_email(item),
        source=ApifyContactSource.name,
        source_ref=_first_str(item, "publicIdentifier", "id"),
        # `experience` carries the current employer too, which is correct: if the user
        # also worked there, "we both worked at Acme" is true and worth saying.
        # `signals.py` decides, this only reports.
        past_companies=_names(item.get("experience"), "companyName", "company", "name",
                              "organisation", "organization"),
        schools=_names(item.get("education"), "schoolName", "school", "name", "title",
                       "institution"),
        location=_location(item),
        evidence={"actor": _ACTOR},
    )


class ApifyContactSource:
    name = "apify"

    def __init__(self, mode: str = "Full + email search", token: str | None = None):
        """`mode` is the actor's `profileScraperMode`. "Full" is cheaper ($0.004 vs $0.01
        per profile) but returns no address at all, which leaves the candidate
        uncontactable — so email mode is the default and "Full" is there for when
        addresses come from somewhere else."""
        self.mode = mode
        self._token = token

    def _post(self, body: dict) -> list | None:
        token = self._token or os.environ.get(_TOKEN_ENV)
        if not token:
            # Not configured is not an error — same shape as the Reed connector and the
            # embedding pipeline, which no-op without their keys.
            return None
        try:
            r = httpx.post(
                _ENDPOINT,
                json=body,
                headers={"Authorization": f"Bearer {token}"},
                params={"timeout": _ACTOR_TIMEOUT, "format": "json"},
                timeout=_CLIENT_TIMEOUT,
            )
        except Exception as exc:
            # TYPE only. A provider's reply can echo the request, and the request carries
            # the token — `digest.smtp_sender` and `outreach/send.py` set this precedent.
            # One attempt, no retry: the spec's "no retry storm", and a failure here falls
            # through to the next source rather than blocking the application.
            logger.warning("apify contact search failed: %s", type(exc).__name__)
            return None
        if r.status_code >= 400:
            # Status code only — never the body, which can quote the request.
            logger.warning("apify contact search returned HTTP %s", r.status_code)
            return None
        try:
            items = r.json()
        except Exception as exc:
            logger.warning("apify contact search sent unparseable JSON: %s", type(exc).__name__)
            return None
        return items if isinstance(items, list) else None

    def find(self, company: str, titles: list[str], limit: int) -> list[ContactCandidate]:
        if not company or not company.strip() or limit <= 0:
            return []

        body = {
            "currentCompanies": [company.strip()],
            "maxItems": limit,
            "profileScraperMode": self.mode,
        }
        wanted = [t.strip() for t in (titles or []) if t and t.strip()]
        if wanted:
            body["currentJobTitles"] = wanted

        items = self._post(body)
        if not items:
            return []

        out = [
            c for c in (_candidate(i, company) for i in items if isinstance(i, dict))
            if c is not None
        ]
        # Contactable first, then a stable key. GAPS 6.6 was a real nondeterminism bug
        # from ranking with no tiebreaker, and with auto-send on the tiebreaker decides
        # who receives mail — so dataset order, which Apify does not promise, must not be
        # what settles it.
        out.sort(key=lambda c: (c.email is None, (c.source_ref or ""), c.full_name))
        return out[:limit]
