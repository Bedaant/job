from connectors.normalize import canonical_hash, normalize_location


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
