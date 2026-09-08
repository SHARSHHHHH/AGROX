"""Integration tests for the crop / market / fertilizer endpoints.

These go through the real FastAPI stack including auth, so they prove the
features are reachable from the frontend — not merely that the service
functions exist.
"""

import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from app.main import app


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="module")
def token(client):
    """Log in as the seeded demo farmer."""
    resp = client.post("/api/auth/login",
                       data={"username": "farmer@demo.com",
                             "password": "demo123"})
    assert resp.status_code == 200, resp.text
    return resp.json()["access_token"]


@pytest.fixture(scope="module")
def auth(token):
    return {"Authorization": f"Bearer {token}"}


# ---------------------------------------------------------------- crops

def test_crop_list_endpoint(client):
    resp = client.get("/api/crops/list")
    assert resp.status_code == 200
    keys = {c["key"] for c in resp.json()}
    assert {"soybean", "wheat", "chickpea", "maize", "cotton"} <= keys


def test_season_endpoint(client):
    resp = client.get("/api/crops/season")
    assert resp.status_code == 200
    assert resp.json()["season"] in ("kharif", "rabi", "zaid")


def test_recommend_requires_auth(client):
    assert client.get("/api/crops/recommend").status_code == 401


def test_recommend_returns_ranked_crops(client, auth):
    resp = client.get("/api/crops/recommend", headers=auth, params={
        "ph": 6.8, "nitrogen": 30, "phosphorus": 40, "potassium": 70,
        "moisture": 60, "temperature": 28, "soil_type": "black",
        "season": "kharif", "use_my_data": False,
    })
    assert resp.status_code == 200
    body = resp.json()

    scores = [r["score"] for r in body["recommendations"]]
    assert scores == sorted(scores, reverse=True)
    assert body["best"] is not None
    assert body["data_confidence"] == "high"
    assert "Krishi Vigyan Kendra" in body["disclaimer"]


def test_recommend_reports_missing_data(client, auth):
    resp = client.get("/api/crops/recommend", headers=auth,
                      params={"season": "rabi", "use_my_data": False})
    body = resp.json()
    assert body["data_confidence"] == "low"
    assert "pH" in body["data_missing"]


def test_recommend_pulls_farmer_own_data(client, auth):
    """use_my_data=true should populate inputs from the seeded soil test."""
    resp = client.get("/api/crops/recommend", headers=auth,
                      params={"use_my_data": True})
    assert resp.status_code == 200
    body = resp.json()
    assert "sources" in body
    assert "inputs" in body


def test_lifecycle_endpoint(client):
    resp = client.get("/api/crops/lifecycle/wheat")
    assert resp.status_code == 200
    body = resp.json()
    assert body["crop"] == "wheat"
    assert body["stage_count"] == 6
    names = [s["stage"] for s in body["stages"]]
    assert "Crown root initiation" in names


def test_lifecycle_alias_resolves(client):
    assert client.get("/api/crops/lifecycle/gram").json()["crop"] == "chickpea"


def test_lifecycle_unknown_crop_404s(client):
    resp = client.get("/api/crops/lifecycle/dragonfruit")
    assert resp.status_code == 404
    assert "Supported" in resp.json()["detail"]


def test_stage_endpoint_returns_tasks(client):
    resp = client.get("/api/crops/lifecycle/wheat/stage",
                      params={"days_after_sowing": 21})
    assert resp.status_code == 200
    body = resp.json()
    assert body["stage"] == "Crown root initiation"
    assert body["tasks"]
    assert body["risks"]
    assert "critical" in body["irrigation"].lower()


def test_stage_rejects_negative_days(client):
    resp = client.get("/api/crops/lifecycle/wheat/stage",
                      params={"days_after_sowing": -5})
    assert resp.status_code == 422


# ---------------------------------------------------------------- market

def test_price_endpoint_labels_mock(client, monkeypatch):
    monkeypatch.setattr(settings, "ALLOW_MOCK_MARKET_DATA", True)
    body = client.get("/api/market/price", params={"crop": "soybean"}).json()
    assert body["status"] == "mock"
    assert "MOCK" in body["display"]


def test_price_endpoint_unavailable_when_mock_off(client, monkeypatch):
    monkeypatch.setattr(settings, "ALLOW_MOCK_MARKET_DATA", False)
    body = client.get("/api/market/price", params={"crop": "soybean"}).json()
    assert body["status"] == "unavailable"
    assert body["prices"] is None


def test_unknown_crop_never_priced(client, monkeypatch):
    monkeypatch.setattr(settings, "ALLOW_MOCK_MARKET_DATA", True)
    body = client.get("/api/market/price",
                      params={"crop": "dragonfruit"}).json()
    assert body["status"] == "unavailable"


def test_multi_price_endpoint(client, monkeypatch):
    monkeypatch.setattr(settings, "ALLOW_MOCK_MARKET_DATA", True)
    body = client.get("/api/market/prices",
                      params={"crops": "soybean,wheat"}).json()
    assert set(body["results"].keys()) == {"soybean", "wheat"}


def test_my_crop_price(client, auth):
    resp = client.get("/api/market/my-crop", headers=auth)
    assert resp.status_code == 200
    assert "status" in resp.json()


# ---------------------------------------------------------------- fertilizer

def test_offers_endpoint(client, monkeypatch):
    monkeypatch.setattr(settings, "ALLOW_MOCK_MARKET_DATA", True)
    body = client.get("/api/fertilizer/offers").json()
    assert body["status"] == "mock"
    assert all("MOCK" in o["vendor"] for o in body["offers"])


def test_roi_endpoint_computes(client, auth):
    resp = client.post("/api/fertilizer/roi", headers=auth, json={
        "offer_price": 100, "standard_price": 150, "bags": 10,
        "distance_km": 10, "crop": "default", "acres": 1,
        "crop_price_per_tonne": None,
    })
    assert resp.status_code == 200
    body = resp.json()
    assert body["breakdown"]["purchase_cost"] == 1000.0
    assert body["breakdown"]["transport_cost"] == 500.0
    assert body["breakdown"]["store_savings"] == 500.0
    assert body["profit"] == -1000.0
    assert body["worth_it"] is False


def test_roi_never_uses_mock_price_for_money(client, auth, monkeypatch):
    """A financial figure must never rest on demonstration data.

    ROI now reads the real government mandi feed. With no API key configured
    there is no price, so yield revenue must be counted as ZERO and the
    response must say so — never silently substitute a sample figure.
    """
    monkeypatch.setattr(settings, "DATA_GOV_API_KEY", "")
    resp = client.post("/api/fertilizer/roi", headers=auth, json={
        "offer_price": 320, "standard_price": 400, "bags": 20,
        "distance_km": 10, "crop": "soybean", "acres": 2,
    })
    body = resp.json()
    assert body["crop_price_source"] in ("not_configured", "unavailable", "empty")
    assert body["yield_revenue_counted"] is False
    assert body["breakdown"]["revenue_gain"] == 0.0
    assert any("ZERO" in a or "understates" in a for a in body["assumptions"])


def test_roi_requires_auth(client):
    resp = client.post("/api/fertilizer/roi", json={
        "offer_price": 100, "standard_price": 150, "bags": 1,
        "distance_km": 1})
    assert resp.status_code == 401
