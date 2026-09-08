"""Local Qwen provider (Qwen/Qwen2.5-1.5B-Instruct).

Runs fully offline once the weights are cached, which removes the API key, the
rate limits and the "server busy" failure mode entirely.

DESIGN NOTES

Singleton load
    The model is loaded once and reused. Loading 1.5B parameters takes tens of
    seconds; doing it per request would be unusable. `warmup()` is called from
    the FastAPI startup event so the first farmer never pays that cost.

Blocking inference off the event loop
    transformers `generate()` is synchronous and CPU/GPU bound. Called directly
    inside an async endpoint it would block the entire event loop and freeze
    every other request. It is therefore run in a thread executor.

Token budget
    QWEN_MAX_NEW_TOKENS defaults to 200. On CPU, generation is roughly linear
    in output length, so this cap is the main latency control. Our prompts ask
    for short farmer-facing answers, and the agronomic facts are already
    computed deterministically, so 200 is sufficient.

Memory
    ~3 GB in float32 on CPU, ~1.5 GB in float16 on GPU. The dtype is chosen
    automatically.
"""

import asyncio
import logging
import threading
from typing import Optional

from app.ai.providers.base import BaseLLMProvider, ProviderError
from app.core.config import settings

log = logging.getLogger("agri.qwen")

_model = None
_tokenizer = None
_device = None
_load_lock = threading.Lock()


def _torch():
    try:
        import torch
        return torch
    except ImportError as exc:
        raise ProviderError(
            "missing_dependency",
            "PyTorch is not installed. Install the local-model extras with: "
            "pip install -r requirements-qwen.txt "
            "(or set LLM_PROVIDER=gemini in .env to use the API instead).",
            provider="qwen") from exc


def _load():
    """Load tokenizer + model once. Thread-safe."""
    global _model, _tokenizer, _device

    if _model is not None:
        return _model, _tokenizer, _device

    with _load_lock:
        if _model is not None:            # another thread won the race
            return _model, _tokenizer, _device

        torch = _torch()

        try:
            from transformers import AutoModelForCausalLM, AutoTokenizer
        except ImportError as exc:
            raise ProviderError(
                "missing_dependency",
                "transformers is not installed. Install with: "
                "pip install -r requirements-qwen.txt",
                provider="qwen") from exc

        model_id = settings.QWEN_MODEL
        use_gpu = torch.cuda.is_available()
        device = "cuda" if use_gpu else "cpu"
        dtype = torch.float16 if use_gpu else torch.float32

        log.info("Loading %s on %s (%s). First run downloads ~3 GB.",
                 model_id, device, dtype)

        try:
            tokenizer = AutoTokenizer.from_pretrained(model_id)
            model = AutoModelForCausalLM.from_pretrained(
                model_id, torch_dtype=dtype, low_cpu_mem_usage=True)
            model.to(device)
            # Disables dropout and other training-time behaviour. Without this
            # the same prompt can give different answers run to run.
            model.eval()
        except Exception as exc:
            raise ProviderError(
                "load_failed",
                f"Could not load '{model_id}': {type(exc).__name__}: {exc}. "
                f"Check disk space (~3 GB needed) and network access to "
                f"huggingface.co, or set LLM_PROVIDER=gemini.",
                provider="qwen") from exc

        _model, _tokenizer, _device = model, tokenizer, device
        log.info("Qwen ready on %s", device)
        return _model, _tokenizer, _device


def warmup() -> dict:
    """Preload at application startup. Never raises — degrades instead."""
    if settings.LLM_PROVIDER.lower() != "qwen":
        return {"loaded": False, "reason": "LLM_PROVIDER is not 'qwen'"}
    try:
        _, _, device = _load()
        return {"loaded": True, "device": device, "model": settings.QWEN_MODEL}
    except ProviderError as exc:
        log.warning("Qwen warmup failed (%s): %s", exc.kind, exc)
        return {"loaded": False, "kind": exc.kind, "reason": str(exc)}


def is_loaded() -> bool:
    return _model is not None


def unload() -> None:
    """Free the weights. Used by tests and by provider switching."""
    global _model, _tokenizer, _device
    _model = _tokenizer = _device = None


def _generate_sync(system_prompt: str, user_prompt: str,
                   temperature: float, max_new_tokens: int) -> str:
    """Blocking generation. Always called inside a thread executor."""
    torch = _torch()
    model, tokenizer, device = _load()

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]

    # Qwen2.5-Instruct is trained on a specific chat template. Concatenating
    # the prompts manually instead degrades instruction-following badly.
    text = tokenizer.apply_chat_template(
        messages, tokenize=False, add_generation_prompt=True)

    inputs = tokenizer([text], return_tensors="pt")
    inputs.pop("token_type_ids", None)
    inputs = inputs.to(device)

    # temperature=0 means greedy; sampling with temperature 0 is undefined.
    do_sample = temperature > 0.01

    gen_kwargs = {
        "max_new_tokens": max_new_tokens,
        "do_sample": do_sample,
        "pad_token_id": tokenizer.eos_token_id,
    }
    if do_sample:
        gen_kwargs.update(temperature=temperature, top_p=0.9)

    # no_grad keeps activation memory flat; without it a long generation can
    # exhaust RAM on a laptop.
    with torch.no_grad():
        output_ids = model.generate(**inputs, **gen_kwargs)

    # Strip the prompt tokens so only the completion is decoded.
    new_ids = output_ids[0][inputs["input_ids"].shape[-1]:]
    return tokenizer.decode(new_ids, skip_special_tokens=True).strip()


class QwenProvider(BaseLLMProvider):
    name = "qwen"

    async def chat(self, system_prompt: str, user_prompt: str,
                   temperature: float = 0.3,
                   max_tokens: Optional[int] = None) -> str:
        max_new = max_tokens or settings.QWEN_MAX_NEW_TOKENS

        # Fail fast while the model is still loading.
        #
        # Without this, a request arriving during startup blocks on the
        # threading.Lock inside _load() for however long the download takes —
        # potentially minutes — and the caller just hangs with no explanation.
        # An immediate, honest error is far more useful than a silent stall.
        if not is_loaded():
            raise ProviderError(
                "loading",
                "The local Qwen model is still loading. The first run "
                "downloads about 3 GB, which can take several minutes. Check "
                "the server log for 'Qwen ready', then try again.",
                provider=self.name)

        try:
            text = await asyncio.wait_for(
                asyncio.to_thread(_generate_sync, system_prompt, user_prompt,
                                  temperature, max_new),
                timeout=settings.QWEN_TIMEOUT_S)
        except asyncio.TimeoutError:
            raise ProviderError(
                "timeout",
                f"Qwen did not finish generating within "
                f"{settings.QWEN_TIMEOUT_S}s. On a CPU-only machine, lower "
                f"QWEN_MAX_NEW_TOKENS (currently {max_new}) in backend/.env, "
                f"or raise QWEN_TIMEOUT_S.",
                provider=self.name)
        except ProviderError:
            raise
        except Exception as exc:
            raise ProviderError(
                "generation_failed",
                f"Qwen generation failed: {type(exc).__name__}: {exc}",
                provider=self.name) from exc

        # A model that emits only whitespace has failed, even though the
        # string is truthy. Strip before the emptiness check.
        text = (text or "").strip()
        if not text:
            raise ProviderError("empty", "Qwen returned an empty response.",
                                provider=self.name)
        return text

    def describe(self) -> dict:
        return {
            "provider": self.name,
            "model": settings.QWEN_MODEL,
            "max_new_tokens": settings.QWEN_MAX_NEW_TOKENS,
            "loaded": is_loaded(),
            "device": _device or "not loaded",
            "requires": "torch + transformers, ~3 GB disk, no API key",
        }
