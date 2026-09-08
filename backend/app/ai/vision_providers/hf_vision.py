"""Local Hugging Face image-classification vision provider.

Replaces the Gemini vision call with a model that runs entirely on your
machine, so Plant Health works on a network that blocks Google.

DESIGN: LABELS ARE DISCOVERED, NOT HARDCODED
--------------------------------------------
The class list is read from the model's own `config.id2label` at load time.
Nothing here assumes a particular label set, so the same code works with
Kathir56/plant-disease-tamilnadu, a PlantVillage MobileNetV2, or any other
`AutoModelForImageClassification` checkpoint. Point HF_VISION_MODEL at it and
the provider adapts.

This matters because a hardcoded label list that disagrees with the checkpoint
silently maps predictions to the WRONG disease — index 7 of my list is not
index 7 of yours — and the farmer gets a confident, completely wrong diagnosis.

GROUNDING
---------
A raw label is not a diagnosis. Every prediction is matched against DISEASE_KB;
if it cannot be grounded there we return `unknown` rather than a bare label,
because the downstream engine has no symptoms, causes or treatment for a
disease it does not know.

OVERCONFIDENCE
--------------
Softmax probabilities from an image classifier are badly calibrated — a photo
of a dog or a blurry hand will still produce a 0.95 "Tomato Early Blight". So
three independent gates must pass:

    1. top-1 probability      >= HF_VISION_MIN_CONFIDENCE
    2. margin (top1 - top2)   >= HF_VISION_MIN_MARGIN
    3. normalised entropy     <= HF_VISION_MAX_ENTROPY

Gates 2 and 3 catch the "confidently spread across several classes" case that
a threshold on top-1 alone lets through.
"""

import asyncio
import logging
import math
import re
import threading
from typing import Dict, List, Optional, Tuple

from app.ai.vision_providers.base import (BaseVisionProvider, VisionObservation,
                                          VisionProviderError)
from app.core.config import settings
from app.ml.knowledge import DISEASE_KB

log = logging.getLogger("agri.vision.hf")

_model = None
_processor = None
_id2label: Dict[int, str] = {}
_device = "cpu"
_lock = threading.Lock()


# --------------------------------------------------------------------------
# Label normalisation
#
# Checkpoints label classes in wildly different ways:
#   "Tomato___Early_blight"   "tomato early blight"   "Early Blight"
#   "Tomato_Late_blight"      "TOMATO__LATE_BLIGHT"
# Normalising to lowercase words lets one matcher handle all of them.
# --------------------------------------------------------------------------

def _normalise(label: str) -> str:
    text = re.sub(r"[_\-]+", " ", str(label))
    return re.sub(r"\s+", " ", text).strip().lower()


# Extra spellings that normalisation alone will not resolve onto DISEASE_KB.
DISEASE_ALIASES = {
    "early blight": "Early Blight",
    "alternaria": "Early Blight",
    "late blight": "Late Blight",
    "phytophthora": "Late Blight",
    "leaf mold": "Leaf Mold",
    "leaf mould": "Leaf Mold",
    "bacterial spot": "Bacterial Spot",
    "bacterial leaf spot": "Bacterial Spot",
    "powdery mildew": "Powdery Mildew",
    "yellow leaf curl virus": "Leaf Curl",
    "yellow leaf curl": "Leaf Curl",
    "leaf curl": "Leaf Curl",
    "rice blast": "Blast",
    "leaf blast": "Blast",
    "blast": "Blast",
    "downy mildew": "Downy Mildew",
    "anthracnose": "Anthracnose",
    "mosaic virus": "Mosaic Virus",
    "mosaic": "Mosaic Virus",
}

HEALTHY_WORDS = ("healthy", "normal", "no disease", "fresh")


def ground_label(raw_label: str) -> Tuple[Optional[str], Optional[str], str]:
    """Map a model label onto DISEASE_KB.

    Returns (kb_disease_or_None, crop_or_None, kind) where kind is
    "disease" | "healthy" | "unknown".
    """
    norm = _normalise(raw_label)

    if any(w in norm for w in HEALTHY_WORDS):
        parts = norm.split()
        return None, (parts[0] if parts and parts[0] not in HEALTHY_WORDS else None), "healthy"

    for kb_name in DISEASE_KB:
        if _normalise(kb_name) == norm:
            return kb_name, None, "disease"

    # Longest alias wins, so "yellow leaf curl" beats "leaf curl".
    for alias in sorted(DISEASE_ALIASES, key=len, reverse=True):
        if alias in norm:
            kb_name = DISEASE_ALIASES[alias]
            crop = norm.split(alias)[0].strip() or None
            return kb_name, crop, "disease"

    return None, None, "unknown"


def _entropy(probs: List[float]) -> float:
    """Shannon entropy normalised to 0-1. High means the model is spreading
    its bet across many classes, i.e. it does not really know."""
    n = len(probs)
    if n <= 1:
        return 0.0
    h = -sum(p * math.log(p + 1e-12) for p in probs)
    return h / math.log(n)


# --------------------------------------------------------------------------
# Model loading
# --------------------------------------------------------------------------

def _load():
    global _model, _processor, _id2label, _device

    if _model is not None:
        return _model, _processor

    with _lock:
        if _model is not None:
            return _model, _processor

        model_id = (settings.HF_VISION_MODEL or "").strip()
        if not model_id:
            raise VisionProviderError(
                "not_configured",
                "HF_VISION_MODEL is empty. Set it in backend/.env, for example "
                "HF_VISION_MODEL=Kathir56/plant-disease-tamilnadu",
                provider="huggingface")

        try:
            import torch
            from transformers import (AutoImageProcessor,
                                      AutoModelForImageClassification)
        except ImportError as exc:
            raise VisionProviderError(
                "missing_dependency",
                "torch/transformers are not installed. Run: "
                "pip install -r requirements-qwen.txt",
                provider="huggingface") from exc

        log.info("Loading vision model %s", model_id)
        try:
            processor = AutoImageProcessor.from_pretrained(model_id)
            model = AutoModelForImageClassification.from_pretrained(model_id)
            model.eval()
        except Exception as exc:
            raise VisionProviderError(
                "load_failed",
                f"Could not load vision model '{model_id}': "
                f"{type(exc).__name__}: {exc}. Check that the model ID exists "
                f"on Hugging Face and is public, that there is disk space, and "
                f"that huggingface.co is reachable from this machine.",
                provider="huggingface") from exc

        # Labels come from the checkpoint itself — never assumed.
        raw = getattr(model.config, "id2label", None) or {}
        _id2label = {int(k): v for k, v in raw.items()}

        if not _id2label or all(str(v).upper().startswith("LABEL_")
                                for v in _id2label.values()):
            raise VisionProviderError(
                "no_labels",
                f"Model '{model_id}' does not publish usable class names "
                f"(id2label is empty or generic LABEL_n). Without real labels a "
                f"prediction cannot be grounded in the disease knowledge base, "
                f"and an ungrounded diagnosis is worse than none.",
                provider="huggingface")

        _device = "cuda" if torch.cuda.is_available() else "cpu"
        model.to(_device)

        _model, _processor = model, processor
        log.info("Vision model ready on %s with %d classes", _device, len(_id2label))
        return _model, _processor


def warmup() -> dict:
    if (settings.VISION_PROVIDER or "").lower() not in ("huggingface", "hf", "local"):
        return {"loaded": False, "reason": "VISION_PROVIDER is not 'huggingface'"}
    try:
        _load()
        return {"loaded": True, "device": _device,
                "model": settings.HF_VISION_MODEL, "classes": len(_id2label)}
    except VisionProviderError as exc:
        log.warning("Vision warmup failed (%s): %s", exc.kind, exc)
        return {"loaded": False, "kind": exc.kind, "reason": str(exc)}


def is_loaded() -> bool:
    return _model is not None


def unload() -> None:
    global _model, _processor, _id2label
    _model = _processor = None
    _id2label = {}


def labels() -> List[str]:
    return [_id2label[i] for i in sorted(_id2label)]


# --------------------------------------------------------------------------
# Inference
# --------------------------------------------------------------------------

def classify_sync(image_path: str, top_k: int = 5):
    """Blocking classification. Always called from a thread executor.

    Returns (ranked_top_k, all_probabilities).
    """
    import torch
    from PIL import Image

    model, processor = _load()

    try:
        image = Image.open(image_path).convert("RGB")
    except Exception as exc:
        raise VisionProviderError(
            "bad_image", f"Could not read the image: {type(exc).__name__}",
            provider="huggingface") from exc

    inputs = processor(images=image, return_tensors="pt").to(_device)

    with torch.no_grad():
        logits = model(**inputs).logits

    probs = torch.softmax(logits, dim=-1)[0]
    k = min(top_k, probs.shape[-1])
    top = torch.topk(probs, k)

    ranked = [(_id2label.get(int(i), f"LABEL_{int(i)}"), float(p))
              for p, i in zip(top.values, top.indices)]
    return ranked, [float(x) for x in probs]


class HuggingFaceVisionProvider(BaseVisionProvider):
    name = "huggingface"

    async def analyze(self, image_path: str, crop: str = "") -> VisionObservation:
        if not is_loaded():
            # Load lazily rather than refusing: unlike the 3 GB LLM, an image
            # classifier is small (tens of MB) and loads in seconds.
            await asyncio.to_thread(_load)

        try:
            ranked, all_probs = await asyncio.to_thread(classify_sync, image_path)
        except VisionProviderError:
            raise
        except Exception as exc:
            raise VisionProviderError(
                "inference_failed",
                f"Vision inference failed: {type(exc).__name__}: {exc}",
                provider=self.name) from exc

        top_label, top_prob = ranked[0]
        second_prob = ranked[1][1] if len(ranked) > 1 else 0.0
        margin = top_prob - second_prob
        ent = _entropy(all_probs)

        kb_name, detected_crop, kind = ground_label(top_label)

        evidence = (f"Model's best match: {top_label} ({top_prob:.0%}). "
                    f"Runner-up: {ranked[1][0]} ({second_prob:.0%})."
                    if len(ranked) > 1 else
                    f"Model's best match: {top_label} ({top_prob:.0%}).")

        # --- three independent confidence gates ---
        reasons = []
        if top_prob < settings.HF_VISION_MIN_CONFIDENCE:
            reasons.append(f"top confidence {top_prob:.0%} is below the "
                           f"{settings.HF_VISION_MIN_CONFIDENCE:.0%} minimum")
        if margin < settings.HF_VISION_MIN_MARGIN:
            reasons.append(f"the top two classes are only {margin:.0%} apart, "
                           f"so the model cannot separate them")
        if ent > settings.HF_VISION_MAX_ENTROPY:
            reasons.append("the model spread its prediction across many classes, "
                           "which usually means the image is unclear or not a "
                           "plant leaf")

        if reasons:
            return VisionObservation(
                crop=crop or detected_crop or "", problem="", kind="unknown",
                confidence=top_prob, symptoms=[], severity="unknown",
                visible_evidence=evidence + " Rejected because " +
                                 "; ".join(reasons) + ".",
                provider=self.name)

        if kind == "healthy":
            return VisionObservation(
                crop=crop or detected_crop or "", problem="Healthy",
                kind="healthy", confidence=top_prob, symptoms=[],
                severity="none", visible_evidence=evidence, provider=self.name)

        if kb_name is None:
            return VisionObservation(
                crop=crop or detected_crop or "", problem="", kind="unknown",
                confidence=top_prob, symptoms=[], severity="unknown",
                visible_evidence=(
                    f"{evidence} The label '{top_label}' is not in the disease "
                    f"knowledge base, so no grounded advice can be given for it. "
                    f"Add it to DISEASE_KB or DISEASE_ALIASES."),
                provider=self.name)

        entry = DISEASE_KB[kb_name]
        symptoms = entry.get("symptoms", "")
        if isinstance(symptoms, str):
            symptoms = [s.strip() for s in symptoms.split(",") if s.strip()][:5]

        return VisionObservation(
            crop=crop or detected_crop or "",
            problem=kb_name,
            kind="disease",
            confidence=top_prob,
            symptoms=symptoms,
            # A classifier reports WHAT, not HOW BAD. Severity is graded by the
            # deterministic engine from coverage, crop and conditions.
            severity="unknown",
            visible_evidence=evidence,
            provider=self.name)

    def describe(self) -> dict:
        return {
            "provider": self.name,
            "model": settings.HF_VISION_MODEL or "(not configured)",
            "loaded": is_loaded(),
            "device": _device if is_loaded() else "not loaded",
            "classes": len(_id2label) if is_loaded() else 0,
            "min_confidence": settings.HF_VISION_MIN_CONFIDENCE,
            "min_margin": settings.HF_VISION_MIN_MARGIN,
            "max_entropy": settings.HF_VISION_MAX_ENTROPY,
            "requires": "torch + transformers, no API key, works offline",
        }
