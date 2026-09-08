"""data.gov.in mandi price service tests.

The FIXTURE below is a real response captured from
api.data.gov.in on 2026-08-29, not an invented shape. Testing against
fabricated JSON would defeat the purpose — the whole risk with this API is
getting the field names or date format wrong.
"""

import httpx
import pytest

from app.core.config import settings
from app.services import mandi_price as mp

# --- verbatim from the live API, trimmed to 4 records ---------------------
REAL_RESPONSE = {
    "index_name": "9ef84268-d588-465a-a308-a864a43d0070",
    "title": "Current Daily Price of Various Commodities from Various Markets (Mandi)",
    "status": "ok",
    "total": 14396,
    "count": 4,
    "limit": 10,
    "offset": 0,
    "records": [
        {"state": "Tripura", "district": "Dhalai", "market": "Kulai APMC",
         "commodity": "Bottle gourd", "variety": "Bottle Gourd", "grade": "Grade B",
         "arrival_date": "29/08/2026", "min_price": "2000", "max_price": "2500",
         "modal_price": "2300"},
        {"state": "Andhra Pradesh", "district": "Prakasam", "market": "Maddipadu APMC",
         "commodity": "Paddy(Common)", "variety": "B P T", "grade": "FAQ",
         "arrival_date": "29/08/2026", "min_price": "2800", "max_price": "2800",
         "modal_price": "2800"},
        {"state": "Keralam", "district": "Kozhikode(Calicut)", "market": "Mukkom Market",
         "commodity": "Tomato", "variety": "Tomato", "grade": "FAQ",
         "arrival_date": "29/08/2026", "min_price": "1800", "max_price": "2200",
         "modal_price": "2000"},
        {"state": "Keralam", "district": "Kozhikode(Calicut)", "market": "Mukkom Market",
         "commodity": "Carrot", "variety": "Carrot", "grade": "FAQ",
         "arrival_date": "29/08/2026", "min_price": "8000", "max_price": "8300",
         "modal_price": "8200"},
    ],
}


class FakeResponse:
    def __init__(self, status_code=200, payload=None, text=""):
        self.status_code = status_code
        self._payload = payload if payload is not None else {}
        self.text = text or str(self._payload)

    def json(self):
        if self._payload is None:
            raise ValueError("not json")
        return self._payload


class FakeClient:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def get(self, url, params=None):
        self.calls.append({"url": url, "params": params})
        item = self.responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    mp.clear_cache()
    monkeypatch.setattr(settings, "DATA_GOV_API_KEY", "test-key")
    monkeypatch.setattr(settings, "DATA_GOV_RESOURCE_ID", "test-resource")

    async def _no_sleep(_):
        return None
    monkeypatch.setattr(mp.asyncio, "sleep", _no_sleep)
    yield
    mp.clear_cache()


def install(monkeypatch, responses):
    client = FakeClient(responses)
    monkeypatch.setattr(mp.httpx, "AsyncClient", lambda **kw: client)
    return client


# ---------------------------------------------------------------- field mapping


def test_real_response_parses():
    result = mp._build_result(REAL_RESPONSE, "k", use_cache=False)
    assert result["status"] == "ok"
    assert result["count"] == 4
    assert result["total_available"] == 14396


def test_all_real_fields_are_mapped():
    rec = mp.normalise_record(REAL_RESPONSE["records"][2])
    assert rec["state"] == "Keralam"
    assert rec["district"] == "Kozhikode(Calicut)"
    assert rec["market"] == "Mukkom Market"
    assert rec["commodity"] == "Tomato"
    assert rec["variety"] == "Tomato"
    assert rec["grade"] == "FAQ"
    assert rec["min_price"] == 1800.0
    assert rec["max_price"] == 2200.0
    assert rec["modal_price"] == 2000.0
    assert rec["unit"] == "INR/quintal"


def test_ddmmyyyy_date_is_parsed_not_misread():
    """29/08/2026 must become 2026-08-29, not 2026-29-08 or a crash."""
    assert mp.parse_arrival_date("29/08/2026") == "2026-08-29"
    assert mp.parse_arrival_date("01/12/2026") == "2026-12-01"


def test_unparseable_date_returns_none_not_a_guess():
    assert mp.parse_arrival_date("not-a-date") is None
    assert mp.parse_arrival_date("") is None


def test_prices_arrive_as_strings_and_become_floats():
    """The API returns numbers as JSON strings."""
    rec = mp.normalise_record({"modal_price": "2300", "min_price": "2000",
                               "max_price": "2500", "arrival_date": "29/08/2026"})
    assert isinstance(rec["modal_price"], float)
    assert rec["modal_price"] == 2300.0


def test_record_without_price_is_dropped():
    assert mp.normalise_record({"commodity": "Tomato", "modal_price": ""}) is None
    assert mp.normalise_record({"commodity": "Tomato"}) is None


# ---------------------------------------------------------------- filters


@pytest.mark.asyncio
async def test_state_uses_keyword_suffix(monkeypatch):
    """The API exposes state as `state.keyword`; plain `state` returns nothing."""
    client = install(monkeypatch, [FakeResponse(200, REAL_RESPONSE)])
    await mp.fetch_prices(state="Madhya Pradesh")

    params = client.calls[0]["params"]
    assert "filters[state.keyword]" in params
    assert params["filters[state.keyword]"] == "Madhya Pradesh"


@pytest.mark.asyncio
async def test_kerala_alias_maps_to_agmarknet_spelling(monkeypatch):
    """Live data says 'Keralam'. Sending 'Kerala' silently returns nothing."""
    client = install(monkeypatch, [FakeResponse(200, REAL_RESPONSE)])
    await mp.fetch_prices(state="Kerala")
    assert client.calls[0]["params"]["filters[state.keyword]"] == "Keralam"


@pytest.mark.asyncio
async def test_soybean_maps_to_agmarknet_commodity(monkeypatch):
    """AGMARKNET lists 'Soyabean', not 'Soybean'."""
    client = install(monkeypatch, [FakeResponse(200, REAL_RESPONSE)])
    await mp.fetch_prices(commodity="soybean")
    assert client.calls[0]["params"]["filters[commodity]"] == "Soyabean"


@pytest.mark.asyncio
async def test_chickpea_maps_to_bengal_gram(monkeypatch):
    client = install(monkeypatch, [FakeResponse(200, REAL_RESPONSE)])
    await mp.fetch_prices(commodity="chickpea")
    assert "Bengal Gram" in client.calls[0]["params"]["filters[commodity]"]


@pytest.mark.asyncio
async def test_json_format_is_requested(monkeypatch):
    """The API defaults to XML — without format=json parsing fails."""
    client = install(monkeypatch, [FakeResponse(200, REAL_RESPONSE)])
    await mp.fetch_prices()
    assert client.calls[0]["params"]["format"] == "json"


@pytest.mark.asyncio
async def test_district_and_market_filters(monkeypatch):
    client = install(monkeypatch, [FakeResponse(200, REAL_RESPONSE)])
    await mp.fetch_prices(district="indore", market="Indore APMC")
    p = client.calls[0]["params"]
    assert p["filters[district]"] == "Indore"
    assert p["filters[market]"] == "Indore APMC"


@pytest.mark.asyncio
async def test_limit_is_clamped(monkeypatch):
    client = install(monkeypatch, [FakeResponse(200, REAL_RESPONSE)])
    await mp.fetch_prices(limit=99999)
    assert client.calls[0]["params"]["limit"] == 1000


# ---------------------------------------------------------------- failures


@pytest.mark.asyncio
async def test_missing_key_is_reported_not_crashed(monkeypatch):
    monkeypatch.setattr(settings, "DATA_GOV_API_KEY", "")
    out = await mp.fetch_prices(commodity="soybean")
    assert out["status"] == "not_configured"
    assert "DATA_GOV_API_KEY" in out["message"]
    assert out["records"] == []


@pytest.mark.asyncio
async def test_bad_key_is_not_retried(monkeypatch):
    client = install(monkeypatch, [FakeResponse(403, {}, "forbidden")])
    out = await mp.fetch_prices(commodity="soybean")
    assert out["status"] == "unavailable"
    assert "rejected the API key" in out["message"]
    assert len(client.calls) == 1


@pytest.mark.asyncio
async def test_server_error_is_retried(monkeypatch):
    client = install(monkeypatch, [
        FakeResponse(503, {}, "busy"),
        FakeResponse(503, {}, "busy"),
        FakeResponse(200, REAL_RESPONSE),
    ])
    out = await mp.fetch_prices(commodity="tomato")
    assert out["status"] == "ok"
    assert len(client.calls) == 3


@pytest.mark.asyncio
async def test_timeout_gives_up_honestly(monkeypatch):
    install(monkeypatch, [httpx.ReadTimeout("slow")] * 3)
    out = await mp.fetch_prices(commodity="tomato")
    assert out["status"] == "unavailable"
    assert "unavailable" in out["message"].lower()
    assert out["records"] == []


@pytest.mark.asyncio
async def test_malformed_payload_is_rejected(monkeypatch):
    install(monkeypatch, [FakeResponse(200, {"unexpected": True})])
    out = await mp.fetch_prices(commodity="tomato")
    assert out["status"] == "unavailable"
    assert "records" in out["message"]


@pytest.mark.asyncio
async def test_empty_result_is_distinct_from_failure(monkeypatch):
    """No arrivals today is NOT the same as the API being down."""
    install(monkeypatch, [FakeResponse(200, {"records": [], "total": 0})])
    out = await mp.fetch_prices(commodity="soybean", state="Madhya Pradesh")
    assert out["status"] == "empty"
    assert "No mandi price records" in out["message"]


# ---------------------------------------------------------------- caching


@pytest.mark.asyncio
async def test_second_identical_call_is_cached(monkeypatch):
    client = install(monkeypatch, [FakeResponse(200, REAL_RESPONSE)])
    first = await mp.fetch_prices(commodity="tomato")
    second = await mp.fetch_prices(commodity="tomato")

    assert first["cached"] is False
    assert second["cached"] is True
    assert len(client.calls) == 1, "cache did not prevent a second API call"


@pytest.mark.asyncio
async def test_different_filters_are_cached_separately(monkeypatch):
    client = install(monkeypatch, [FakeResponse(200, REAL_RESPONSE),
                                   FakeResponse(200, REAL_RESPONSE)])
    await mp.fetch_prices(commodity="tomato")
    await mp.fetch_prices(commodity="wheat")
    assert len(client.calls) == 2


# ---------------------------------------------------------------- summary


def test_summary_picks_highest_modal_market():
    result = mp._build_result(REAL_RESPONSE, "k", use_cache=False)
    s = mp.summarise(result, "mixed")
    assert s["status"] == "ok"
    assert s["modal_max"] == 8200.0          # carrot
    assert s["modal_min"] == 2000.0          # tomato
    assert s["best_market"]["market"] == "Mukkom Market"
    assert s["latest_date"] == "2026-08-29"


def test_summary_of_unavailable_stays_unavailable():
    s = mp.summarise({"status": "unavailable", "message": "down"}, "soybean")
    assert s["status"] == "unavailable"


def test_facts_forbid_quoting_a_price_when_unavailable():
    facts = " ".join(mp.grounded_facts(
        {"status": "unavailable", "message": "down", "crop": "soybean"}))
    assert "DATA UNAVAILABLE" in facts
    assert "Do NOT state any price" in facts


def test_facts_forbid_inventing_when_available():
    result = mp._build_result(REAL_RESPONSE, "k", use_cache=False)
    facts = " ".join(mp.grounded_facts(mp.summarise(result, "tomato")))
    assert "AGMARKNET" in facts
    assert "Do NOT invent or adjust any price" in facts
    assert "actual selling price varies" in facts


def test_api_key_never_appears_in_output():
    """The key must not leak into anything returned to the browser."""
    result = mp._build_result(REAL_RESPONSE, "k", use_cache=False)
    blob = str(result) + str(mp.summarise(result, "tomato"))
    assert settings.DATA_GOV_API_KEY not in blob
    assert "api-key" not in blob
