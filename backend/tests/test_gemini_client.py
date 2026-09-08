"""Tests for the Gemini client: retries, error classification and config.

These use a stubbed HTTP layer, so they run offline and never spend quota.
"""

import httpx
import pytest

from app.ai import llm
from app.core.config import settings


class FakeResponse:
    def __init__(self, status_code, json_body=None, text=""):
        self.status_code = status_code
        self._json = json_body or {}
        self.text = text or str(json_body or "")

    def json(self):
        return self._json


class FakeClient:
    """Records calls and replays a queued list of responses/exceptions."""

    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []
        self.is_closed = False

    async def post(self, url, json=None, headers=None):
        self.calls.append({"url": url, "json": json, "headers": headers})
        item = self.responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item

    async def get(self, url, headers=None):
        self.calls.append({"url": url, "headers": headers})
        item = self.responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


def text_response(text="Hello farmer"):
    return FakeResponse(200, {
        "candidates": [{
            "content": {"parts": [{"text": text}]},
            "finishReason": "STOP",
        }]
    })


@pytest.fixture(autouse=True)
def _key(monkeypatch):
    """Every test runs as if a key is configured, and with no real sleeping."""
    monkeypatch.setattr(settings, "GEMINI_API_KEY", "test-key-value")
    # These tests exercise the Gemini transport specifically, so pin the
    # provider regardless of what LLM_PROVIDER is set to in .env.
    monkeypatch.setattr(settings, "LLM_PROVIDER", "gemini")
    from app.ai.providers import reset_cache
    reset_cache()

    async def _no_sleep(_):
        return None

    monkeypatch.setattr(llm.asyncio, "sleep", _no_sleep)


def _install(monkeypatch, responses):
    client = FakeClient(responses)
    monkeypatch.setattr(llm, "get_client", lambda: client)
    return client


# ---------------------------------------------------------------- happy path

@pytest.mark.asyncio
async def test_chat_returns_text(monkeypatch):
    _install(monkeypatch, [text_response("Water your tomatoes tomorrow.")])
    out = await llm.chat("system", "user")
    assert out == "Water your tomatoes tomorrow."


@pytest.mark.asyncio
async def test_key_is_sent_as_header_not_query_string(monkeypatch):
    client = _install(monkeypatch, [text_response()])
    await llm.chat("system", "user")

    call = client.calls[0]
    assert call["headers"]["x-goog-api-key"] == "test-key-value"
    # The key must never appear in the URL, where proxies would log it.
    assert "key=" not in call["url"]


# ---------------------------------------------------------------- retries

@pytest.mark.asyncio
async def test_retries_on_503_then_succeeds(monkeypatch):
    """503 is the 'server busy' condition — it must be retried, not surfaced."""
    client = _install(monkeypatch, [
        FakeResponse(503, text="model is overloaded"),
        FakeResponse(503, text="model is overloaded"),
        text_response("Recovered"),
    ])
    out = await llm.chat("system", "user")
    assert out == "Recovered"
    assert len(client.calls) == 3


@pytest.mark.asyncio
async def test_retries_on_429(monkeypatch):
    client = _install(monkeypatch, [
        FakeResponse(429, text="quota exceeded"),
        text_response("OK"),
    ])
    assert await llm.chat("system", "user") == "OK"
    assert len(client.calls) == 2


@pytest.mark.asyncio
async def test_gives_up_after_max_attempts(monkeypatch):
    client = _install(monkeypatch, [FakeResponse(503, text="overloaded")] * 3)
    with pytest.raises(llm.GeminiError) as exc:
        await llm.chat_strict("system", "user")

    assert exc.value.kind == "overloaded"
    assert len(client.calls) == llm.MAX_ATTEMPTS


@pytest.mark.asyncio
async def test_auth_failure_is_not_retried(monkeypatch):
    """A bad key will never fix itself, so retrying only wastes time."""
    client = _install(monkeypatch, [FakeResponse(401, text="invalid key")])
    with pytest.raises(llm.GeminiError) as exc:
        await llm.chat_strict("system", "user")

    assert exc.value.kind == "auth"
    assert len(client.calls) == 1


@pytest.mark.asyncio
async def test_404_is_not_retried_and_names_the_model(monkeypatch):
    _install(monkeypatch, [FakeResponse(404, text="model not found")])
    with pytest.raises(llm.GeminiError) as exc:
        await llm.chat_strict("system", "user")

    assert exc.value.kind == "not_found"
    assert settings.GEMINI_MODEL in str(exc.value)


# ---------------------------------------------------------------- errors surface

@pytest.mark.asyncio
async def test_missing_key_is_reported_clearly(monkeypatch):
    monkeypatch.setattr(settings, "GEMINI_API_KEY", "")
    with pytest.raises(llm.GeminiError) as exc:
        await llm.chat_strict("system", "user")

    assert exc.value.kind == "no_key"
    assert "GEMINI_API_KEY" in str(exc.value)


@pytest.mark.asyncio
async def test_chat_never_raises_but_states_the_reason(monkeypatch):
    """The app must keep working AND the cause must remain visible."""
    _install(monkeypatch, [FakeResponse(401, text="invalid key")])
    out = await llm.chat("system", "user")

    assert "irrigation" in out          # fallback content still present
    assert "auth" in out                # and the real cause is named


@pytest.mark.asyncio
async def test_blocked_prompt_is_explained(monkeypatch):
    _install(monkeypatch, [FakeResponse(200, {"promptFeedback": {"blockReason": "SAFETY"}})])
    with pytest.raises(llm.GeminiError) as exc:
        await llm.chat_strict("system", "user")

    assert exc.value.kind == "blocked"
    assert "SAFETY" in str(exc.value)


@pytest.mark.asyncio
async def test_max_tokens_points_at_thinking_budget(monkeypatch):
    """Empty output on a reasoning model usually means thinking ate the budget."""
    _install(monkeypatch, [FakeResponse(200, {
        "candidates": [{"content": {"parts": []}, "finishReason": "MAX_TOKENS"}]
    })])
    with pytest.raises(llm.GeminiError) as exc:
        await llm.chat_strict("system", "user")

    assert exc.value.kind == "max_tokens"
    assert "THINKING_BUDGET" in str(exc.value)


@pytest.mark.asyncio
async def test_timeout_is_classified(monkeypatch):
    _install(monkeypatch, [httpx.ReadTimeout("too slow")] * 3)
    with pytest.raises(llm.GeminiError) as exc:
        await llm.chat_strict("system", "user")

    assert exc.value.kind == "timeout"


# ---------------------------------------------------------------- generation config

@pytest.mark.asyncio
async def test_thinking_budget_is_sent(monkeypatch):
    monkeypatch.setattr(settings, "GEMINI_THINKING_BUDGET", 0)
    client = _install(monkeypatch, [text_response()])
    await llm.chat("system", "user")

    cfg = client.calls[0]["json"]["generationConfig"]
    assert cfg["thinkingConfig"]["thinkingBudget"] == 0


@pytest.mark.asyncio
async def test_negative_thinking_budget_omits_the_field(monkeypatch):
    """-1 means 'let the model decide', which is expressed by sending nothing."""
    monkeypatch.setattr(settings, "GEMINI_THINKING_BUDGET", -1)
    client = _install(monkeypatch, [text_response()])
    await llm.chat("system", "user")

    assert "thinkingConfig" not in client.calls[0]["json"]["generationConfig"]


@pytest.mark.asyncio
async def test_output_tokens_are_capped(monkeypatch):
    client = _install(monkeypatch, [text_response()])
    await llm.chat("system", "user")

    cfg = client.calls[0]["json"]["generationConfig"]
    assert cfg["maxOutputTokens"] == settings.GEMINI_MAX_OUTPUT_TOKENS


# ---------------------------------------------------------------- function calling

@pytest.mark.asyncio
async def test_function_call_is_returned_not_executed(monkeypatch):
    _install(monkeypatch, [FakeResponse(200, {
        "candidates": [{"content": {"parts": [
            {"functionCall": {"name": "get_weather", "args": {"location": "Chennai"}}}
        ]}}]
    })])

    result = await llm.chat_with_tools("sys", "weather in Chennai?", [
        {"name": "get_weather", "description": "d", "parameters": {}}])

    assert result["type"] == "function_call"
    assert result["name"] == "get_weather"
    assert result["args"]["location"] == "Chennai"


@pytest.mark.asyncio
async def test_tools_turn_falls_back_to_text(monkeypatch):
    _install(monkeypatch, [text_response("I need more detail.")])
    result = await llm.chat_with_tools("sys", "hello", [
        {"name": "get_weather", "description": "d", "parameters": {}}])

    assert result["type"] == "text"
    assert result["text"] == "I need more detail."


# ---------------------------------------------------------------- model listing

@pytest.mark.asyncio
async def test_list_models_strips_prefix(monkeypatch):
    _install(monkeypatch, [FakeResponse(200, {"models": [
        {"name": "models/gemini-3.7-flash"},
        {"name": "models/gemini-3.6-flash"},
    ]})])

    models = await llm.list_models()
    assert "gemini-3.7-flash" in models
    assert all(not m.startswith("models/") for m in models)
