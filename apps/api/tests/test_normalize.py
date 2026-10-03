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
    # "20260909" is a valid ISO 8601 basic-format date. Date parsing is tried
    # before any numeric/epoch interpretation, so it is read as the date it
    # actually is, not misread as epoch seconds (which would wrongly give
    # 1970-08-23).
    assert coerce_posted_at("20260909") == datetime(2026, 9, 9)


def test_coerce_posted_at_longer_compact_form_misread_as_epoch_ms_returns_none():
    # "20260909120000" (14 digits) is not a date string Python's ISO parser
    # accepts (no separators), so it falls to the numeric path, where its
    # magnitude (>1e12) gets read as epoch milliseconds -- decoding to the
    # year 2612. That is outside the sane calendar window, so it is rejected
    # as None rather than returned as a wrong-but-plausible datetime. This is
    # the regression a plain magnitude floor did not close (it only moved
    # the boundary); the fix is to validate the *decoded* date, not the
    # input's magnitude.
    assert coerce_posted_at("20260909120000") is None


def test_coerce_posted_at_another_compact_datetime_form_also_returns_none():
    # A second 14-digit compact datetime ("20261231235959"), same failure
    # class as above: decodes to year 2612 as epoch-ms, rejected as None.
    assert coerce_posted_at("20261231235959") is None


def test_coerce_posted_at_epoch_seconds_string_still_works():
    assert coerce_posted_at("1790265606") == datetime(2026, 9, 24, 16, 0, 6)


def test_coerce_posted_at_epoch_milliseconds_string_still_works():
    assert coerce_posted_at("1790265606000") == datetime(2026, 9, 24, 16, 0, 6)


def test_coerce_posted_at_nine_digit_numeric_string_is_a_genuine_epoch_value():
    # 999999999 is not a date string and decodes to 2001-09-09, a wholly
    # plausible epoch-seconds timestamp -- the earlier magnitude-floor fix
    # rejected this as an arbitrary side effect of where its floor sat; the
    # calendar-window check correctly accepts it since there is nothing
    # actually wrong with this value.
    assert coerce_posted_at("999999999") == datetime(2001, 9, 9, 1, 46, 39)


def test_coerce_posted_at_billion_second_boundary_is_epoch():
    assert coerce_posted_at("1000000000") == datetime(2001, 9, 9, 1, 46, 40)
