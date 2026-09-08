"""Local vision provider tests.

The real checkpoint cannot be downloaded here (huggingface.co is blocked), so
these build a genuine tiny image classifier locally with PlantVillage-style
labels and run the identical code path: AutoImageProcessor -> model ->
softmax -> confidence gates -> DISEASE_KB grounding -> API response shape.

If these pass, a failure with the real checkpoint is a download/label problem,
not a wiring problem.
"""

import pytest

from app.ai.vision_providers import VisionProviderError, reset_cache
from app.ai.vision_providers import hf_vision
from app.core.config import settings

try:
    import torch  # noqa: F401
    from PIL import Image  # noqa: F401
    from transformers import AutoModelForImageClassification  # noqa: F401
    HAS_TORCH = True
except Exception:
    HAS_TORCH = False

needs_torch = pytest.mark.skipif(
    not HAS_TORCH, reason="torch/transformers not installed")


@pytest.fixture(autouse=True)
def _clean():
    reset_cache()
    hf_vision.unload()
    yield
    reset_cache()
    hf_vision.unload()


# ------------------------------------------------- label grounding (no torch)


@pytest.mark.parametrize("raw,expected", [
    ("Tomato___Early_blight", "Early Blight"),
    ("Tomato_Late_blight", "Late Blight"),
    ("TOMATO__LATE_BLIGHT", "Late Blight"),
    ("Potato___Late_blight", "Late Blight"),
    ("tomato leaf mold", "Leaf Mold"),
    ("Tomato___Leaf_Mould", "Leaf Mold"),
    ("Pepper__bell___Bacterial_spot", "Bacterial Spot"),
    ("Grape___Powdery_mildew", "Powdery Mildew"),
    ("Rice___Leaf_Blast", "Blast"),
    ("Tomato___Tomato_mosaic_virus", "Mosaic Virus"),
    ("Chilli___Anthracnose", "Anthracnose"),
])
def test_label_grounding_maps_onto_kb(raw, expected):
    """Checkpoints label classes inconsistently; all must reach DISEASE_KB."""
    kb_name, _crop, kind = hf_vision.ground_label(raw)
    assert kind == "disease"
    assert kb_name == expected


def test_longest_alias_wins():
    """'yellow leaf curl virus' must not be shortened to 'leaf curl' wrongly."""
    kb_name, _, kind = hf_vision.ground_label("Tomato___Yellow_Leaf_Curl_Virus")
    assert kb_name == "Leaf Curl" and kind == "disease"


@pytest.mark.parametrize("raw", [
    "Tomato___healthy", "Apple___healthy", "healthy", "Corn_(maize)___healthy",
])
def test_healthy_labels_detected(raw):
    kb_name, _crop, kind = hf_vision.ground_label(raw)
    assert kind == "healthy"
    assert kb_name is None


@pytest.mark.parametrize("raw", [
    "Orange___Haunglongbing", "Squash___Some_Unknown_Thing", "LABEL_7", "",
])
def test_ungrounded_labels_return_unknown(raw):
    """A label with no KB entry must NOT become a diagnosis."""
    kb_name, _crop, kind = hf_vision.ground_label(raw)
    assert kind == "unknown"
    assert kb_name is None


def test_crop_extracted_from_label():
    _kb, crop, _kind = hf_vision.ground_label("Tomato___Early_blight")
    assert crop == "tomato"


# ------------------------------------------------- entropy gate


def test_entropy_low_when_confident():
    assert hf_vision._entropy([0.97, 0.01, 0.01, 0.01]) < 0.2


def test_entropy_high_when_uniform():
    assert hf_vision._entropy([0.25, 0.25, 0.25, 0.25]) > 0.99


# ------------------------------------------------- configuration


@pytest.mark.asyncio
async def test_missing_model_id_refuses(monkeypatch):
    monkeypatch.setattr(settings, "HF_VISION_MODEL", "")
    with pytest.raises(VisionProviderError) as exc:
        await hf_vision.HuggingFaceVisionProvider().analyze("/tmp/x.jpg")
    assert exc.value.kind == "not_configured"


# ------------------------------------------------- real model path


@pytest.fixture(scope="module")
def tiny_vision_model(tmp_path_factory):
    """Build a real image classifier with PlantVillage-style labels locally."""
    if not HAS_TORCH:
        pytest.skip("torch not installed")

    import torch
    from transformers import (AutoImageProcessor, AutoModelForImageClassification,
                              MobileNetV2Config)

    out = tmp_path_factory.mktemp("tiny-vision")

    labels = ["Tomato___Early_blight", "Tomato___Late_blight",
              "Tomato___Leaf_Mold", "Tomato___healthy",
              "Orange___Haunglongbing"]
    id2label = {i: l for i, l in enumerate(labels)}

    torch.manual_seed(20260827)
    cfg = MobileNetV2Config(
        num_labels=len(labels), image_size=64, depth_multiplier=0.35,
        id2label=id2label, label2id={l: i for i, l in id2label.items()})
    model = AutoModelForImageClassification.from_config(cfg)
    model.save_pretrained(out)

    proc = AutoImageProcessor.from_pretrained(
        "google/mobilenet_v2_1.0_224") if False else None
    # Build the processor from config rather than downloading one.
    from transformers import MobileNetV2ImageProcessor
    MobileNetV2ImageProcessor(size={"shortest_edge": 64},
                              crop_size={"height": 64, "width": 64}
                              ).save_pretrained(out)

    return str(out), labels


@pytest.fixture
def leaf_image(tmp_path):
    from PIL import Image
    p = tmp_path / "leaf.jpg"
    Image.new("RGB", (200, 200), (40, 120, 40)).save(p)
    return str(p)


@needs_torch
def test_labels_are_read_from_the_checkpoint(monkeypatch, tiny_vision_model):
    """The class list must come from the model, never from hardcoded guesses."""
    path, labels = tiny_vision_model
    monkeypatch.setattr(settings, "HF_VISION_MODEL", path)
    hf_vision.unload()

    hf_vision._load()
    assert hf_vision.labels() == labels
    assert hf_vision.is_loaded()


@needs_torch
def test_classify_returns_ranked_probabilities(monkeypatch, tiny_vision_model,
                                               leaf_image):
    path, _ = tiny_vision_model
    monkeypatch.setattr(settings, "HF_VISION_MODEL", path)
    hf_vision.unload()

    ranked, all_probs = hf_vision.classify_sync(leaf_image)

    assert len(ranked) > 1
    assert ranked[0][1] >= ranked[1][1], "results must be sorted"
    assert abs(sum(all_probs) - 1.0) < 1e-4, "softmax must sum to 1"


@needs_torch
@pytest.mark.asyncio
async def test_low_confidence_is_rejected_not_diagnosed(monkeypatch,
                                                        tiny_vision_model,
                                                        leaf_image):
    """A random model is not confident; it must return unknown, not a disease."""
    path, _ = tiny_vision_model
    monkeypatch.setattr(settings, "HF_VISION_MODEL", path)
    monkeypatch.setattr(settings, "HF_VISION_MIN_CONFIDENCE", 0.95)
    hf_vision.unload()

    obs = await hf_vision.HuggingFaceVisionProvider().analyze(leaf_image, "tomato")

    assert obs.kind == "unknown"
    assert obs.uncertain is True
    assert "Rejected because" in obs.visible_evidence


@needs_torch
@pytest.mark.asyncio
async def test_entropy_gate_rejects_spread_predictions(monkeypatch,
                                                       tiny_vision_model,
                                                       leaf_image):
    """Catches the 'confident but spread across classes' case."""
    path, _ = tiny_vision_model
    monkeypatch.setattr(settings, "HF_VISION_MODEL", path)
    monkeypatch.setattr(settings, "HF_VISION_MIN_CONFIDENCE", 0.0)
    monkeypatch.setattr(settings, "HF_VISION_MIN_MARGIN", 0.0)
    monkeypatch.setattr(settings, "HF_VISION_MAX_ENTROPY", 0.01)
    hf_vision.unload()

    obs = await hf_vision.HuggingFaceVisionProvider().analyze(leaf_image)
    assert obs.kind == "unknown"
    assert "spread" in obs.visible_evidence


@needs_torch
@pytest.mark.asyncio
async def test_accepted_prediction_is_grounded_in_kb(monkeypatch,
                                                     tiny_vision_model,
                                                     leaf_image):
    """With gates open, an accepted label must carry real KB symptoms."""
    from app.ml.knowledge import DISEASE_KB

    path, _ = tiny_vision_model
    monkeypatch.setattr(settings, "HF_VISION_MODEL", path)
    monkeypatch.setattr(settings, "HF_VISION_MIN_CONFIDENCE", 0.0)
    monkeypatch.setattr(settings, "HF_VISION_MIN_MARGIN", 0.0)
    monkeypatch.setattr(settings, "HF_VISION_MAX_ENTROPY", 1.0)
    hf_vision.unload()

    obs = await hf_vision.HuggingFaceVisionProvider().analyze(leaf_image, "tomato")

    # Whatever it predicted, the outcome must be grounded or honestly unknown.
    assert obs.kind in ("disease", "healthy", "unknown")
    if obs.kind == "disease":
        assert obs.problem in DISEASE_KB
        assert obs.symptoms, "a grounded disease must carry KB symptoms"
    if obs.kind == "unknown":
        assert not obs.problem


@needs_torch
@pytest.mark.asyncio
async def test_ungrounded_label_never_becomes_a_diagnosis(monkeypatch,
                                                          tiny_vision_model,
                                                          leaf_image):
    """'Orange___Haunglongbing' has no KB entry — it must not be diagnosed."""
    path, _ = tiny_vision_model
    monkeypatch.setattr(settings, "HF_VISION_MODEL", path)
    monkeypatch.setattr(settings, "HF_VISION_MIN_CONFIDENCE", 0.0)
    monkeypatch.setattr(settings, "HF_VISION_MIN_MARGIN", 0.0)
    monkeypatch.setattr(settings, "HF_VISION_MAX_ENTROPY", 1.0)
    hf_vision.unload()

    # Force the ungrounded class to win.
    monkeypatch.setattr(hf_vision, "classify_sync",
                        lambda p, top_k=5: ([("Orange___Haunglongbing", 0.99),
                                             ("Tomato___healthy", 0.01)],
                                            [0.99, 0.01]))
    hf_vision._model = object()   # skip loading; classify is stubbed

    obs = await hf_vision.HuggingFaceVisionProvider().analyze(leaf_image)
    assert obs.kind == "unknown"
    assert "not in the disease knowledge base" in obs.visible_evidence


@needs_torch
@pytest.mark.asyncio
async def test_full_api_shape_via_analyze_image(monkeypatch, tiny_vision_model,
                                                leaf_image):
    """End to end through vision.analyze_image, the function the API calls."""
    from app.ml import vision

    path, _ = tiny_vision_model
    monkeypatch.setattr(settings, "VISION_PROVIDER", "huggingface")
    monkeypatch.setattr(settings, "HF_VISION_MODEL", path)
    monkeypatch.setattr(settings, "HF_VISION_MIN_CONFIDENCE", 0.0)
    monkeypatch.setattr(settings, "HF_VISION_MIN_MARGIN", 0.0)
    monkeypatch.setattr(settings, "HF_VISION_MAX_ENTROPY", 1.0)
    hf_vision.unload()
    reset_cache()

    result = await vision.analyze_image(leaf_image, "tomato")

    # Existing frontend contract must be preserved.
    for key in ("disease", "confidence", "uncertain"):
        assert key in result
    assert isinstance(result["confidence"], float)


@needs_torch
@pytest.mark.asyncio
async def test_bad_model_id_falls_back_without_crashing(monkeypatch, leaf_image):
    """A missing local model must not break Plant Health — it degrades."""
    from app.ml import vision

    monkeypatch.setattr(settings, "VISION_PROVIDER", "huggingface")
    monkeypatch.setattr(settings, "HF_VISION_MODEL", "/nonexistent/model")
    monkeypatch.setattr(settings, "GEMINI_API_KEY", "")
    hf_vision.unload()
    reset_cache()

    result = await vision.analyze_image(leaf_image, "tomato")

    assert result["uncertain"] is True
    assert "unavailable" in result["recommendation"].lower()


@needs_torch
@pytest.mark.asyncio
async def test_fallback_can_be_disabled_for_full_offline(monkeypatch, leaf_image):
    """With VISION_ALLOW_FALLBACK=false, no request may reach Gemini."""
    from app.ml import vision

    monkeypatch.setattr(settings, "VISION_PROVIDER", "huggingface")
    monkeypatch.setattr(settings, "HF_VISION_MODEL", "/nonexistent/model")
    monkeypatch.setattr(settings, "VISION_ALLOW_FALLBACK", False)
    hf_vision.unload()
    reset_cache()

    called = {"gemini": False}

    async def spy(*a, **kw):
        called["gemini"] = True
        raise AssertionError("Gemini must not be called when fallback is off")

    from app.ai.vision_providers import gemini_vision
    monkeypatch.setattr(gemini_vision.GeminiVisionProvider, "analyze", spy)

    result = await vision.analyze_image(leaf_image, "tomato")

    assert called["gemini"] is False
    assert result["uncertain"] is True
    assert "huggingface" in result["recommendation"]
