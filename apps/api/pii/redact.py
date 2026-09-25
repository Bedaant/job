"""PII redaction for cached company dossiers (F7) and generation history (F8),
DEPENDENCIES.md §3. Microsoft Presidio, MIT — analyzer detects entities
(names, emails, phone numbers, etc.), anonymizer replaces them with
`<ENTITY_TYPE>` placeholders. Module-level singletons: AnalyzerEngine() loads
a spaCy NLP model (en_core_web_lg, ~400MB, downloaded once on first import),
expensive to construct per-call.
"""
from presidio_analyzer import AnalyzerEngine
from presidio_anonymizer import AnonymizerEngine

_analyzer = AnalyzerEngine()
_anonymizer = AnonymizerEngine()


def redact_pii(text: str) -> str:
    if not text:
        return text
    results = _analyzer.analyze(text=text, language="en")
    return _anonymizer.anonymize(text, results).text
