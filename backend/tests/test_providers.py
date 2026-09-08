"""Provider abstraction, switching and fallback tests.

Qwen is tested with a stubbed generation function so these run offline and
without downloading ~3 GB of weights.
"""

import pytest

from app.ai.providers import ProviderError, get_provider, reset_cache
from app.ai.providers.base import BaseLLMProvider
from app.ai.vision_providers import (VisionObservation, VisionProviderError,
                                     get_vision_provider)
from app.ai.vision_providers import reset_cache as reset_vision_cache
from app.core.config import settings


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    reset_cache()
    reset_vision_cache()
    # QwenProvider.chat() now refuses to run while the model is still loading.
    # These tests stub generation directly, so report the model as ready.
    from app.ai.providers import qwen as _qwen
    monkeypatch.setattr(_qwen, "is_loaded", lambda: True)
    yield
    reset_cache()
    reset_vision_cache()


# ---------------------------------------------------------------- factory

def test_factory_returns_gemini(monkeypatch):
    monkeypatch.setattr(settings, "LLM_PROVIDER", "gemini")
    provider = get_provider()
    assert provider.name == "gemini"
    assert isinstance(provider, BaseLLMProvider)


def test_factory_returns_qwen(monkeypatch):
    monkeypatch.setattr(settings, "LLM_PROVIDER", "qwen")
    provider = get_provider()
    assert provider.name == "qwen"
    assert isinstance(provider, BaseLLMProvider)


def test_factory_returns_groq(monkeypatch):
    monkeypatch.setattr(settings, "LLM_PROVIDER", "groq")
    provider = get_provider()
    assert provider.name == "groq"
    assert isinstance(provider, BaseLLMProvider)


def test_factory_caches_instances(monkeypatch):
    """A local model must never be loaded twice."""
    monkeypatch.setattr(settings, "LLM_PROVIDER", "qwen")
    assert get_provider() is get_provider()


def test_unknown_provider_fails_loudly(monkeypatch):
    monkeypatch.setattr(settings, "LLM_PROVIDER", "gpt4")
    with pytest.raises(ProviderError) as exc:
        get_provider()
    assert exc.value.kind == "unknown_provider"
    assert "qwen" in str(exc.value) and "gemini" in str(exc.value) \
        and "groq" in str(exc.value)


def test_explicit_name_overrides_settings(monkeypatch):
    monkeypatch.setattr(settings, "LLM_PROVIDER", "gemini")
    assert get_provider("qwen").name == "qwen"


# ---------------------------------------------------------------- qwen

@pytest.mark.asyncio
async def test_qwen_chat_uses_generation(monkeypatch):
    from app.ai.providers import qwen as qwen_mod

    captured = {}

    def fake_generate(system, user, temperature, max_new_tokens):
        captured.update(system=system, user=user, temperature=temperature,
                        max_new_tokens=max_new_tokens)
        return "Sow soybean after the first good monsoon rain."

    monkeypatch.setattr(qwen_mod, "_generate_sync", fake_generate)

    out = await qwen_mod.QwenProvider().chat("You are an advisor.",
                                             "When should I sow soybean?")
    assert out.startswith("Sow soybean")
    assert captured["max_new_tokens"] == settings.QWEN_MAX_NEW_TOKENS


@pytest.mark.asyncio
async def test_qwen_respects_max_tokens_override(monkeypatch):
    from app.ai.providers import qwen as qwen_mod

    captured = {}

    def fake_generate(system, user, temperature, max_new_tokens):
        captured["max_new_tokens"] = max_new_tokens
        return "ok"

    monkeypatch.setattr(qwen_mod, "_generate_sync", fake_generate)
    await qwen_mod.QwenProvider().chat("s", "u", max_tokens=32)
    assert captured["max_new_tokens"] == 32


@pytest.mark.asyncio
async def test_qwen_empty_output_raises(monkeypatch):
    from app.ai.providers import qwen as qwen_mod
    monkeypatch.setattr(qwen_mod, "_generate_sync",
                        lambda s, u, t, m: "   ")

    with pytest.raises(ProviderError) as exc:
        await qwen_mod.QwenProvider().chat("s", "u")
    assert exc.value.kind == "empty"


@pytest.mark.asyncio
async def test_qwen_missing_dependency_is_actionable(monkeypatch):
    from app.ai.providers import qwen as qwen_mod

    def boom(system, user, temperature, max_new_tokens):
        raise ProviderError("missing_dependency",
                            "PyTorch is not installed. Install the local-model "
                            "extras with: pip install -r requirements-qwen.txt",
                            provider="qwen")

    monkeypatch.setattr(qwen_mod, "_generate_sync", boom)

    with pytest.raises(ProviderError) as exc:
        await qwen_mod.QwenProvider().chat("s", "u")
    assert exc.value.kind == "missing_dependency"
    assert "requirements-qwen.txt" in str(exc.value)


def test_qwen_warmup_skipped_when_provider_is_gemini(monkeypatch):
    from app.ai.providers import qwen as qwen_mod
    monkeypatch.setattr(settings, "LLM_PROVIDER", "gemini")
    result = qwen_mod.warmup()
    assert result["loaded"] is False
    assert "not 'qwen'" in result["reason"]


# ------------------------------------------------- provider switching end-to-end

@pytest.mark.asyncio
async def test_llm_chat_routes_to_qwen(monkeypatch):
    """The whole app calls llm.chat; switching LLM_PROVIDER must reroute it."""
    from app.ai import llm
    from app.ai.providers import qwen as qwen_mod

    monkeypatch.setattr(settings, "LLM_PROVIDER", "qwen")
    monkeypatch.setattr(qwen_mod, "_generate_sync",
                        lambda s, u, t, m: "answer from qwen")

    assert await llm.chat("system", "user") == "answer from qwen"


@pytest.mark.asyncio
async def test_llm_chat_degrades_without_crashing(monkeypatch):
    """A dead provider must not take the app down, and must state the cause."""
    from app.ai import llm
    from app.ai.providers import qwen as qwen_mod

    monkeypatch.setattr(settings, "LLM_PROVIDER", "qwen")

    def boom(system, user, temperature, max_new_tokens):
        raise ProviderError("load_failed", "model weights missing",
                            provider="qwen")

    monkeypatch.setattr(qwen_mod, "_generate_sync", boom)

    out = await llm.chat("system", "user")
    assert "irrigation" in out           # fallback still useful
    assert "load_failed" in out          # real cause still visible


@pytest.mark.asyncio
async def test_provider_health_reports_failure(monkeypatch):
    from app.ai.providers import qwen as qwen_mod
    monkeypatch.setattr(settings, "LLM_PROVIDER", "qwen")

    def boom(system, user, temperature, max_new_tokens):
        raise ProviderError("load_failed", "no weights", provider="qwen")

    monkeypatch.setattr(qwen_mod, "_generate_sync", boom)

    health = await qwen_mod.QwenProvider().health()
    assert health["healthy"] is False
    assert health["kind"] == "load_failed"


# ---------------------------------------------------------------- groq

class _FakeResp:
    def __init__(self, status_code, payload=None, text=""):
        self.status_code = status_code
        self._payload = payload or {}
        self.text = text or str(payload)

    def json(self):
        return self._payload


class _FakeClient:
    def __init__(self, responses):
        self._responses = list(responses)
        self.calls = []

    async def post(self, url, json=None, headers=None):
        self.calls.append({"url": url, "json": json, "headers": headers})
        return self._responses.pop(0)


@pytest.mark.asyncio
async def test_groq_chat_returns_text(monkeypatch):
    from app.ai.providers import groq as groq_mod

    monkeypatch.setattr(settings, "GROQ_API_KEY", "test-key")
    fake = _FakeClient([_FakeResp(200, {
        "choices": [{"message": {"content": "Water your tomato crop today."}}]
    })])
    monkeypatch.setattr(groq_mod, "_get_client", lambda: fake)

    out = await groq_mod.GroqProvider().chat("system", "Should I water today?")
    assert out == "Water your tomato crop today."
    # API key never lands in the URL/query string, only the Authorization header.
    assert "key" not in fake.calls[0]["url"]
    assert fake.calls[0]["headers"]["Authorization"] == "Bearer test-key"


@pytest.mark.asyncio
async def test_groq_missing_key_is_actionable(monkeypatch):
    from app.ai.providers import groq as groq_mod

    monkeypatch.setattr(settings, "GROQ_API_KEY", "")
    with pytest.raises(ProviderError) as exc:
        await groq_mod.GroqProvider().chat("s", "u")
    assert exc.value.kind == "no_key"
    assert "console.groq.com" in str(exc.value)


@pytest.mark.asyncio
async def test_groq_retries_then_succeeds(monkeypatch):
    from app.ai.providers import groq as groq_mod

    monkeypatch.setattr(settings, "GROQ_API_KEY", "test-key")
    monkeypatch.setattr(groq_mod.asyncio, "sleep", lambda *_: _noop())
    fake = _FakeClient([
        _FakeResp(503, text="overloaded"),
        _FakeResp(200, {"choices": [{"message": {"content": "ok now"}}]}),
    ])
    monkeypatch.setattr(groq_mod, "_get_client", lambda: fake)

    out = await groq_mod.GroqProvider().chat("s", "u")
    assert out == "ok now"
    assert len(fake.calls) == 2


async def _noop():
    return None


@pytest.mark.asyncio
async def test_groq_auth_failure_does_not_retry(monkeypatch):
    from app.ai.providers import groq as groq_mod

    monkeypatch.setattr(settings, "GROQ_API_KEY", "bad-key")
    fake = _FakeClient([_FakeResp(401, text="invalid api key")])
    monkeypatch.setattr(groq_mod, "_get_client", lambda: fake)

    with pytest.raises(ProviderError) as exc:
        await groq_mod.GroqProvider().chat("s", "u")
    assert exc.value.kind == "auth"
    assert len(fake.calls) == 1     # no wasted retries on a non-transient error


@pytest.mark.asyncio
async def test_llm_chat_routes_to_groq(monkeypatch):
    """Switching LLM_PROVIDER=groq must reroute the whole app's chat() calls."""
    from app.ai import llm
    from app.ai.providers import groq as groq_mod

    monkeypatch.setattr(settings, "LLM_PROVIDER", "groq")
    monkeypatch.setattr(settings, "GROQ_API_KEY", "test-key")
    fake = _FakeClient([_FakeResp(200, {
        "choices": [{"message": {"content": "answer from groq"}}]
    })])
    monkeypatch.setattr(groq_mod, "_get_client", lambda: fake)

    assert await llm.chat("system", "user") == "answer from groq"


# ---------------------------------------------------------------- vision

def test_vision_factory_returns_gemini(monkeypatch):
    monkeypatch.setattr(settings, "VISION_PROVIDER", "gemini")
    assert get_vision_provider().name == "gemini"


def test_vision_factory_unknown_fails(monkeypatch):
    monkeypatch.setattr(settings, "VISION_PROVIDER", "clip")
    with pytest.raises(VisionProviderError) as exc:
        get_vision_provider()
    assert exc.value.kind == "unknown_provider"


@pytest.mark.asyncio
async def test_hf_vision_requires_a_model_id(monkeypatch):
    """Without HF_VISION_MODEL it must refuse, not invent a default."""
    monkeypatch.setattr(settings, "VISION_PROVIDER", "huggingface")
    monkeypatch.setattr(settings, "HF_VISION_MODEL", "")

    from app.ai.vision_providers import hf_vision
    hf_vision.unload()

    with pytest.raises(VisionProviderError) as exc:
        await get_vision_provider().analyze("/tmp/leaf.jpg", "tomato")
    assert exc.value.kind == "not_configured"
    assert "HF_VISION_MODEL" in str(exc.value)


def test_observation_clamps_confidence():
    assert VisionObservation(confidence=1.7).confidence == 1.0
    assert VisionObservation(confidence=-3).confidence == 0.0


def test_observation_marks_low_confidence_uncertain():
    low = VisionObservation(problem="Aphids", kind="pest", confidence=0.30)
    high = VisionObservation(problem="Aphids", kind="pest", confidence=0.90)
    assert low.uncertain is True
    assert high.uncertain is False


def test_observation_rejects_invalid_enums():
    obs = VisionObservation(kind="treatment", severity="apocalyptic")
    assert obs.kind == "unknown"
    assert obs.severity == "unknown"


def test_observation_has_no_treatment_field():
    """Structural guarantee: a vision provider cannot prescribe treatment."""
    fields = set(VisionObservation().to_dict().keys())
    for forbidden in ("treatment", "pesticide", "dose", "dosage",
                      "recommendation", "spray"):
        assert forbidden not in fields
