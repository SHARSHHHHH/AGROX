"""Gemini provider.

Thin adapter over the existing, already-tested transport in app/ai/llm.py
(retry with backoff, error classification, connection pooling, thinking-budget
cap). Deliberately no duplicated HTTP logic — one transport, one place to fix.
"""

from typing import Optional

from app.ai.providers.base import BaseLLMProvider, ProviderError
from app.core.config import settings


class GeminiProvider(BaseLLMProvider):
    name = "gemini"

    async def chat(self, system_prompt: str, user_prompt: str,
                   temperature: float = 0.3,
                   max_tokens: Optional[int] = None) -> str:
        # Imported here rather than at module scope: llm.py asks the factory
        # which provider to use, so a top-level import would be circular.
        from app.ai import llm

        try:
            return await llm.chat_strict(system_prompt, user_prompt,
                                         temperature=temperature,
                                         max_output_tokens=max_tokens)
        except llm.GeminiError as exc:
            raise ProviderError(exc.kind, str(exc), provider=self.name) from exc

    async def close(self) -> None:
        from app.ai import llm
        await llm.close_client()

    def describe(self) -> dict:
        return {
            "provider": self.name,
            "model": settings.GEMINI_MODEL,
            "thinking_budget": settings.GEMINI_THINKING_BUDGET,
            "max_output_tokens": settings.GEMINI_MAX_OUTPUT_TOKENS,
            "requires": "GEMINI_API_KEY, network access",
        }
