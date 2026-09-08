"""Deterministic domain engine tests.

These engines decide what the farmer is told and what the hardware does, so
they are tested directly rather than through the LLM.
"""

from datetime import datetime, timedelta, timezone

import pytest

from app.core.config import settings
from app.services import fertilizer, irrigation, lifecycle, market
from app.services.crop_suitability import (MP_CROPS, current_season,
                                           recommend_crops, score_crop)

# ---------------------------------------------------------------- crop suitability


def test_all_mp_crops_present():
    for crop in ("soybean", "wheat", "chickpea", "maize", "cotton"):
        assert crop in MP_CROPS


def test_season_calendar():
    from datetime import date
    assert current_season(date(2026, 7, 15)) == "kharif"
    assert current_season(date(2026, 12, 15)) == "rabi"
    assert current_season(date(2026, 4, 15)) == "zaid"


def test_soybean_scores_well_in_kharif():
    result = score_crop("soybean", ph=6.8, nitrogen=30, phosphorus=40,
                        potassium=70, moisture=60, temperature=28,
                        soil_type="black", season="kharif")
    assert result["verdict"] in ("HIGHLY SUITABLE", "SUITABLE")
    assert result["score"] >= 55


def test_wrong_season_is_heavily_penalised():
    """Season is the dominant factor — wheat in kharif must not be recommended."""
    kharif = score_crop("wheat", ph=6.5, moisture=50, temperature=20,
                        season="kharif")
    rabi = score_crop("wheat", ph=6.5, moisture=50, temperature=20,
                      season="rabi")
    assert rabi["score"] > kharif["score"]
    assert any("wrong season" in lim for lim in kharif["limitations"])


def test_bad_ph_lowers_score():
    good = score_crop("soybean", ph=6.8, season="kharif")
    bad = score_crop("soybean", ph=4.2, season="kharif")
    assert good["score"] > bad["score"]
    assert any("pH" in lim for lim in bad["limitations"])


def test_missing_data_is_neutral_not_penalised():
    """Absent measurements must not push a crop down the ranking."""
    result = score_crop("soybean", season="kharif")
    assert result["factor_scores"]["ph"] == 0.5
    assert result["factor_scores"]["npk"] == 0.5


def test_recommend_ranks_descending():
    out = recommend_crops(ph=6.5, nitrogen=40, phosphorus=45, potassium=80,
                          moisture=60, temperature=28, soil_type="black",
                          season="kharif")
    scores = [r["score"] for r in out["recommendations"]]
    assert scores == sorted(scores, reverse=True)
    assert out["best"]["score"] == scores[0]


def test_confidence_reflects_available_data():
    rich = recommend_crops(ph=6.5, nitrogen=40, phosphorus=45, potassium=80,
                           moisture=60, temperature=28, season="kharif")
    sparse = recommend_crops(season="kharif")
    assert rich["data_confidence"] == "high"
    assert sparse["data_confidence"] == "low"
    assert "pH" in sparse["data_missing"]


def test_recommendation_carries_disclaimer():
    out = recommend_crops(season="rabi")
    assert "Krishi Vigyan Kendra" in out["disclaimer"]


# ---------------------------------------------------------------- lifecycle


def test_lifecycle_covers_all_mp_crops():
    for crop in ("soybean", "wheat", "chickpea", "maize", "cotton"):
        assert lifecycle.get_lifecycle(crop) is not None


def test_lifecycle_aliases_resolve():
    assert lifecycle.resolve_crop("gram") == "chickpea"
    assert lifecycle.resolve_crop("chana") == "chickpea"
    assert lifecycle.resolve_crop("corn") == "maize"


def test_unknown_crop_returns_none_not_a_guess():
    assert lifecycle.get_lifecycle("dragonfruit") is None
    assert lifecycle.current_stage("dragonfruit", 20) is None


def test_stages_are_contiguous_and_ordered():
    for crop in lifecycle.supported_crops():
        stages = lifecycle.LIFECYCLE[crop]
        for earlier, later in zip(stages, stages[1:]):
            assert earlier["end_day"] < later["start_day"], crop
            assert earlier["start_day"] < earlier["end_day"], crop


def test_current_stage_identifies_wheat_crown_root():
    """The most critical irrigation in wheat must be surfaced at ~day 21."""
    stage = lifecycle.current_stage("wheat", 21)
    assert stage["stage"] == "Crown root initiation"
    assert "critical" in stage["irrigation"].lower()


def test_current_stage_reports_next_stage():
    stage = lifecycle.current_stage("soybean", 40)
    assert stage["stage"] == "Flowering"
    assert stage["next_stage"]["stage"] == "Pod filling"
    assert stage["next_stage"]["in_days"] > 0


def test_past_maturity_is_flagged():
    stage = lifecycle.current_stage("soybean", 200)
    assert stage["stage"] == "Past maturity"


# ---------------------------------------------------------------- market honesty


@pytest.mark.asyncio
async def test_market_returns_mock_clearly_labelled(monkeypatch):
    monkeypatch.setattr(settings, "ALLOW_MOCK_MARKET_DATA", True)
    result = await market.get_price("soybean")

    assert result["status"] == "mock"
    assert "MOCK" in result["display"]
    assert "MOCK" in result["prices"]["mandi"]
    assert "warning" in result


@pytest.mark.asyncio
async def test_market_unavailable_when_mock_disabled(monkeypatch):
    monkeypatch.setattr(settings, "ALLOW_MOCK_MARKET_DATA", False)
    result = await market.get_price("soybean")

    assert result["status"] == "unavailable"
    assert result["prices"] is None
    assert "unavailable" in result["display"].lower()


@pytest.mark.asyncio
async def test_unknown_crop_never_gets_invented_price(monkeypatch):
    monkeypatch.setattr(settings, "ALLOW_MOCK_MARKET_DATA", True)
    result = await market.get_price("dragonfruit")
    assert result["status"] == "unavailable"
    assert result["prices"] is None


@pytest.mark.asyncio
async def test_market_facts_forbid_quoting_a_number(monkeypatch):
    """When data is missing the agent must be told not to state a price."""
    monkeypatch.setattr(settings, "ALLOW_MOCK_MARKET_DATA", False)
    result = await market.get_price("soybean")
    facts = market.grounded_facts(result)

    joined = " ".join(facts)
    assert "DATA UNAVAILABLE" in joined
    assert "Do NOT state any price" in joined


@pytest.mark.asyncio
async def test_mock_facts_announce_they_are_mock(monkeypatch):
    monkeypatch.setattr(settings, "ALLOW_MOCK_MARKET_DATA", True)
    facts = market.grounded_facts(await market.get_price("wheat"))
    assert "MOCK" in " ".join(facts)


# ---------------------------------------------------------------- ROI


def test_roi_profitable_case():
    roi = fertilizer.calculate_roi(offer_price=320, standard_price=400,
                                   bags=20, distance_km=10, crop="soybean",
                                   acres=2, crop_price_per_tonne=46500)
    assert roi["worth_it"] is True
    assert roi["profit"] > 0


def test_roi_transport_can_destroy_the_saving():
    """A cheap bag 200 km away is not a bargain."""
    near = fertilizer.calculate_roi(offer_price=320, standard_price=400,
                                    bags=5, distance_km=5, crop="soybean")
    far = fertilizer.calculate_roi(offer_price=320, standard_price=400,
                                   bags=5, distance_km=200, crop="soybean")
    assert near["profit"] > far["profit"]
    assert far["worth_it"] is False


def test_roi_breakdown_is_fully_itemised():
    roi = fertilizer.calculate_roi(offer_price=300, standard_price=380,
                                   bags=10, distance_km=20, crop="wheat")
    for key in ("purchase_cost", "transport_cost", "total_cost",
                "store_savings", "revenue_gain", "extra_tonnes"):
        assert key in roi["breakdown"]


def test_roi_arithmetic_is_correct():
    roi = fertilizer.calculate_roi(offer_price=100, standard_price=150,
                                   bags=10, distance_km=10, crop="default",
                                   acres=1, crop_price_per_tonne=None,
                                   transport_rate_per_km=25)
    b = roi["breakdown"]
    assert b["purchase_cost"] == 1000.0        # 100 * 10
    assert b["transport_cost"] == 500.0        # 10 km * 2 * 25
    assert b["store_savings"] == 500.0         # (150-100) * 10
    # No crop price, so revenue is zero: 0 + 500 - 1500 = -1000
    assert roi["profit"] == -1000.0


def test_roi_without_crop_price_says_so():
    roi = fertilizer.calculate_roi(offer_price=300, standard_price=380,
                                   bags=10, distance_km=20, crop="wheat",
                                   crop_price_per_tonne=None)
    assert roi["yield_revenue_counted"] is False
    assert roi["breakdown"]["revenue_gain"] == 0.0
    assert "unavailable" in roi["revenue_note"].lower()


def test_roi_labels_yield_boost_as_an_assumption():
    roi = fertilizer.calculate_roi(offer_price=300, standard_price=380,
                                   bags=10, distance_km=20, crop="wheat",
                                   crop_price_per_tonne=24500)
    assert any("placeholder" in a or "Assumed" in a for a in roi["assumptions"])


def test_roi_facts_forbid_recalculation():
    roi = fertilizer.calculate_roi(offer_price=300, standard_price=380,
                                   bags=10, distance_km=20, crop="wheat")
    facts = " ".join(fertilizer.grounded_facts(roi))
    assert "Do NOT recalculate" in facts


@pytest.mark.asyncio
async def test_offers_are_mock_labelled(monkeypatch):
    monkeypatch.setattr(settings, "ALLOW_MOCK_MARKET_DATA", True)
    out = await fertilizer.get_offers()
    assert out["status"] == "mock"
    assert all("MOCK" in o["vendor"] for o in out["offers"])


@pytest.mark.asyncio
async def test_offers_unavailable_when_mock_disabled(monkeypatch):
    monkeypatch.setattr(settings, "ALLOW_MOCK_MARKET_DATA", False)
    out = await fertilizer.get_offers()
    assert out["status"] == "unavailable"
    assert out["offers"] == []


# ---------------------------------------------------------------- irrigation safety


def _fresh():
    return datetime.now(timezone.utc) - timedelta(minutes=2)


def test_pump_approved_in_normal_dry_conditions():
    d = irrigation.evaluate_pump_request(
        soil_moisture=22, water_level=80, temperature=34, humidity=40,
        rain_probability=10, crop="tomato", reading_time=_fresh())
    assert d.allowed is True
    assert d.duration_min > 0


def test_stale_sensor_blocks_pump():
    old = datetime.now(timezone.utc) - timedelta(hours=3)
    d = irrigation.evaluate_pump_request(
        soil_moisture=15, water_level=90, rain_probability=0,
        crop="tomato", reading_time=old)
    assert d.allowed is False
    assert any("stale" in b.lower() or "old" in b.lower() for b in d.blocks)


def test_missing_sensor_blocks_pump():
    d = irrigation.evaluate_pump_request(
        soil_moisture=None, water_level=90, rain_probability=0,
        crop="tomato", reading_time=None)
    assert d.allowed is False


def test_saturated_soil_blocks_pump():
    d = irrigation.evaluate_pump_request(
        soil_moisture=92, water_level=90, rain_probability=0,
        crop="rice", reading_time=_fresh())
    assert d.allowed is False
    assert any("saturation" in b.lower() or "waterlog" in b.lower()
               for b in d.blocks)


def test_low_water_level_blocks_pump():
    """Protects the pump from dry-running damage."""
    d = irrigation.evaluate_pump_request(
        soil_moisture=15, water_level=5, rain_probability=0,
        crop="tomato", reading_time=_fresh())
    assert d.allowed is False
    assert any("dry-running" in b for b in d.blocks)


def test_unknown_water_level_blocks_pump():
    d = irrigation.evaluate_pump_request(
        soil_moisture=15, water_level=None, rain_probability=0,
        crop="tomato", reading_time=_fresh())
    assert d.allowed is False


def test_heavy_rain_blocks_pump():
    d = irrigation.evaluate_pump_request(
        soil_moisture=25, water_level=90, rain_probability=85,
        crop="tomato", reading_time=_fresh())
    assert d.allowed is False
    assert any("rain" in b.lower() for b in d.blocks)


def test_manual_override_beats_rain_but_not_hardware_safety():
    """A farmer may override advice. They may not override equipment safety."""
    rain = irrigation.evaluate_pump_request(
        soil_moisture=25, water_level=90, rain_probability=85, crop="tomato",
        reading_time=_fresh(), requested_minutes=15, manual_override=True)
    assert rain.allowed is True

    dry_tank = irrigation.evaluate_pump_request(
        soil_moisture=25, water_level=3, rain_probability=85, crop="tomato",
        reading_time=_fresh(), requested_minutes=15, manual_override=True)
    assert dry_tank.allowed is False


def test_duration_is_clamped_to_safe_bounds():
    long = irrigation.evaluate_pump_request(
        soil_moisture=15, water_level=90, rain_probability=0, crop="tomato",
        reading_time=_fresh(), requested_minutes=600)
    assert long.duration_min == irrigation.MAX_RUN_MINUTES

    short = irrigation.evaluate_pump_request(
        soil_moisture=15, water_level=90, rain_probability=0, crop="tomato",
        reading_time=_fresh(), requested_minutes=1)
    assert short.duration_min == irrigation.MIN_RUN_MINUTES


def test_adequate_moisture_declines_without_blocking():
    d = irrigation.evaluate_pump_request(
        soil_moisture=70, water_level=90, rain_probability=0, crop="tomato",
        reading_time=_fresh())
    assert d.allowed is False
    assert d.blocks == []          # declined on advice, not blocked on safety


def test_blocked_facts_tell_the_model_not_to_override():
    d = irrigation.evaluate_pump_request(
        soil_moisture=15, water_level=2, rain_probability=0, crop="tomato",
        reading_time=_fresh())
    facts = " ".join(irrigation.grounded_facts(d))
    assert "BLOCKED" in facts
    assert "Do NOT tell the farmer to irrigate" in facts


def test_decision_records_it_was_deterministic():
    d = irrigation.evaluate_pump_request(
        soil_moisture=22, water_level=80, rain_probability=10, crop="tomato",
        reading_time=_fresh())
    assert d.to_dict()["decided_by"] == "deterministic_rule_engine"
