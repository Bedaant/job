from matching.near_duplicate import simhash, hamming_distance, is_near_duplicate


def test_simhash_identical_text_same_fingerprint():
    a = simhash("Senior Backend Engineer at Acme building Python microservices")
    b = simhash("Senior Backend Engineer at Acme building Python microservices")
    assert a == b


def test_simhash_reworded_title_is_near_duplicate():
    """The exact case DEPENDENCIES.md calls out: same job, reworded title,
    which canonical_hash's exact-match dedupe misses."""
    a = simhash("Senior Backend Engineer - Python/FastAPI - Remote")
    b = simhash("Backend Engineer (Senior) - Python & FastAPI - Remote")
    assert is_near_duplicate(a, b, threshold=10)


def test_simhash_unrelated_jobs_are_not_near_duplicates():
    a = simhash("Senior Backend Engineer building Python microservices at Acme")
    b = simhash("Growth Marketing Manager running paid acquisition at Ferngrove")
    assert not is_near_duplicate(a, b, threshold=3)


def test_hamming_distance_identical_is_zero():
    assert hamming_distance(0b1010, 0b1010) == 0


def test_hamming_distance_counts_differing_bits():
    assert hamming_distance(0b1010, 0b1000) == 1
    assert hamming_distance(0b1111, 0b0000) == 4
