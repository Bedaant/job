"""SPEC.md §3.5 parse-back check: render -> extract text -> fuzzy-match each
bullet against its source fact at >=0.9 similarity. A bullet that doesn't
survive the round trip fails the build — this is the check, run it in CI on
every template change (SPEC's own words).
"""
from rapidfuzz import fuzz

from parsing.extract import extract_text_from_docx

SIMILARITY_THRESHOLD = 0.9


def parse_back_check(docx_bytes: bytes, facts: list[dict]) -> list[dict]:
    extracted_text = extract_text_from_docx(docx_bytes)

    results = []
    for fact in facts:
        similarity = fuzz.partial_ratio(fact["achievement"], extracted_text) / 100
        results.append({
            "fact_id": fact["id"],
            "similarity": similarity,
            "passed": similarity >= SIMILARITY_THRESHOLD,
        })
    return results
