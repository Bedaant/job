"""Text from job pages and forms is data, never instructions (NEXT-WORK-PLAN 4.5, P1 #17)."""
import re

# ponytail: a phrase list, not a classifier. Callers keep a second line (the evidence check,
# the truth gate, human review) for anything phrased around it.
INJECTION = re.compile(
    r"\bignore\b.{0,20}\b(?:previous|prior|above|earlier|all)\b|\bdisregard\b|system prompt"
    r"|\byou are now\b|\bnew instructions\b|(?:^|\W)(?:system|assistant)\s*:"
    r"|\b(?:answer|fill|select|pick)\b.{0,15}\b(?:every|all)\b.{0,15}\b(?:question|field)s?\b",
    re.I,
)


def looks_like_instructions(text: str | None) -> bool:
    return bool(text and INJECTION.search(text))
