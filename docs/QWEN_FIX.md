# Why Qwen Wasn't Responding — Diagnosis

**150 tests passing**, including 10 that run a **real transformers model**
end to end through the app path.

You were right that the connection differed somewhere. I found **four bugs**,
three of them mine from the previous build.

---

## Bug 1 — The server froze during startup ← the "not responding" cause

`main.py` had a **synchronous** startup handler calling `qwen_warmup()` inline:

```python
@app.on_event("startup")
def startup():                      # <-- sync
    log.info("Qwen warmup: %s", qwen_warmup())
```

Starlette runs a sync startup handler **directly on the event loop** — look at
`Router.startup()`: it calls `handler()` with no threadpool. So loading a 1.5B
model, or worse downloading 3 GB on first run, blocked the loop completely.
uvicorn accepted **no connections at all** until it finished. The server looked
dead, not slow.

**Fixed:** warmup now runs on a daemon thread. The API is up immediately; the
first chat request picks up the model once it is ready.

## Bug 2 — `/api/health` always said "gemini"

```python
"llm_provider": "gemini",           # hardcoded string
```

I left literal `"gemini"` in the health endpoint and the startup log when I
patched this file. So however you configured it, the app **reported Gemini**.
That is why it still looked like it was "focussing on gemini".

**Fixed.** Now:
```json
{"llm_provider": "qwen",
 "llm": {"provider": "qwen", "model": "Qwen/Qwen2.5-1.5B-Instruct",
         "loaded": false, "device": "not loaded"},
 "vision_provider": "gemini"}
```

## Bug 3 — `/api/test-gemini` failed under Qwen

It returned `failed: GEMINI_API_KEY is not configured` even when Qwen was
working perfectly, because it gated on the Gemini key regardless of provider.

**Fixed:** it now tests whichever provider is active, and reports
`status: loading` while Qwen is still warming rather than blocking.

## Bug 4 — Every non-English answer cost TWO model calls

```python
answer_en = await chat(...)                      # call 1
answer = await nlp.translate(answer_en, lang)    # call 2
```

Generate in English, then call the LLM *again* to translate. On a cloud API
that is wasteful; on a local CPU model it **doubles the wait**, so a Tamil or
Hindi farmer waited twice as long as an English one for the same answer. It
also hurt quality — a 1.5B model translating its own output compounds any error
in the first pass.

**Fixed:** one call that answers directly in the farmer's language.

---

## Also hardened

**Requests fail fast while loading.** Previously a request arriving during
startup blocked on the `threading.Lock` inside `_load()` for however long the
download took, with no explanation. Now it returns immediately:

> "The local Qwen model is still loading. The first run downloads about 3 GB…"

**Generation timeout** (`QWEN_TIMEOUT_S=120`). A stalled generation surfaces as
an error naming `QWEN_MAX_NEW_TOKENS`, instead of hanging forever.

**Frontend timeout** (180s) with a helpful message instead of an endless spinner.

---

## Proof it works

I could not download the real Qwen weights — huggingface.co returns **403** from
my sandbox. So I built a **tiny Qwen2 model locally with transformers** and ran
the identical code path:

```
1. request BEFORE load   -> ProviderError[loading] fails fast, no hang
2. warmup()              -> {'loaded': True, 'device': 'cpu'}
3. llm.chat()            -> 0.03s
   output               -> 'refarmeristugatrhvisosacfareatop'
   REAL generation?     -> YES
4. provider now          -> qwen | loaded: True
5. switch to gemini      -> gemini
```

The gibberish is expected — random weights. What matters is that
`tokenizer.apply_chat_template → model.generate → prompt-token stripping →
decode → thread executor → QwenProvider → factory → llm.chat` all work.

```bash
python -m pytest tests/test_qwen_pipeline.py -v    # 10 passed
```

Those tests skip automatically if torch is absent, so the suite stays green
either way.

**One honest note on that test suite:** my first version passed by luck. With
random weights the model sometimes emits only special tokens, which decode to
`""`. I tried suppressing those logits by forcing the weight rows to `-100`,
which *does not work* — a logit is `w·h`, so a strongly negative weight flips
**positive** whenever the hidden state is negative. Seeding the model
construction is the correct fix. Verified deterministic across six runs.

---

## What you need to do

```bash
cd backend
pip install -r requirements-qwen.txt     # ~3 GB
uvicorn app.main:app --reload
```

Watch the log. You should see:
```
Qwen loading in background (first run downloads ~3 GB)...
Active LLM provider: {'provider': 'qwen', ...}
Startup complete. Provider=qwen Demo=True
...
Qwen ready on cpu
```

The server answers requests **immediately** now, even before that last line.
Until it appears, chat returns the honest "still loading" message.

Then verify:
```bash
curl localhost:8000/api/health        # llm_provider must say "qwen"
curl localhost:8000/api/test-gemini   # tests the ACTIVE provider
```

---

## Two things I still cannot verify

**Real Qwen2.5-1.5B weights have never run through this code.** HF is blocked
here (403) and torch plus weights exceed my disk. The pipeline is proven with a
real transformers model; what is unproven is that particular checkpoint loading
on your machine. If it fails, the error will now name the cause.

**Expect it to be slow.** Qwen2.5-1.5B on a CPU laptop generates roughly 5-15
tokens/sec, so a 200-token answer takes 15-40 seconds. That is inherent to
running a local model without a GPU, not a bug. If it is too slow, lower
`QWEN_MAX_NEW_TOKENS` to 120, or switch back to `LLM_PROVIDER=gemini` once you
are off the blocked network.

**Vision is still Gemini.** `VISION_PROVIDER=gemini`, so Plant Health stays
broken on a network that blocks Google. Qwen2.5-1.5B-Instruct is text-only and
cannot process images at all — that needs a separate vision model.
