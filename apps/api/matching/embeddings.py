"""Voyage AI embeddings (DEPENDENCIES.md §1.4 — hosted embeddings chosen over
sentence-transformers). No-ops (returns None) if VOYAGE_API_KEY isn't
configured, same pattern as the Reed connector for optional external config.
"""
import voyageai

from core.config import get_settings
from providers import guard

MODEL = "voyage-3-lite"  # 512-dim, matches models.EMBEDDING_DIM
_USD_PER_TOKEN = 0.02 / 1_000_000  # voyage-3-lite list price


def embed_texts(texts: list[str], input_type: str) -> list[list[float]] | None:
    """input_type is 'query' or 'document' per Voyage's asymmetric-embedding
    guidance. Returns None if no API key configured or texts is empty.
    """
    if not texts:
        return None
    api_key = get_settings().voyage_api_key
    if not api_key:
        return None
    client = voyageai.Client(api_key=api_key, timeout=guard.timeout("voyage"))
    cost = sum(len(t) for t in texts) / 4 * _USD_PER_TOKEN
    result = guard.call("voyage", lambda: client.embed(texts, model=MODEL, input_type=input_type),
                        cost_usd=cost)
    return result.embeddings


def compute_centroid(embeddings: list[list[float]]) -> list[float]:
    """Mean of fact embeddings, for Profile.fact_centroid (SPEC.md §3.2)."""
    dim = len(embeddings[0])
    return [sum(e[i] for e in embeddings) / len(embeddings) for i in range(dim)]


def cosine_similarity(a: list[float], b: list[float]) -> float:
    """1.0 = identical direction, 0.0 = orthogonal. Used as the `semantic`
    input to matching.scoring.compute_match_score (SPEC.md §3.2's formula
    is defined as `1 - cosine_distance`, i.e. cosine similarity)."""
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = sum(x * x for x in a) ** 0.5
    norm_b = sum(y * y for y in b) ** 0.5
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)
