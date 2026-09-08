# Changes in this build

**Tests: 51 passing** (33 existing, unchanged + 18 new). **Frontend builds clean.**

---

## ⚠️ Do this first: rotate your API key

`backend/.env` with a live `GEMINI_API_KEY` was committed inside the zip you
uploaded. Treat that key as compromised:

1. Delete it at https://aistudio.google.com/apikey and create a new one.
2. Put the new key in `backend/.env` (already gitignored).
3. `backend/.env.example` is now committed instead — same variables, no secrets.

Your `WEATHER_API_KEY` was in there too.

---

## Two things I got wrong before checking, and what's actually true

**`gemini-3.7-flash` is a real model.** I assumed it was hallucinated (it looks
like a Claude/Gemini mashup). I searched: it shipped **13 August 2026**, stable
ID `gemini-3.7-flash`, 1M context. My training data ends May 2026, so I hadn't
seen it. **Your model name was correct — don't change it.**

**Your `AQ.` API key format is also fine.** 53 chars starting `AQ.Ab8` looked
wrong to me, since Google keys were `AIza...` for a decade. Google began issuing
`AQ.` keys around June 2026. They work on the native `generativelanguage`
endpoint, which is what your code calls. Breakage only happens in
OpenAI-compatible wrappers that regex-validate the `AIza` prefix.

---

## Your actual bug

`app/ai/llm.py` wrapped the entire call in one `except Exception` and returned a
canned sentence. A bad key, a rate limit, an overload, and a safety block **all
produced identical output**. There was no way to tell what was wrong, so it just
looked like "Gemini is not working."

Underneath that, the likely real failure is **HTTP 503 "model is overloaded"** —
Gemini's literal *server busy* response — with **no retry**. One transient blip
became a hard failure every time.

### What I changed in `llm.py`

| Fix | Effect |
|---|---|
| Classify every failure (`auth`/`rate_limit`/`overloaded`/`not_found`/`blocked`/`timeout`) | You now see *why*, not a generic sentence |
| Retry 429/503 with exponential backoff + jitter, 3 attempts | Fixes "server busy" |
| Don't retry 401/404 | A bad key never fixes itself; fail fast |
| Module-level pooled `AsyncClient` | Removes a TLS handshake (~100–300 ms) per call |
| `thinkingConfig.thinkingBudget = 0` | **Biggest speed win — see below** |
| `maxOutputTokens` cap | Bounded latency and cost |
| Key moved to `x-goog-api-key` header | Keys no longer land in proxy logs |

### The speed fix

`gemini-3.7-flash` is a **reasoning model with an explicit thinking mode**. Left
uncapped it spends tokens thinking before emitting anything — slow, and thinking
tokens bill at the *output* rate. Your app doesn't need it: the agronomic facts
come from your own deterministic IPM/severity engines, and the model only
phrases them. So `GEMINI_THINKING_BUDGET=0` in `.env`. Raise to `512` if you
later want reasoning on complex chains.

### On dotenv

`python-dotenv` was **already installed and already in use** — `config.py` calls
`load_dotenv()` at line 8. It loads variables from a file into the process
environment and has **no effect on latency or rate limits**. It cannot fix
"server busy." (If you meant `venv`, that's isolation, also not speed.) The
speed comes from the four items above.

### See the real error

```bash
cd backend
python scripts/check_gemini.py
```

Checks key → model access → live generation → function calling, and prints the
actual upstream error plus a latency warning if thinking is slowing you down.
Also exposed at `GET /api/diagnostics/gemini` and `/api/diagnostics/models`
(admin only).

---

## Voice on every page

You asked for browser-side speech available everywhere, not just AI Advisor.

**New files:**
- `hooks/useSpeech.ts` — Web Speech API, all 6 languages, interim results, auto-restart
- `contexts/LanguageContext.tsx` — language that works **before login**
- `components/VoiceInput.tsx` — `VoiceMic`, `VoiceField`, `LanguagePicker`, `SpeakButton`

**Why browser-side, not Whisper upload:** the old flow recorded audio → uploaded
→ waited for server Whisper. That can't work on Login (no auth token), costs
seconds of round-trip on a rural connection, and needs the backend up. The Web
Speech API runs locally, streams as you speak, and is free.

**I also fixed a real bug in the old `VoiceButton`:**
```js
setTimeout(() => transcript && onResult(transcript), 300)
```
`transcript` was captured from the closure at click time — empty on the Whisper
path, since transcription finishes *after* stop. The parent often never received
the result. The new hook keeps callbacks in refs.

**Accuracy notes:** full BCP-47 tags (`ta-IN`, not `ta`) — bare codes are the
most common cause of poor Indian-language recognition. `continuous` + manual
restart in `onend`, because Chrome silently stops after a few seconds of silence.

**Wired into Login** as a working reference: language picker + voice email
field. Password is deliberately **not** voice-enabled — dictating a password
aloud is a security problem, not a convenience.

To add to any other page:
```tsx
import { VoiceField } from '../components/VoiceInput'
<VoiceField label="Crop" value={crop} onChange={setCrop} />
```

Browser support: Chrome/Edge/Android yes, Firefox no. `supported` is `false`
there and the field degrades to normal typing.

---

## What I did NOT build

You listed roughly six weeks of work. I fixed the blocker and the voice layer
rather than shipping six untested stubs.

**Not started:**

1. **Manure & Offers ROI calculator.** The formula is straightforward, but it
   needs a `vendors`/`offers` table, distance calculation, and yield-boost
   coefficients per crop. Those coefficients are agronomic claims — I'd want
   them sourced, not invented, since the output is a financial promise.

2. **Vendor role + portals.** `models.py` has `role = farmer | balcony | admin`.
   A vendor role needs the enum, auth guards, and a portal. The admin scheme
   editor is a straightforward CRUD form over the existing `Scheme` table.

3. **Role-specific onboarding.** Right now all three roles get the same
   dashboard. Farmer needs land size/crop/soil/irrigation; balcony needs
   container count, sunlight hours, what they want to grow. Your `Farm` model
   *already has* the balcony fields (`sunlight`, `growing_medium`,
   `watering_method`) — they're just not collected or used.

4. **Market prices.** Deliberately skipped: this needs a real data source
   (Agmarknet / data.gov.in). Hardcoding prices would put fake numbers in front
   of someone deciding when to sell.

5. **Full Gemini function-calling agent.** `chat_with_tools()` is built and
   tested, but `agent.py` still routes by keyword intent. Migrating it is a
   contained next step now that the transport works.

**Suggested order:** confirm Gemini works via `check_gemini.py` → role-specific
onboarding (unlocks everything personalised) → admin scheme editor → vendor role
+ ROI → market prices once you have a data source.

---

## Run it

```bash
cd backend
pip install -r requirements.txt
python scripts/check_gemini.py     # verify Gemini FIRST
uvicorn app.main:app --reload

cd frontend
npm install && npm run dev
```

Login page now has a language picker; pick தமிழ் and the mic will listen in Tamil.
