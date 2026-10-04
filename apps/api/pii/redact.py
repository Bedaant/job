"""PII redaction for cached company dossiers (F7) and generation history (F8),
DEPENDENCIES.md §3. Microsoft Presidio, MIT — analyzer detects entities
(names, emails, phone numbers, etc.), anonymizer replaces them with
`<ENTITY_TYPE>` placeholders. Module-level singletons: AnalyzerEngine() loads
a spaCy NLP model (en_core_web_lg, ~400MB, downloaded once on first import),
expensive to construct per-call.
"""
from collections.abc import Iterable

from presidio_analyzer import AnalyzerEngine, PatternRecognizer
from presidio_anonymizer import AnonymizerEngine

_analyzer = AnalyzerEngine()
_anonymizer = AnonymizerEngine()


def redact_pii(text: str, known_names: Iterable[str | None] = ()) -> str:
    """Replace detected PII with `<ENTITY_TYPE>` placeholders.

    `known_names` is matched exactly rather than left to the NER model.
    Measured 2026-10-04: spaCy's `en_core_web_lg` labels some uncommon names
    ORG instead of PERSON — "Bedaant Srivastav" survived redaction while
    "John Smith", "Priya Sharma" and "Rahul Gupta" were caught. For a product
    aimed at Indian users that is the wrong failure to accept, and the name
    that matters is not a guess: a profile already stores `full_name`, so
    callers pass it and it is redacted by a deny-list regardless of what the
    model thinks (verified live: deny-list hits PERSON at score 1.0).

    Blank and duplicate entries are dropped — a deny_list containing "" would
    match everywhere, which a profile with no `full_name` set would otherwise
    produce.
    """
    if not text:
        return text
    names = list(dict.fromkeys(n.strip() for n in known_names if n and n.strip()))
    recognizers = (
        [PatternRecognizer(supported_entity="PERSON", deny_list=names)] if names else None
    )
    results = _analyzer.analyze(text=text, language="en", ad_hoc_recognizers=recognizers)
    return _anonymizer.anonymize(text, results).text
