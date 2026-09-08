"""Pest detection via Google Gemini Vision — now hybrid.

The vision model only picks a label (or, when nothing on the known list
fits, a free-text description) and confidence; all pest facts still come
from PEST_KB, never from the model.

Hybrid matching, in order:
  1. Exact match against PEST_KB (fast path, the original behaviour).
  2. Semantic match — embed the model's free-text guess and compare against
     PEST_KB entries by meaning (pest_embeddings.semantic_match_pest). Lets
     a locally-worded or slightly different-sounding pest still resolve to
     the correct verified KB entry instead of getting force-fit into the
     nearest LISTED name or dismissed as unknown.
  3. RAG fallback — if nothing matches closely enough, hand back the
     nearest reference entries for pest_pipeline to run through
     pest_rag_fallback.grounded_fallback(), which hedges instead of
     guessing.

  - the vision model never fabricates a disease diagnosis; it just reports
    the model's disease/pest determination and, if a pest, either grounds
    the details in PEST_KB directly or triggers the fallback path.
  - low confidence -> explicit "Unknown / Low confidence", never a guess
    dressed up as certainty
"""
from __future__ import annotations

import json
import logging
import re

from PIL import Image
from app.core.config import settings
from app.ml.pest_knowledge import PEST_KB, KNOWN_PESTS
from app.ml.pest_embeddings import semantic_match_pest, nearest_kb_entries

log = logging.getLogger("agri.pest_vision")

# Reuse the same confidence bar as disease detection for consistency.
CONFIDENCE_THRESHOLD = 0.55


def validate_image(path: str) -> bool:
    """Same basic validation as disease detection: real image, not tiny."""
    try:
        img = Image.open(path)
        img.verify()
        img = Image.open(path)
        w, h = img.size
        return w >= 64 and h >= 64
    except Exception:
        return False


async def detect_pest(path: str, crop: str = "") -> dict:
    """Return a structured pest determination for an image.

    Result shape (never raises for model issues — degrades honestly):
      {
        "type": "pest" | "pest_unmatched" | "disease" | "healthy" | "uncertain",
        "pest_name": str | None,
        "crop": str,
        "confidence": float,
        "visible_infestation": "none|low|moderate|high|unknown",
        "affected_leaf_pct": float | None,
        "kb": <PEST_KB entry> | None,
        "uncertain": bool,
        "message": str | None,        # present when uncertain
        "model_guess": str | None,    # low-confidence guess, if any
        "matched_via": "exact" | "semantic" | None,
        "nearest_candidates": [(name, score), ...],   # only for pest_unmatched
      }
    """
    if not validate_image(path):
        return _uncertain("The uploaded file does not look like a valid plant image. "
                          "Please upload a clear photo of the affected leaves or the insect.")

    try:
        data = await _gemini_pest(path, crop)
    except Exception as e:
        log.error("Pest vision call failed (%s): %s", type(e).__name__, e)
        return _uncertain(f"Vision model is unavailable right now ({type(e).__name__}). "
                          "Please try again shortly or consult an agricultural expert.")

    return await _resolve_pest(data, crop)


def _pest_prompt(crop: str) -> str:
    pest_list = ", ".join(KNOWN_PESTS)
    return (
        f"You are an agricultural entomologist. Examine this {crop or 'crop'} image "
        f"for INSECT PESTS. First decide whether the main problem is a pest, a "
        f"disease, or a healthy plant. If it is a pest, check whether it matches one "
        f"of these known pests: [{pest_list}]. If it clearly matches one, use that "
        f"exact name. If it looks like a real pest but does NOT match any of these "
        f"well, set pest_name to \"other\" and instead describe it precisely in "
        f"pest_description (what it looks like, the damage pattern, which insect "
        f"family it resembles) — do not force-fit it to the closest listed name. "
        f"Also estimate how much of the visible foliage is affected. "
        f"Respond ONLY as JSON with these keys: "
        f'{{"type": "pest|disease|healthy", '
        f'"pest_name": "<exact name from the list, \\"other\\", or empty if not a pest>", '
        f'"pest_description": "<only when pest_name is \\"other\\": a precise free-text '
        f'description>", '
        f'"confidence": <0.0-1.0>, '
        f'"visible_infestation": "none|low|moderate|high", '
        f'"affected_leaf_pct": <integer 0-100>, '
        f'"visible_indicators": "<short description of what you see>"}}. '
        f"Be honest about confidence; if you are unsure, use a low number. Do not "
        f"guess a specific pest you cannot actually see, and do not force an "
        f"unfamiliar pest into the known list just because it's the closest name."
    )


async def _gemini_pest(path: str, crop: str) -> dict:
    """Pest detection via Google Gemini Vision."""
    from app.ml.gemini_vision import gemini_vision_json
    data = await gemini_vision_json(path, _pest_prompt(crop))
    return data


async def _resolve_pest(data: dict, crop: str) -> dict:
    """Interpret Gemini output, resolve the pest name against the KB (exact
    then semantic), and ground facts in PEST_KB — or route to the RAG
    fallback when nothing matches closely enough."""
    kind = str(data.get("type", "")).lower()
    pest_name = (data.get("pest_name") or "").strip()
    pest_description = (data.get("pest_description") or "").strip()
    conf = float(data.get("confidence", 0) or 0)
    infest = str(data.get("visible_infestation", "unknown")).lower()
    pct = data.get("affected_leaf_pct")
    try:
        pct = float(pct) if pct is not None else None
    except (TypeError, ValueError):
        pct = None
    indicators = data.get("visible_indicators", "")

    # Healthy plant
    if kind == "healthy" and conf >= CONFIDENCE_THRESHOLD:
        return {
            "type": "healthy", "pest_name": None, "crop": crop,
            "confidence": round(conf or 0.8, 2), "visible_infestation": "none",
            "affected_leaf_pct": pct if pct is not None else 0.0,
            "kb": None, "uncertain": False,
            "message": "No obvious pest infestation detected. Continue regular monitoring.",
            "visible_indicators": indicators,
        }

    # Model thinks it's a disease, not a pest -> hand back to disease workflow.
    if kind == "disease" and conf >= CONFIDENCE_THRESHOLD:
        return {
            "type": "disease", "pest_name": None, "crop": crop,
            "confidence": round(conf, 2), "visible_infestation": "unknown",
            "affected_leaf_pct": pct, "kb": None, "uncertain": False,
            "message": "This looks like a plant disease rather than an insect pest. "
                       "Use the Plant Health (disease) analysis for a diagnosis.",
            "visible_indicators": indicators,
        }

    # Not confident, or no pest claim at all -> honest uncertainty.
    if conf < CONFIDENCE_THRESHOLD or (not pest_name):
        return _uncertain(
            "I couldn't confidently identify the pest from this image. Please upload "
            "a clearer image showing the affected leaves or the insect close-up.",
            partial={"pest_name": pest_name or None, "confidence": round(conf, 2)})

    # 1) Exact match — the original fast path.
    if pest_name in PEST_KB:
        return {
            "type": "pest", "pest_name": pest_name, "crop": crop,
            "confidence": round(conf, 2),
            "visible_infestation": infest if infest in ("none", "low", "moderate", "high") else "unknown",
            "affected_leaf_pct": pct, "kb": PEST_KB[pest_name], "uncertain": False,
            "message": None, "visible_indicators": indicators, "matched_via": "exact",
        }

    # 2) "other" or an unlisted name -> try semantic match against the KB by
    #    meaning before giving up.
    query_name = pest_description or pest_name
    matched_name, score = await semantic_match_pest(pest_name, pest_description)
    if matched_name:
        return {
            "type": "pest", "pest_name": matched_name, "crop": crop,
            "confidence": round(conf, 2),
            "visible_infestation": infest if infest in ("none", "low", "moderate", "high") else "unknown",
            "affected_leaf_pct": pct, "kb": PEST_KB[matched_name], "uncertain": False,
            "message": None, "visible_indicators": indicators,
            "matched_via": "semantic", "original_guess": query_name,
            "match_similarity": round(score, 3),
        }

    # 3) Nothing in the KB is close enough -> RAG fallback territory. Hand
    #    back the nearest reference entries so the pipeline doesn't need a
    #    second embedding round-trip.
    nearest = await nearest_kb_entries(pest_name, pest_description, k=3)
    return {
        "type": "pest_unmatched", "pest_name": query_name, "crop": crop,
        "confidence": round(conf, 2),
        "visible_infestation": infest if infest in ("none", "low", "moderate", "high") else "unknown",
        "affected_leaf_pct": pct, "kb": None, "uncertain": False,
        "message": None, "visible_indicators": indicators,
        "nearest_candidates": nearest,
    }


def _uncertain(message: str, partial: dict | None = None) -> dict:
    out = {
        "type": "uncertain",
        "pest_name": None,
        "crop": "",
        "confidence": partial.get("confidence", 0.0) if partial else 0.0,
        "visible_infestation": "unknown",
        "affected_leaf_pct": None,
        "kb": None,
        "uncertain": True,
        "message": message,
    }
    if partial and partial.get("pest_name"):
        out["model_guess"] = partial["pest_name"]
    return out


def _parse_json(text: str) -> dict:
    try:
        return json.loads(text)
    except Exception:
        m = re.search(r"\{.*\}", text, re.DOTALL)
        if m:
            try:
                return json.loads(m.group())
            except Exception:
                pass
    return {}