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
