"""LLM provider interface.

Every provider takes the same inputs and returns plain text. Nothing above this
layer knows or cares which model answered, which is what makes LLM_PROVIDER a
one-line switch.

Contract:
  * chat() returns text, or raises ProviderError with a specific reason.
  * Providers NEVER decide agronomic facts. By the time a provider is called,
    the deterministic engines have already produced the numbers; the model is
    only phrasing them.
"""

from abc import ABC, abstractmethod
from typing import Optional


class ProviderError(Exception):
    """A provider failed, with a classified, actionable reason."""

    def __init__(self, kind: str, message: str, provider: str = ""):
        self.kind = kind
        self.provider = provider
        super().__init__(message)


class BaseLLMProvider(ABC):
    """Interface every LLM provider must implement."""

    name: str = "base"

    @abstractmethod
    async def chat(self, system_prompt: str, user_prompt: str,
                   temperature: float = 0.3,
                   max_tokens: Optional[int] = None) -> str:
        """Return the model's plain-text reply, or raise ProviderError."""

    async def health(self) -> dict:
        """Report whether this provider can actually serve a request."""
        try:
            text = await self.chat("Answer in one short sentence.",
                                   "Say OK if you can read this.",
                                   temperature=0.0, max_tokens=32)
            return {"provider": self.name, "healthy": True,
                    "detail": text[:120]}
        except ProviderError as exc:
            return {"provider": self.name, "healthy": False,
                    "kind": exc.kind, "detail": str(exc)}

    async def close(self) -> None:
        """Release any resources. Overridden where relevant."""
        return None
