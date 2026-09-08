# What Works Now — Verification

**140 tests passing.** Frontend builds clean. Every claim below has a command
you can run to check it yourself.

---

## Fixed in this build

### 1. Crop Advisor is now visible

Previously `crop_suitability.py` and `lifecycle.py` existed with tests but had
**no API endpoints and no UI**. Now wired end to end.

- **Page:** sidebar → 🌾 Crop Advisor
- **Endpoints:** `/api/crops/recommend`, `/api/crops/lifecycle/{crop}`,
  `/api/crops/lifecycle/{crop}/stage`, `/api/crops/list`, `/api/crops/season`

Verify:
```bash
cd backend && python -m pytest tests/test_crops_market_api.py -q   # 20 passed
```

Live output:
```
Soybean   100.0  HIGHLY SUITABLE
Cotton     98.0  HIGHLY SUITABLE
Maize      96.6  HIGHLY SUITABLE
confidence=high
```

The UI shows a per-factor score breakdown (season, pH, moisture, temperature,
NPK, soil type) so a farmer can see *why* a crop ranked where it did, plus a
confidence badge and an explicit list of what was not measured.

### 2. Market & Offers page

- **Page:** sidebar → 💰 Market & Offers
- **Endpoints:** `/api/market/price`, `/api/market/prices`,
  `/api/market/my-crop`, `/api/fertilizer/offers`, `/api/fertilizer/roi`

Every price carries a status badge: **LIVE DATA** / **⚠ SAMPLE DATA** /
**NO DATA**. A mock price is never rendered to look real.

The ROI calculator shows the full itemised breakdown — bags cost, transport,
saving, yield revenue, net — plus break-even distance and its assumptions.

**One behaviour worth knowing:** if the only available crop price is MOCK, the
ROI calculator refuses to use it and counts yield revenue as zero, saying so.
A financial figure never rests on demonstration data.

```
ROI: worth_it=False profit=-5400.0 crop_price_source=mock yield_counted=False
```

### 3. Language selector on every page

Moved `LanguagePicker` from Login into the shared `Layout` sidebar footer. It
now appears on **every authenticated page**. `SpeakButton` added to Crop
Advisor results so answers can be read aloud.

### 4. `.env` switched to Qwen

```
LLM_PROVIDER=qwen
```

**This will not work until you install the extras:**
```bash
cd backend
pip install -r requirements-qwen.txt        # ~3 GB, takes a while
python -c "from app.ai.providers.qwen import warmup; print(warmup())"
```

Until then you will get an honest error naming the missing dependency rather
than a silent failure. To go back: set `LLM_PROVIDER=gemini`.

---

## Still broken, and why

### Plant Health returns "Uncertain" every time

Your screenshot shows `ConnectError` — your machine **cannot open a connection
to Google at all**. Not a key problem, not a rate limit. College or corporate
firewall, or a proxy.

Confirm it:
```bash
curl -sS -o /dev/null -w "%{http_code}\n" https://generativelanguage.googleapis.com/v1beta/models
```
Timeout or connection refused = blocked. Try a phone hotspot.

Switching to Qwen fixes **chat only**. Vision still calls Gemini
(`VISION_PROVIDER=gemini`), so disease and pest detection stay broken on that
network. `VISION_PROVIDER=huggingface` is a deliberate stub that raises rather
than returning a fake diagnosis.

**Fixing this needs a local vision model** — section 1 of
`docs/RESEARCH_PROMPTS.md`, and the PlantVillage / IP102 datasets.

---

## Run it

```bash
cd backend
pip install -r requirements.txt
python -m pytest -q                  # expect 140 passed
uvicorn app.main:app --reload

cd frontend
npm install && npm run dev
```

Login `farmer@demo.com` / `demo123`. New pages: **Crop Advisor**, **Market &
Offers**. Language picker at the bottom of the sidebar.

---

## Test breakdown

| Suite | Tests |
|---|---|
| Original (untouched) | 33 |
| Gemini transport | 18 |
| Provider abstraction | 20 |
| Domain engines | 42 |
| Grounded workflow E2E | 7 |
| **Crop/market API (new)** | **20** |
| **Total** | **140** |

---

## Honest status

| Feature | Status |
|---|---|
| Crop suitability | **WORKING** — API + UI + 20 tests |
| Crop lifecycle | **WORKING** — API + UI |
| Market prices | **WORKING, MOCK DATA** — needs Agmarknet key |
| Fertilizer ROI | **WORKING** — math verified |
| Fertilizer offers | **MOCK** — needs vendor portal |
| Language on all pages | **WORKING** |
| Qwen provider | **NEEDS INSTALL** — code complete, never run on real weights |
| Plant disease vision | **BROKEN on your network** — needs local model |
| Voice chatbot (multi-turn) | **NOT BUILT** |
| ESP32 auto-irrigation | **NOT BUILT** — safety engine exists, no hardware control |
| Proactive alerts | **NOT BUILT** |
| Govt district analytics | **NOT BUILT** |
| Balcony-specific flows | **PARTIAL** — thresholds exist, no dedicated UI |
| Onboarding + geolocation | **NOT BUILT** |

Nine features remain. See `docs/RESEARCH_PROMPTS.md` — paste one section at a
time into a model with web search.
