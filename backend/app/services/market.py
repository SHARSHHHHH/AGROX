"""Market price service.

HARD RULE
---------
This service NEVER invents a price. A farmer deciding when to sell on the back
of a fabricated mandi rate can lose real money, so every response is one of
exactly three shapes:

    status="ok"           real data from a configured upstream source
    status="mock"         clearly labelled sample data, dev/demo only
    status="unavailable"  no source configured or upstream failed

The LLM layer is instructed to relay `status` verbatim. There is no code path
that produces a number without a status attached to it.

WIRING A REAL SOURCE
--------------------
India's mandi prices come from Agmarknet via data.gov.in:
    https://api.data.gov.in/resource/9ef84268-d588-465a-a308-a864a43d0070
Register for a key, set MARKET_API_KEY and MARKET_API_URL in .env, and
implement _fetch_upstream() below. Until then this returns "unavailable"
(or MOCK when ALLOW_MOCK_MARKET_DATA=true).
"""

import logging
from datetime import date
from typing import List, Optional

from app.core.config import settings

log = logging.getLogger("agri.market")

STATUS_OK = "ok"
STATUS_MOCK = "mock"
STATUS_UNAVAILABLE = "unavailable"

# Sample rows for demos only. Every field is prefixed MOCK so a label can never
# be mistaken for a real quote, even if the status field is dropped somewhere
# downstream. These are NOT real mandi prices.
_MOCK_ROWS = {
    "soybean": {"min": 4200, "modal": 4650, "max": 4900, "unit": "INR/quintal",
                "mandi": "MOCK - Indore"},
    "wheat":   {"min": 2300, "modal": 2450, "max": 2600, "unit": "INR/quintal",
                "mandi": "MOCK - Bhopal"},
    "chickpea": {"min": 5200, "modal": 5600, "max": 6000, "unit": "INR/quintal",
                 "mandi": "MOCK - Vidisha"},
    "maize":   {"min": 1900, "modal": 2100, "max": 2250, "unit": "INR/quintal",
                "mandi": "MOCK - Chhindwara"},
    "cotton":  {"min": 6800, "modal": 7300, "max": 7800, "unit": "INR/quintal",
                "mandi": "MOCK - Khargone"},
}


def _unavailable(crop: str, reason: str) -> dict:
    return {
        "status": STATUS_UNAVAILABLE,
        "crop": crop,
        "prices": None,
        "message": reason,
        "display": "Price data unavailable",
        "advice": ("Check the current rate at your nearest mandi or on the "
                   "Agmarknet portal before selling."),
    }


async def _fetch_upstream(crop: str, state: str, market: str) -> Optional[dict]:
    """Real data source. Not wired yet — returns None deliberately.

    Implement against data.gov.in Agmarknet here. Returning None (rather than a
    guess) is what makes the "unavailable" path honest.
    """
    if not getattr(settings, "MARKET_API_KEY", ""):
        return None
    # Intentionally unimplemented: a partial implementation that returned
    # approximate numbers would be worse than none.
    return None


async def get_price(crop: str, state: str = "Madhya Pradesh",
                    market: str = "") -> dict:
    """Current market price for one crop."""
    crop_key = (crop or "").strip().lower()
    if not crop_key:
        return _unavailable(crop, "No crop was specified.")

    try:
        upstream = await _fetch_upstream(crop_key, state, market)
    except Exception as exc:
        log.warning("Market upstream failed: %s", type(exc).__name__)
        upstream = None

    if upstream:
        return {"status": STATUS_OK, "crop": crop_key, "prices": upstream,
                "source": "Agmarknet (data.gov.in)",
                "fetched_on": date.today().isoformat(),
                "display": f"{upstream['modal']} {upstream['unit']}"}

    if settings.ALLOW_MOCK_MARKET_DATA and crop_key in _MOCK_ROWS:
        row = dict(_MOCK_ROWS[crop_key])
        return {
            "status": STATUS_MOCK,
            "crop": crop_key,
            "prices": row,
            "source": "MOCK SAMPLE DATA — not a real market quote",
            "fetched_on": date.today().isoformat(),
            "display": f"MOCK {row['modal']} {row['unit']}",
            "warning": ("This is demonstration data, not a real mandi price. "
                        "Set MARKET_API_KEY and implement _fetch_upstream() "
                        "for live rates, or set ALLOW_MOCK_MARKET_DATA=false."),
        }

    return _unavailable(
        crop_key,
        "No market price source is configured. Set MARKET_API_KEY in "
        "backend/.env and implement the Agmarknet fetch in "
        "app/services/market.py.")


async def get_prices(crops: List[str], state: str = "Madhya Pradesh") -> dict:
    """Prices for several crops at once."""
    results = {}
    for crop in crops:
        results[crop.strip().lower()] = await get_price(crop, state)

    statuses = {r["status"] for r in results.values()}
    overall = (STATUS_OK if statuses == {STATUS_OK}
               else STATUS_MOCK if STATUS_MOCK in statuses
               else STATUS_UNAVAILABLE)

    return {"status": overall, "state": state, "results": results}


def grounded_facts(price_result: dict) -> List[str]:
    """Fact lines for the agent's grounded context.

    The status is stated in words so the model cannot quietly present mock or
    missing data as a real price.
    """
    status = price_result.get("status")

    if status == STATUS_UNAVAILABLE:
        return [f"Market price for {price_result.get('crop')}: DATA UNAVAILABLE. "
                f"Tell the farmer the price could not be retrieved and to check "
                f"their local mandi. Do NOT state any price figure."]

    prices = price_result.get("prices") or {}

    if status == STATUS_MOCK:
        return [f"Market price for {price_result.get('crop')}: "
                f"{prices.get('modal')} {prices.get('unit')} "
                f"(MOCK DEMONSTRATION DATA, not a real quote). "
                f"State clearly that this is sample data."]

    return [f"Market price for {price_result.get('crop')}: modal "
            f"{prices.get('modal')} {prices.get('unit')} at "
            f"{prices.get('mandi')} (range {prices.get('min')}-"
            f"{prices.get('max')}). Source: Agmarknet."]
