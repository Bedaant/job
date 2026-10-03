from datetime import datetime

from connectors.normalize import canonical_hash, coerce_posted_at, normalize_location


def test_canonical_hash_same_job_different_sources_matches():
    # Same role, slightly different company-suffix/title casing — must collapse to one hash
    h1 = canonical_hash("Acme Corp Inc", "Senior Backend Engineer", "Remote")
    h2 = canonical_hash("Acme Corp, Inc.", "senior backend engineer", "remote")
    assert h1 == h2


def test_canonical_hash_strips_seniority_suffix_noise():
    h1 = canonical_hash("Acme", "Backend Engineer II", "Remote")
    h2 = canonical_hash("Acme", "Backend Engineer", "Remote")
    assert h1 == h2


def test_canonical_hash_different_companies_differ():
    h1 = canonical_hash("Acme", "Backend Engineer", "Remote")
    h2 = canonical_hash("Globex", "Backend Engineer", "Remote")
    assert h1 != h2


def test_canonical_hash_different_locations_differ():
    h1 = canonical_hash("Acme", "Backend Engineer", "Remote")
    h2 = canonical_hash("Acme", "Backend Engineer", "Berlin, Germany")
    assert h1 != h2


def test_canonical_hash_is_deterministic_and_hex():
    h = canonical_hash("Acme", "Backend Engineer", "Remote")
    assert h == canonical_hash("Acme", "Backend Engineer", "Remote")
    assert len(h) == 64
    int(h, 16)  # raises if not valid hex


def test_normalize_location_remote_variants_collapse():
    assert normalize_location("Remote") == "remote"
    assert normalize_location("REMOTE - US") == "remote"
    assert normalize_location("Fully remote") == "remote"


def test_normalize_location_city_country_normalized():
    assert normalize_location("Berlin, Germany") == normalize_location("berlin,  germany")


def test_normalize_location_none_returns_empty_string():
    assert normalize_location(None) == ""


def test_coerce_posted_at_iso_with_z_suffix():
    assert coerce_posted_at("2026-09-09T10:50:29Z") == datetime(2026, 9, 9, 10, 50, 29)


def test_coerce_posted_at_iso_with_offset_converts_to_utc_naive():
    assert coerce_posted_at("2026-09-09T10:50:29-04:00") == datetime(2026, 9, 9, 14, 50, 29)


def test_coerce_posted_at_epoch_seconds():
    assert coerce_posted_at(1790265606) == datetime(2026, 9, 24, 16, 0, 6)


def test_coerce_posted_at_epoch_milliseconds():
    assert coerce_posted_at(1790265606000) == datetime(2026, 9, 24, 16, 0, 6)


def test_coerce_posted_at_none_returns_none():
    assert coerce_posted_at(None) is None


def test_coerce_posted_at_empty_string_returns_none():
    assert coerce_posted_at("") is None


def test_coerce_posted_at_garbage_string_returns_none():
    assert coerce_posted_at("not a date") is None


def test_coerce_posted_at_datetime_passes_through_unchanged():
    dt = datetime(2026, 1, 1, 0, 0, 0)
    assert coerce_posted_at(dt) == dt


def test_coerce_posted_at_compact_numeric_date_parses_as_iso_date():
    # "20260909" is a valid ISO 8601 basic-format date -- a str is always
    # read as a date string (or None), never as a numeric epoch value.
    assert coerce_posted_at("20260909") == datetime(2026, 9, 9)


def test_coerce_posted_at_longer_compact_form_returns_none():
    # "20260909120000" (14 digits) is not a date string Python's ISO parser
    # accepts (no separators for the time component). With no numeric-epoch
    # fallback for strings, it is simply None -- not a misread.
    assert coerce_posted_at("20260909120000") is None


def test_coerce_posted_at_another_compact_datetime_form_also_returns_none():
    assert coerce_posted_at("20261231235959") is None


def test_coerce_posted_at_invalid_calendar_compact_date_feb_30_returns_none():
    # "20260230" -- Feb 30 does not exist. fromisoformat rejects it
    # (day out of range for month); there is no numeric fallback left to
    # misread it as epoch seconds, so it is None.
    assert coerce_posted_at("20260230") is None


def test_coerce_posted_at_invalid_calendar_month_99_returns_none():
    # "99999999" -- month 99 is invalid. Previously this fell through to a
    # numeric interpretation and silently became a wrong-but-plausible
    # 1973-03-03 (small enough to pass every magnitude/window guard tried in
    # earlier rounds). With the numeric-string path removed entirely, an
    # invalid date string is just None.
    assert coerce_posted_at("99999999") is None


def test_coerce_posted_at_invalid_calendar_year_zero_returns_none():
    # "00000101" -- year 0 is invalid (datetime's minimum year is 1).
    assert coerce_posted_at("00000101") is None


def test_coerce_posted_at_epoch_value_as_string_is_not_supported_returns_none():
    # No wired connector sends an epoch as a string (Greenhouse/Ashby send
    # ISO strings, JobSpy sends a date string, Lever sends epoch ms as a
    # number). Three rounds of trying to distinguish a genuine numeric-epoch
    # string from an invalid/compact date string each produced a different
    # wrong-but-plausible datetime for some input. A str is parsed as a date
    # or it's None -- full stop, no epoch interpretation for strings at all.
    assert coerce_posted_at("1790265606") is None
    assert coerce_posted_at("1790265606000") is None


def test_coerce_posted_at_epoch_seconds_as_number_still_works():
    # Pins the str/number distinction: the exact same value as an int is a
    # genuine epoch-seconds timestamp and must still decode correctly.
    assert coerce_posted_at(1790265606) == datetime(2026, 9, 24, 16, 0, 6)
