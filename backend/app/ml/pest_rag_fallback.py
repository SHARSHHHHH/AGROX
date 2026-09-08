"""Grounded-generation fallback for pests the curated KB doesn't cover.

This is the last resort in the hybrid pipeline, reached only when:
  1. the pest doesn't exactly match a PEST_KB key, AND
  2. pest_embeddings.semantic_match_pest() found nothing above the
     similarity threshold either.

Design choices that keep this honest rather than a hallucination risk:

  - The model is given ONLY the retrieved nearest-KB reference text as
    context — never asked to recall pest facts from its own training data.
  - It is explicitly told it may be wrong about the exact species and must
    say so, and must always defer to a human (local KVK / agricultural
    extension officer) before any chemical use.
  - No specific chemical product, dose, or "definitely" language is allowed
    to reach the user — `_passes_guardrail()` checks for both and, on
    failure, the caller gets a safe canned response instead of the model's
    text. Silent, generic degradation beats a plausible-sounding wrong
    answer here.
  - Every response is tagged `verified: False` and `origin: "ai_fallback"`
    so the API/frontend can visibly distinguish it from curated-KB answers
    the rest of the pipeline returns.
"""
from __future__ import annotations

import re
from typing import List, Tuple

from app.ai.llm import chat_strict, GeminiError
from app.ml.pest_knowledge import PEST_KB

# Phrases that would overstate certainty or imply a specific treatable
# product/dose — if the model's output contains any of these, discard it.
_BANNED_PATTERNS = [
    r"\bdefinitely\b", r"\bcertainly is\b", r"\b100% \b",
    r"\bmg/l\b", r"\bml/l\b", r"\bg/l\b", r"\bppm\b",
]

_SAFE_FALLBACK_MESSAGE = (
    "This doesn't clearly match a pest in the verified database, so no "
    "specific treatment can be safely recommended from this photo alone. "
    "Please take a clear close-up of the insect and the damage pattern and "
    "show it to your local Krishi Vigyan Kendra (KVK) or agricultural "
    "extension officer for confirmation before taking any action, "
    "especially before using any chemical control."
)


def _reference_context(nearest: List[Tuple[str, float]]) -> str:
    lines = []
    for name, score in nearest:
        entry = PEST_KB.get(name)
        if not entry:
            continue
        lines.append(
            f"- {name} (similarity {score:.2f}): affects "
            f"{', '.join(entry.get('affected_crops', []))}. "
            f"Symptoms: {entry.get('symptoms', '')}"
        )
    return "\n".join(lines) if lines else "(no reasonably similar reference entries found)"


def _passes_guardrail(text: str) -> bool:
    lowered = text.lower()
    if any(re.search(p, lowered) for p in _BANNED_PATTERNS):
        return False
    if "extension" not in lowered and "kvk" not in lowered:
        return False
    return True


async def grounded_fallback(
    pest_guess: str,
    crop: str,
    visible_indicators: str,
    nearest: List[Tuple[str, float]],
) -> dict:
    """Produce an honest, hedge-first advisory grounded only in nearest-KB
    reference text, or the safe canned message if generation fails the
    guardrail check.

    Returns a dict shaped for pest_pipeline.run_pest_pipeline's grounded_facts
    convention: {"summary": str, "grounded_facts": [str, ...], "verified": False}.
    """
    context = _reference_context(nearest)
    system = (
        "You are an agricultural assistant helping a smallholder farmer in "
        "India. You have NOT confirmed the exact pest species — only the "
        "farmer's rough description and some possibly-similar reference "
        "entries are available. You must:\n"
        "1. Never claim certainty about the exact pest identity.\n"
        "2. Use ONLY the reference entries below as factual grounding — do "
        "not add any pest facts from general knowledge.\n"
        "3. Recommend only general, safe, non-chemical first steps "
        "(monitoring, removing affected material, sanitation) appropriate "
        "across the reference entries.\n"
        "4. Always tell the farmer to confirm with their local Krishi "
        "Vigyan Kendra (KVK) or agricultural extension officer before any "
        "chemical use.\n"
        "5. Never name a specific chemical product or give a dose.\n"
        "Keep the answer under 120 words."
    )
    user = (
        f"Crop: {crop or 'not specified'}\n"
        f"Farmer's description / model guess: {pest_guess or 'not specified'}\n"
        f"Visible indicators from the photo: {visible_indicators or 'not specified'}\n\n"
        f"Possibly related reference entries (may not be the actual pest):\n{context}\n\n"
        "Write a short, hedged, safe first-response for the farmer."
    )

    try:
        text = await chat_strict(system, user, temperature=0.2, max_output_tokens=300)
    except GeminiError:
        text = ""

    if not text or not _passes_guardrail(text):
        return {
            "summary": _SAFE_FALLBACK_MESSAGE,
            "grounded_facts": [
                "The photo did not clearly match any pest in the verified "
                "knowledge base.",
                "No treatment is recommended without expert confirmation.",
            ],
            "verified": False,
            "origin": "ai_fallback_safe_default",
        }

    facts = [
        "This pest could not be matched to the verified knowledge base with "
        "confidence; the guidance below is general and hedged, not a "
        "confirmed diagnosis.",
    ]
    if nearest:
        facts.append(
            "Closest reference entries considered: "
            + ", ".join(f"{n} ({s:.0%} similar)" for n, s in nearest)
        )

    return {
        "summary": text,
        "grounded_facts": facts,
        "verified": False,
        "origin": "ai_fallback",
    }
