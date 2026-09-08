# Gemini Key, Lost Data, and How the Models Connect

Three straight answers.

---

## 1. Why did the data keep disappearing?

**It didn't. It's still in your old folder.**

Your database is a single file: `backend/agri.db`. It holds your farm profile,
diagnoses, sensor readings and chat history.

Every version extracts to a **different folder**:

```
Documents\sustainable-agriculture-gemini\backend\agri.db   <- data from that install
Documents\sustainable-agriculture-v4\backend\agri.db       <- separate, unrelated
Documents\sustainable-agriculture-v6\backend\agri.db       <- separate again
```

Extracting a new zip never touches the old folder. You were looking at a brand
new database and reasonably concluded everything was erased.

### Two mistakes of mine that made this much worse

**I was shipping my own test database.** The `agri.db` inside v4/v5/v6 was a
snapshot from *my sandbox*, dated Aug 25 — 4 fake diagnoses, 27 fake sensor
readings, 2 stray chat messages. So you didn't just get an empty database, you
got **my junk data**, which makes it look even more like yours vanished.
It is now excluded from the zip.

**The database path was relative.** `DATABASE_URL = "sqlite:///./agri.db"` —
the `./` resolves against whatever directory you launched uvicorn from. Start
from `backend\` and you get `backend\agri.db`. Start from the project root and
you silently get a **different, empty** database in the root folder. Same
symptom, different cause. It is now anchored to the backend directory
regardless of where you start the server.

### Get your data back

```powershell
cd backend
python scripts\migrate_data.py --list

python scripts\migrate_data.py "C:\Users\SHARUMITHA\Documents\sustainable-agriculture-gemini\sustainable-agriculture\backend\agri.db"
```

It shows both databases, backs up the current one, then copies the old one in.
Demo users and schemes are re-seeded on startup, so nothing is lost either way.

**From now on:** run `python scripts\migrate_data.py --backup` before you
upgrade, and copy your `agri.db` into each new folder.

---

## 2. Where is the Gemini key actually used?

With your current config — `LLM_PROVIDER=qwen`, `VISION_PROVIDER=huggingface` —
here is every place it could be touched:

| Path | Uses Gemini now? |
|---|---|
| Chat, agent, NLP, translation | **No** — routed to local Qwen |
| Plant disease vision | **No** — routed to local classifier |
| Vision fallback if the local model fails to load | **Yes** |
| `/api/test-gemini`, `/api/diagnostics/gemini` | Only if you call them |

So **one** live path remains: if the local vision model cannot load, the
request falls back to Gemini rather than failing outright.

### To remove Gemini completely

In `backend\.env`:

```
VISION_ALLOW_FALLBACK=false
```

Now no request can leave your machine, and you can delete `GEMINI_API_KEY`
entirely. There is a test asserting this — with fallback off, Gemini is never
called even when the local model is broken.

### Should you keep the key?

Keep it if you might demo somewhere with working internet, since Gemini is
much faster than CPU Qwen. Delete it if you want a hard guarantee that nothing
leaves the machine. **Either way, rotate the key that was committed in your
uploaded zip** — treat it as compromised.

---

## 3. How the models connect

**Two separate models doing two different jobs.** They never talk to each
other.

```
                    ┌─────────────────────────────┐
   Farmer types  →  │  LLM: Qwen2.5-1.5B-Instruct │  text in, text out
   or speaks        │  ~3 GB · text only          │
                    └─────────────────────────────┘
                                  ↑
                    facts from deterministic engines
                                  ↑
                    ┌─────────────────────────────┐
   Farmer uploads → │  VISION: image classifier   │  image in, LABEL out
   a leaf photo     │  ~10-50 MB                  │
                    └─────────────────────────────┘
```

### Why two models and not one

Qwen2.5-1.5B-Instruct is **text-only**. It has no image encoder — you cannot
show it a photo, no matter how you prompt it. Image work needs a separate
vision model. That is not a design choice, it is what the architecture allows.

### What each one is allowed to decide

The vision model outputs **a label and a probability**. Nothing else. Not
severity, not treatment, not a dose. `VisionObservation` has no field in which
a treatment could even be expressed.

That label then goes through:

```
label → confidence gates → DISEASE_KB grounding → severity engine
      → IPM ladder → treatment ranking → Qwen phrases the result
```

Every number the farmer acts on is computed by deterministic Python before
Qwen sees anything. Qwen writes the sentences; it cannot change the answer.

### How they're wired

Both sit behind a factory, selected by one line of config:

```
backend/app/ai/providers/          LLM       (qwen | gemini)
backend/app/ai/vision_providers/   vision    (huggingface | gemini)
```

Swapping either is a `.env` change and a restart. No code changes anywhere,
because `llm.chat()` and `vision.analyze_image()` are the only entry points
the rest of the app uses.

### Adding a third model later

A pest classifier, say. Write a provider class implementing `analyze()`,
register it in the vision factory, add a config value. Roughly 50 lines. The
IPM engine, the API and the frontend need no changes.

---

## What to do now, in order

1. **Recover your data** — `python scripts\migrate_data.py --list`, then point
   it at your old `agri.db`.
2. **Rotate the Gemini API key** that was in the uploaded zip.
3. **Decide on fallback** — set `VISION_ALLOW_FALLBACK=false` if you want zero
   external calls, or leave it on as a safety net.
4. **Install the local models** — `pip install -r requirements-qwen.txt`.
   Watch the log for `Qwen ready` and `Vision ready`.
5. **Back up before each upgrade** — `python scripts\migrate_data.py --backup`.
