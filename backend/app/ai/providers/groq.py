"""Groq provider.

Groq runs open models (Llama, etc.) on their LPU inference hardware, which is
why it exists here: it answers in a few hundred milliseconds where a CPU-bound
local Qwen model can take 20-60s, and it is far faster than most hosted GPU
APIs too. The API is OpenAI-compatible (`/openai/v1/chat/completions`), so no
extra SDK is needed — the same httpx client style already used for Gemini in
this codebase is enough.

DESIGN NOTES

Same contract, different wire format
    BaseLLMProvider.chat() takes (system_prompt, user_prompt) and returns
    plain text. Groq's chat-completions endpoint wants a `messages` list with
    role="system"/"user", which this adapter builds directly — there is no
    shared transport with Gemini because the payload shapes are different.

Retry policy
    Same idea as app/ai/llm.py: retry 429/5xx with exponential backoff +
    jitter, because a transient "server busy" should not surface as a hard
    failure to the farmer on the very first attempt.

Connection pooling
    One module-level AsyncClient, reused across requests, avoiding a fresh TLS
    handshake per chat message.
"""

import asyncio
import logging
import random
import time
from typing import Optional

import httpx

from app.ai.providers.base import BaseLLMProvider, ProviderError
from app.core.config import settings

log = logging.getLogger("agri.groq")

API_URL = "https://api.groq.com/openai/v1/chat/completions"

# read= MUST come from GROQ_TIMEOUT_S. It used to be hardcoded to 30.0, so
# lowering GROQ_TIMEOUT_S in .env changed the error message and nothing else —
# the socket still waited a full 30 seconds.
def _timeout() -> httpx.Timeout:
    return httpx.Timeout(connect=5.0, read=float(settings.GROQ_TIMEOUT_S),
                         write=10.0, pool=5.0)
_LIMITS = httpx.Limits(max_connections=20, max_keepalive_connections=10)

# Retry ONLY transient server-side conditions.
#   429  rate limited      — a short wait genuinely helps
#   5xx  Groq-side fault   — usually a different node on retry
# NOT retried:
#   timeout  the model is genuinely slow to generate; retrying triples the
#            wait for the same result. This was turning one 60s call into a
#            ~3 minute request.
#   401/403/404  configuration errors. A bad key or model id will be exactly
#            as bad on the third attempt.
RETRY_STATUS = {429, 500, 502, 503, 504}
MAX_ATTEMPTS = 3

_client: Optional[httpx.AsyncClient] = None


def _get_client() -> httpx.AsyncClient:
    global _client
    if _client is None or _client.is_closed:
        _client = httpx.AsyncClient(timeout=_timeout(), limits=_LIMITS)
    return _client


def _classify(status: int, body: str, provider: str) -> ProviderError:
    snippet = (body or "")[:300]

    if status in (401, 403):
        return ProviderError(
            "auth",
            f"Groq rejected the API key (HTTP {status}). Check GROQ_API_KEY "
            f"in backend/.env — create one free at https://console.groq.com/keys. "
            f"Detail: {snippet}", provider)
    if status == 404:
        return ProviderError(
            "not_found",
            f"Groq model '{settings.GROQ_MODEL}' was not found (HTTP 404). "
            f"See the current model list at "
            f"https://console.groq.com/docs/models and update GROQ_MODEL. "
            f"Detail: {snippet}", provider)
    if status == 429:
        return ProviderError(
            "rate_limit",
            f"Groq rate limit reached (HTTP 429). The free tier has a "
            f"requests/tokens-per-minute cap; wait a moment and retry. "
            f"Detail: {snippet}", provider)
    if status in (500, 502, 503, 504):
        return ProviderError(
            "overloaded",
            f"Groq is temporarily unavailable (HTTP {status}). Already "
            f"retried {MAX_ATTEMPTS} times with backoff. Detail: {snippet}",
            provider)
    return ProviderError("http_error", f"Groq returned HTTP {status}. "
                         f"Detail: {snippet}", provider)


class GroqProvider(BaseLLMProvider):
    name = "groq"

    async def chat(self, system_prompt: str, user_prompt: str,
                   temperature: float = 0.3,
                   max_tokens: Optional[int] = None) -> str:
        if not settings.GROQ_API_KEY:
            raise ProviderError(
                "no_key",
                "GROQ_API_KEY is not set. Add it to backend/.env and restart "
                "the server. Create a free key at "
                "https://console.groq.com/keys", provider=self.name)

        payload = {
            "model": settings.GROQ_MODEL,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": temperature,
            "max_tokens": max_tokens or settings.GROQ_MAX_OUTPUT_TOKENS,
        }
        headers = {
            "Authorization": f"Bearer {settings.GROQ_API_KEY}",
            "Content-Type": "application/json",
        }

        client = _get_client()
        last: Optional[ProviderError] = None
        _t0 = time.perf_counter()

        for attempt in range(1, MAX_ATTEMPTS + 1):
            try:
                resp = await client.post(API_URL, json=payload, headers=headers)
            except httpx.TimeoutException:
                # Fail immediately. Do NOT retry: the request timed out
                # because generation is slow, and a second attempt will be
                # slow in exactly the same way. The caller falls back to the
                # deterministic facts template, which is instant.
                elapsed = time.perf_counter() - _t0
                log.warning("[GROQ] timeout after %.1fs on attempt %d — not "
                            "retrying; caller will use the deterministic "
                            "fallback", elapsed, attempt)
                raise ProviderError(
                    "timeout",
                    f"Groq did not respond within {settings.GROQ_TIMEOUT_S}s.",
                    self.name)
            except httpx.HTTPError as exc:
                # A transport-level failure can be transient (DNS blip, reset
                # connection), so this one is still retried.
                last = ProviderError(
                    "network",
                    f"Could not reach Groq ({type(exc).__name__}). Check "
                    f"network access and any corporate proxy/firewall.",
                    self.name)
            else:
                if resp.status_code == 200:
                    data = resp.json()
                    choices = data.get("choices") or []
                    if not choices:
                        raise ProviderError("empty", "Groq returned no choices.",
                                            self.name)
                    text = (choices[0].get("message", {}).get("content")
                            or "").strip()
                    if not text:
                        raise ProviderError("empty",
                                            "Groq returned an empty response.",
                                            self.name)
                    log.info("[GROQ] ok on attempt %d in %.2fs (model=%s, "
                             "max_tokens=%s)", attempt,
                             time.perf_counter() - _t0, settings.GROQ_MODEL,
                             payload.get("max_tokens"))
                    return text

                last = _classify(resp.status_code, resp.text, self.name)
                if resp.status_code not in RETRY_STATUS:
                    raise last

            # Every retry is logged with its cumulative cost, because a
            # 3-attempt storm at a 30s timeout is ~95s of pure waiting and is
            # invisible in a single "the chat is slow" report.
            log.warning("[GROQ] attempt %d/%d failed: %s (elapsed %.1fs)",
                        attempt, MAX_ATTEMPTS, last.kind,
                        time.perf_counter() - _t0)

            if attempt < MAX_ATTEMPTS:
                delay = (2 ** (attempt - 1)) * 0.5
                delay += random.uniform(0, delay)
                log.warning("[GROQ] retrying in %.1fs", delay)
                await asyncio.sleep(delay)

        raise last or ProviderError("unknown", "Groq call failed.", self.name)

    async def close(self) -> None:
        global _client
        if _client is not None and not _client.is_closed:
            await _client.aclose()
        _client = None

    def describe(self) -> dict:
        return {
            "provider": self.name,
            "model": settings.GROQ_MODEL,
            "max_output_tokens": settings.GROQ_MAX_OUTPUT_TOKENS,
            "requires": "GROQ_API_KEY, network access",
        }
