# Research Prompt — 9 Remaining Features

Copy the block below into a model with web search (ChatGPT, Gemini, Perplexity).
Paste **one section at a time**, not the whole thing — a single mega-prompt gets
you nine shallow answers instead of one useful one.

---

## Context block (paste this first, every time)

```
I am building a Sustainable Agriculture Advisory Platform for farmers in
Madhya Pradesh, India. Existing stack:

- Backend: Python 3, FastAPI, SQLAlchemy, SQLite
- Frontend: React 18 + TypeScript + Vite + TailwindCSS
- LLM: local Qwen2.5-1.5B-Instruct via transformers (provider-swappable
  with Google Gemini API)
- Vision: currently Gemini vision; need a local replacement
- STT/TTS: browser Web Speech API, 6 Indian languages
- IoT: ESP32 sensors reporting soil moisture, temperature, humidity,
  water level
- Users: three roles — farmer, balcony/home grower, government admin

ARCHITECTURAL CONSTRAINT (do not violate this in your answer):
All agronomic and financial numbers are computed by deterministic Python
rule engines. The LLM only phrases pre-computed facts into the farmer's
language. It must never invent a pesticide dose, a market price, a
subsidy amount, or an irrigation command. Any solution you propose must
preserve this separation.

CONSTRAINT: Deployment is in rural India — intermittent connectivity,
low-end Android phones, and some users are semi-literate. Prefer
offline-capable and low-bandwidth solutions.

For each answer give me:
1. The specific tool/library/dataset/API name with a working URL
2. Whether it is free, freemium, or paid (with the actual rate limits)
3. A minimal working code example in Python or TypeScript
4. Known failure modes and limitations
5. Rough implementation time for one developer

Do not give me generic advice. Be specific and cite sources.
```

---

## 1. Local plant disease + pest vision

```
I need to replace a cloud vision API with a LOCAL image classifier that
identifies plant diseases and insect pests from a farmer's phone photo,
running on a CPU-only laptop (no GPU, 8 GB RAM), inference under 5 seconds.

Answer these:
a) Compare PlantVillage, PlantDoc and IP102 datasets: size, class count,
   licence, and — critically — how well models trained on each generalise
   to real field photos with hands, soil and cluttered backgrounds.
   PlantVillage is lab images on plain backgrounds; quantify how much
   accuracy actually drops on field photos and cite the study.
b) Recommend a specific pretrained checkpoint on Hugging Face for Indian
   crop disease detection. Give the exact model ID and a transformers
   code example.
c) What quantisation (ONNX Runtime, OpenVINO, torch.quantization) gets a
   ResNet/EfficientNet/ViT classifier under 5s on CPU? Give benchmark
   numbers.
d) How do I make the model output a CALIBRATED confidence score, so that
   below a threshold I return "uncertain" instead of a wrong label?
   Cover temperature scaling and why raw softmax is overconfident.
e) How do I detect out-of-distribution images (a photo of a dog, a blurry
   photo) so the system refuses rather than guessing a disease?
```

## 2. Live market prices (Agmarknet)

```
I need live Indian mandi commodity prices for soybean, wheat, chickpea,
maize and cotton in Madhya Pradesh.

a) Give me the exact data.gov.in Agmarknet API resource ID, the full
   request URL format, how to register for a key, and the rate limits.
b) A working Python example using httpx that fetches today's modal price
   for soybean in Indore, with the exact query parameter names.
c) How stale is this data typically — same day, or lagged? How do I
   handle days with no reported arrivals?
d) Are there alternative sources (eNAM, state APMC portals, Bhav Copy)
   and how do they compare on coverage and freshness?
e) Best practice for caching so I do not exhaust the rate limit, given
   prices update at most once a day.
```

## 3. Government schemes data

```
I need structured, current data on Indian agricultural subsidy schemes
(PM-KISAN, PMFBY, KCC, soil health card, state MP schemes) including
eligibility rules, benefit amounts, required documents and application
links.

a) Is there ANY official API or bulk dataset? Check myscheme.gov.in,
   data.gov.in, and the DA&FW portal. If none exists, say so plainly.
b) If manual curation is the only option, give me a JSON schema for
   representing eligibility rules that a deterministic matcher can
   evaluate against a farmer profile (land size, category, state, crop).
c) How do other agri-tech products keep scheme data current? What is the
   realistic maintenance burden?
d) Legal position on scraping myscheme.gov.in — terms of service and
   robots.txt.
e) How should I handle a scheme whose deadline has passed or whose rules
   changed, so a farmer is never told they qualify for something they do not?
```

## 4. ESP32 automated irrigation

```
I have ESP32 nodes reporting soil moisture, temperature, humidity and
water level to a FastAPI backend. I now need to physically switch an
irrigation pump on and off from that backend.

a) Hardware: exact relay module for a 1 HP AC pump from an ESP32 GPIO.
   Cover optocoupler isolation, contactor rating, and why driving a
   contactor rather than the pump directly matters.
b) Safety interlocks that MUST be in firmware rather than the server —
   dry-run protection, maximum runtime watchdog, and what happens when
   wifi drops mid-irrigation. The pump must fail safe (off).
c) Command delivery: MQTT vs HTTP polling vs WebSocket for a device on
   flaky rural wifi. Which survives intermittent connectivity best?
d) How do I guarantee a command is executed exactly once and not
   replayed? Give an idempotency design.
e) Authentication so nobody else can turn on my pump. Device certificates
   vs pre-shared tokens on ESP32.
f) Full working ESP32 Arduino/PlatformIO sketch for relay control with a
   runtime watchdog.
```

## 5. Proactive alerts and scheduling

```
I need to send farmers unprompted alerts: rain forecast before a planned
spray, critical irrigation stage reached, pest risk from weather
conditions, low water level.

a) Scheduler for a FastAPI app: APScheduler vs Celery vs cron. Which for
   a single-server deployment, and how do I avoid duplicate sends when
   the app restarts?
b) Delivery to rural India: compare SMS (which gateway, cost per message
   in INR), WhatsApp Business API (approval process, template message
   rules, cost), and web push. Include actual current pricing.
c) WhatsApp template message rules — what needs pre-approval, and can I
   send a free-form message outside the 24-hour window?
d) Alert fatigue: how do I decide an alert is worth interrupting someone
   for? Give a concrete prioritisation scheme.
e) Deduplication design so a farmer is not told about the same rain event
   five times.
```

## 6. Conversational voice chatbot with dialogue state

```
My AI agent is stateless — it classifies one message, calls tools,
answers, forgets. I need multi-turn slot-filling conversations in 6
Indian languages, mostly by voice.

Example that currently breaks:
  Assistant: What crop are you growing?
  Farmer: Soybean.        <- no context, intent classifier scores zero

a) Design a dialogue state machine for slot filling (crop, land size,
   sowing date, location) that is DETERMINISTIC — the LLM must not decide
   what to ask next. Give the data model and the transition logic.
b) Voice-specific problems: barge-in (mic hearing the TTS output),
   handling the 3rd failed recognition, and confirming numeric values
   read back to the user. Why is number confirmation critical?
c) Web Speech API limitations for ta-IN, hi-IN, te-IN, kn-IN, ml-IN.
   Which are well supported, which are poor, and what are the fallbacks?
d) Compare browser Web Speech API vs server-side Whisper vs WhatsApp
   voice notes vs IVR telephony for rural India — reach, cost, accuracy
   on 8kHz telephony audio for Indian languages.
e) How to keep spoken answers short. My IPM engine outputs a 5-tier
   treatment plan that takes 90 seconds to read aloud.
```

## 7. Government admin analytics dashboard

```
A government officer selects a state or district and sees aggregate
agricultural intelligence: common pest outbreaks, scheme uptake, crop
distribution, alerts issued.

a) Aggregation query patterns in SQLAlchemy for time-series pest and
   alert data grouped by district, that stay fast without a warehouse.
b) PRIVACY: what must I do so individual farmers are not re-identifiable
   in district aggregates? Cover k-anonymity thresholds and minimum
   group size before showing a statistic.
c) Geographic visualisation of Indian district-level data in React —
   which library, and where do I get accurate district boundary GeoJSON
   for Madhya Pradesh?
d) Outbreak detection: statistical method to flag an unusual spike in
   pest reports for a district versus normal seasonal variation.
e) What would actually be useful to a real agriculture department
   officer? Cite how existing government dashboards (like the Krishi
   portals) present this.
```

## 8. Balcony / home grower experience

```
A distinct user type: urban home growers with pots on a balcony, not
acres. My current crop engine uses economic thresholds that are
meaningless to them (5% fruit damage matters nothing with 6 plants).

a) Container gardening data source: which vegetables suit which container
   size, sunlight hours, and season for Indian urban climates. Any
   structured dataset or must this be curated?
b) How to convert field-scale recommendations to container scale —
   fertiliser per pot instead of per acre, irrigation per plant.
c) Home composting guidance: structured decision data for what a city
   household can compost, ratios, and timelines.
d) Which government schemes actually apply to urban home growers? Most
   require land records. Is there anything real, or should I stop
   claiming this?
e) Weather-based crop suggestion using only a pin code and current
   season, with no soil test available.
```

## 9. Onboarding, geolocation and soil inference

```
At registration I want to capture the farmer's location and land, then
infer soil properties without requiring a lab test.

a) Getting soil properties from coordinates: SoilGrids (ISRIC) API
   coverage and accuracy for India, versus India's own Soil Health Card
   data. Give the API call and the realistic resolution — is a 250m
   raster useful for a 2-acre plot?
b) Land area capture on a phone: walking the boundary with GPS versus
   drawing a polygon on a map. Accuracy of phone GPS for a 2-acre
   boundary, and which JS library for map polygon drawing.
c) Reverse geocoding coordinates to Indian state and district, offline
   or free-tier.
d) How honest should I be about inferred soil values? If I infer pH from
   a 250m raster and the farmer's actual field differs, what confidence
   should I display?
e) Progressive onboarding UX for semi-literate users — how few questions
   can I ask before giving useful output, and what can be deferred?
```

---

## How to use the answers

Anything that comes back claiming a specific number — a subsidy amount, a
pesticide dose, a market price, a yield figure — **treat as unverified until
you find it on a government or university source**. That is exactly the class
of fact this project is architected to never let a model invent, and that
applies to the model you are researching with too.
