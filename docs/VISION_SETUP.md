# Local Plant Disease Detection

Plant Health now runs a **local image classifier**, so it works on a network
that blocks Google. `VISION_PROVIDER=huggingface` is the new default.

**32 vision tests pass**, run against a real image classifier built locally.

---

## Important: I could not verify your model exists

`Kathir56/plant-disease-tamilnadu` does not appear in any search result, and
huggingface.co returns **403** from my sandbox, so **I could not download it,
read its label list, or confirm it is public.**

I therefore did **not** hardcode a class list. The provider reads labels from
the model's own `config.id2label` at load time.

This matters more than it sounds. If I had guessed a 38-class PlantVillage
list and your checkpoint has a different order, index 7 of my list is not index
7 of yours — every prediction maps to the **wrong disease**, confidently, with
no error. Reading labels from the checkpoint makes that impossible.

If the model ID is wrong or private you will get a clear error naming it, not a
silent wrong answer.

---

## Setup

```bash
cd backend
pip install -r requirements-qwen.txt
uvicorn app.main:app --reload --port 8080
```

**I added `torchvision` to that file.** It was missing, and without it
`AutoImageProcessor` raises ImportError, which surfaces as a confusing
"vision model load_failed". You would have hit this.

Watch the log:

```
Vision model loading in background...
Vision ready on cpu (N classes)
```

Check it:

```powershell
Invoke-RestMethod http://localhost:8080/api/health | ConvertTo-Json -Depth 5
```

The `vision` block reports `loaded`, `classes` and the active gates.

---

## If the model fails to load

The error names the cause. Common ones:

| Error | Meaning |
|---|---|
| `load_failed ... 401/404` | Model ID wrong, or the repo is private |
| `no_labels` | Checkpoint publishes `LABEL_0, LABEL_1…` instead of real names |
| `missing_dependency` | `pip install -r requirements-qwen.txt` |

**Verified working alternatives** if that ID doesn't resolve — both are public
PlantVillage fine-tunes with 38 classes:

```
HF_VISION_MODEL=linkanjarad/mobilenet_v2_1.0_224-plant-disease-identification
HF_VISION_MODEL=Diginsa/Plant-Disease-Detection-Project
```

No code change needed — labels are read from whichever model you point at.

The `no_labels` case is a hard refusal on purpose. A checkpoint that only says
`LABEL_12` cannot be grounded in `DISEASE_KB`, and an ungrounded diagnosis is
worse than none.

---

## Three gates against confident wrong answers

Image-classifier softmax is badly calibrated. A photo of a **dog** will still
score 0.95 on some leaf class. So three independent checks must all pass:

| Gate | Default | Catches |
|---|---|---|
| top-1 probability | `≥ 0.60` | weak predictions |
| margin (top1 − top2) | `≥ 0.15` | two classes the model can't separate |
| normalised entropy | `≤ 0.55` | probability spread across many classes |

Gates 2 and 3 catch what a threshold alone misses: a model can be "60%
confident" while spreading the rest across four classes, which means it is
guessing.

Verified live — a random model produced `[0.2, 0.2, 0.2, ...]` and was
correctly rejected:

```
--- strict gates (production defaults) ---
   disease: Uncertain | uncertain: True
```

Tune in `backend/.env`. Raise `HF_VISION_MIN_CONFIDENCE` to reject more.

---

## Grounding: a label is not a diagnosis

Every accepted prediction is matched against `DISEASE_KB`. Labels are
normalised, so all of these reach the same entry:

```
Tomato___Early_blight   Tomato_Early_Blight   TOMATO EARLY BLIGHT
```

If a label has no KB entry, the result is **uncertain**, not a bare label:

```
--- ungrounded label must NOT become a diagnosis ---
   disease: Uncertain | uncertain: True
```

That is deliberate. `Orange___Haunglongbing` might be a correct prediction, but
your KB has no symptoms, causes or treatment for it, so there is nothing
grounded to tell the farmer.

**To add a disease:** put it in `DISEASE_KB` (in `app/ml/knowledge.py`), then
add spellings to `DISEASE_ALIASES` in `hf_vision.py` if needed.

Currently grounded: Early Blight, Late Blight, Leaf Mold, Bacterial Spot,
Powdery Mildew, Leaf Curl, Blast, Downy Mildew, Anthracnose, Mosaic Virus.

---

## Automatic fallback

If the local model fails for a **configuration** reason — not downloaded, no
labels, missing dependency — the request falls back to Gemini automatically,
and vice versa.

A genuine low-confidence result is **not** a failure and does not trigger
fallback. Falling back on "I'm not sure" would just ask a second model to guess.

---

## Severity is not the classifier's job

The classifier reports **what**, never **how bad**. Severity is graded by your
existing deterministic engine from coverage, crop, growth stage and conditions.

A classifier trained on single leaves has no idea what fraction of your field
is affected, and `VisionObservation` has no field in which it could express a
treatment. That separation is structural, not a convention.

---

## Test it

```bash
python -m pytest tests/test_vision_local.py -v    # 32 passed
```

These build a real classifier locally, so they need no download and prove the
full path: processor → model → softmax → gates → grounding → API shape.

---

## Honest limits

- **The real checkpoint has never run through this code.** The pipeline is
  proven with a real transformers image classifier; that specific model is not.
- **PlantVillage-trained models drop sharply on real field photos.** They are
  trained on single leaves against plain backgrounds. Your uploaded photo — a
  leaf held in a hand, soil and other plants behind it — is exactly the
  harder case. The three gates should return "uncertain" rather than guess, but
  expect more uncertains than a benchmark number suggests.
- **Only 10 diseases are grounded.** A 38-class model will predict classes your
  KB cannot support, and those correctly return uncertain. Expanding
  `DISEASE_KB` directly expands what the system can act on.
