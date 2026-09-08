"""Semantic pest matching — the retrieval half of the pest RAG hybrid.

WHY THIS EXISTS
----------------
`pest_knowledge.PEST_KB` only matches an EXACT key. The vision model
(`pest_vision.py`) used to be forced to pick a name from that fixed list,
which meant any pest outside it got silently mis-labelled as the nearest
listed one — confident-looking, but wrong.

This module lets the vision model describe a pest in its own words, then
finds the closest real KB entry by meaning (embedding cosine similarity)
rather than exact string match. Two outcomes:

  - similarity >= PEST_SEMANTIC_MATCH_THRESHOLD: treat it as that KB entry.
    Every fact shown to the farmer still comes from the verified KB — this
    only widens *matching*, it never invents agronomic facts.
  - similarity below threshold: genuinely not in the KB. The caller
    (`pest_vision.py` / `pest_pipeline.py`) should route to
    `pest_rag_fallback.py` instead of guessing.

CACHING
-------
KB entry embeddings are computed once per process and kept in memory
(`_KB_EMBEDDING_CACHE`). They also don't change at runtime, so recomputing
per request would just add latency for nothing.
"""
from __future__ import annotations

import logging
import math
from typing import Dict, List, Optional, Tuple

from app.ai.llm import get_client, GeminiError
from app.core.config import settings
from app.ml.pest_knowledge import PEST_KB

log = logging.getLogger("agri.pest_embeddings")

EMBED_URL_TMPL = (
    "https://generativelanguage.googleapis.com/v1beta/models/{model}:embedContent"
)

# name -> embedding vector, populated lazily on first use.
_KB_EMBEDDING_CACHE: Dict[str, List[float]] = {}


def _kb_reference_text(name: str, entry: dict) -> str:
    """Short text representing a KB entry for embedding — name, crops and
    symptoms carry the most identifying signal; long control text doesn't."""
    crops = ", ".join(entry.get("affected_crops", []))
    return f"{name}. Affects: {crops}. Symptoms: {entry.get('symptoms', '')}"


async def embed_text(text: str) -> List[float]:
    """Embed one piece of text via Gemini's embedding endpoint.

    Raises GeminiError on failure — callers decide the fallback, same
    convention as chat_strict() in app/ai/llm.py.
    """
    if not settings.GEMINI_API_KEY:
        raise GeminiError("no_key", "GEMINI_API_KEY is not set; cannot embed text.")

    model = settings.GEMINI_EMBEDDING_MODEL
    url = EMBED_URL_TMPL.format(model=model)
    client = get_client()
    payload = {"content": {"parts": [{"text": text}]}}
    headers = {"x-goog-api-key": settings.GEMINI_API_KEY, "Content-Type": "application/json"}

    resp = await client.post(url, json=payload, headers=headers)
    if resp.status_code != 200:
        raise GeminiError("embed_error",
                          f"Embedding request failed (HTTP {resp.status_code}): "
                          f"{resp.text[:200]}", resp.status_code)
    data = resp.json()
    values = (data.get("embedding") or {}).get("values")
    if not values:
        raise GeminiError("embed_empty", "Embedding response had no values.")
    return values


def _cosine(a: List[float], b: List[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


async def _get_kb_embeddings() -> Dict[str, List[float]]:
    """Build (once) and return name -> embedding for every PEST_KB entry."""
    missing = [n for n in PEST_KB if n not in _KB_EMBEDDING_CACHE]
    for name in missing:
        text = _kb_reference_text(name, PEST_KB[name])
        try:
            _KB_EMBEDDING_CACHE[name] = await embed_text(text)
        except GeminiError as exc:
            log.error("Could not embed KB entry '%s': %s", name, exc)
    return _KB_EMBEDDING_CACHE


async def semantic_match_pest(
    guess_name: str, description: str = ""
) -> Tuple[Optional[str], float]:
    """Find the closest PEST_KB entry to a free-text vision guess.

    Returns (matched_name, similarity). matched_name is None when nothing
    clears settings.PEST_SEMANTIC_MATCH_THRESHOLD — the caller should treat
    that as "not in the curated KB" rather than force a guess.
    """
    query_text = guess_name if not description else f"{guess_name}. {description}"
    query_text = query_text.strip()
    if not query_text:
        return None, 0.0

    try:
        query_vec = await embed_text(query_text)
        kb_vecs = await _get_kb_embeddings()
    except GeminiError as exc:
        log.error("Semantic pest match unavailable (%s): %s", exc.kind, exc)
        return None, 0.0

    best_name, best_score = None, 0.0
    for name, vec in kb_vecs.items():
        score = _cosine(query_vec, vec)
        if score > best_score:
            best_name, best_score = name, score

    if best_score >= settings.PEST_SEMANTIC_MATCH_THRESHOLD:
        log.info("Semantic match: '%s' -> '%s' (similarity %.3f, threshold %.2f)",
                 query_text, best_name, best_score, settings.PEST_SEMANTIC_MATCH_THRESHOLD)
        return best_name, best_score
    log.info("No semantic match: '%s' closest was '%s' (similarity %.3f, below "
             "threshold %.2f)", query_text, best_name, best_score,
             settings.PEST_SEMANTIC_MATCH_THRESHOLD)
    return None, best_score


async def nearest_kb_entries(
    guess_name: str, description: str = "", k: int = 3
) -> List[Tuple[str, float]]:
    """Top-k KB entries by similarity, regardless of threshold — used as
    reference context for the ungrounded-fallback generator, never as a
    confident identification."""
    query_text = (guess_name if not description else f"{guess_name}. {description}").strip()
    if not query_text:
        return []
    try:
        query_vec = await embed_text(query_text)
        kb_vecs = await _get_kb_embeddings()
    except GeminiError as exc:
        log.error("Nearest-KB lookup unavailable (%s): %s", exc.kind, exc)
        return []

    scored = sorted(
        ((name, _cosine(query_vec, vec)) for name, vec in kb_vecs.items()),
        key=lambda kv: kv[1], reverse=True,
    )
    return scored[:k]