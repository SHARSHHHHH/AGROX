"""Fertilizer and manure offers, with a transparent ROI calculation.

TWO HARD RULES
--------------
1. Offer prices are never invented. Same three-state contract as market.py:
   ok / mock / unavailable.

2. The ROI arithmetic is deterministic and fully itemised. The LLM receives the
   finished numbers and may only phrase them. It must never compute, adjust or
   round a figure that a farmer will spend money on.

ROI formula (every term is shown to the farmer):

    revenue_gain = yield_boost_t_per_acre * acres * crop_price_per_tonne
    savings      = (standard_price - offer_price) * bags
    cost         = offer_price * bags + transport
    transport    = distance_km * 2 * rate_per_km   (round trip)
    profit       = revenue_gain + savings - cost

YIELD BOOST CAVEAT
------------------
yield_boost_t_per_acre is the weakest input in this calculation. Organic manure
response varies enormously with soil carbon, rainfall and crop. The defaults
below are conservative placeholders and are labelled as assumptions in the
output. Replace them with trial data from your state agricultural university
before presenting this as financial advice.
"""

import logging
from typing import List, Optional

from app.core.config import settings

log = logging.getLogger("agri.fertilizer")

STATUS_OK = "ok"
STATUS_MOCK = "mock"
STATUS_UNAVAILABLE = "unavailable"

# Default transport assumption for a small tractor-trailer or hired tempo.
DEFAULT_TRANSPORT_RATE_PER_KM = 25.0   # INR per km, one way

# Conservative assumed yield response to a full recommended dose of organic
# manure, in tonnes per acre. LABELLED AS AN ASSUMPTION in every response.
ASSUMED_YIELD_BOOST_T_PER_ACRE = {
    "soybean": 0.08,
    "wheat": 0.12,
    "chickpea": 0.06,
    "maize": 0.15,
    "cotton": 0.10,
    "default": 0.08,
}

_MOCK_OFFERS = [
    {"id": "MOCK-1", "vendor": "MOCK - Indore Organics",
     "product": "Vermicompost", "bag_kg": 50,
     "offer_price": 320.0, "standard_price": 400.0,
     "distance_km": 12.0, "stock_bags": 200},
    {"id": "MOCK-2", "vendor": "MOCK - Bhopal Agro Centre",
     "product": "Farmyard Manure (composted)", "bag_kg": 50,
     "offer_price": 180.0, "standard_price": 220.0,
     "distance_km": 35.0, "stock_bags": 500},
]


async def _fetch_offers_upstream(state: str, product: str) -> Optional[List[dict]]:
    """Real vendor offers. Not wired yet — returns None deliberately.

    Intended source: the platform's own `vendors`/`offers` tables, populated by
    merchants through the vendor portal. Until that portal exists there is no
    honest source of live offers.
    """
    return None


async def get_offers(state: str = "Madhya Pradesh", product: str = "") -> dict:
    """Available manure/fertiliser offers."""
    try:
        upstream = await _fetch_offers_upstream(state, product)
    except Exception as exc:
        log.warning("Offer upstream failed: %s", type(exc).__name__)
        upstream = None

    if upstream:
        return {"status": STATUS_OK, "state": state, "offers": upstream,
                "source": "vendor portal"}

    if settings.ALLOW_MOCK_MARKET_DATA:
        return {
            "status": STATUS_MOCK, "state": state,
            "offers": [dict(o) for o in _MOCK_OFFERS],
            "source": "MOCK SAMPLE DATA — not real vendor offers",
            "warning": ("These are demonstration offers, not real listings. "
                        "Set ALLOW_MOCK_MARKET_DATA=false to disable."),
        }

    return {
        "status": STATUS_UNAVAILABLE, "state": state, "offers": [],
        "message": ("No fertiliser offer source is configured. Offers become "
                    "available once vendors register through the vendor "
                    "portal."),
    }


def calculate_roi(*, offer_price: float, standard_price: float, bags: int,
                  distance_km: float, crop: str = "default",
                  acres: float = 1.0,
                  crop_price_per_tonne: Optional[float] = None,
                  transport_rate_per_km: float = DEFAULT_TRANSPORT_RATE_PER_KM
                  ) -> dict:
    """Itemised, deterministic ROI. Every term is returned, not just the total."""

    bags = max(0, int(bags))
    acres = max(0.0, float(acres))
    distance_km = max(0.0, float(distance_km))

    # --- costs ---
    purchase_cost = round(offer_price * bags, 2)
    transport_cost = round(distance_km * 2 * transport_rate_per_km, 2)
    total_cost = round(purchase_cost + transport_cost, 2)

    # --- savings vs the standard shelf price ---
    per_bag_saving = max(0.0, standard_price - offer_price)
    store_savings = round(per_bag_saving * bags, 2)

    # --- revenue from assumed yield response ---
    boost_per_acre = ASSUMED_YIELD_BOOST_T_PER_ACRE.get(
        crop.lower(), ASSUMED_YIELD_BOOST_T_PER_ACRE["default"])
    extra_tonnes = round(boost_per_acre * acres, 3)

    assumptions = [
        f"Assumed yield response of {boost_per_acre} tonnes per acre for "
        f"{crop}. This is a conservative placeholder, not trial data for your "
        f"field.",
        f"Transport assumed at INR {transport_rate_per_km:.0f} per km, round "
        f"trip over {distance_km:.0f} km.",
    ]

    if crop_price_per_tonne is None:
        revenue_gain = 0.0
        revenue_note = ("Crop price unavailable, so the yield-boost revenue is "
                        "counted as zero. The profit below therefore reflects "
                        "ONLY the purchase saving against transport cost.")
        yield_counted = False
    else:
        revenue_gain = round(extra_tonnes * crop_price_per_tonne, 2)
        revenue_note = (f"Yield-boost revenue uses a crop price of INR "
                        f"{crop_price_per_tonne:,.0f} per tonne.")
        yield_counted = True
        assumptions.append(revenue_note)

    profit = round(revenue_gain + store_savings - total_cost, 2)
    worth_it = profit > 0

    # Break-even distance: how far you could travel before profit hits zero.
    margin_before_transport = revenue_gain + store_savings - purchase_cost
    if transport_rate_per_km > 0 and margin_before_transport > 0:
        break_even_km = round(margin_before_transport / (2 * transport_rate_per_km), 1)
    else:
        break_even_km = 0.0

    return {
        "worth_it": worth_it,
        "profit": profit,
        "currency": "INR",
        "breakdown": {
            "purchase_cost": purchase_cost,
            "transport_cost": transport_cost,
            "total_cost": total_cost,
            "store_savings": store_savings,
            "revenue_gain": revenue_gain,
            "extra_tonnes": extra_tonnes,
            "per_bag_saving": round(per_bag_saving, 2),
            "bags": bags,
            "acres": acres,
            "distance_km": distance_km,
        },
        "yield_revenue_counted": yield_counted,
        "revenue_note": revenue_note,
        "break_even_distance_km": break_even_km,
        "assumptions": assumptions,
        "verdict": (
            f"Buying {bags} bags at INR {offer_price:,.0f} would "
            f"{'gain' if worth_it else 'cost'} about INR {abs(profit):,.0f} "
            f"overall."),
        "disclaimer": ("This is an arithmetic estimate from the figures shown, "
                       "not a guarantee. Yield response varies with soil and "
                       "season."),
    }


def grounded_facts(roi: dict) -> List[str]:
    """Fact lines for the agent. The model phrases these; it never recomputes."""
    b = roi["breakdown"]
    facts = [
        f"ROI verdict: {'PROFITABLE' if roi['worth_it'] else 'NOT PROFITABLE'}",
        f"Net profit: INR {roi['profit']:,.2f}",
        f"Purchase cost: INR {b['purchase_cost']:,.2f} for {b['bags']} bags",
        f"Transport cost: INR {b['transport_cost']:,.2f} "
        f"({b['distance_km']} km round trip)",
        f"Saving vs standard price: INR {b['store_savings']:,.2f}",
    ]

    if roi["yield_revenue_counted"]:
        facts.append(f"Assumed yield-boost revenue: INR "
                     f"{b['revenue_gain']:,.2f} from {b['extra_tonnes']} extra "
                     f"tonnes")
    else:
        facts.append("Yield-boost revenue NOT counted — crop price unavailable. "
                     "Say so explicitly.")

    facts.append(f"Break-even distance: {roi['break_even_distance_km']} km")
    facts.append("These figures are already calculated. Do NOT recalculate, "
                 "adjust or round them.")
    return facts
