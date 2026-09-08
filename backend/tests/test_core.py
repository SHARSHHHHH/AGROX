"""Core recommendation + eligibility + NLP tests."""
from app.services.recommendation import recommend_irrigation, analyze_soil, classify_moisture
from app.services.simulator import generate, set_scenario, SCENARIOS
from app.ai import nlp


def test_dry_soil_triggers_irrigation():
    rec = recommend_irrigation(soil_moisture=18, temperature=36, humidity=35,
                               rain_probability=10, crop="tomato")
    assert rec["irrigate"] is True
    assert rec["priority"] in ("HIGH", "CRITICAL")
    assert rec["duration_min"] > 0


def test_rain_postpones_irrigation():
    rec = recommend_irrigation(soil_moisture=25, temperature=30, humidity=70,
                               rain_probability=85, crop="tomato")
    assert rec["irrigate"] is False
    assert "rain" in rec["reason"].lower()


def test_adequate_moisture_no_irrigation():
    rec = recommend_irrigation(soil_moisture=60, temperature=28, humidity=60,
                               rain_probability=10, crop="tomato")
    assert rec["irrigate"] is False


def test_moisture_classification_is_crop_specific():
    # Rice needs more water than chilli
    assert classify_moisture(45, "rice") in ("LOW", "VERY LOW")
    assert classify_moisture(45, "chilli") == "OPTIMAL"


def test_soil_analysis_flags_low_nitrogen():
    res = analyze_soil(nitrogen=10, phosphorus=40, potassium=90, ph=6.3, crop="tomato")
    assert res["nitrogen"]["status"] in ("LOW", "VERY LOW")
    assert any("itrogen" in w for w in res["warnings"])


def test_simulator_respects_scenario():
    set_scenario("low_water")
    r = generate()
    lo, hi = SCENARIOS["low_water"]["water"]
    assert lo <= r["water_level"] <= hi
    assert r["source"] == "simulated"


def test_language_detection():
    assert nlp.detect_language("Should I water my plants?") == "en"
    assert nlp.detect_language("என் தக்காளி செடிக்கு தண்ணி ஊத்தணுமா?") == "ta"
    assert nlp.detect_language("मेरी फसल को पानी चाहिए") == "hi"


def test_intent_classification():
    assert nlp.classify_intent("Should I irrigate now?") == "irrigation"
    assert nlp.classify_intent("Which government scheme can I get?") == "scheme"
    assert nlp.classify_intent("என் இலை மஞ்சளா ஆகுது") == "disease"


def test_entity_extraction_crop():
    assert nlp.extract_entities("my tomato plant is sick")["crop"] == "tomato"
    assert nlp.extract_entities("என் தக்காளி செடி")["crop"] == "tomato"


def test_disease_matching_from_text():
    hits = nlp.match_diseases(
        "My tomato leaves have brown spots with concentric rings on the older leaves")
    assert hits
    assert hits[0]["disease"] == "Early Blight"


def test_disease_matching_respects_crop_filter():
    # Blast only affects rice — a tomato query must not surface it even if a
    # phrase happens to overlap.
    hits = nlp.match_diseases("diamond shaped lesion on my tomato leaves",
                              crop="tomato")
    assert all(h["disease"] != "Blast" for h in hits)


def test_disease_matching_returns_nothing_for_vague_text():
    assert nlp.match_diseases("my plant looks sad today") == []


def test_nutrient_deficiency_matching():
    hits = nlp.match_nutrient_deficiency(
        "the leaves are showing yellowing between veins but veins stay green")
    assert hits
    assert hits[0]["nutrient"] == "Magnesium"
