"""Shared defensive check: never trust an LLM to reference an id it wasn't
actually given. A model can invent a plausible-looking id that doesn't exist
in the real dataset it was shown (a fact id, a form field id, ...) — this is
the single place that check lives, instead of being reimplemented per call
site (previously: tailoring/engine.py's Bullet field_validator did this
inline; formfill/map_fields.py achieved it only implicitly via a dict.get
that silently drops unknown ids).
"""


def validate_ids_against_known_set(ids: list[str], known_ids: set[str], *, field_name: str) -> list[str]:
    """Return `ids` unchanged if every one is in `known_ids`; otherwise raise
    ValueError naming the invented id(s), so the caller decides what to do
    (e.g. instructor retry, or catch-and-degrade)."""
    unknown = [i for i in ids if i not in known_ids]
    if unknown:
        raise ValueError(f"{field_name} references id(s) not present in the known set: {unknown}")
    return ids
