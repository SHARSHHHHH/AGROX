"""Data.gov.in mandi price service (AGMARKNET).

Resource: "Current Daily Price of Various Commodities from Various Markets"
          9ef84268-d588-465a-a308-a864a43d0070

FIELD NAMES ARE VERIFIED, NOT GUESSED
-------------------------------------
Confirmed against a live response on 2026-08-29 (14,396 records):

    state         keyword
    district      keyword
    market        keyword
    commodity     keyword
    variety       keyword
    grade         keyword
    arrival_date  string, DD/MM/YYYY  <- NOT ISO
    min_price     rupees per quintal
    max_price     rupees per quintal
    modal_price   rupees per quintal

Three quirks that will bite you if unhandled:

1. `arrival_date` is DD/MM/YYYY, so naive ISO parsing fails.
2. The state filter is exposed as `state.keyword`, while district, market and
   commodity are plain names. Using `state` alone silently returns nothing.
3. State spellings are AGMARKNET's, not the common ones — the live response
   returns "Keralam", not "Kerala". STATE_ALIASES below maps these.

SECURITY
--------
DATA_GOV_API_KEY is read from the environment and used only here, server side.
It is never returned in a response body and never reaches the browser.
"""

import asyncio
import logging
import random
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import httpx

from app.core.config import settings

log = logging.getLogger("agri.market.datagov")

BASE_URL = "https://api.data.gov.in/resource"

STATUS_OK = "ok"
STATUS_EMPTY = "empty"
STATUS_UNAVAILABLE = "unavailable"
STATUS_NOT_CONFIGURED = "not_configured"

# AGMARKNET spellings differ from common usage. Verified live: "Keralam".
STATE_ALIASES = {
    "kerala": "Keralam",
    "keralam": "Keralam",
    "orissa": "Odisha",
    "pondicherry": "Pondicherry",
    "uttaranchal": "Uttarakhand",
    "chattisgarh": "Chhattisgarh",
    "madhya pradesh": "Madhya Pradesh",
    "mp": "Madhya Pradesh",
}

# Our internal crop keys -> AGMARKNET commodity names. The API will not match
# "soybean"; the commodity is listed as "Soyabean".
COMMODITY_ALIASES = {
    # --- cereals ---
    "wheat": "Wheat",
    "rice": "Rice",
    "paddy": "Paddy(Dhan)(Common)",
    "maize": "Maize",
    "corn": "Maize",
    "jowar": "Jowar(Sorghum)",
    "sorghum": "Jowar(Sorghum)",
    "bajra": "Bajra(Pearl Millet/Cumbu)",
    "barley": "Barley (Jau)",
    "ragi": "Ragi (Finger Millet)",
    # --- pulses ---
    "chickpea": "Bengal Gram(Gram)(Whole)",
    "gram": "Bengal Gram(Gram)(Whole)",
    "chana": "Bengal Gram(Gram)(Whole)",
    "tur": "Arhar (Tur/Red Gram)(Whole)",
    "arhar": "Arhar (Tur/Red Gram)(Whole)",
    "pigeonpea": "Arhar (Tur/Red Gram)(Whole)",
    "moong": "Green Gram (Moong)(Whole)",
    "greengram": "Green Gram (Moong)(Whole)",
    "urad": "Black Gram (Urd Beans)(Whole)",
    "blackgram": "Black Gram (Urd Beans)(Whole)",
    "masoor": "Masur Dal",
    "lentil": "Masur Dal",
    "peas": "Peas(Dry)",
    # --- oilseeds ---
    "soybean": "Soyabean",
    "soyabean": "Soyabean",
    "soya": "Soyabean",
    "wheat": "Wheat",
    "chickpea": "Bengal Gram(Gram)(Whole)",
    "gram": "Bengal Gram(Gram)(Whole)",
    "chana": "Bengal Gram(Gram)(Whole)",
    "maize": "Maize",
    "corn": "Maize",
    "cotton": "Cotton",
    "rice": "Paddy(Dhan)(Common)",
    "paddy": "Paddy(Dhan)(Common)",
    "tomato": "Tomato",
    "potato": "Potato",
    "onion": "Onion",
    "brinjal": "Brinjal",
    "chilli": "Green Chilli",
    "banana": "Banana",
    "okra": "Bhindi(Ladies Finger)",
    "bhindi": "Bhindi(Ladies Finger)",
    "mustard": "Mustard",
    "sarson": "Mustard",
    "groundnut": "Groundnut",
    "peanut": "Groundnut",
    "sesame": "Sesamum(Sesame,Gingelly,Til)",
    "til": "Sesamum(Sesame,Gingelly,Til)",
    "sunflower": "Sunflower",
    "linseed": "Linseed",
    "castor": "Castor Seed",
    # --- vegetables ---
    "cauliflower": "Cauliflower",
    "cabbage": "Cabbage",
    "carrot": "Carrot",
    "peas_green": "Green Peas",
    "bottlegourd": "Bottle gourd",
    "bittergourd": "Bitter gourd",
    "pumpkin": "Pumpkin",
    "cucumber": "Cucumbar(Kheera)",
    "garlic": "Garlic",
    "ginger": "Ginger(Green)",
    "coriander": "Coriander(Leaves)",
    "spinach": "Spinach",
    "drumstick": "Drumstick",
    "beans": "Beans",
    "cowpea": "Cowpea(Veg)",
    "radish": "Raddish",
    "beetroot": "Beetroot",
    "capsicum": "Capsicum",
    # --- fruits ---
    "mango": "Mango",
    "papaya": "Papaya",
    "guava": "Guava",
    "orange": "Orange",
    "pomegranate": "Pomogranate",
    "grapes": "Grapes",
    "watermelon": "Water Melon",
    "lemon": "Lemon",
    # --- commercial ---
    "sugarcane": "Sugarcane",
    "turmeric": "Turmeric",
    "coriander_seed": "Coriander(Seed)",
    "cumin": "Cummin Seed(Jeera)",
    "jute": "Jute",
    "arecanut": "Arecanut(Betelnut/Supari)",
    "coconut": "Coconut",
}

_cache: Dict[str, Dict[str, Any]] = {}
CACHE_TTL_SECONDS = 900          # mandi data updates at most daily
MAX_ATTEMPTS = 3
RETRY_STATUS = {429, 500, 502, 503, 504}


def canonical_state(state: str) -> str:
    if not state:
        return ""
    return STATE_ALIASES.get(state.strip().lower(), state.strip().title())


def canonical_commodity(crop: str) -> str:
    if not crop:
        return ""
    return COMMODITY_ALIASES.get(crop.strip().lower(), crop.strip().title())


def _cache_key(params: Dict[str, Any]) -> str:
    return "|".join(f"{k}={v}" for k, v in sorted(params.items()) if k != "api-key")


def _from_cache(key: str) -> Optional[Dict[str, Any]]:
    hit = _cache.get(key)
    if not hit:
        return None
    if time.time() - hit["cached_at"] > CACHE_TTL_SECONDS:
        _cache.pop(key, None)
        return None
    out = dict(hit["payload"])
    out["cached"] = True
    out["cache_age_s"] = round(time.time() - hit["cached_at"])
    return out


def parse_arrival_date(raw: str) -> Optional[str]:
    """DD/MM/YYYY -> ISO. Returns None rather than guessing on odd input."""
    if not raw:
        return None
    for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y"):
        try:
            return datetime.strptime(raw.strip(), fmt).date().isoformat()
        except ValueError:
            continue
    return None


def _to_float(value: Any) -> Optional[float]:
    try:
        return float(str(value).strip())
    except (TypeError, ValueError):
        return None


def normalise_record(rec: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Map one API record onto our schema. Drops records with no usable price."""
    modal = _to_float(rec.get("modal_price"))
    if modal is None:
        return None

    iso = parse_arrival_date(rec.get("arrival_date", ""))
    return {
        "state": rec.get("state", ""),
        "district": rec.get("district", ""),
        "market": rec.get("market", ""),
        "commodity": rec.get("commodity", ""),
        "variety": rec.get("variety", ""),
        "grade": rec.get("grade", ""),
        "arrival_date": iso,
        "arrival_date_raw": rec.get("arrival_date", ""),
        "min_price": _to_float(rec.get("min_price")),
        "max_price": _to_float(rec.get("max_price")),
        "modal_price": modal,
        "unit": "INR/quintal",
    }


def _unavailable(status: str, message: str, **extra) -> Dict[str, Any]:
    out = {
        "status": status,
        "records": [],
        "count": 0,
        "source": "data.gov.in AGMARKNET",
        "message": message,
    }
    out.update(extra)
    return out


async def fetch_prices(
    *,
    state: str = "",
    district: str = "",
    market: str = "",
    commodity: str = "",
    arrival_date: str = "",
    limit: int = 50,
    offset: int = 0,
    use_cache: bool = True,
) -> Dict[str, Any]:
    """Query the mandi price API. Never raises; returns a status field."""

    if not settings.DATA_GOV_API_KEY:
        return _unavailable(
            STATUS_NOT_CONFIGURED,
            "DATA_GOV_API_KEY is not set in backend/.env. Register free at "
            "https://data.gov.in to obtain one.")

    resource = settings.DATA_GOV_RESOURCE_ID
    if not resource:
        return _unavailable(
            STATUS_NOT_CONFIGURED,
            "DATA_GOV_RESOURCE_ID is not set in backend/.env.")

    params: Dict[str, Any] = {
        "api-key": settings.DATA_GOV_API_KEY,
        "format": "json",          # default is XML
        "limit": max(1, min(int(limit), 1000)),
        "offset": max(0, int(offset)),
    }

    # The state filter is exposed as `state.keyword`; the rest are plain.
    if state:
        params["filters[state.keyword]"] = canonical_state(state)
    if district:
        params["filters[district]"] = district.strip().title()
    if market:
        params["filters[market]"] = market.strip()
    if commodity:
        params["filters[commodity]"] = canonical_commodity(commodity)
    if arrival_date:
        params["filters[arrival_date]"] = arrival_date.strip()

    key = _cache_key(params)
    if use_cache:
        cached = _from_cache(key)
        if cached:
            log.debug("mandi cache hit: %s", key)
            return cached

    url = f"{BASE_URL}/{resource}"
    timeout = httpx.Timeout(connect=5.0, read=20.0, write=10.0, pool=5.0)
    last_error = ""

    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                resp = await client.get(url, params=params)
        except httpx.TimeoutException:
            last_error = "data.gov.in did not respond within the timeout"
        except httpx.HTTPError as exc:
            last_error = f"could not reach data.gov.in ({type(exc).__name__})"
        else:
            if resp.status_code == 200:
                try:
                    payload = resp.json()
                except ValueError:
                    last_error = "data.gov.in returned a non-JSON response"
                    break
                return _build_result(
                    payload, key, use_cache,
                    commodity=canonical_commodity(commodity) if commodity else "",
                    state=canonical_state(state) if state else "",
                    district=district.strip().title() if district else "")

            if resp.status_code in (401, 403):
                return _unavailable(
                    STATUS_UNAVAILABLE,
                    f"data.gov.in rejected the API key (HTTP {resp.status_code}). "
                    f"Check DATA_GOV_API_KEY in backend/.env.")

            last_error = f"data.gov.in returned HTTP {resp.status_code}"
            if resp.status_code not in RETRY_STATUS:
                break

        if attempt < MAX_ATTEMPTS:
            delay = (2 ** (attempt - 1)) * 0.5
            delay += random.uniform(0, delay)
            log.warning("mandi attempt %d/%d failed (%s); retry in %.1fs",
                        attempt, MAX_ATTEMPTS, last_error, delay)
            await asyncio.sleep(delay)

    log.error("mandi fetch failed: %s", last_error)
    return _unavailable(
        STATUS_UNAVAILABLE,
        f"Live mandi price is currently unavailable ({last_error}). "
        f"Please check your local mandi or the AGMARKNET portal.")


def _matches(rec: Dict[str, Any], commodity: str, state: str,
             district: str) -> bool:
    """Client-side verification of the server-side filter.

    data.gov.in silently ignores a filter it cannot apply and returns the
    UNFILTERED feed instead of an error. That is why every crop was showing
    the same price: the response was simply the first N rows of everything.

    Re-checking here guarantees a caller asking for Soyabean never receives
    Carrot rows, whatever the API decided to do with the filter.
    """
    if commodity:
        want = commodity.strip().lower()
        got = str(rec.get("commodity", "")).strip().lower()
        # Substring both ways: "Paddy(Dhan)(Common)" vs "Paddy(Common)".
        if want not in got and got not in want:
            return False
    if state:
        if str(rec.get("state", "")).strip().lower() != state.strip().lower():
            return False
    if district:
        if str(rec.get("district", "")).strip().lower() != district.strip().lower():
            return False
    return True


def _build_result(payload: Dict[str, Any], cache_key: str,
                  use_cache: bool, *, commodity: str = "", state: str = "",
                  district: str = "") -> Dict[str, Any]:
    """Validate and normalise an API payload."""
    if not isinstance(payload, dict):
        return _unavailable(STATUS_UNAVAILABLE,
                            "data.gov.in returned an unexpected response shape.")

    raw_records = payload.get("records")
    if not isinstance(raw_records, list):
        return _unavailable(STATUS_UNAVAILABLE,
                            "data.gov.in response contained no 'records' array.")

    verified = [x for x in raw_records
                if isinstance(x, dict) and _matches(x, commodity, state, district)]

    dropped = len(raw_records) - len(verified)
    if dropped:
        log.info("mandi: dropped %d row(s) the server filter did not apply",
                 dropped)

    records = [r for r in (normalise_record(x) for x in verified)
               if r is not None]

    if not records:
        return _unavailable(
            STATUS_EMPTY,
            "No mandi price records match this crop and location today. "
            "Prices are only published for markets that reported arrivals.",
            total_available=payload.get("total"))

    result = {
        "status": STATUS_OK,
        "records": records,
        "count": len(records),
        "total_available": payload.get("total"),
        "source": "data.gov.in AGMARKNET",
        "unit": "INR/quintal",
        "cached": False,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "disclaimer": ("These are wholesale mandi rates reported to AGMARKNET. "
                       "The price you actually receive depends on quality, "
                       "quantity, grading and negotiation."),
    }

    if use_cache:
        _cache[cache_key] = {"cached_at": time.time(), "payload": result}
    return result


def summarise(result: Dict[str, Any], crop: str = "") -> Dict[str, Any]:
    """Reduce many market rows to one headline figure plus the best market.

    Deterministic arithmetic — no model involvement.
    """
    if result.get("status") != STATUS_OK or not result.get("records"):
        return {"status": result.get("status", STATUS_UNAVAILABLE),
                "message": result.get("message", ""), "crop": crop}

    records = result["records"]
    modals = [r["modal_price"] for r in records if r["modal_price"] is not None]
    best = max(records, key=lambda r: r["modal_price"])

    dates = sorted({r["arrival_date"] for r in records if r["arrival_date"]})

    return {
        "status": STATUS_OK,
        "crop": crop or records[0]["commodity"],
        "markets_reporting": len(records),
        "modal_min": min(modals),
        "modal_max": max(modals),
        "modal_avg": round(sum(modals) / len(modals), 2),
        "unit": "INR/quintal",
        "best_market": {
            "market": best["market"],
            "district": best["district"],
            "state": best["state"],
            "modal_price": best["modal_price"],
            "min_price": best["min_price"],
            "max_price": best["max_price"],
            "arrival_date": best["arrival_date"],
        },
        "latest_date": dates[-1] if dates else None,
        "cached": result.get("cached", False),
        "source": result["source"],
        "disclaimer": result["disclaimer"],
    }


def grounded_facts(summary: Dict[str, Any]) -> List[str]:
    """Fact lines for the agent. Status is stated in words so the model cannot
    present missing data as a real price."""
    if summary.get("status") != STATUS_OK:
        return [f"Mandi price for {summary.get('crop') or 'this crop'}: "
                f"DATA UNAVAILABLE. {summary.get('message', '')} "
                f"Tell the farmer the live price could not be retrieved and to "
                f"check their local mandi. Do NOT state any price figure."]

    b = summary["best_market"]
    return [
        f"Mandi price source: data.gov.in AGMARKNET (real government data).",
        f"Crop: {summary['crop']}",
        f"{summary['markets_reporting']} market(s) reporting on "
        f"{summary['latest_date']}",
        f"Modal price range across markets: INR {summary['modal_min']:.0f} to "
        f"{summary['modal_max']:.0f} per quintal (average "
        f"{summary['modal_avg']:.0f})",
        f"Highest modal price: INR {b['modal_price']:.0f} at {b['market']}, "
        f"{b['district']}, {b['state']}",
        "These figures are already retrieved. Do NOT invent or adjust any "
        "price. State clearly that the actual selling price varies with "
        "quality, quantity and negotiation.",
    ]


async def fetch_bulk_by_commodity(
    commodities: List[str], *, state: str = "", limit: int = 1000
) -> Dict[str, Dict[str, Any]]:
    """Prices for many crops in ONE API call, grouped by our crop key.

    The advisory engine previously looped over crops and issued a separate
    request per crop, each with up to 3 retries. Five crops meant up to
    fifteen sequential HTTP calls before the farmer saw anything, which is
    both very slow and the fastest way to hit a rate limit — the "server
    busy" symptom.

    One wide request filtered by state, grouped locally, is dramatically
    faster and far kinder to the API.
    """
    wanted = {c: canonical_commodity(c) for c in commodities}

    raw = await fetch_prices(state=state, limit=limit)

    out: Dict[str, Dict[str, Any]] = {}
    if raw.get("status") != STATUS_OK:
        for key in commodities:
            out[key] = {"status": raw.get("status", STATUS_UNAVAILABLE),
                        "message": raw.get("message", ""), "crop": key}
        return out

    records = raw["records"]
    for key, api_name in wanted.items():
        want = api_name.strip().lower()
        subset = [r for r in records
                  if want in r["commodity"].strip().lower()
                  or r["commodity"].strip().lower() in want]
        if subset:
            out[key] = summarise({**raw, "records": subset}, key)
        else:
            out[key] = {
                "status": STATUS_EMPTY, "crop": key,
                "message": f"No mandi reported {api_name} in this state today.",
            }
    return out


def clear_cache() -> None:
    _cache.clear()
