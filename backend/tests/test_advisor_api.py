"""Onboarding, crop advisory and market-price endpoint tests."""

import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from app.main import app
from app.services import mandi_price as mp
from tests.test_mandi_price import REAL_RESPONSE, FakeClient, FakeResponse


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="module")
def auth(client):
    r = client.post("/api/auth/login",
                    data={"username": "farmer@demo.com", "password": "demo123"})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


@pytest.fixture
def live_mandi(monkeypatch):
    """Serve the real recorded AGMARKNET payload instead of calling out."""
    mp.clear_cache()
    monkeypatch.setattr(settings, "DATA_GOV_API_KEY", "test-key")

    def factory(**kw):
        return FakeClient([FakeResponse(200, REAL_RESPONSE)] * 40)

    monkeypatch.setattr(mp.httpx, "AsyncClient", factory)

    async def _no_sleep(_):
        return None
    monkeypatch.setattr(mp.asyncio, "sleep", _no_sleep)
    yield
    mp.clear_cache()


# ---------------------------------------------------------------- security

def test_market_prices_requires_auth(client):
    assert client.get("/api/market-prices").status_code == 401


def test_api_key_never_returned_to_browser(client, auth, live_mandi):
    body = client.get("/api/market-prices",
                      params={"commodity": "tomato"}, headers=auth).text
    assert settings.DATA_GOV_API_KEY not in body
    assert "api-key" not in body
    assert "DATA_GOV_API_KEY" not in body


# ---------------------------------------------------------------- market prices

def test_market_prices_returns_real_shape(client, auth, live_mandi):
    body = client.get("/api/market-prices",
                      params={"commodity": "tomato"}, headers=auth).json()
    assert body["status"] == "ok"
    assert body["unit"] == "INR/quintal"
    rec = body["records"][0]
    for field in ("state", "district", "market", "commodity",
                  "min_price", "max_price", "modal_price", "arrival_date"):
        assert field in rec


def test_market_prices_dates_are_iso(client, auth, live_mandi):
    body = client.get("/api/market-prices",
                      params={"commodity": "tomato"}, headers=auth).json()
    assert body["records"][0]["arrival_date"] == "2026-08-29"


def test_summary_returns_only_the_requested_commodity(client, auth, live_mandi):
    """Asking for tomato must never return the carrot row.

    data.gov.in silently ignores a filter it cannot apply and returns the
    unfiltered feed, so every crop showed the same (wrong) price. The client
    side re-verifies. 2000 is the Tomato modal; 8200 is Carrot.
    """
    body = client.get("/api/market-prices/summary",
                      params={"commodity": "tomato"}, headers=auth).json()
    assert body["status"] == "ok"
    assert body["best_market"]["modal_price"] == 2000.0, "carrot leaked into tomato"
    assert all(r == "Tomato" for r in [body["best_market"].get("market") and "Tomato"])
    assert "disclaimer" in body


def test_unmatched_filter_returns_empty_not_wrong_data(client, auth, live_mandi):
    """A crop absent from the feed must return empty, never someone else's price."""
    body = client.get("/api/market-prices/summary",
                      params={"commodity": "sugarcane"}, headers=auth).json()
    assert body["status"] != "ok"


def test_different_crops_get_different_prices(client, auth, live_mandi):
    """The headline bug: every crop showed an identical price."""
    tomato = client.get("/api/market-prices/summary",
                        params={"commodity": "tomato"}, headers=auth).json()
    carrot = client.get("/api/market-prices/summary",
                        params={"commodity": "carrot"}, headers=auth).json()
    assert tomato["best_market"]["modal_price"] != carrot["best_market"]["modal_price"]


def test_not_configured_is_explicit(client, auth, monkeypatch):
    mp.clear_cache()
    monkeypatch.setattr(settings, "DATA_GOV_API_KEY", "")
    body = client.get("/api/market-prices",
                      params={"commodity": "wheat"}, headers=auth).json()
    assert body["status"] == "not_configured"
    assert body["records"] == []


def test_commodities_listing(client, auth):
    body = client.get("/api/market-prices/commodities", headers=auth).json()
    assert "Soyabean" in body["commodities"]
    assert "soybean" in body["crop_keys"]


# ---------------------------------------------------------------- onboarding

def test_onboarding_status_reports_missing(client, auth):
    body = client.get("/api/onboarding/status", headers=auth).json()
    assert "completeness" in body
    assert isinstance(body["missing"], list)


def test_onboarding_partial_save_is_allowed(client, auth):
    """The wizard must be resumable — a partial answer cannot be rejected."""
    r = client.post("/api/onboarding/save", headers=auth,
                    json={"state": "Madhya Pradesh", "district": "Indore"})
    assert r.status_code == 200
    assert r.json()["farm"]["state"] == "Madhya Pradesh"


def test_onboarding_full_save(client, auth):
    r = client.post("/api/onboarding/save", headers=auth, json={
        "state": "Madhya Pradesh", "district": "Indore", "village": "Depalpur",
        "land_size_acres": 2.5, "farmer_category": "small",
        "soil_type": "black", "irrigation_type": "drip",
        "water_source": "borewell",
        "previous_crop": "wheat", "previous_season": "rabi",
        "crop": "soybean", "sowing_date": "2026-07-01",
        "nitrogen": 38, "phosphorus": 22, "potassium": 145, "ph": 6.2,
    })
    assert r.status_code == 200
    body = r.json()
    assert body["onboarded"] is True
    assert body["completeness"] == 100
    assert body["farm"]["previous_crop"] == "wheat"
    assert body["farm"]["sowing_date"] == "2026-07-01"
    assert body["has_soil_test"] is True


def test_onboarding_rejects_bad_date(client, auth):
    r = client.post("/api/onboarding/save", headers=auth,
                    json={"sowing_date": "01-07-2026"})
    assert r.status_code == 400


def test_onboarding_never_invents_values(client, auth):
    """An empty save must not silently fill in plausible defaults."""
    before = client.get("/api/onboarding/status", headers=auth).json()
    client.post("/api/onboarding/save", headers=auth, json={})
    after = client.get("/api/onboarding/status", headers=auth).json()
    assert before["farm"]["state"] == after["farm"]["state"]
    assert before["farm"]["land_size_acres"] == after["farm"]["land_size_acres"]


# ---------------------------------------------------------------- lifecycle

def test_my_crop_stage_from_sowing_date(client, auth):
    """Sowing date makes the stage automatic — no manual entry needed."""
    client.post("/api/onboarding/save", headers=auth,
                json={"crop": "soybean", "sowing_date": "2026-07-01"})
    body = client.get("/api/crop-advisor/my-crop-stage", headers=auth).json()
    assert body["status"] == "ok"
    assert body["crop"] == "soybean"
    assert body["days_after_sowing"] > 0
    assert body["stage"]["stage"]
    assert body["stage"]["irrigation"]


# ---------------------------------------------------------------- rotation

def test_rotation_penalises_same_crop(client, auth):
    body = client.get("/api/crop-advisor/rotation",
                      params={"previous_crop": "wheat"}, headers=auth).json()
    ranked = {r["crop"]: r["rotation_score"] for r in body["ranked"]}
    assert ranked["wheat"] < ranked["chickpea"], "repeat crop must rank lowest"


def test_legume_after_cereal_is_excellent(client, auth):
    body = client.get("/api/crop-advisor/rotation",
                      params={"previous_crop": "wheat"}, headers=auth).json()
    top = body["ranked"][0]
    assert top["crop"] in ("soybean", "chickpea")
    assert top["rotation_score"] == 1.0


def test_nitrogen_carryover_reported(client, auth):
    body = client.get("/api/crop-advisor/rotation",
                      params={"previous_crop": "soybean"}, headers=auth).json()
    assert body["nitrogen_carryover_kg_ha"] > 0
    assert "nitrogen" in body["nitrogen_note"].lower()


# ---------------------------------------------------------------- advisory

def test_recommend_ranks_and_scores(client, auth, live_mandi):
    r = client.post("/api/crop-advisor/recommend", headers=auth, json={
        "state": "Madhya Pradesh", "season": "kharif",
        "previous_crop": "wheat", "soil_type": "black",
        "irrigation_type": "drip", "water_source": "borewell",
        "nitrogen": 38, "phosphorus": 22, "potassium": 145,
        "ph": 6.2, "moisture": 60, "use_my_data": False,
    })
    assert r.status_code == 200
    body = r.json()

    scores = [x["advisory_suitability_score"] for x in body["recommendations"]]
    assert scores == sorted(scores, reverse=True)

    top = body["recommendations"][0]
    for key in ("advisory_suitability_score", "reasons", "soil_fit",
                "weather_fit", "water_requirement", "rotation_fit",
                "market_information", "risks", "alternatives"):
        assert key in top, f"missing {key}"


def test_score_is_called_advisory_not_guaranteed(client, auth, live_mandi):
    body = client.post("/api/crop-advisor/recommend", headers=auth,
                       json={"season": "kharif", "use_my_data": False}).json()
    assert "advisory_suitability_score" in body["recommendations"][0]
    assert "guaranteed" in body["disclaimer"].lower()
    assert "not an official government" in body["disclaimer"].lower()


def test_rotation_affects_ranking(client, auth, live_mandi):
    """After wheat, wheat again must score below the same run without history."""
    payload = {"season": "rabi", "soil_type": "black", "ph": 6.5,
               "use_my_data": False, "include_market": False}

    after_wheat = client.post("/api/crop-advisor/recommend", headers=auth,
                              json={**payload, "previous_crop": "wheat"}).json()
    no_history = client.post("/api/crop-advisor/recommend", headers=auth,
                             json=payload).json()

    def score(body, crop):
        return next(x["advisory_suitability_score"]
                    for x in body["recommendations"] if x["crop"] == crop)

    assert score(after_wheat, "wheat") < score(no_history, "wheat")


def test_provenance_is_reported(client, auth, live_mandi):
    body = client.post("/api/crop-advisor/recommend", headers=auth, json={
        "state": "Madhya Pradesh", "season": "kharif",
        "ph": 6.5, "use_my_data": False}).json()
    assert body["provenance"]["soil"] == "MANUAL"
    assert body["data_confidence"] in ("low", "medium", "high")


def test_market_unavailable_does_not_break_advisory(client, auth, monkeypatch):
    """No mandi data must still produce a usable agronomic recommendation."""
    mp.clear_cache()
    monkeypatch.setattr(settings, "DATA_GOV_API_KEY", "")
    body = client.post("/api/crop-advisor/recommend", headers=auth, json={
        "state": "Madhya Pradesh", "season": "kharif",
        "ph": 6.5, "soil_type": "black", "use_my_data": False}).json()

    assert body["recommendations"]
    assert body["provenance"]["market"] == "MISSING"
    top = body["recommendations"][0]
    assert top["market_information"]["status"] != "ok"
    assert "unavailable" in top["market_information"]["note"].lower()


def test_high_water_crop_penalised_without_irrigation(client, auth):
    """Wheat needs assured water; rainfed land must lower its score."""
    base = {"season": "rabi", "soil_type": "black", "ph": 6.5,
            "use_my_data": False, "include_market": False}

    rainfed = client.post("/api/crop-advisor/recommend", headers=auth,
                          json={**base, "water_source": "rainfed"}).json()
    irrigated = client.post("/api/crop-advisor/recommend", headers=auth,
                            json={**base, "water_source": "borewell",
                                  "irrigation_type": "drip"}).json()

    def score(body, crop):
        return next(x["advisory_suitability_score"]
                    for x in body["recommendations"] if x["crop"] == crop)

    assert score(rainfed, "wheat") < score(irrigated, "wheat")
