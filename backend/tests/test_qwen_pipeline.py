"""Qwen pipeline tests.

WHAT THESE PROVE
----------------
The real Qwen2.5-1.5B weights cannot be downloaded in CI (no Hugging Face
access), so these tests exercise the SAME code path with a tiny randomly
initialised Qwen2 model built locally. That covers everything except the
weights themselves:

    tokenizer.apply_chat_template  ->  model.generate  ->  prompt-token
    stripping  ->  decode  ->  thread executor  ->  QwenProvider  ->
    factory  ->  llm.chat  ->  agent

If these pass, a failure with real weights is a download/RAM problem, not a
wiring problem.

Tests needing torch are skipped automatically when it is absent, so the suite
stays green without the ~3 GB local-model extras installed.
"""

import asyncio

import pytest

from app.ai.providers import ProviderError, reset_cache
from app.ai.providers import qwen as qwen_mod
from app.core.config import settings


try:
    import torch  # noqa: F401
    from transformers import AutoTokenizer  # noqa: F401
    HAS_TORCH = True
except Exception:
    HAS_TORCH = False

needs_torch = pytest.mark.skipif(
    not HAS_TORCH,
    reason="torch/transformers not installed (pip install -r requirements-qwen.txt)")


@pytest.fixture(autouse=True)
def _clean():
    reset_cache()
    yield
    reset_cache()
    qwen_mod.unload()


# ------------------------------------------------- wiring (no torch needed)


def test_provider_is_qwen_when_configured(monkeypatch):
    from app.ai.providers import get_provider
    monkeypatch.setattr(settings, "LLM_PROVIDER", "qwen")
    assert get_provider().name == "qwen"


@pytest.mark.asyncio
async def test_request_during_loading_fails_fast(monkeypatch):
    """A request arriving while the model loads must not hang for minutes."""
    monkeypatch.setattr(qwen_mod, "is_loaded", lambda: False)

    with pytest.raises(ProviderError) as exc:
        await qwen_mod.QwenProvider().chat("s", "u")

    assert exc.value.kind == "loading"
    assert "still loading" in str(exc.value)


@pytest.mark.asyncio
async def test_generation_timeout_is_bounded(monkeypatch):
    """A stalled generation surfaces as an error, never an indefinite hang."""
    monkeypatch.setattr(qwen_mod, "is_loaded", lambda: True)
    monkeypatch.setattr(settings, "QWEN_TIMEOUT_S", 1)

    def slow(system, user, temperature, max_new_tokens):
        import time
        time.sleep(5)
        return "too late"

    monkeypatch.setattr(qwen_mod, "_generate_sync", slow)

    with pytest.raises(ProviderError) as exc:
        await qwen_mod.QwenProvider().chat("s", "u")

    assert exc.value.kind == "timeout"
    assert "QWEN_MAX_NEW_TOKENS" in str(exc.value)


@pytest.mark.asyncio
async def test_generation_does_not_block_the_event_loop(monkeypatch):
    """transformers.generate() is blocking; it must run off the event loop.

    If it ran inline, the concurrent ticker below could not advance while
    generation was in progress.
    """
    monkeypatch.setattr(qwen_mod, "is_loaded", lambda: True)

    def blocking(system, user, temperature, max_new_tokens):
        import time
        time.sleep(0.4)
        return "generated"

    monkeypatch.setattr(qwen_mod, "_generate_sync", blocking)

    ticks = 0

    async def ticker():
        nonlocal ticks
        for _ in range(20):
            await asyncio.sleep(0.02)
            ticks += 1

    result, _ = await asyncio.gather(
        qwen_mod.QwenProvider().chat("s", "u"), ticker())

    assert result == "generated"
    assert ticks > 5, "event loop was blocked during generation"


# ------------------------------------------------- real model path (torch)


@pytest.fixture(scope="module")
def tiny_model(tmp_path_factory):
    """Build a tiny Qwen2 model + tokenizer locally. No network required."""
    if not HAS_TORCH:
        pytest.skip("torch not installed")

    import torch
    from tokenizers import Tokenizer, models, pre_tokenizers, trainers
    from transformers import (AutoModelForCausalLM, PreTrainedTokenizerFast,
                              Qwen2Config)

    out = tmp_path_factory.mktemp("tiny-qwen")

    # --- minimal BPE tokenizer trained on a scrap of agricultural text ---
    tok = Tokenizer(models.BPE(unk_token="<unk>"))
    tok.pre_tokenizer = pre_tokenizers.Whitespace()
    trainer = trainers.BpeTrainer(
        vocab_size=300,
        special_tokens=["<unk>", "<|endoftext|>", "<|im_start|>", "<|im_end|>"])
    tok.train_from_iterator([
        "soybean wheat chickpea maize cotton irrigation soil moisture",
        "the farmer should water the crop today because the soil is dry",
        "system user assistant advisor pest disease fertilizer",
    ] * 40, trainer)

    fast = PreTrainedTokenizerFast(
        tokenizer_object=tok,
        unk_token="<unk>",
        eos_token="<|im_end|>",
        pad_token="<|endoftext|>",
    )
    # The Qwen2.5-Instruct ChatML template, verbatim in structure.
    fast.chat_template = (
        "{% for message in messages %}"
        "{{'<|im_start|>' + message['role'] + '\n' + message['content'] + '<|im_end|>\n'}}"
        "{% endfor %}"
        "{% if add_generation_prompt %}{{'<|im_start|>assistant\n'}}{% endif %}"
    )
    fast.save_pretrained(out)

    # Seed BEFORE constructing the model.
    #
    # A freshly randomised model picks tokens near-uniformly, so on some runs
    # it emits only special tokens, which decode() strips to "" — making these
    # tests pass or fail by chance. Suppressing those logits does not work
    # reliably either: a logit is w.h, so forcing the weight row strongly
    # negative flips POSITIVE whenever the hidden state is negative.
    #
    # Seeding fixes the weights, so generation is reproducible and the test
    # measures the PIPELINE rather than the dice. Real Qwen weights need none
    # of this.
    torch.manual_seed(20260826)

    cfg = Qwen2Config(
        vocab_size=fast.vocab_size + 10,
        hidden_size=32, intermediate_size=64,
        num_hidden_layers=2, num_attention_heads=4, num_key_value_heads=2,
        max_position_embeddings=256,
        eos_token_id=fast.eos_token_id,
        pad_token_id=fast.pad_token_id,
        # Qwen2 ties lm_head to the embedding matrix by default, so editing
        # lm_head below would be silently discarded on save. Untie it.
        tie_word_embeddings=False,
    )
    model = AutoModelForCausalLM.from_config(cfg)

    model.save_pretrained(out)

    return str(out)


@needs_torch
def test_tiny_model_loads_through_our_loader(monkeypatch, tiny_model):
    """_load() must work against a real transformers checkpoint."""
    monkeypatch.setattr(settings, "QWEN_MODEL", tiny_model)
    qwen_mod.unload()

    model, tokenizer, device = qwen_mod._load()

    assert model is not None and tokenizer is not None
    assert device in ("cpu", "cuda")
    assert qwen_mod.is_loaded() is True


@needs_torch
def test_generate_sync_produces_text(monkeypatch, tiny_model):
    """The real generate path: chat template, generate, strip prompt, decode."""
    monkeypatch.setattr(settings, "QWEN_MODEL", tiny_model)
    qwen_mod.unload()

    out = qwen_mod._generate_sync(
        "You are an agricultural advisor.",
        "Should I water the soybean today?",
        temperature=0.0, max_new_tokens=16)

    # Random weights produce gibberish; what matters is that the pipeline
    # returns a decoded string rather than raising or echoing the prompt.
    assert isinstance(out, str)
    assert out.strip(), "generation produced no tokens"
    assert "<|im_start|>" not in out, "chat template markers leaked into output"
    assert "You are an agricultural advisor" not in out, "prompt was not stripped"


@needs_torch
def test_prompt_tokens_are_stripped(monkeypatch, tiny_model):
    """The reply must not contain the prompt echoed back."""
    monkeypatch.setattr(settings, "QWEN_MODEL", tiny_model)
    qwen_mod.unload()

    prompt = "irrigation moisture soil wheat"
    out = qwen_mod._generate_sync("system", prompt, 0.0, 8)
    assert prompt not in out


@needs_torch
@pytest.mark.asyncio
async def test_end_to_end_through_llm_chat(monkeypatch, tiny_model):
    """The full app path: llm.chat -> factory -> QwenProvider -> real model."""
    from app.ai import llm

    monkeypatch.setattr(settings, "QWEN_MODEL", tiny_model)
    monkeypatch.setattr(settings, "LLM_PROVIDER", "qwen")
    qwen_mod.unload()
    reset_cache()

    qwen_mod._load()          # stand in for background warmup
    assert qwen_mod.is_loaded()

    answer = await llm.chat("You are an advisor.",
                            "Should I irrigate today?",
                            max_output_tokens=16)

    assert isinstance(answer, str) and answer
    # The fallback text means the provider failed; we want a real generation.
    assert "AI unavailable" not in answer


@needs_torch
def test_warmup_reports_loaded(monkeypatch, tiny_model):
    monkeypatch.setattr(settings, "QWEN_MODEL", tiny_model)
    monkeypatch.setattr(settings, "LLM_PROVIDER", "qwen")
    qwen_mod.unload()

    result = qwen_mod.warmup()
    assert result["loaded"] is True
    assert result["device"] in ("cpu", "cuda")


@needs_torch
def test_bad_model_path_gives_actionable_error(monkeypatch):
    monkeypatch.setattr(settings, "QWEN_MODEL", "/nonexistent/model/path")
    qwen_mod.unload()

    with pytest.raises(ProviderError) as exc:
        qwen_mod._load()

    assert exc.value.kind == "load_failed"
    assert "LLM_PROVIDER=gemini" in str(exc.value)
