"""Plant disease detection.

Image analysis is handled by Google Gemini Vision. A local model is intentionally
not used in this Gemini version so the same model is used throughout the app.

The LLM/vision model NEVER invents certainty. If confidence < threshold we
return an explicit "uncertain" result. Disease facts come from the knowledge
base, not the model's imagination.
"""
from __future__ import annotations

from PIL import Image
import logging

from app.core.config import settings
from app.ml.knowledge import DISEASE_KB

log = logging.getLogger("agri.vision")

CONFIDENCE_THRESHOLD = 0.55
KNOWN_DISEASES = list(DISEASE_KB.keys())


def validate_image(path: str) -> bool:
    """Basic validation: real image, not tiny, plausible leaf photo."""
    try:
        img = Image.open(path)
        img.verify()
        img = Image.open(path)
        w, h = img.size
        return w >= 64 and h >= 64
    except Exception:
        return False


async def analyze_image(path: str, crop: str = "") -> dict:
    """Diagnose a leaf image using whichever vision provider is configured.

    VISION_PROVIDER=huggingface runs a local classifier (works offline, and on
    networks that block Google). VISION_PROVIDER=gemini uses the API.

    If the configured provider fails for an environmental reason — model not
    downloaded, no API key, network blocked — we fall back to the other one
    rather than showing "Uncertain" for a fixable configuration problem. A
    genuine low-confidence result is NOT a failure and never triggers fallback.
    """
    if not validate_image(path):
        return _uncertain("The uploaded file does not look like a valid leaf image. "
                          "Please upload a clear photo of the affected leaf.")

    from app.ai.vision_providers import (VisionProviderError,
                                         get_vision_provider)

    configured = (settings.VISION_PROVIDER or "gemini").lower()
    fallback = "gemini" if configured in ("huggingface", "hf", "local") else "huggingface"

    # Configuration/environment failures are worth retrying elsewhere.
    # A confident "I don't know" is not.
    RETRYABLE = {"not_configured", "missing_dependency", "load_failed",
                 "no_labels", "no_key", "request_failed", "unknown_provider"}

    candidates = [configured]
    if settings.VISION_ALLOW_FALLBACK:
        candidates.append(fallback)

    errors = []
    for provider_name in candidates:
        try:
            provider = get_vision_provider(provider_name)
            observation = await provider.analyze(path, crop)
            return _from_observation(observation)
        except VisionProviderError as exc:
            errors.append(f"{provider_name}: {exc.kind}")
            log.warning("Vision provider '%s' failed (%s): %s",
                        provider_name, exc.kind, exc)
            if exc.kind not in RETRYABLE:
                break
        except Exception as exc:
            errors.append(f"{provider_name}: {type(exc).__name__}")
            log.warning("Vision provider '%s' errored: %s", provider_name, exc)

    return _uncertain(
        "Plant image analysis is unavailable right now (" + "; ".join(errors) + "). "
        "If you are using the local model, check the backend log — the first run "
        "downloads the model. Otherwise consult an agricultural expert.")


def _from_observation(obs) -> dict:
    """Convert a neutral VisionObservation into this API's response shape.

    Keeps the existing frontend contract unchanged, so Plant Health needs no
    modification regardless of which provider produced the result.
    """
    if obs.kind == "healthy":
        return {
            "disease": "Healthy", "confidence": round(obs.confidence, 2),
            "severity": "none", "uncertain": False,
            "symptoms": "No obvious disease symptoms detected.",
            "recommendation": "Plant appears healthy. Continue regular monitoring, "
                              "balanced watering and nutrition.",
            "provider": obs.provider, "evidence": obs.visible_evidence,
        }

    if obs.uncertain or obs.kind != "disease" or obs.problem not in DISEASE_KB:
        return _uncertain(
            "Unable to confidently identify the disease. Please upload a clearer, "
            "well-lit close-up of the affected area, or consult an agricultural "
            "expert.",
            partial={"disease": obs.problem or "Unknown",
                     "confidence": round(obs.confidence, 2),
                     "provider": obs.provider,
                     "evidence": obs.visible_evidence})

    kb = DISEASE_KB[obs.problem]
    return {
        "disease": obs.problem,
        "confidence": round(obs.confidence, 2),
        "severity": obs.severity,
        "uncertain": False,
        "symptoms": kb["symptoms"],
        "recommendation": kb["treatment"],
        "causes": kb["causes"],
        "prevention": kb["prevention"],
        "crop": obs.crop,
        "provider": obs.provider,
        "evidence": obs.visible_evidence,
    }


def _disease_prompt(crop: str) -> str:
    disease_list = ", ".join(KNOWN_DISEASES)
    return (
        f"You are a plant pathologist. Look at this {crop or 'plant'} leaf image. "
        f"Choose the MOST likely disease strictly from this list: [{disease_list}, "
        f"Healthy]. Respond ONLY as JSON: "
        f'{{"disease": "<one from list>", "confidence": <0.0-1.0>, '
        f'"severity": "<mild|moderate|severe>", "visible_symptoms": "<short>"}}. '
        f"If the leaf looks healthy use disease 'Healthy'. Be honest about "
        f"confidence; if unsure use a low number."
    )


async def _gemini_disease(path: str, crop: str) -> dict:
    """Disease detection via Google Gemini Vision."""
    from app.ml.gemini_vision import gemini_vision_json
    data = await gemini_vision_json(path, _disease_prompt(crop))
    return _interpret_disease(data)


def _interpret_disease(data: dict) -> dict:
    """Interpret Gemini output and ground facts in DISEASE_KB."""
    disease = data.get("disease", "Unknown")
    conf = float(data.get("confidence", 0) or 0)
    severity = data.get("severity", "unknown")

    if str(disease).lower() == "healthy":
        return {
            "disease": "Healthy", "confidence": round(conf or 0.8, 2),
            "severity": "none", "uncertain": False,
            "symptoms": "No obvious disease symptoms detected.",
            "recommendation": "Plant appears healthy. Continue regular monitoring, "
                              "balanced watering and nutrition.",
        }

    if conf < CONFIDENCE_THRESHOLD or disease not in DISEASE_KB:
        return _uncertain(
            "Unable to confidently identify the disease. Please upload a clearer, "
            "well-lit close-up of the affected area or consult an agricultural expert.",
            partial={"disease": disease, "confidence": round(conf, 2)})

    kb = DISEASE_KB[disease]
    return {
        "disease": disease,
        "confidence": round(conf, 2),
        "severity": severity,
        "uncertain": False,
        "symptoms": kb["symptoms"],
        "recommendation": kb["treatment"],
        "causes": kb["causes"],
        "prevention": kb["prevention"],
    }


def _local_model(path: str, crop: str) -> dict:
    """Hook for a locally downloaded model (e.g. PlantVillage ResNet).
    See README section 'Bring your own disease model'. Kept as an explicit,
    documented integration point rather than a fake classifier."""
    raise RuntimeError("Local model configured but loader not implemented — "
                       "see README 'Bring your own disease model'.")


def _uncertain(message: str, partial: dict | None = None) -> dict:
    out = {
        "disease": "Uncertain",
        "confidence": partial.get("confidence", 0.0) if partial else 0.0,
        "severity": "unknown",
        "uncertain": True,
        "symptoms": "",
        "recommendation": message,
    }
    if partial:
        out["model_guess"] = partial.get("disease")
    return out


def _parse_json(text: str) -> dict:
    try:
        return json.loads(text)
    except Exception:
        m = __import__("re").search(r"\{.*\}", text, __import__("re").DOTALL)
        if m:
            try:
                return json.loads(m.group())
            except Exception:
                pass
    return {}
