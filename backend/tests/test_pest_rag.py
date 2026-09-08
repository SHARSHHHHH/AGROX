"""Tests for the hybrid pest RAG layer: extended KB integrity, semantic
matching, the fallback guardrail, and the pipeline's pest_unmatched route.

Embedding/LLM calls are monkeypatched throughout — no network access needed,
matching the existing convention in test_pest.py for the vision layer.
"""
import pytest
from PIL import Image

from app.ml.pest_knowledge import PEST_KB, KNOWN_PESTS
from app.ml.pest_kb_extended import PEST_KB_EXTENDED


# ---------------- Extended KB is really merged in ----------------

def test_extended_entries_are_merged_into_pest_kb():
    for name in PEST_KB_EXTENDED:
        assert name in PEST_KB
        assert name in KNOWN_PESTS


def test_extended_kb_covers_indigenous_and_major_crops():
    all_crops = set()
    for entry in PEST_KB.values():
        all_crops.update(c.lower() for c in entry.get("affected_crops", []))
    # A sample of major + indigenous crops the extended KB was meant to add.
    expected = ["rice", "sorghum (jowar)", "pearl millet (bajra)",
               "finger millet (ragi)", "pigeon pea (arhar/tur)", "coconut"]
    for crop in expected:
        assert crop in all_crops, f"expected crop coverage missing: {crop}"


# ---------------- Semantic matching ----------------

@pytest.mark.asyncio
async def test_semantic_match_finds_close_entry(monkeypatch):
    from app.ml import pest_embeddings

    async def fake_embed(text):
        # Make "cotton mealybug" resolve to the same vector as the KB
        # entry text for Mealybugs, and everything else orthogonal.
        if "Mealybugs" in text or "cotton mealybug" in text.lower():
            return [1.0, 0.0, 0.0]
        return [0.0, 1.0, 0.0]

    monkeypatch.setattr(pest_embeddings, "embed_text", fake_embed)
    monkeypatch.setattr(pest_embeddings, "_KB_EMBEDDING_CACHE", {})
    monkeypatch.setattr(pest_embeddings.settings, "PEST_SEMANTIC_MATCH_THRESHOLD", 0.9)

    name, score = await pest_embeddings.semantic_match_pest("cotton mealybug", "")
    assert name == "Mealybugs"
    assert score >= 0.9


@pytest.mark.asyncio
async def test_semantic_match_returns_none_below_threshold(monkeypatch):
    from app.ml import pest_embeddings

    async def fake_embed(text):
        return [1.0, 0.0, 0.0] if "query" in text else [0.0, 1.0, 0.0]

    monkeypatch.setattr(pest_embeddings, "embed_text", fake_embed)
    monkeypatch.setattr(pest_embeddings, "_KB_EMBEDDING_CACHE", {})
    monkeypatch.setattr(pest_embeddings.settings, "PEST_SEMANTIC_MATCH_THRESHOLD", 0.99)

    name, score = await pest_embeddings.semantic_match_pest("query pest", "")
    assert name is None


# ---------------- Grounded fallback guardrail ----------------

@pytest.mark.asyncio
async def test_fallback_rejects_overconfident_text(monkeypatch):
    from app.ml import pest_rag_fallback

    async def fake_chat_strict(system, user, temperature=0.2, max_output_tokens=300):
        return "This is definitely a rare beetle, spray 5ml/l immediately."

    monkeypatch.setattr(pest_rag_fallback, "chat_strict", fake_chat_strict)

    result = await pest_rag_fallback.grounded_fallback(
        "unknown bug", "tomato", "small black insect", [("Aphids", 0.5)])
    assert result["verified"] is False
    assert result["origin"] == "ai_fallback_safe_default"
    assert "krishi vigyan kendra" in result["summary"].lower() or "kvk" in result["summary"].lower()


@pytest.mark.asyncio
async def test_fallback_accepts_hedged_text(monkeypatch):
    from app.ml import pest_rag_fallback

    async def fake_chat_strict(system, user, temperature=0.2, max_output_tokens=300):
        return ("This may be a sap-sucking insect similar to aphids. Monitor the plant "
                "and remove affected leaves. Please confirm with your local KVK or "
                "extension officer before any chemical use.")

    monkeypatch.setattr(pest_rag_fallback, "chat_strict", fake_chat_strict)

    result = await pest_rag_fallback.grounded_fallback(
        "unknown bug", "tomato", "small black insect", [("Aphids", 0.6)])
    assert result["verified"] is False
    assert result["origin"] == "ai_fallback"
    assert "aphids" in result["summary"].lower() or "Aphids" in str(result["grounded_facts"])


# ---------------- Pipeline: pest_unmatched path ----------------

def _fake_image(path):
    Image.new("RGB", (128, 128), (0, 128, 0)).save(path)


@pytest.mark.asyncio
async def test_pipeline_routes_unmatched_pest_to_fallback(tmp_path, monkeypatch):
    from app.services import pest_pipeline

    async def fake_detect(image_path, crop=""):
        return {"type": "pest_unmatched", "pest_name": "strange spotted beetle",
                "crop": crop, "confidence": 0.7, "visible_infestation": "low",
                "affected_leaf_pct": 5, "kb": None, "uncertain": False,
                "message": None, "visible_indicators": "small spotted beetle on leaf",
                "nearest_candidates": [("Aphids", 0.4)]}

    async def fake_fallback(pest_guess, crop, visible_indicators, nearest):
        return {"summary": "Monitor and consult your local KVK before any treatment.",
                "grounded_facts": ["Not matched to the verified KB."],
                "verified": False, "origin": "ai_fallback"}

    monkeypatch.setattr(pest_pipeline, "detect_pest", fake_detect)
    monkeypatch.setattr(pest_pipeline, "grounded_fallback", fake_fallback)
    pest_pipeline._result_cache.clear()

    img = tmp_path / "beetle.jpg"; _fake_image(str(img))
    res = await pest_pipeline.run_pest_pipeline(str(img), "tomato")

    assert res["type"] == "pest_unmatched"
    assert res["verified"] is False
    assert res["uncertain"] is True
    assert "KVK" in res["message"]
    assert res["ipm"]["chemical_status"] == "not_recommended"


@pytest.mark.asyncio
async def test_pipeline_caches_repeat_fallback_query(tmp_path, monkeypatch):
    from app.services import pest_pipeline

    calls = {"n": 0}

    async def fake_detect(image_path, crop=""):
        return {"type": "pest_unmatched", "pest_name": "mystery bug",
                "crop": crop, "confidence": 0.6, "visible_infestation": "low",
                "affected_leaf_pct": 3, "kb": None, "uncertain": False,
                "message": None, "visible_indicators": "tiny bug",
                "nearest_candidates": []}

    async def fake_fallback(pest_guess, crop, visible_indicators, nearest):
        calls["n"] += 1
        return {"summary": "Consult your local KVK.", "grounded_facts": [],
                "verified": False, "origin": "ai_fallback"}

    monkeypatch.setattr(pest_pipeline, "detect_pest", fake_detect)
    monkeypatch.setattr(pest_pipeline, "grounded_fallback", fake_fallback)
    pest_pipeline._result_cache.clear()

    img = tmp_path / "bug.jpg"; _fake_image(str(img))
    await pest_pipeline.run_pest_pipeline(str(img), "tomato")
    await pest_pipeline.run_pest_pipeline(str(img), "tomato")

    assert calls["n"] == 1  # second call served from cache
