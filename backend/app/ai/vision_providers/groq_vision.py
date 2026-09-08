"""Groq vision provider (Llama 4 multimodal).

WHY THIS EXISTS
---------------
Two problems drove this:

  1. The HuggingFace classifier returns low-confidence guesses on ordinary
     field photos. Below the confidence gate the app correctly refuses to
     answer — which is honest, but leaves the farmer with nothing.
  2. Pest analysis was timing out. A local model has to be downloaded and then
     run on CPU; on a cold start that routinely exceeds any sane request
     timeout.

Groq already powers the text LLM in this project, so the key, the account and
the operational knowledge are all in place. Its Llama 4 models accept images
through an OpenAI-compatible endpoint and answer in well under a second, which
solves both problems with one provider.

THE BOUNDARY IS UNCHANGED
-------------------------
This returns a VisionObservation and nothing else. It cannot name a pesticide
or state a dose, because VisionObservation has no field to put one in. The
deterministic IPM and severity engines still decide what the farmer is told.
A faster, more confident model does not get more authority.

MODEL IDS CHANGE
----------------
Groq deprecates and renames vision models regularly (the llama-3.2-vision
preview models were retired, for instance). The model is therefore read from
GROQ_VISION_MODEL in .env rather than hardcoded, and a wrong id produces an
explicit "model not found" error naming the setting to change instead of a
generic failure.
"""

import base64
import json
import logging
import mimetypes
import re
from pathlib import Path

import httpx

from app.ai.vision_providers.base import (BaseVisionProvider,
                                          VisionObservation,
                                          VisionProviderError)
from app.core.config import settings

log = logging.getLogger("agri.vision.groq")

GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"

# Groq rejects base64 payloads over ~4 MB. Phone photos are routinely larger,
# so oversized images are downscaled rather than allowed to fail the request.
MAX_B64_BYTES = 3_500_000
MAX_EDGE_PX = 1024

PROMPT = """You are an agricultural image analyst looking at a photo of a {crop}.

Decide whether what you see is mainly a PEST (an insect, mite, or the damage
insects leave), a DISEASE (fungal, bacterial or viral symptoms), a HEALTHY
plant, or whether you genuinely cannot tell.

REPORT CONFIDENCE HONESTLY. This matters more than being helpful. If the image
is blurred, dark, overexposed, taken from too far away, shows no clear symptom,
or shows a plant you cannot identify, then confidence MUST be below 0.5. A
farmer may spray a chemical based on what you say. An confident wrong answer
costs them money and harms their soil; an honest "unknown" costs them nothing
but a second photo.

Do NOT recommend any treatment, product, chemical, brand or dose. You are
describing what is visible, nothing more. Another system decides treatment.

Respond with ONLY a JSON object, no markdown fence, no commentary:
{{"kind": "pest" | "disease" | "healthy" | "unknown",
  "problem": "common name of the pest or disease, or Healthy, or empty string",
  "crop": "crop name if identifiable, else empty string",
  "confidence": number between 0.0 and 1.0,
  "symptoms": ["short symptom phrase", "..."],
  "severity": "none" | "mild" | "moderate" | "severe" | "unknown",
  "coverage_hint": "sparse" | "moderate" | "widespread" | null,
  "visible_evidence": "one short sentence describing what you actually see"}}"""


def _encode_image(path: str) -> tuple[str, str]:
    """Read an image as base64, downscaling if it would exceed Groq's limit."""
    p = Path(path)
    if not p.exists():
        raise VisionProviderError("no_image", f"Image not found: {path}",
                                  provider="groq")

    mime = mimetypes.guess_type(str(p))[0] or "image/jpeg"
    raw = p.read_bytes()

    # base64 inflates by ~4/3, so check the encoded size, not the file size.
    if len(raw) * 4 / 3 > MAX_B64_BYTES:
        try:
            from io import BytesIO

            from PIL import Image

            img = Image.open(BytesIO(raw))
            img.thumbnail((MAX_EDGE_PX, MAX_EDGE_PX))
            if img.mode in ("RGBA", "P"):
                img = img.convert("RGB")
            buf = BytesIO()
            img.save(buf, format="JPEG", quality=85, optimize=True)
            raw = buf.getvalue()
            mime = "image/jpeg"
            log.info("Downscaled oversized image to %d bytes", len(raw))
        except ImportError:
            raise VisionProviderError(
                "image_too_large",
                "This photo is too large for the vision API and Pillow is not "
                "installed to resize it. Run: pip install Pillow",
                provider="groq")
        except Exception as exc:                        # noqa: BLE001
            raise VisionProviderError(
                "image_unreadable",
                f"Could not read or resize this image: {exc}",
                provider="groq") from exc

    return base64.b64encode(raw).decode("ascii"), mime


def _extract_json(text: str) -> dict | None:
    """Parse the model's JSON, tolerating fences and stray prose.

    Instruction-tuned models wrap JSON in ```json fences or add a sentence
    before it often enough that strict json.loads() alone would fail requests
    that actually contain a perfectly good answer.
    """
    if not text:
        return None

    cleaned = re.sub(r"^```(?:json)?|```$", "", text.strip(),
                     flags=re.M).strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass

    # Fall back to the outermost braces.
    start, end = cleaned.find("{"), cleaned.rfind("}")
    if start >= 0 and end > start:
        try:
            return json.loads(cleaned[start:end + 1])
        except json.JSONDecodeError:
            return None
    return None


class GroqVisionProvider(BaseVisionProvider):
    name = "groq"

    async def analyze(self, image_path: str, crop: str = "") -> VisionObservation:
        key = (settings.GROQ_API_KEY or "").strip()
        if not key or key.startswith("PASTE"):
            raise VisionProviderError(
                "no_key",
                "GROQ_API_KEY is not set in backend/.env. Get a free key at "
                "https://console.groq.com/keys and paste it there.",
                provider=self.name)

        b64, mime = _encode_image(image_path)
        model = settings.GROQ_VISION_MODEL

        payload = {
            "model": model,
            "messages": [{
                "role": "user",
                "content": [
                    {"type": "text",
                     "text": PROMPT.format(crop=crop or "plant")},
                    {"type": "image_url",
                     "image_url": {"url": f"data:{mime};base64,{b64}"}},
                ],
            }],
            # Low temperature: we want a consistent reading of the same photo,
            # not creative variation.
            "temperature": 0.1,
            "max_tokens": settings.GROQ_VISION_MAX_TOKENS,
        }

        try:
            async with httpx.AsyncClient(
                    timeout=settings.GROQ_VISION_TIMEOUT_S) as client:
                resp = await client.post(
                    GROQ_URL, json=payload,
                    headers={"Authorization": f"Bearer {key}",
                             "Content-Type": "application/json"})
        except httpx.TimeoutException as exc:
            raise VisionProviderError(
                "timeout",
                f"Groq vision did not respond within "
                f"{settings.GROQ_VISION_TIMEOUT_S}s. Raise "
                f"GROQ_VISION_TIMEOUT_S in backend/.env if this recurs.",
                provider=self.name) from exc
        except httpx.HTTPError as exc:
            raise VisionProviderError(
                "network",
                f"Could not reach Groq: {type(exc).__name__}: {exc}",
                provider=self.name) from exc

        if resp.status_code == 401:
            raise VisionProviderError(
                "bad_key", "Groq rejected the API key (401). Check "
                           "GROQ_API_KEY in backend/.env.", provider=self.name)
        if resp.status_code == 404:
            raise VisionProviderError(
                "bad_model",
                f"Groq does not recognise the model '{model}' (404). Groq "
                f"retires vision models fairly often — check the current list "
                f"at https://console.groq.com/docs/models and update "
                f"GROQ_VISION_MODEL in backend/.env.",
                provider=self.name)
        if resp.status_code == 429:
            raise VisionProviderError(
                "rate_limited",
                "Groq rate limit reached. Wait a moment and try again.",
                provider=self.name)
        if resp.status_code >= 400:
            raise VisionProviderError(
                "http_error",
                f"Groq returned {resp.status_code}: {resp.text[:300]}",
                provider=self.name)

        try:
            body = resp.json()
            text = body["choices"][0]["message"]["content"]
        except (ValueError, KeyError, IndexError) as exc:
            raise VisionProviderError(
                "unparseable",
                "Groq returned an unexpected response shape.",
                provider=self.name) from exc

        data = _extract_json(text)
        if not data:
            raise VisionProviderError(
                "unparseable",
                "Groq vision did not return parseable JSON.",
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
            kind=(data.get("kind") or "unknown").lower().strip(),
            confidence=confidence,
            symptoms=[str(s) for s in symptoms][:6],
            severity=(data.get("severity") or "unknown").lower().strip(),
            coverage_hint=(data.get("coverage_hint") or None),
            visible_evidence=data.get("visible_evidence") or "",
            provider=self.name,
        )

    def describe(self) -> dict:
        key = (settings.GROQ_API_KEY or "").strip()
        return {
            "provider": self.name,
            "model": settings.GROQ_VISION_MODEL,
            "key_configured": bool(key and not key.startswith("PASTE")),
            "timeout_s": settings.GROQ_VISION_TIMEOUT_S,
            "requires": "GROQ_API_KEY, network access",
        }
