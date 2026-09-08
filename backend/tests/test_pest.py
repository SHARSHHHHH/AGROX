"""Tests for the pest detection -> severity -> IPM -> sustainable treatment
pipeline, plus NLP intent and API wiring.

Gemini vision requires an API key in production; the
image-analysis tests monkeypatch the vision layer to exercise the deterministic
pipeline end to end without a model. The severity/IPM/NLP tests are fully
deterministic and need no network.
"""
import io
import pytest
from PIL import Image

from app.services.pest_severity import assess_severity
from app.services.ipm import build_ipm, rank_sustainable_treatment, SUSTAINABLE_ORDER
from app.ml.pest_knowledge import PEST_KB, KNOWN_PESTS
from app.ai import nlp


# ---------------- Knowledge base integrity ----------------

def test_pest_kb_entries_have_required_fields():
    required = ["scientific_name", "affected_crops", "symptoms", "visual_indicators",
                "common_causes", "favorable_conditions", "prevention",
                "cultural_control", "mechanical_control", "biological_control",
                "chemical_control", "severity_threshold"]
    for name, entry in PEST_KB.items():
        for field in required:
            assert field in entry, f"{name} missing {field}"


def test_pest_kb_chemical_has_no_dose_numbers():
    # Chemical guidance must stay label-deferring: no obvious ml/g dose tokens.
    banned = ["ml/l", "ml per", "grams per", "g/l", "mg/l", " ml ", " gram"]
    for name, entry in PEST_KB.items():
        chem = entry["chemical_control"].lower()
        assert not any(b in chem for b in banned), f"{name} chemical text looks dosed"


# ---------------- Severity ----------------

def test_severity_low():
    s = assess_severity("Aphids", 0.9, "low", None, "", {"temperature": 22, "humidity": 40})
    assert s["level"] == "LOW"


def test_severity_moderate():
    s = assess_severity("Aphids", 0.9, "moderate", None, "", None)
    assert s["level"] == "MODERATE"


def test_severity_high():
    s = assess_severity("Aphids", 0.9, "high", 60, "flowering",
                        {"temperature": 31, "humidity": 72})
    assert s["level"] == "HIGH"
    assert s["priority_note"]  # warm+humid escalation present


def test_severity_unknown_low_confidence():
    s = assess_severity("Aphids", 0.3, "high", None, "", None)
    assert s["level"] == "UNKNOWN"


def test_severity_unknown_no_signal():
    s = assess_severity("Thrips", 0.8, "unknown", None, "", None)
    assert s["level"] == "UNKNOWN"


def test_severity_is_always_estimate():
    s = assess_severity("Aphids", 0.9, "moderate", None, "", None)
    assert s["is_estimate"] is True


def test_severity_pct_overrides_label():
    # A high % should push toward HIGH even if label said low.
    s = assess_severity("Caterpillars", 0.9, "low", 40, "fruiting",
                        {"temperature": 30, "humidity": 70})
    assert s["level"] == "HIGH"


# ---------------- IPM ----------------

def test_ipm_low_has_no_chemical():
    ipm = build_ipm("Aphids", "LOW", None)
    assert ipm["chemical_status"] == "not_recommended"
    assert ipm["chemical"] == []
    assert ipm["monitoring"]           # monitoring present
    assert ipm["cultural"]             # cultural present


def test_ipm_moderate_gates_chemical():
    ipm = build_ipm("Aphids", "MODERATE", None)
    assert ipm["chemical_status"] == "threshold_gated"
    assert ipm["biological"]           # biological offered before chemical


def test_ipm_high_has_escalation():
    ipm = build_ipm("Fruit Borers", "HIGH", None)
    assert ipm["escalation"]           # containment/removal steps
    assert ipm["chemical_status"] == "threshold_gated"


def test_ipm_unknown_is_monitoring_only():
    ipm = build_ipm("Aphids", "UNKNOWN", None)
    assert ipm["chemical_status"] == "not_recommended"
    assert ipm["monitoring"]


def test_sustainable_order_chemical_never_first():
    for level in ["LOW", "MODERATE", "HIGH", "UNKNOWN"]:
        ipm = build_ipm("Aphids", level, {"temperature": 30, "humidity": 70})
        ranked = rank_sustainable_treatment("Aphids", level, ipm)
        cats = [s["category"] for s in ranked["ordered_steps"] if s["category"] != "monitoring"]
        if cats:
            assert cats[0] != "chemical", f"chemical first at {level}"
            # chemical, if present, must be last
            if "chemical" in cats:
                assert cats[-1] == "chemical"


def test_sustainable_order_follows_ladder():
    ipm = build_ipm("Aphids", "HIGH", None)
    ranked = rank_sustainable_treatment("Aphids", "HIGH", ipm)
    cats = [s["category"] for s in ranked["ordered_steps"] if s["category"] != "monitoring"]
    # Order of appearance must respect SUSTAINABLE_ORDER
    idx = [SUSTAINABLE_ORDER.index(c) for c in cats]
    assert idx == sorted(idx)


# ---------------- NLP ----------------

def test_pest_intent_english():
    assert nlp.classify_intent("Are aphids attacking my tomato plants?") == "pest_management"


def test_pest_intent_hindi():
    assert nlp.classify_intent("क्या इस पौधे में माहू कीट हैं?") == "pest_management"


def test_pest_intent_tamil():
    assert nlp.classify_intent("என் செடியில் பூச்சி தாக்குதல் உள்ளதா?") == "pest_management"


def test_pest_entity_extraction():
    assert nlp.extract_pest("I see whiteflies on the leaves") == "Whiteflies"
    assert nlp.extract_pest("aphids everywhere") == "Aphids"


def test_existing_intents_still_work():
    # Guardrail: pest keywords must not have broken the other intents.
    assert nlp.classify_intent("Should I irrigate now?") == "irrigation"
    assert nlp.classify_intent("Which government scheme can I get?") == "scheme"
    assert nlp.classify_intent("My soil nitrogen is low") == "soil"
    assert nlp.classify_intent("What is the weather forecast?") == "weather"
    assert nlp.classify_intent("How much fertilizer urea to add?") == "fertilizer"


# ---------------- Full pipeline (vision monkeypatched) ----------------

def _fake_image(path):
    Image.new("RGB", (128, 128), (0, 128, 0)).save(path)


@pytest.mark.asyncio
async def test_pipeline_pest_path(tmp_path, monkeypatch):
    from app.services import pest_pipeline

    async def fake_detect(image_path, crop=""):
        return {"type": "pest", "pest_name": "Aphids", "crop": crop,
                "confidence": 0.86, "visible_infestation": "moderate",
                "affected_leaf_pct": 18, "kb": PEST_KB["Aphids"], "uncertain": False,
                "visible_indicators": "clusters under leaves"}

    monkeypatch.setattr(pest_pipeline, "detect_pest", fake_detect)
    img = tmp_path / "leaf.jpg"; _fake_image(str(img))
    res = await pest_pipeline.run_pest_pipeline(str(img), "tomato", "flowering",
                                                {"temperature": 30, "humidity": 70})
    assert res["type"] == "pest"
    assert res["pest"]["name"] == "Aphids"
    assert res["severity"]["level"] in ("MODERATE", "HIGH")
    assert res["ipm"]["ordered_steps"]
    # chemical never first
    cats = [s["category"] for s in res["ipm"]["ordered_steps"] if s["category"] != "monitoring"]
    assert cats[0] != "chemical"


@pytest.mark.asyncio
async def test_pipeline_low_confidence(tmp_path, monkeypatch):
    from app.services import pest_pipeline

    async def fake_detect(image_path, crop=""):
        return {"type": "uncertain", "pest_name": None, "crop": crop,
                "confidence": 0.2, "uncertain": True,
                "message": "I couldn't confidently identify the pest from this image."}

    monkeypatch.setattr(pest_pipeline, "detect_pest", fake_detect)
    img = tmp_path / "blurry.jpg"; _fake_image(str(img))
    res = await pest_pipeline.run_pest_pipeline(str(img), "tomato")
    assert res["uncertain"] is True
    assert res["type"] == "uncertain"
    assert "couldn't confidently" in res["message"].lower()


@pytest.mark.asyncio
async def test_pipeline_disease_handback(tmp_path, monkeypatch):
    from app.services import pest_pipeline

    async def fake_detect(image_path, crop=""):
        return {"type": "disease", "pest_name": None, "crop": crop,
                "confidence": 0.8, "uncertain": False,
                "message": "This looks like a plant disease rather than an insect pest."}

    monkeypatch.setattr(pest_pipeline, "detect_pest", fake_detect)
    img = tmp_path / "spots.jpg"; _fake_image(str(img))
    res = await pest_pipeline.run_pest_pipeline(str(img), "tomato")
    assert res["type"] == "disease"
    assert "disease" in res["message"].lower()


@pytest.mark.asyncio
async def test_pipeline_invalid_image(tmp_path):
    from app.services import pest_pipeline
    bad = tmp_path / "notimage.jpg"
    bad.write_text("this is not an image")
    res = await pest_pipeline.run_pest_pipeline(str(bad), "tomato")
    assert res["uncertain"] is True
