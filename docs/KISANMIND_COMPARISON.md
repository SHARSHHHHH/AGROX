# KisanMind Comparison — What's Worth Extracting

Source: https://github.com/divyamohan1993/kisanmind (MIT licence, ET AI Hackathon 2026)

**Read this first:** KisanMind runs on Google Earth Engine, Google Cloud STT/TTS/
Translation, Google Maps Platform, Twilio and Gemini 3 Flash. It is a
cloud-heavy build. Your project deliberately went the other way — local Qwen,
local vision, browser speech, no API keys — because your network blocks Google
entirely. **Do not try to copy their architecture.** Copy specific ideas.

---

## Honest scorecard

| Capability | KisanMind | Yours |
|---|---|---|
| Satellite crop health (44 params) | ✅ 4 constellations | ❌ none |
| Mandi prices | ✅ live AgMarkNet, 112 crops | ⚠️ MOCK, service ready |
| Voice | ✅ Cloud STT/TTS, 22 langs, phone calls | ✅ browser, 6 langs, free |
| LLM | ☁️ Gemini only | ✅ local Qwen **or** Gemini |
| Plant disease from photo | ❌ **none** — refers to KVK | ✅ local classifier |
| Pest IPM ladder | ❌ none | ✅ 8-rung, chemical gated |
| IoT / soil sensors | ❌ none | ✅ ESP32 |
| Crop lifecycle stages | ✅ 10 crops, GDD-based | ✅ 5 crops, day-based |
| Anti-hallucination | ✅ LLM fact-checks LLM | ✅ deterministic engines |
| Works offline / blocked network | ❌ no | ✅ yes |
| Government admin portal | ❌ none | ⚠️ partial |

You are ahead on disease/pest diagnosis, IPM, IoT and offline operation. They
are ahead on data breadth, market integration and voice reach.

---

## Worth extracting — ranked by value ÷ effort

### 1. Net-profit mandi ranking ⭐ highest value

They don't just show the best price — they rank mandis by **profit after
costs**:

```
net = price − transport(₹3.5/km/quintal) − commission(4%) − spoilage
```

with **crop-specific spoilage rates** (tomato 0.5%/hour vs wheat 0.01%/hour).
That is a genuinely better answer than "highest price", because the highest
price is often 200 km away and the trip eats the gain.

**Why it fits you:** this is the same shape as your `fertilizer.calculate_roi()`
— itemised deterministic arithmetic the LLM only phrases. You already have the
pattern. Add `market.rank_mandis_by_profit()` beside it.

**Effort:** ~half a day once you have real Agmarknet data. Distance can come
from stored mandi coordinates + haversine; you do not need Google Maps.

### 2. Confidence per data source ⭐

Every KisanMind response tags each source HIGH / MEDIUM / LOW / UNAVAILABLE,
and reports `data_age_minutes` and a `freshness_note`.

You already do a version of this — `data_confidence` in crop recommendations,
`status: ok|mock|unavailable` in market. **Extend it everywhere**: sensor age,
weather age, soil-test age. A farmer acting on a 3-day-old soil moisture
reading should be told it is 3 days old.

**Effort:** small, and it strengthens the honesty story you already have.

### 3. Cross-source conflict detection ⭐⭐ best idea in the repo

Their strongest concept. When independent sensors **disagree**, flag the
conflict instead of picking one:

> NDVI declining + adequate rain → **not** an irrigation problem. Flags
> pest/disease and refers to KVK.

And crucially: seven correlated red-edge indices count as **one** independent
basis, so confidence is never inflated by redundant sensors measuring the same
thing.

**Why it fits you:** you have genuinely independent sources — ESP32 soil
moisture, weather API, and now a leaf image. Today they feed the same answer
separately. A conflict rule like *"soil moisture adequate but leaves show
stress → do not irrigate, investigate disease"* is exactly the kind of
deterministic rule your architecture is built for.

**Effort:** ~1 day. High demo value — "our system tells you when it is unsure"
is a strong differentiator.

### 4. GDD-based growth stage instead of day counting

Your `lifecycle.py` uses days after sowing. They compute **Growing Degree
Days** from 90 days of real temperature history. GDD is meaningfully more
accurate — a cold January genuinely delays wheat, and a day-count cannot know
that.

**Effort:** ~half a day. Open-Meteo's archive API is free and needs no key, and
you already call Open-Meteo.

### 5. KVK referral for anything uncertain

They never name a pesticide; they refer to Krishi Vigyan Kendra on
**1800-180-1551**. You already refuse to invent doses — adding a concrete
helpline turns a refusal into a next step. Cheap and genuinely useful.

### 6. Trivia filler while data loads

Small UX idea that matters for you specifically: local Qwen takes 15-40s on
CPU. Farming trivia during the wait beats a spinner.

---

## Do NOT copy

**Satellite integration.** Earth Engine needs a Google Cloud project with
billing, and your network blocks Google. Weeks of work for a dependency you
cannot reach.

**Twilio phone calls.** Impressive, but a paid number plus webhooks plus
telephony-quality STT is a project on its own. Their number is US-based.

**Cloud STT/TTS.** Your browser speech is free and already works in 6
languages. Their 22 languages are mostly "via Hindi" fallbacks anyway — only 12
have native voices.

**"Gemini fact-checks Gemini".** Their anti-hallucination layer asks one LLM to
verify another. Your deterministic engines are a **stronger** guarantee — a
rule engine cannot be talked out of its answer. Do not trade down.

---

## Suggested order

1. Cross-source conflict detection — best idea, fits your architecture
2. Net-profit mandi ranking — needs the Agmarknet key
3. Source confidence + data age everywhere
4. GDD growth stage
5. KVK referral line
