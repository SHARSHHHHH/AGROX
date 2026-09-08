# Architecture

## The core principle

Every number a farmer acts on is computed by deterministic Python. The language
model only phrases those numbers in the farmer's language.

```
Farmer question (any of 6 languages)
        │
        ▼
   NLP layer            language detection, intent, entity extraction
        │                (keyword rules — works with the LLM offline)
        ▼
   Agent               decides WHICH tools are needed for this intent
        │
        ▼
   Deterministic tools  irrigation · soil · IPM · severity · schemes
        │               crop suitability · lifecycle · market · ROI
        │
        │  ── produces GROUNDED FACTS (plain text, already final) ──
        ▼
   LLM provider         Qwen (local)  OR  Gemini (API)
        │               phrases the facts; cannot change them
        ▼
   Translation          into the farmer's language
        │
        ▼
      Farmer
```

The model sits at the **end** of the pipeline, not the middle. By the time it is
called, the decision is already made.

## Why this shape

An agricultural advisor that invents a pesticide dose, a mandi price or a pump
command causes real harm — money lost, crops damaged, equipment destroyed. LLMs
are fluent whether or not they are correct, and fluency is exactly what makes a
fabricated number dangerous.

So the split is:

| Layer | Decides | Can the LLM affect it? |
|---|---|---|
| Rule engines | irrigation, IPM tier, severity, crop score, ROI | **No** |
| Knowledge bases | symptoms, controls, thresholds, lifecycle stages | **No** |
| External data | weather, sensors, market prices | **No** |
| LLM | wording, tone, language, follow-up answers | Yes |

This is enforced structurally, not by prompt instruction:

- `VisionObservation` has **no field** in which a treatment could be expressed.
  A vision model literally cannot return a dose.
- `irrigation.evaluate_pump_request()` takes no parameter through which a model
  could override a safety block.
- `fertilizer.grounded_facts()` ends with "Do NOT recalculate, adjust or round
  these figures."
- `market.grounded_facts()` returns "DATA UNAVAILABLE … Do NOT state any price
  figure" when there is no source.

`tests/test_grounded_workflow.py` asserts these mechanically, including a test
where the stub model explicitly says "go ahead and irrigate" while the engine
has blocked the pump — and the block stands.

## Provider abstraction

```
app/ai/providers/
    base.py       BaseLLMProvider — chat(system, user, temperature, max_tokens)
    gemini.py     GeminiProvider  — adapter over the tested transport in llm.py
    qwen.py       QwenProvider    — local transformers, singleton, thread pool
    factory.py    get_provider()  — reads LLM_PROVIDER, caches instances
```

`llm.chat()` routes through the factory, so **every existing caller switches
providers with no code change**. `agent.py`, `nlp.py` and the pest pipeline were
not modified.

Vision mirrors this exactly under `app/ai/vision_providers/`.

### Qwen implementation notes

- **Singleton load.** 1.5B parameters take tens of seconds to load; per-request
  loading would be unusable. `warmup()` runs on FastAPI startup.
- **Thread executor.** `transformers.generate()` is synchronous and compute
  bound. Called directly in an async endpoint it blocks the entire event loop
  and freezes every other request. It runs via `asyncio.to_thread`.
- **`model.eval()` + `torch.no_grad()`.** Without `eval()`, dropout stays active
  and identical prompts give different answers. Without `no_grad()`, activation
  memory grows through generation and can exhaust RAM on a laptop.
- **Chat template.** Qwen2.5-Instruct is trained on a specific template;
  concatenating prompts manually degrades instruction-following badly.
- **`QWEN_MAX_NEW_TOKENS=200`.** On CPU, generation time is roughly linear in
  output length, so this is the main latency control. Our answers are short
  because the facts come from elsewhere.

### Gemini notes

The transport in `app/ai/llm.py` handles retry with exponential backoff on 429
and 503 (the "server busy" condition), classifies every failure kind, pools
connections, and caps the reasoning budget. `gemini-3.7-flash` is a reasoning
model — leaving `GEMINI_THINKING_BUDGET` unset made it slow, because thinking
tokens are generated before any text and billed at the output rate.

## Data honesty contract

`market.py` and `fertilizer.py` return exactly one of three states:

| status | meaning |
|---|---|
| `ok` | real data from a configured upstream source |
| `mock` | clearly labelled sample data, every field prefixed `MOCK` |
| `unavailable` | no source configured, or upstream failed |

There is **no code path that produces a number without a status attached**.
Setting `ALLOW_MOCK_MARKET_DATA=false` removes the mock path entirely.

## Layout

```
backend/app/
  ai/
    llm.py                    provider-agnostic chat() + Gemini transport
    nlp.py                    language/intent/entities (unchanged)
    speech.py                 Whisper STT (unchanged)
    providers/                LLM provider abstraction          [NEW]
    vision_providers/         vision provider abstraction       [NEW]
  services/
    recommendation.py         irrigation advice + soil analysis (unchanged)
    irrigation.py             pump-control SAFETY engine        [NEW]
    crop_suitability.py       MP crop scoring                   [NEW]
    lifecycle.py              stage-by-stage guidance           [NEW]
    market.py                 mandi prices, honest states       [NEW]
    fertilizer.py             offers + itemised ROI             [NEW]
    ipm.py, pest_severity.py, pest_pipeline.py   (unchanged)
    alerts.py, schemes.py, weather.py, simulator.py (unchanged)
  ml/                         vision + knowledge bases (unchanged)
  api/                        routers (diagnostics added)
```

## Reference data caveat

The agronomic values in `crop_suitability.py` and `lifecycle.py` are
representative for Madhya Pradesh, compiled for this project. They are **not a
substitute for state agricultural university recommendations**. Before
production use, have them reviewed against JNKVV (Jabalpur) or RVSKVV (Gwalior)
package-of-practices. Every response carries this disclaimer to the farmer.

The `ASSUMED_YIELD_BOOST_T_PER_ACRE` values in `fertilizer.py` are the weakest
input in the system — organic manure response varies enormously with soil
carbon, rainfall and crop. They are conservative placeholders, labelled as
assumptions in every ROI response. Replace them with local trial data before
presenting ROI as financial advice.
