"""REACH-C — why this person, and in what order (`docs/PLAN-OUTREACH.md`).

A referral ask that opens with a real connection reads as a person writing to a person.
One that opens with "I saw your profile" reads as a mail merge. This module decides which
connection, if any, is true — and refuses to assert one that is not.

WHAT THE DATA ACTUALLY SUPPORTS. `ResumeFact` has no structured employer or school
column: it carries `category`, free-text `achievement` and `proof`, `metric`, `tags` and
a date range. So employer and school overlap cannot be a key comparison. They are text
matches against the user's own facts, which is a heuristic with a real ceiling — see the
`ponytail:` note on `_mentions`.

And what is known about the CONTACT depends on which adapter found them (see
`contacts.ContactCandidate`). GitHub supplies no work history, education or location, so
a GitHub candidate usually reaches `same_role` or `none`. That is the right answer for
the data available, not a gap to fill by guessing.
"""
from models import ResumeFact

from outreach.contacts import ContactCandidate, _title_tokens

# Strongest first. The email leads with whichever of these is found.
_RANK = {
    "former_employer": 0,   # verifiable, specific, and the strongest opener there is
    "same_role": 1,         # owner's addition: a PM asking a PM is a natural approach
    "same_university": 2,
    "same_city": 3,
    "none": 4,
}

# Stripped before matching a company name, so "Flipkart" matches "Flipkart Internet Pvt
# Ltd". `connectors/normalize.py` does the same job for job rows; this is deliberately a
# separate, smaller list rather than a shared import, because that one is tuned for
# dedupe keys and changing it would move `canonical_hash` for every stored job.
_CORP_NOISE = (
    " private limited", " pvt ltd", " pvt. ltd.", " pvt", " limited", " ltd", " llc",
    " inc", " corp", " corporation", " technologies", " technology", " labs",
    " internet", " india", " solutions", " services", " group", ".com", ",", ".",
)

# Below this, a name is a substring of ordinary prose: "HP" hits "sHiPped" and "PHP".
# A short employer is better missed than falsely asserted in an email someone sends
# under their own name.
_MIN_MATCH_LEN = 4


def _strip_corp(name: str) -> str:
    out = name.strip().casefold()
    for noise in _CORP_NOISE:
        out = out.replace(noise, " ")
    return " ".join(out.split())


def _mentions(needle: str, facts: list[ResumeFact], categories: tuple[str, ...]) -> str | None:
    """Return the id of the first fact whose text mentions `needle`, else None.

    ponytail: substring match over free text, because `ResumeFact` has no employer or
    school column. Ceiling: it cannot tell "worked at Acme" from "competitor of Acme",
    and it misses an employer the user never named in a fact. Upgrade path is structured
    employer/school fields on `ResumeFact`, populated at parse time — which is a resume
    parser change, not a change here.
    """
    key = _strip_corp(needle)
    if len(key) < _MIN_MATCH_LEN:
        return None
    for fact in sorted(facts, key=lambda f: (f.created_at or 0, f.id)):
        if fact.category not in categories:
            continue
        haystack = _strip_corp(" ".join(filter(None, [fact.achievement, fact.proof])))
        if key in haystack:
            return fact.id
    return None


def _signal(c: ContactCandidate, facts: list[ResumeFact], profile, job_title: str) -> dict:
    """The strongest TRUE connection between this contact and this user.

    Order matters and short-circuits: the first hit wins, so a former colleague is
    approached as a former colleague even if they also share a city.
    """
    # 1. Both worked at the same company. Needs the contact's history (Apify, not GitHub).
    for company in c.past_companies:
        fact_id = _mentions(company, facts, ("experience",))
        if fact_id:
            return {"kind": "former_employer", "value": company, "source_fact_id": fact_id}

    # 2. They hold the role being applied for. Asserts nothing about the USER — it is
    # verifiable from `Job.title` plus their own title, both already in the system — so
    # it carries no fact id and needs none.
    if c.title and job_title:
        wanted = _title_tokens([job_title])
        theirs = _title_tokens([c.title])
        shared = wanted & theirs
        if shared:
            return {"kind": "same_role", "value": c.title, "source_fact_id": None,
                    "shared_terms": sorted(shared)}

    # 3. Same university.
    for school in c.schools:
        fact_id = _mentions(school, facts, ("education",))
        if fact_id:
            return {"kind": "same_university", "value": school, "source_fact_id": fact_id}

    # 4. Same city. `Profile.city` is structured, so this one is a real comparison rather
    # than a text search — but the contact's location is free text ("Bengaluru, India"),
    # so the city has to be found inside it.
    if c.location and profile is not None and profile.city:
        if _strip_corp(profile.city) in _strip_corp(c.location):
            return {"kind": "same_city", "value": profile.city, "source_fact_id": None}

    return {"kind": "none", "value": None, "source_fact_id": None}


def rank_contacts(
    candidates: list[ContactCandidate],
    facts: list[ResumeFact],
    profile,
    job_title: str,
) -> list[ContactCandidate]:
    """Annotate each candidate with its warm signal and return them strongest first.

    Ordering is deterministic. GAPS 6.6 records a real nondeterminism bug from ranking
    with no tiebreaker — which job a capped run applied to was undefined whenever two
    rows tied. It matters more here: with auto-send on, the tiebreaker decides who
    receives mail.
    """
    facts = list(facts or [])
    for c in candidates:
        c.warm_signal = _signal(c, facts, profile, job_title)
    return sorted(
        candidates,
        key=lambda c: (_RANK[c.warm_signal["kind"]], (c.email or "").casefold(), c.full_name),
    )
