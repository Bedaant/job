"""Phase 2 item 4b — board tokens are the cheap coverage lever (ATS sources are
already exhaustible and already swept), but a token is only as good as the
company behind it.

Two traps this guards, both hit for real while adding the 2026-10-03 batch:

1. **An unmapped token becomes the company name.** greenhouse.py/lever.py/
   ashby.py fall back to the raw token string when `TOKEN_COMPANY_NAMES` has no
   entry, and `company` feeds `canonical_hash` — so an unmapped token means a
   board's jobs can never dedupe against the same role from a feed listing the
   real name. Lever and Ashby payloads carry no company name at all, so the map
   is the only source of truth there.

2. **A plausible slug is often a different company.** Verified live before
   adding, and three candidates were rejected on the evidence:
     slice   -> "Slice", a US/Macedonia pizza business (Ohrid, Skopje, New
                Jersey, Connecticut), not the Indian fintech.
     porter  -> "Porter Works" on Greenhouse (LA/SF/Seattle) and another US
                Porter on Lever (Amherst MA, Boston, Michigan), neither the
                Indian logistics company.
     navi    -> San Francisco only, 3 postings; the Indian Navi is Bengaluru.
   Never add a token because the slug matches a company name. Fetch the board
   and read its locations first.
"""
from connectors import config


def _all_tokens():
    return (
        [("greenhouse", t) for t in config.GREENHOUSE_BOARD_TOKENS]
        + [("lever", t) for t in config.LEVER_COMPANY_TOKENS]
        + [("ashby", t) for t in config.ASHBY_ORG_TOKENS]
        # Workday tenants are board tokens too: the same token->name rule applies,
        # and an unmapped tenant would become the `company` value (COLLECT-C).
        + [("workday", t) for t in config.WORKDAY_BOARDS]
    )


def test_every_board_token_maps_to_a_real_company_name():
    """An unmapped token silently becomes the `company` value, and therefore
    part of `canonical_hash`. See trap 1 in this module's docstring.
    """
    unmapped = [(src, t) for src, t in _all_tokens() if t not in config.TOKEN_COMPANY_NAMES]
    assert unmapped == [], f"tokens with no TOKEN_COMPANY_NAMES entry: {unmapped}"


def test_token_company_names_are_clean_display_text():
    """The map exists to beat payload cruft (Greenhouse returns "Rubrik Job
    Board" for rubrik and "Fivetran " with a trailing space), so the curated
    value must not carry that cruft itself.
    """
    for token, name in config.TOKEN_COMPANY_NAMES.items():
        assert name == name.strip(), f"{token}: {name!r} has surrounding whitespace"
        assert name, f"{token}: empty company name"
        assert "job board" not in name.lower(), f"{token}: {name!r} carries board-page cruft"


def test_no_token_is_configured_twice_on_the_same_platform():
    """A duplicate token is a duplicate fetch of the same board every run."""
    for name, tokens in (
        ("greenhouse", config.GREENHOUSE_BOARD_TOKENS),
        ("lever", config.LEVER_COMPANY_TOKENS),
        ("ashby", config.ASHBY_ORG_TOKENS),
    ):
        assert len(tokens) == len(set(tokens)), f"{name} has duplicate tokens"


def test_the_map_has_no_entries_for_tokens_nothing_fetches():
    """A name left behind after its token was removed is dead weight, and worse,
    hides that removing the token tombstoned that board's inventory.
    """
    configured = {t for _, t in _all_tokens()}
    orphans = sorted(set(config.TOKEN_COMPANY_NAMES) - configured)
    assert orphans == [], f"TOKEN_COMPANY_NAMES entries with no token: {orphans}"


# --- COLLECT-G rejects, 2026-10-10 -------------------------------------------
# 86 slugs from career-ops' portals.example.yml -> 77 answered -> 69 added.
# These eight are the rejects, pinned so re-adding one has to be deliberate.

_IDENTITY_REJECTS = {
    # slug -> (platform it answered on, what it actually is)
    "sanctuary": ("ashby", 'construction firm — "Civil Engineer", dept "Construction", '
                           "Delhi + Dripping Springs/Austin TX. Not Sanctuary AI."),
}
_RECENCY_REJECTS = {
    "hightouch": ("ashby", "1 posting, newest 2033 days old"),
    "inngest": ("ashby", "1 posting, newest 541 days old"),
    "glacis-ai": ("ashby", "2 postings, 92 days"),
    "humeai": ("greenhouse", "5 postings, 94 days"),
}


def test_identity_rejects_are_not_configured():
    """`sanctuary` is the third instance of the slug/=company trap, after
    slice/porter/navi and hevo. Its board is a CONSTRUCTION company in Delhi and
    Texas; Sanctuary AI is Vancouver robotics. A wrong company silently pollutes
    every user's match list, which is worse than a missing board.
    """
    for slug, (platform, what) in _IDENTITY_REJECTS.items():
        assert slug not in config.ASHBY_ORG_TOKENS, f"{slug} ({platform}): {what}"
        assert slug not in config.GREENHOUSE_BOARD_TOKENS, f"{slug}: {what}"
        assert slug not in config.LEVER_COMPANY_TOKENS, f"{slug}: {what}"


def test_lovable_is_the_ashby_board_and_not_the_greenhouse_one():
    """One slug, two platforms, TWO DIFFERENT COMPANIES — the sharpest version of
    the trap seen so far.

    greenhouse/lovable is Italian: 61 postings in Modena, Savignano sul Rubicone
    and Grassobbio. ashby/lovable is the Swedish AI company (Stockholm, London,
    New York). Taking the greenhouse one would have filled the pool with an
    unrelated Italian employer's jobs under the name "Lovable".
    """
    assert "lovable" in config.ASHBY_ORG_TOKENS
    assert "lovable" not in config.GREENHOUSE_BOARD_TOKENS, (
        "greenhouse/lovable is an Italian company (Modena/Grassobbio), not Lovable"
    )


def test_recency_rejects_are_not_configured():
    """An account existing proves nothing — cars24's SmartRecruiters account was
    abandoned in 2018 and still answered. Bar: newest posting within 60 days.
    """
    configured = (set(config.GREENHOUSE_BOARD_TOKENS) | set(config.LEVER_COMPANY_TOKENS)
                  | set(config.ASHBY_ORG_TOKENS))
    for slug, (platform, why) in _RECENCY_REJECTS.items():
        assert slug not in configured, f"{slug} ({platform}) was rejected: {why}"


def test_no_company_is_ingested_from_two_platforms_at_once():
    """The generalised guard, and the reason two COLLECT-G candidates were dropped.

    `helsing` answered with 158 postings on BOTH greenhouse and ashby; `qonto`
    with 49 on BOTH lever and ashby. Configuring both sides fetches one company's
    inventory twice every run, and GAPS 4.3 records that two live rows sharing a
    `canonical_hash` are never re-collapsed — so the duplicates would persist in
    every user's match list.

    Keyed on the curated company NAME rather than the token, because the same
    company can legitimately carry different slugs per platform.
    """
    seen: dict[str, str] = {}
    clashes = []
    for platform, tokens in (
        ("greenhouse", config.GREENHOUSE_BOARD_TOKENS),
        ("lever", config.LEVER_COMPANY_TOKENS),
        ("ashby", config.ASHBY_ORG_TOKENS),
        ("workday", list(config.WORKDAY_BOARDS)),
    ):
        for token in tokens:
            name = config.TOKEN_COMPANY_NAMES.get(token, token)
            if name in seen:
                clashes.append(f"{name}: {seen[name]}/{token} and {platform}/{token}")
            seen[name] = platform
    assert clashes == [], f"same company on two platforms: {clashes}"


def test_helsing_is_greenhouse_only_and_qonto_is_ashby_only():
    """The two kept sides of the duplicate pairs, with the reason each won.

    helsing -> greenhouse, because only Greenhouse's payload carries
    `company_name`; Lever and Ashby carry none, so it is one free identity signal.
    qonto -> ashby, whose location strings are fuller ("Paris, France" vs "Paris"),
    and `passes_hard_filters` reads locations.
    """
    assert "helsing" in config.GREENHOUSE_BOARD_TOKENS
    assert "helsing" not in config.ASHBY_ORG_TOKENS
    assert "qonto" in config.ASHBY_ORG_TOKENS
    assert "qonto" not in config.LEVER_COMPANY_TOKENS
