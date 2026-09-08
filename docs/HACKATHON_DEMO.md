# Hackathon Demo Script

**Total: 7 minutes.** Everything below is runnable against the committed code.

---

## Before you start (do this the night before)

```bash
cd backend
pip install -r requirements.txt

# Verify whichever provider you plan to demo:
python scripts/check_gemini.py          # if LLM_PROVIDER=gemini
# or, for local Qwen:
pip install -r requirements-qwen.txt    # ~3 GB download, do NOT do this live
python -c "from app.ai.providers.qwen import warmup; print(warmup())"

python -m pytest -q                     # expect 120 passed
uvicorn app.main:app --reload
```

```bash
cd frontend && npm install && npm run dev
```

**Pre-warm the model before you present.** A cold Qwen load takes tens of
seconds and will look like a crash on stage.

**Decide your provider in advance.** Local Qwen demos well ("no API key, no
internet, no rate limits") but is slower on a laptop CPU. Gemini is faster but
depends on conference wifi. If the venue network is bad, use Qwen.

---

## The 7 minutes

### 0:00 — The problem (45s)

> "A farmer in Madhya Pradesh asks an AI chatbot whether to spray his soybean.
> The chatbot invents a pesticide and a dose. It sounds completely confident.
> That is the failure mode we designed against."

One line to land: **fluency is not correctness, and in agriculture a confident
wrong answer costs money and crops.**

### 0:45 — Architecture in one slide (60s)

Show the pipeline from `docs/ARCHITECTURE.md`:

```
NLP → deterministic tools → GROUNDED FACTS → LLM phrases them → farmer
```

> "The model is at the end, not the middle. By the time it speaks, the decision
> is already made. It cannot change a number — it can only translate one."

### 1:45 — Live: the safety engine refuses (90s)

**This is your strongest moment. Lead with a refusal, not a success.**

```bash
python -m pytest tests/test_grounded_workflow.py::test_model_output_cannot_change_the_decision -v
```

> "In this test the language model explicitly says 'go ahead and irrigate for 60
> minutes.' The soil is at 92% moisture. The engine blocks the pump anyway, and
> the block is what governs. The model's opinion never reaches the hardware."

Then show why blocks exist:

```bash
python -m pytest tests/test_domain_engines.py -k "blocks_pump or override" -v
```

Five gates: stale sensor data, saturated soil, low water level, heavy rain,
duration clamp.

> "A farmer can override our *advice*. They cannot override *equipment safety* —
> running a pump dry destroys the impeller."

### 3:15 — Live: provider switch (60s)

In `backend/.env`:

```bash
LLM_PROVIDER=gemini    →    LLM_PROVIDER=qwen
```

Restart. Ask the same question in the UI.

> "Same question, same grounded facts, different model. No code changed. The
> deterministic layer produced byte-identical numbers — only the wording moved."

```bash
python -m pytest tests/test_grounded_workflow.py::test_same_facts_regardless_of_provider -v
```

> "Local Qwen means no API key, no rate limits, and it runs with the network
> unplugged. That matters for rural deployment."

### 4:15 — Live: crop recommendation (75s)

In the UI, enter soil values: pH 6.8, N 30, P 40, K 70, moisture 60%, black soil.

> "Soybean scores highest — Madhya Pradesh's largest crop. But look at *why*:
> the score decomposes into season, pH, moisture, temperature, NPK and soil
> type. Nothing here came from a model. It's arithmetic you can audit."

Point at the confidence field:

> "It also tells you how much evidence the ranking rests on. With two inputs it
> says 'low confidence' rather than pretending."

### 5:30 — Live: the honesty contract (60s)

Ask for a market price.

```bash
# In .env set ALLOW_MOCK_MARKET_DATA=false, restart
```

> "We haven't wired Agmarknet yet. So instead of inventing a mandi rate, it says
> *data unavailable* and tells the farmer to check locally. The prompt sent to
> the model literally contains 'Do NOT state any price figure.'"

```bash
python -m pytest tests/test_domain_engines.py -k "market" -v
```

> "Five tests exist purely to prove we never invent a price."

### 6:30 — Close (30s)

> "120 tests. Every agronomic number is deterministic and auditable. The model
> is swappable between local and cloud with one line. And when we don't know
> something, the system says so — which for a farmer is worth more than a
> confident guess."

---

## Questions you will be asked

**"Isn't this just a rules engine with a chatbot on top?"**
Yes, deliberately. The agent still chooses which tools to call — that's the
agentic part. But tool *outputs* are authoritative. In a domain where a wrong
number costs a season's income, that's the correct trade.

**"Why Qwen 1.5B and not something bigger?"**
It runs on a laptop CPU with no GPU, and it only has to phrase pre-computed
facts — not reason about agronomy. The hard reasoning is in Python. A larger
model would add latency without adding correctness.

**"How do you know the agronomic data is right?"**
We don't claim it is verified. It's compiled representative data for MP, and
every response carries a disclaimer pointing to the local Krishi Vigyan Kendra.
Validating it against JNKVV package-of-practices is required before real use.
Being clear about that is part of the design.

**"What happens when the LLM is down?"**
The farmer still gets the numbers. Try it:
```bash
python -m pytest tests/test_grounded_workflow.py::test_deterministic_output_survives_total_llm_outage -v
```
The advice survives; the failure reason is shown rather than hidden.

---

## If something breaks on stage

| Symptom | Do this |
|---|---|
| Gemini "server busy" | It retries 3× automatically. If it persists, switch `LLM_PROVIDER=qwen` |
| Qwen slow / freezing | It wasn't pre-warmed. Switch to `gemini`, keep talking |
| No network at all | Switch to `qwen`, and make it the story — offline is the point |
| Vision fails | `VISION_PROVIDER=huggingface` is a **stub and raises by design**. Keep it on `gemini` |
| Anything else | Fall back to `python -m pytest -q` — 120 green tests is itself a demo |

**Do not** run `pip install -r requirements-qwen.txt` live. It is a ~3 GB
download and it will not finish before your time does.
