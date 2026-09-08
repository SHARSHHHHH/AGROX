"""Vision provider factory. Mirrors the LLM factory."""

import logging
from typing import Dict

from app.ai.vision_providers.base import BaseVisionProvider, VisionProviderError
from app.core.config import settings

log = logging.getLogger("agri.vision")

_cache: Dict[str, BaseVisionProvider] = {}

SUPPORTED = ("groq", "gemini", "huggingface")


def get_vision_provider(name: str = "") -> BaseVisionProvider:
    key = (name or settings.VISION_PROVIDER or "gemini").lower().strip()

    if key in _cache:
        return _cache[key]

    if key == "groq":
        from app.ai.vision_providers.groq_vision import GroqVisionProvider
        provider: BaseVisionProvider = GroqVisionProvider()
    elif key == "gemini":
        from app.ai.vision_providers.gemini_vision import GeminiVisionProvider
        provider = GeminiVisionProvider()
    elif key in ("huggingface", "hf", "local"):
        from app.ai.vision_providers.hf_vision import HuggingFaceVisionProvider
        provider = HuggingFaceVisionProvider()
    else:
        raise VisionProviderError(
            "unknown_provider",
            f"VISION_PROVIDER='{key}' is not supported. "
            f"Use one of: {', '.join(SUPPORTED)}.")

    _cache[key] = provider
    log.info("Vision provider active: %s", key)
    return provider


def reset_cache() -> None:
    _cache.clear()


def describe_active() -> dict:
    try:
        return get_vision_provider().describe()
    except VisionProviderError as exc:
        return {"provider": settings.VISION_PROVIDER, "error": str(exc)}
