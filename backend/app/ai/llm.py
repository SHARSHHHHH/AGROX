"""Gemini integration for chat, agent reasoning, translation and tool use.

WHY THIS WAS REWRITTEN
----------------------
The previous version wrapped the whole call in a bare `except Exception` and
returned a canned fallback string. That meant every distinct failure — a bad
key, a rate limit, a model overload, a safety block — produced the same
generic sentence, so there was no way to tell what was actually wrong. That is
the single biggest reason "Gemini is not working" was hard to diagnose.

What changed:

1. ERRORS ARE NOW VISIBLE. Every failure is classified (auth / rate limit /
   overloaded / not-found / blocked / timeout) and returned with a specific,
   actionable message. The fallback text still keeps the app running, but it
   now tells you WHY.

2. RETRY WITH EXPONENTIAL BACKOFF + JITTER on 429 and 503. Gemini returns 503
   UNAVAILABLE ("the model is overloaded") under load — this is exactly the
   "server busy" symptom. A single attempt surfaces it as a hard failure; three
   attempts with backoff almost always succeed.

3. CONNECTION POOLING. A module-level AsyncClient is reused instead of opening
   a new TLS connection on every request, which removes a full handshake
   (~100-300 ms) per call.

4. THINKING BUDGET IS CAPPED. gemini-3.7-flash is a reasoning model with an
   explicit thinking mode. Left uncapped it can spend a large number of tokens
   thinking before it answers, which is slow AND billed at the output rate. For
   short farmer-facing answers we cap it.

5. KEY MOVED TO A HEADER. `?key=` lands in proxy logs and browser histories;
   `x-goog-api-key` does not.

NOTE ON .env AND SPEED
----------------------
python-dotenv only loads variables from a file into the process environment.
It has no effect on latency or on rate limits. It was already in use before
this rewrite. Speed comes from items 2, 3 and 4 above.
"""

import asyncio
import logging
import random
from typing import Any, Dict, List, Optional

import httpx

from app.core.config import settings

log = logging.getLogger("agri.llm")

API_ROOT = "https://generativelanguage.googleapis.com/v1beta/models"

# Connect fast, allow generous read time (reasoning models think before they
# stream the first token), and keep connections warm between requests.
_TIMEOUT = httpx.Timeout(connect=10.0, read=90.0, write=15.0, pool=10.0)
_LIMITS = httpx.Limits(max_connections=20, max_keepalive_connections=10)

_client: Optional[httpx.AsyncClient] = None

RETRY_STATUS = {429, 500, 502, 503, 504}
MAX_ATTEMPTS = 3


class GeminiError(Exception):
    """Raised with a human-readable, actionable cause."""

    def __init__(self, kind: str, message: str, status: int = 0):
        self.kind = kind
        self.status = status
        super().__init__(message)


def get_client() -> httpx.AsyncClient:
    global _client
    if _client is None or _client.is_closed:
        _client = httpx.AsyncClient(timeout=_TIMEOUT, limits=_LIMITS)
    return _client


async def close_client():
    global _client
    if _client is not None and not _client.is_closed:
        await _client.aclose()
    _client = None


def _headers() -> Dict[str, str]:
    return {
        "x-goog-api-key": settings.GEMINI_API_KEY,
        "Content-Type": "application/json",
    }


def _classify(status: int, body: str) -> GeminiError:
    """Turn an HTTP failure into a specific, actionable message."""
    snippet = (body or "")[:300]

    if status in (401, 403):
        return GeminiError(
            "auth",
            "Gemini rejected the API key (HTTP %d). Check GEMINI_API_KEY in "
            "backend/.env. Both 'AIza...' and the newer 'AQ....' key formats are "
            "valid on this endpoint, so the likely causes are a truncated key, a "
            "key from a project without the Generative Language API enabled, or "
            "a key restricted by IP/referrer. Detail: %s" % (status, snippet),
            status)

    if status == 404:
        return GeminiError(
            "not_found",
            "Gemini model '%s' was not found (HTTP 404). Verify the exact model "
            "ID with: GET %s . Detail: %s"
            % (settings.GEMINI_MODEL, API_ROOT, snippet),
            status)

    if status == 429:
        return GeminiError(
            "rate_limit",
            "Gemini rate limit reached (HTTP 429). The free tier allows a "
            "limited number of requests per minute. Wait, reduce request "
            "frequency, or enable billing. Detail: %s" % snippet,
            status)

    if status in (500, 502, 503, 504):
        return GeminiError(
            "overloaded",
            "Gemini is temporarily overloaded or unavailable (HTTP %d). This is "
            "the 'server busy' condition and it is transient — the client "
            "already retried %d times with backoff. Detail: %s"
            % (status, MAX_ATTEMPTS, snippet),
            status)

    return GeminiError("http_error",
                       "Gemini returned HTTP %d. Detail: %s" % (status, snippet),
                       status)


def _extract_text(data: Dict[str, Any]) -> str:
    """Pull text out of a response, explaining refusals instead of hiding them."""
    candidates = data.get("candidates") or []

    if not candidates:
        feedback = data.get("promptFeedback", {})
        blocked = feedback.get("blockReason")
        if blocked:
            raise GeminiError(
                "blocked",
                "Gemini blocked the prompt (reason: %s). Rephrase the question "
                "or relax safety settings." % blocked)
        raise GeminiError("empty", "Gemini returned no candidates.")

    cand = candidates[0]
    finish = cand.get("finishReason", "")

    parts = (cand.get("content") or {}).get("parts") or []
    text = "".join(p.get("text", "") for p in parts).strip()

    if not text:
        if finish == "MAX_TOKENS":
            raise GeminiError(
                "max_tokens",
                "Gemini hit the output token limit before producing any text. "
                "On a reasoning model this usually means the thinking budget "
                "consumed the whole allowance — raise GEMINI_MAX_OUTPUT_TOKENS "
                "or lower GEMINI_THINKING_BUDGET.")
        if finish == "SAFETY":
            raise GeminiError("blocked",
                              "Gemini stopped generation for safety reasons.")
        raise GeminiError("empty",
                          "Gemini returned an empty response (finishReason=%s)."
                          % (finish or "unknown"))

    return text


def _generation_config(temperature: float,
                       max_output_tokens: Optional[int] = None) -> Dict[str, Any]:
    cfg: Dict[str, Any] = {
        "temperature": temperature,
        "maxOutputTokens": max_output_tokens or settings.GEMINI_MAX_OUTPUT_TOKENS,
    }

    # Cap reasoning effort. Farmer-facing answers are short and factual; the
    # grounded facts are computed by our own engines, so deep chain-of-thought
    # adds latency and cost without adding accuracy.
    if settings.GEMINI_THINKING_BUDGET >= 0:
        cfg["thinkingConfig"] = {
            "thinkingBudget": settings.GEMINI_THINKING_BUDGET
        }

    return cfg


async def _post(model: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    """POST with retry + exponential backoff and jitter on transient failures."""
    if not settings.GEMINI_API_KEY:
        raise GeminiError(
            "no_key",
            "GEMINI_API_KEY is not set. Add it to backend/.env and restart the "
            "server. Create a key at https://aistudio.google.com/apikey")

    url = f"{API_ROOT}/{model}:generateContent"
    client = get_client()
    last: Optional[GeminiError] = None

    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            resp = await client.post(url, json=payload, headers=_headers())
        except httpx.TimeoutException as exc:
            last = GeminiError(
                "timeout",
                "Gemini did not respond within the timeout. If this is "
                "persistent, lower GEMINI_THINKING_BUDGET — reasoning models "
                "can spend a long time before emitting the first token. "
                "Detail: %s" % type(exc).__name__)
        except httpx.HTTPError as exc:
            last = GeminiError(
                "network",
                "Could not reach the Gemini API (%s). Check network access and "
                "any corporate proxy or firewall." % type(exc).__name__)
        else:
            if resp.status_code == 200:
                if attempt > 1:
                    log.info("Gemini succeeded on attempt %d/%d",
                             attempt, MAX_ATTEMPTS)
                return resp.json()

            last = _classify(resp.status_code, resp.text)
            if resp.status_code not in RETRY_STATUS:
                raise last

        if attempt < MAX_ATTEMPTS:
            # Exponential backoff with jitter: 0.5-1.5s, then 1-3s.
            delay = (2 ** (attempt - 1)) * 0.5
            delay += random.uniform(0, delay)
            log.warning("Gemini attempt %d/%d failed (%s); retrying in %.1fs",
                        attempt, MAX_ATTEMPTS, last.kind, delay)
            await asyncio.sleep(delay)

    raise last or GeminiError("unknown", "Gemini call failed.")


# -------------------------------------------------------------------
# Public API
# -------------------------------------------------------------------

async def chat(system: str, user: str, temperature: float = 0.3,
               max_output_tokens: Optional[int] = None) -> str:
    """Provider-agnostic entry point used by the agent and NLP layers.

    Routes through the provider factory, so flipping LLM_PROVIDER between
    'qwen' and 'gemini' switches every caller with no code change anywhere
    else in the application.

    Never raises: on failure it returns a fallback string that states the real
    reason, so the app keeps working and the cause stays visible.
    """
    # Imported lazily: the factory imports the providers, and the Gemini
    # provider imports this module, so a top-level import would be circular.
    from app.ai.providers import ProviderError, get_provider

    try:
        provider = get_provider()
        return await provider.chat(system, user, temperature=temperature,
                                   max_tokens=max_output_tokens)
    except ProviderError as exc:
        log.error("LLM provider '%s' failed (%s): %s",
                  exc.provider or settings.LLM_PROVIDER, exc.kind, exc)
        return _fallback(user, note=f"(AI unavailable — {exc.kind}: {exc})")
    except GeminiError as exc:  # defensive: direct-transport failures
        log.error("Gemini failed (%s): %s", exc.kind, exc)
        return _fallback(user, note=f"(AI unavailable — {exc.kind}: {exc})")


async def chat_strict(system: str, user: str, temperature: float = 0.3,
                      max_output_tokens: Optional[int] = None) -> str:
    """Same as chat() but raises GeminiError. Use where you must know it failed."""
    payload = {
        "systemInstruction": {"parts": [{"text": system}]},
        "contents": [{"role": "user", "parts": [{"text": user}]}],
        "generationConfig": _generation_config(temperature, max_output_tokens),
    }
    data = await _post(settings.GEMINI_MODEL, payload)
    return _extract_text(data)


async def chat_with_tools(system: str, user: str,
                          tools: List[Dict[str, Any]],
                          temperature: float = 0.2) -> Dict[str, Any]:
    """Single agentic turn using Gemini function calling.

    `tools` is a list of function declarations. Returns either:
        {"type": "text", "text": ...}
        {"type": "function_call", "name": ..., "args": {...}}

    The caller executes the named local tool and decides what to do with the
    result — deliberately, so the model never executes anything itself.
    """
    payload = {
        "systemInstruction": {"parts": [{"text": system}]},
        "contents": [{"role": "user", "parts": [{"text": user}]}],
        "tools": [{"functionDeclarations": tools}],
        "generationConfig": _generation_config(temperature),
    }

    data = await _post(settings.GEMINI_MODEL, payload)
    candidates = data.get("candidates") or []
    if not candidates:
        raise GeminiError("empty", "Gemini returned no candidates.")

    for part in (candidates[0].get("content") or {}).get("parts") or []:
        if "functionCall" in part:
            call = part["functionCall"]
            return {"type": "function_call",
                    "name": call.get("name"),
                    "args": call.get("args") or {}}

    return {"type": "text", "text": _extract_text(data)}


async def list_models() -> List[str]:
    """List model IDs the key can actually access. Used by diagnostics."""
    if not settings.GEMINI_API_KEY:
        raise GeminiError("no_key", "GEMINI_API_KEY is not set.")

    client = get_client()
    try:
        resp = await client.get(API_ROOT, headers=_headers())
    except httpx.HTTPError as exc:
        raise GeminiError("network",
                          "Could not reach Gemini (%s)." % type(exc).__name__)

    if resp.status_code != 200:
        raise _classify(resp.status_code, resp.text)

    return [m.get("name", "").replace("models/", "")
            for m in resp.json().get("models", [])]


def _fallback(user: str, note: str = "") -> str:
    return (
        "I can help with irrigation, soil health, plant disease, pests, weather "
        "and government schemes. Your sensor and weather data is still shown on "
        "your dashboard. " + note
    ).strip()
