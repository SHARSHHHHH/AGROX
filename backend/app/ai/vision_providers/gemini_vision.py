"""Gemini vision provider.

Reuses the existing, working transport in app/ml/gemini_vision.py and maps its
output onto the neutral VisionObservation schema. No duplicated HTTP logic.
"""

from app.ai.vision_providers.base import (BaseVisionProvider,
                                          VisionObservation,
                                          VisionProviderError)
from app.core.config import settings

PROMPT = """You are an agricultural image analyst. Examine this {crop} image.

Decide whether the main problem visible is a PEST (an insect or insect damage),
a DISEASE (fungal, bacterial or viral symptoms), whether the plant looks
HEALTHY, or whether you cannot tell.

Report confidence HONESTLY. If the image is blurred, dark, taken from too far
away, or the affected area is not clearly visible, confidence MUST be below
0.5. Do not report high confidence in order to be helpful.

Do NOT recommend any treatment, product, chemical or dose. Describe only what
you can see.

Respond ONLY as JSON:
{{"kind": "pest" | "disease" | "healthy" | "unknown",
  "problem": "name of the pest or disease, or Healthy, or null",
  "crop": "crop name if identifiable, else empty string",
  "confidence": number between 0.0 and 1.0,
  "symptoms": ["short symptom phrase", "..."],
  "severity": "none" | "mild" | "moderate" | "severe" | "unknown",
  "coverage_hint": "sparse" | "moderate" | "widespread" | null,
  "visible_evidence": "one short sentence on what you actually see"}}"""


class GeminiVisionProvider(BaseVisionProvider):
    name = "gemini"

    async def analyze(self, image_path: str, crop: str = "") -> VisionObservation:
        from app.ml.gemini_vision import gemini_vision_json

        if not settings.GEMINI_API_KEY:
            raise VisionProviderError(
                "no_key",
                "GEMINI_API_KEY is not configured. Set it in backend/.env or "
                "switch VISION_PROVIDER to a local model.",
                provider=self.name)

        try:
            data = await gemini_vision_json(
                image_path, PROMPT.format(crop=crop or "plant"))
        except Exception as exc:
            raise VisionProviderError(
                "request_failed",
                f"Gemini vision call failed: {type(exc).__name__}: {exc}",
                provider=self.name) from exc

        if not data:
            raise VisionProviderError(
                "unparseable",
                "Gemini vision returned no parseable JSON.",
                provider=self.name)

        symptoms = data.get("symptoms") or []
        if isinstance(symptoms, str):
            symptoms = [symptoms]

        try:
            confidence = float(data.get("confidence") or 0.0)
        except (TypeError, ValueError):
            confidence = 0.0

        return VisionObservation(
            crop=data.get("crop") or crop or "",
            problem=data.get("problem") or "",
            kind=(data.get("kind") or "unknown").lower(),
            confidence=confidence,
            symptoms=[str(s) for s in symptoms][:6],
            severity=(data.get("severity") or "unknown").lower(),
            coverage_hint=(data.get("coverage_hint") or None),
            visible_evidence=data.get("visible_evidence") or "",
            provider=self.name,
        )

    def describe(self) -> dict:
        return {"provider": self.name, "model": settings.VISION_MODEL,
                "requires": "GEMINI_API_KEY, network access"}
