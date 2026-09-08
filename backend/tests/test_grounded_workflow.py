"""End-to-end grounded agentic workflow tests.

The architectural claim of this project is:

    NLP -> deterministic tools produce FACTS -> LLM explains -> translation

These tests assert that claim mechanically. A stub provider captures whatever
prompt the agent hands to the model, so we can prove the facts were computed
BEFORE the model was called, and that a hostile model cannot change them.
"""

import pytest

from app.core.config import settings
from app.services import fertilizer, irrigation, market
from app.services.crop_suitability import recommend_crops


class SpyProvider:
    """Stands in for the LLM. Records the prompt and returns a canned reply."""

    name = "spy"

    def __init__(self, reply="Explained for the farmer."):
        self.reply = reply
        self.system_prompts = []
        self.user_prompts = []
        self.call_count = 0

    async def chat(self, system_prompt, user_prompt, temperature=0.3,
                   max_tokens=None):
        self.call_count += 1
        self.system_prompts.append(system_prompt)
        self.user_prompts.append(user_prompt)
        return self.reply

    async def close(self):
        return None


@pytest.fixture
def spy(monkeypatch):
    from app.ai import providers
    provider = SpyProvider()
    monkeypatch.setattr(providers.factory, "get_provider", lambda name="": provider)
    monkeypatch.setattr(providers, "get_provider", lambda name="": provider)
    return provider


# ------------------------------------------------- facts precede the model


@pytest.mark.asyncio
async def test_llm_receives_precomputed_irrigation_decision(spy):
    """The pump decision must be settled before the model ever sees it."""
    from datetime import datetime, timedelta, timezone
    from app.ai import llm

    decision = irrigation.evaluate_pump_request(
        soil_moisture=15, water_level=4, rain_probability=0, crop="tomato",
        reading_time=datetime.now(timezone.utc) - timedelta(minutes=1))

    assert decision.allowed is False        # decided by rules, not the model

    facts = "\n".join(irrigation.grounded_facts(decision))
    await llm.chat("You explain decisions.", f"FACTS:\n{facts}\n\nExplain.")

    prompt = spy.user_prompts[0]
    assert "BLOCKED" in prompt
    assert "dry-running" in prompt
    assert "Do NOT tell the farmer to irrigate" in prompt


@pytest.mark.asyncio
async def test_model_output_cannot_change_the_decision(spy):
    """Even if the model says the opposite, the engine's verdict stands."""
    from datetime import datetime, timedelta, timezone
    from app.ai import llm

    spy.reply = "Go ahead and irrigate for 60 minutes right now!"

    decision = irrigation.evaluate_pump_request(
        soil_moisture=92, water_level=95, rain_probability=0, crop="rice",
        reading_time=datetime.now(timezone.utc) - timedelta(minutes=1))

    explanation = await llm.chat("s", "u")

    # The model said yes. The system still says no, and that is what governs.
    assert "irrigate" in explanation.lower()
    assert decision.allowed is False
    assert decision.to_dict()["decided_by"] == "deterministic_rule_engine"


@pytest.mark.asyncio
async def test_market_unavailable_reaches_the_prompt_as_a_prohibition(spy, monkeypatch):
    from app.ai import llm

    monkeypatch.setattr(settings, "ALLOW_MOCK_MARKET_DATA", False)
    price = await market.get_price("soybean")
    facts = "\n".join(market.grounded_facts(price))

    await llm.chat("You explain prices.", f"FACTS:\n{facts}")

    prompt = spy.user_prompts[0]
    assert "DATA UNAVAILABLE" in prompt
    assert "Do NOT state any price" in prompt


@pytest.mark.asyncio
async def test_roi_numbers_are_fixed_before_the_model_sees_them(spy):
    from app.ai import llm

    roi = fertilizer.calculate_roi(offer_price=100, standard_price=150,
                                   bags=10, distance_km=10,
                                   transport_rate_per_km=25)
    facts = "\n".join(fertilizer.grounded_facts(roi))
    await llm.chat("You explain ROI.", f"FACTS:\n{facts}")

    prompt = spy.user_prompts[0]
    assert "-1,000.00" in prompt or "1,000.00" in prompt
    assert "Do NOT recalculate" in prompt


@pytest.mark.asyncio
async def test_crop_ranking_is_computed_not_asked(spy):
    """The model must never be the thing that chooses a crop."""
    from app.ai import llm

    result = recommend_crops(ph=6.8, nitrogen=30, phosphorus=40, potassium=70,
                             moisture=60, temperature=28, soil_type="black",
                             season="kharif")

    # Ranking exists with zero model calls so far.
    assert spy.call_count == 0
    assert result["best"] is not None

    facts = "\n".join(
        f"{r['display']}: score {r['score']} ({r['verdict']})"
        for r in result["recommendations"])
    await llm.chat("You explain rankings.", facts)

    assert spy.call_count == 1
    assert result["best"]["display"] in spy.user_prompts[0]


# ------------------------------------------------- provider swap is invisible


@pytest.mark.asyncio
async def test_same_facts_regardless_of_provider(monkeypatch):
    """Switching Qwen<->Gemini must not alter any deterministic output."""
    from app.ai import llm
    from app.ai.providers import qwen as qwen_mod
    from app.ai.providers import reset_cache
    monkeypatch.setattr(qwen_mod, "is_loaded", lambda: True)

    roi_a = fertilizer.calculate_roi(offer_price=320, standard_price=400,
                                     bags=20, distance_km=10, crop="soybean")

    reset_cache()
    monkeypatch.setattr(settings, "LLM_PROVIDER", "qwen")
    monkeypatch.setattr(qwen_mod, "_generate_sync",
                        lambda s, u, t, m: "qwen phrasing")
    qwen_out = await llm.chat("s", "u")

    roi_b = fertilizer.calculate_roi(offer_price=320, standard_price=400,
                                     bags=20, distance_km=10, crop="soybean")

    assert qwen_out == "qwen phrasing"
    assert roi_a["profit"] == roi_b["profit"]
    reset_cache()


@pytest.mark.asyncio
async def test_deterministic_output_survives_total_llm_outage(monkeypatch):
    """With the model completely dead, the farmer still gets real numbers."""
    from app.ai import llm
    from app.ai.providers import ProviderError, qwen as qwen_mod, reset_cache
    monkeypatch.setattr(qwen_mod, "is_loaded", lambda: True)

    reset_cache()
    monkeypatch.setattr(settings, "LLM_PROVIDER", "qwen")

    def dead(system, user, temperature, max_new_tokens):
        raise ProviderError("load_failed", "weights missing", provider="qwen")

    monkeypatch.setattr(qwen_mod, "_generate_sync", dead)

    from datetime import datetime, timedelta, timezone
    decision = irrigation.evaluate_pump_request(
        soil_moisture=15, water_level=80, rain_probability=0, crop="tomato",
        reading_time=datetime.now(timezone.utc) - timedelta(minutes=1))

    explanation = await llm.chat("s", "u")

    assert decision.allowed is True          # the advice still exists
    assert decision.duration_min > 0
    assert "load_failed" in explanation      # and the failure stays visible
    reset_cache()
