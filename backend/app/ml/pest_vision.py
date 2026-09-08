"""Pest detection via Google Gemini Vision.

The vision model only picks a label and confidence; all pest facts are
grounded in PEST_KB.
  - the vision model only picks a LABEL and a self-reported confidence
  - all pest facts come from PEST_KB, never from the model
  - low confidence -> explicit "Unknown / Low confidence", never a guess
    dressed up as certainty

This module also lets the model say the problem looks like a DISEASE rather
than a pest, so the combined image workflow can hand back to disease handling
instead of forcing a pest label. It never fabricates a disease diagnosis here;
it just reports the model's disease/pest determination and, if a pest, grounds
the details in PEST_KB.
"""
from __future__ import annotations

from PIL import Image
from app.core.config import settings
from app.ml.pest_knowledge import PEST_KB, KNOWN_PESTS

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
        "type": "pest" | "disease" | "healthy" | "uncertain",
        "pest_name": str | None,
        "crop": str,
        "confidence": float,
        "visible_infestation": "none|low|moderate|high|unknown",
        "affected_leaf_pct": float | None,
        "kb": <PEST_KB entry> | None,
        "uncertain": bool,
        "message": str | None,       # present when uncertain
        "model_guess": str | None,   # low-confidence guess, if any
      }
    """
    if not validate_image(path):
        return _uncertain("The uploaded file does not look like a valid plant image. "
                          "Please upload a clear photo of the affected leaves or the insect.")

    try:
        return await _gemini_pest(path, crop)
    except Exception as e:
        return _uncertain(f"Vision model is unavailable right now ({type(e).__name__}). "
                          "Please try again shortly or consult an agricultural expert.")


def _pest_prompt(crop: str) -> str:
    pest_list = ", ".join(KNOWN_PESTS)
    return (
        f"You are an agricultural entomologist. Examine this {crop or 'crop'} image "
        f"for INSECT PESTS. First decide whether the main problem is a pest, a "
        f"disease, or a healthy plant. If it is a pest, choose the MOST likely one "
        f"strictly from this list: [{pest_list}]. "
        f"Also estimate how much of the visible foliage is affected. "
        f"Respond ONLY as JSON with these keys: "
        f'{{"type": "pest|disease|healthy", '
        f'"pest_name": "<one from the list, or empty if not a pest>", '
        f'"confidence": <0.0-1.0>, '
        f'"visible_infestation": "none|low|moderate|high", '
        f'"affected_leaf_pct": <integer 0-100>, '
        f'"visible_indicators": "<short description of what you see>"}}. '
        f"Be honest about confidence; if you are unsure, use a low number. Do not "
        f"guess a specific pest you cannot actually see."
    )


async def _gemini_pest(path: str, crop: str) -> dict:
    """Pest detection via Google Gemini Vision."""
    from app.ml.gemini_vision import gemini_vision_json
    data = await gemini_vision_json(path, _pest_prompt(crop))
    return _interpret_pest(data, crop)


def _interpret_pest(data: dict, crop: str) -> dict:
    """Interpret Gemini output and ground facts in PEST_KB."""
    kind = str(data.get("type", "")).lower()
    pest_name = (data.get("pest_name") or "").strip()
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

    # Pest path — require confidence AND a known pest, else be honest.
    if conf < CONFIDENCE_THRESHOLD or pest_name not in PEST_KB:
        return _uncertain(
            "I couldn't confidently identify the pest from this image. Please upload "
            "a clearer image showing the affected leaves or the insect close-up.",
            partial={"pest_name": pest_name or None, "confidence": round(conf, 2)})

    return {
        "type": "pest",
        "pest_name": pest_name,
        "crop": crop,
        "confidence": round(conf, 2),
        "visible_infestation": infest if infest in ("none", "low", "moderate", "high") else "unknown",
        "affected_leaf_pct": pct,
        "kb": PEST_KB[pest_name],
        "uncertain": False,
        "message": None,
        "visible_indicators": indicators,
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
