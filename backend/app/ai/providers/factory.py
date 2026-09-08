"""Provider factory.

Reads LLM_PROVIDER and returns the matching provider, cached so a local model
is never loaded twice. Unknown values fail loudly rather than silently
defaulting, because silently using the wrong model is worse than a clear error.
"""

import logging
from typing import Dict

from app.ai.providers.base import BaseLLMProvider, ProviderError
from app.core.config import settings

log = logging.getLogger("agri.provider")

_cache: Dict[str, BaseLLMProvider] = {}

SUPPORTED = ("qwen", "gemini", "groq")


def get_provider(name: str = "") -> BaseLLMProvider:
    """Return the configured provider instance."""
    key = (name or settings.LLM_PROVIDER or "gemini").lower().strip()

    if key in _cache:
        return _cache[key]

    if key == "gemini":
        from app.ai.providers.gemini import GeminiProvider
        provider: BaseLLMProvider = GeminiProvider()
    elif key == "qwen":
        from app.ai.providers.qwen import QwenProvider
        provider = QwenProvider()
    elif key == "groq":
        from app.ai.providers.groq import GroqProvider
        provider = GroqProvider()
    else:
        raise ProviderError(
            "unknown_provider",
            f"LLM_PROVIDER='{key}' is not supported. "
            f"Use one of: {', '.join(SUPPORTED)}.")

    _cache[key] = provider
    log.info("LLM provider active: %s", key)
    return provider


def reset_cache() -> None:
    """Drop cached providers. Used by tests and when switching at runtime."""
    _cache.clear()


async def close_all() -> None:
    for provider in list(_cache.values()):
        try:
            await provider.close()
        except Exception:  # shutdown must never raise
            pass
    _cache.clear()


def describe_active() -> dict:
    try:
        provider = get_provider()
    except ProviderError as exc:
        return {"provider": settings.LLM_PROVIDER, "error": str(exc)}
    describe = getattr(provider, "describe", None)
    return describe() if describe else {"provider": provider.name}
