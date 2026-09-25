"""Near-duplicate job detection beyond exact canonical_hash dedupe (F4,
SPEC.md §3.1) — DEPENDENCIES.md §3: seomoz/simhash-py's algorithm (MIT,
"unmaintained since 2023, safer to pin a copy"). The actual upstream package
is a Cython/C++ extension (185KB simhash.cpp) needing a compiler toolchain
to build — this project already declined that class of dependency once
(garak, needs Rust/Cargo, 2026-08-15 WORKLOG entry). Charikar's simhash
algorithm itself is small and well-documented; reimplemented in pure Python
here rather than vendoring native code, matching this project's existing
"study upstream, reimplement, don't copy" pattern (esco-skill-extractor,
ats-scrapers in DEPENDENCIES.md §3).
"""
import hashlib
import re

_BITS = 64
_TOKEN_PATTERN = re.compile(r"\w+")


def _token_hash(token: str) -> int:
    return int.from_bytes(hashlib.blake2b(token.encode(), digest_size=8).digest(), "big")


def simhash(text: str) -> int:
    """64-bit weighted fingerprint. Similar text -> low Hamming distance."""
    weights = [0] * _BITS
    for token in _TOKEN_PATTERN.findall(text.lower()):
        h = _token_hash(token)
        for bit in range(_BITS):
            weights[bit] += 1 if (h >> bit) & 1 else -1

    fingerprint = 0
    for bit in range(_BITS):
        if weights[bit] > 0:
            fingerprint |= 1 << bit
    return fingerprint


def hamming_distance(a: int, b: int) -> int:
    return bin(a ^ b).count("1")


def is_near_duplicate(a: int, b: int, threshold: int = 3) -> bool:
    return hamming_distance(a, b) <= threshold
