"""Biogas feasibility and estimation.

WHAT THIS IS, AND IS NOT
------------------------
This is an agricultural PLANNING aid. It answers "is a biogas plant worth
considering on my farm, and roughly what would it produce?" from figures the
farmer types in.

It is NOT an engineering design tool. It does not size pressure vessels, does
not specify construction, and does not certify anything. Digester geometry,
gas piping and structural work are qualified-professional territory, and every
output here says so.

WHY EVERY NUMBER IS A RANGE
---------------------------
Published gas yields for cattle dung vary by roughly a third depending on
breed, diet, dung freshness, ambient temperature and retention time. A farm in
Indore in January and the same farm in June will not perform alike.

Presenting a single figure like "2.4 m3/day" invites a farmer to treat it as a
specification and spend real money against it. So the engine carries a low and
a high figure throughout, and the API surfaces both.

NO LLM IS CALLED FROM THIS FILE
-------------------------------
Every value is arithmetic over published typical yields. The assistant may
later rephrase these results in the farmer's language; it cannot originate a
quantity, because it is never asked to.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

log = logging.getLogger("agri.biogas")

# ---------------------------------------------------------------- constants
#
# Fresh dung per animal per day, kg. Ranges rather than points: a desi cow and
# a crossbred Holstein differ by more than a factor of two, and most farmers
# will not know which figure applies to them.
DUNG_KG_PER_DAY = {
    "cow":      (8.0, 15.0),
    "buffalo":  (12.0, 20.0),
    "bullock":  (10.0, 18.0),
    "goat":     (0.4, 0.8),
    "poultry":  (0.06, 0.12),
}

# Biogas yield from fresh cattle dung, m3 per kg. Widely published Indian
# figures sit around 0.036-0.042 for a well-run plant at mesophilic
# temperatures; the low end reflects winter and imperfect operation.
GAS_M3_PER_KG_DUNG = (0.030, 0.042)

# Crop residue is a richer feedstock per kg but needs chopping and careful
# mixing, and most small plants are not designed to take much of it. Capped
# below at RESIDUE_MAX_FRACTION.
GAS_M3_PER_KG_RESIDUE = (0.20, 0.35)
RESIDUE_MAX_FRACTION = 0.25      # of total feed mass

# Dung is mixed with roughly equal water to make a pumpable slurry.
WATER_TO_DUNG_RATIO = 1.0

# Digestion removes only a small part of the input mass as gas; most of what
# goes in comes out as digestate. ~90-95% of slurry mass by weight.
DIGESTATE_FRACTION = (0.88, 0.95)

# Standard Indian family-size plant capacities, m3 of gas per day.
# MNRE's small-plant programme covers 1-25 m3/day.
PLANT_SIZES_M3 = [1.0, 2.0, 3.0, 4.0, 6.0, 8.0, 10.0, 15.0, 20.0, 25.0]

# PLANT SIZING IS BY FEEDSTOCK, NOT BY GAS OUTPUT.
#
# This was previously sized from the estimated gas volume, which produced a
# plant roughly three times too large: 78 kg of dung gave a "10 m3" plant when
# the correct answer is 3 m3. Sizing to gas output double-counts, because the
# gas figure is itself derived from the dung.
#
# The established norm is ~25 kg dung + 25 litres water per day per 1 m3/day
# of plant capacity (MNRE / KVIC design practice).
DUNG_KG_PER_M3_PLANT = 25.0

# MNRE eligibility guidance: a beneficiary needs roughly 50-60 m2 of space for
# a small plant anywhere in the 1-25 m3 range. It is not proportional to
# capacity the way the old per-m3 figure assumed.
SMALL_PLANT_SPACE_M2 = (50.0, 60.0)

# Below this there is not enough feedstock for a plant to run stably.
MIN_VIABLE_DUNG_KG_DAY = 20.0

# Cooking gas demand, m3/day per person. Used only to make the output
# meaningful — "2 m3" means nothing to most people.
# MNRE guidance: a 2 m3/day plant meets the cooking fuel needs of a
# 5-member family, i.e. ~0.4 m3 per person per day.
COOKING_M3_PER_PERSON_DAY = 0.40

VERDICT_SUITABLE = "SUITABLE"
VERDICT_POSSIBLE = "POSSIBLE"
VERDICT_NOT_YET = "NOT_YET"


def _rng(low: float, high: float) -> Dict[str, float]:
    return {"low": round(low, 2), "high": round(high, 2),
            "mid": round((low + high) / 2, 2)}


# =====================================================================
# Feedstock
# =====================================================================

def dung_from_livestock(herd: List[dict]) -> Dict[str, Any]:
    """Daily dung from a list of {animal_type, count, dung_kg_per_day?}.

    A farmer-entered figure always wins over the typical range — they can see
    their own shed and we cannot. Which source was used is reported, so the
    confidence of everything downstream is traceable.
    """
    low = high = 0.0
    stated = 0.0
    breakdown = []
    used_farmer_figure = False

    for row in herd or []:
        kind = (row.get("animal_type") or "cow").strip().lower()
        count = int(row.get("count") or 0)
        if count <= 0:
            continue

        given = row.get("dung_kg_per_day")
        if given:
            stated += float(given)
            used_farmer_figure = True
            breakdown.append({"animal_type": kind, "count": count,
                              "kg_per_day": round(float(given), 1),
                              "source": "farmer"})
            continue

        lo, hi = DUNG_KG_PER_DAY.get(kind, DUNG_KG_PER_DAY["cow"])
        low += lo * count
        high += hi * count
        breakdown.append({"animal_type": kind, "count": count,
                          "kg_per_day_range": [round(lo * count, 1),
                                               round(hi * count, 1)],
                          "source": "typical"})

    if stated:
        low += stated
        high += stated

    return {
        "total_kg_per_day": _rng(low, high),
        "breakdown": breakdown,
        "used_farmer_figure": used_farmer_figure,
        "note": ("Based on the figures you entered." if used_farmer_figure else
                 "Estimated from typical dung production per animal. Enter "
                 "your own measured figure for a closer estimate."),
    }


def residue_available_kg(crop: str, area_acres: Optional[float]) -> Dict[str, Any]:
    """Approximate residue mass from one crop's area.

    Residue-to-grain ratios are well documented and reasonably stable per
    crop, so this is a more reliable estimate than the gas figures.
    """
    # (residue tonnes per acre low, high)
    RESIDUE_T_PER_ACRE = {
        "rice": (1.2, 2.0), "wheat": (1.0, 1.6), "maize": (1.2, 2.2),
        "sugarcane": (2.0, 4.0), "cotton": (1.0, 2.0),
        "soybean": (0.8, 1.4), "groundnut": (0.8, 1.5),
        "chickpea": (0.6, 1.1), "pigeonpea": (1.0, 2.0),
        "sorghum": (1.2, 2.2), "greengram": (0.5, 0.9),
        "mustard": (0.7, 1.3), "potato": (0.4, 0.8),
        "onion": (0.2, 0.5), "tomato": (0.5, 1.0),
    }
    key = (crop or "").strip().lower()
    if not area_acres or key not in RESIDUE_T_PER_ACRE:
        return {"available": False,
                "note": "Add the crop and its area to estimate residue."}

    lo, hi = RESIDUE_T_PER_ACRE[key]
    return {
        "available": True, "crop": key, "area_acres": area_acres,
        "residue_kg": _rng(lo * 1000 * area_acres, hi * 1000 * area_acres),
        "note": ("Approximate residue mass for this crop and area. Actual "
                 "quantity depends on variety, yield and how you harvest."),
    }


# =====================================================================
# Feasibility
# =====================================================================

def assess(*, dung_kg_per_day: float, residue_kg_available: float = 0.0,
           water_availability: str = "", space_m2: Optional[float] = None,
           collection_regular: bool = True) -> Dict[str, Any]:
    """Is a small biogas setup worth considering on this farm?

    Deliberately three-way rather than yes/no. Most smallholdings land in
    POSSIBLE — they have the dung but not the water, or the space but not the
    cattle — and telling those farmers a flat "no" would lose the one piece
    of advice that actually helps: what specifically is missing.
    """
    blockers: List[str] = []
    warnings: List[str] = []

    if dung_kg_per_day < MIN_VIABLE_DUNG_KG_DAY:
        blockers.append(
            f"Daily dung of about {round(dung_kg_per_day)} kg is below the "
            f"{int(MIN_VIABLE_DUNG_KG_DAY)} kg a small plant needs to run "
            f"steadily. Roughly 2-3 adult cattle are usually needed.")

    if not collection_regular:
        warnings.append(
            "Dung is not collected regularly. A digester needs feeding most "
            "days — irregular feeding stops gas production.")

    water = (water_availability or "").strip().lower()
    if water in ("scarce", "very limited"):
        blockers.append(
            "Water is scarce. Dung must be mixed with roughly its own volume "
            "of water every day, which is a real additional demand.")
    elif water == "limited":
        warnings.append(
            "Water is limited. Check you can spare roughly the same volume of "
            "water as dung, every day.")

    needed_space = None
    if dung_kg_per_day >= MIN_VIABLE_DUNG_KG_DAY:
        # Sized through the SAME path estimate() uses, including residue.
        # Computing it from dung alone here gave a smaller plant than the
        # estimate screen then recommended, so the two disagreed about how
        # much space the farmer needed.
        needed_space = SMALL_PLANT_SPACE_M2[0]
        if space_m2 is not None and space_m2 < needed_space * 0.7:
            blockers.append(
                f"About {needed_space} m2 is usually needed for a plant this "
                f"size, and you have recorded {space_m2} m2.")
        elif space_m2 is not None and space_m2 < needed_space:
            warnings.append(
                f"Space is tight — roughly {needed_space} m2 is typical for "
                f"this size.")

    if blockers:
        verdict = VERDICT_NOT_YET if len(blockers) > 1 else VERDICT_POSSIBLE
    elif warnings:
        verdict = VERDICT_POSSIBLE
    else:
        verdict = VERDICT_SUITABLE

    reason = {
        VERDICT_SUITABLE: ("Based on the information you provided, your farm "
                           "appears suitable for considering a small biogas "
                           "setup."),
        VERDICT_POSSIBLE: ("Based on the information you provided, a small "
                           "biogas setup may be possible, but some "
                           "requirements need attention first."),
        VERDICT_NOT_YET: ("Based on the information you provided, a biogas "
                          "setup does not look practical on your farm at the "
                          "moment. Composting your dung and residues is "
                          "usually a better first step."),
    }[verdict]

    return {
        "verdict": verdict,
        "reason": reason,
        "blockers": blockers,
        "warnings": warnings,
        "space_needed_m2": needed_space,
        "based_on": {
            "dung_kg_per_day": round(dung_kg_per_day, 1),
            "residue_kg_available": round(residue_kg_available, 1),
            "water_availability": water_availability or "not recorded",
            "space_m2": space_m2,
        },
        "caveat": ("This is a planning indication from the details you "
                   "entered, not an engineering assessment. Before building "
                   "anything, get a site visit from a qualified biogas "
                   "installer or your local KVK."),
    }


def _plant_size_from_dung(dung_kg_per_day: float) -> float:
    """Standard plant size for this much daily feedstock.

    Sized from DUNG, per the ~25 kg/day per m3 design norm — not from the gas
    estimate, which is derived from the same dung and would double-count.
    """
    needed = dung_kg_per_day / DUNG_KG_PER_M3_PLANT
    if needed >= PLANT_SIZES_M3[-1]:
        return PLANT_SIZES_M3[-1]
    # Nearest standard size, not the next one up. 78 kg gives 3.12, which is a
    # 3 m3 plant in practice — rounding up to 4 sells the farmer capacity they
    # cannot feed, and an underfed digester runs badly.
    return min(PLANT_SIZES_M3, key=lambda x: abs(x - needed))


# =====================================================================
# Estimation
# =====================================================================

def estimate(*, dung_kg_per_day: float, residue_kg_per_day: float = 0.0,
             household_size: int = 5) -> Dict[str, Any]:
    """Approximate gas, plant size and digestate. Every figure is a range."""
    # A small digester cannot take unlimited residue: too much fibrous
    # material mats, floats and blocks the outlet.
    max_residue = dung_kg_per_day * RESIDUE_MAX_FRACTION / (1 - RESIDUE_MAX_FRACTION)
    residue_used = min(residue_kg_per_day, max_residue)
    residue_capped = residue_used < residue_kg_per_day

    gas_low = (dung_kg_per_day * GAS_M3_PER_KG_DUNG[0]
               + residue_used * GAS_M3_PER_KG_RESIDUE[0])
    gas_high = (dung_kg_per_day * GAS_M3_PER_KG_DUNG[1]
                + residue_used * GAS_M3_PER_KG_RESIDUE[1])

    water = dung_kg_per_day * WATER_TO_DUNG_RATIO
    slurry = dung_kg_per_day + residue_used + water

    dig_low = slurry * DIGESTATE_FRACTION[0]
    dig_high = slurry * DIGESTATE_FRACTION[1]

    plant = _plant_size_from_dung(dung_kg_per_day)
    cook_people = ((gas_low + gas_high) / 2) / COOKING_M3_PER_PERSON_DAY

    return {
        "daily_feed_kg": _rng(dung_kg_per_day + residue_used,
                              dung_kg_per_day + residue_used),
        "water_needed_litres_per_day": round(water),
        "residue_used_kg_per_day": round(residue_used, 1),
        "residue_capped": residue_capped,
        "residue_cap_note": (
            "Only part of your residue can go into the digester — too much "
            "fibrous material mats together and blocks a small plant. The "
            "rest is better composted or returned to the soil."
            if residue_capped else ""),

        "biogas_m3_per_day": _rng(gas_low, gas_high),
        "suggested_plant_size_m3": plant,
        "plant_size_basis": (
            f"Sized from your {round(dung_kg_per_day)} kg of dung per day, at "
            f"about {int(DUNG_KG_PER_M3_PLANT)} kg per 1 m3 of plant capacity "
            f"(the standard design norm). Final sizing must be confirmed by a "
            f"trained biogas technician against your actual feedstock and site."),
        "space_needed_m2": (f"{int(SMALL_PLANT_SPACE_M2[0])}-"
                            f"{int(SMALL_PLANT_SPACE_M2[1])}"),
        "cooking_equivalent_people": round(cook_people, 1),
        "cooking_note": (
            f"Roughly enough cooking gas for about {round(cook_people)} "
            f"people, against a household of {household_size}."),

        "digestate_kg_per_day": _rng(dig_low, dig_high),
        "digestate_kg_per_month": _rng(dig_low * 30, dig_high * 30),

        "assumptions": {
            "gas_m3_per_kg_dung": list(GAS_M3_PER_KG_DUNG),
            "gas_m3_per_kg_residue": list(GAS_M3_PER_KG_RESIDUE),
            "water_to_dung_ratio": WATER_TO_DUNG_RATIO,
            "digestate_fraction_of_slurry": list(DIGESTATE_FRACTION),
            "residue_max_fraction_of_feed": RESIDUE_MAX_FRACTION,
        },
        "confidence": "ESTIMATED",
        "caveat": (
            "These are approximate planning figures, not guaranteed "
            "production. Real output varies with breed, feed, dung freshness, "
            "temperature and how well the plant is run — a plant produces "
            "noticeably less in winter. Nothing here is measured; measurement "
            "would need sensors on an installed plant."),
    }


# =====================================================================
# Monitoring an existing plant
# =====================================================================
"""
WHY THE STATUS IS WORDS, NOT NUMBERS
------------------------------------
"pH 6.2, 34 C, 12 cm H2O" tells a farmer nothing they can act on. What they
need is: is it healthy, and if not, what do I change today?

So every reading is turned into a plain sentence plus an action. The raw
numbers stay available for anyone who wants them, but they are not the answer.

MANUAL LOGS ARE FIRST-CLASS
---------------------------
Almost no small Indian biogas plant has instruments. A farmer who reports only
"the flame was weak and it smelled sour" is giving genuinely diagnostic
information — sour smell plus weak gas is the classic signature of overfeeding
and acid build-up. The rules below work from those observations alone.
"""

STATUS_HEALTHY = "HEALTHY"
STATUS_ATTENTION = "NEEDS_ATTENTION"
STATUS_PROBLEM = "PROBLEM"
STATUS_UNKNOWN = "UNKNOWN"


def plant_status(logs: List[dict], plant_size_m3: Optional[float] = None
                 ) -> Dict[str, Any]:
    """Interpret recent logs into a status, a sentence and an action."""
    if not logs:
        return {
            "status": STATUS_UNKNOWN,
            "headline": "No readings yet.",
            "action": "Add today's reading to start tracking your plant.",
            "readings_used": 0,
        }

    latest = logs[0]
    gas = (latest.get("gas_level") or "").lower()
    flame = (latest.get("flame_quality") or "").lower()
    smell = (latest.get("smell") or "").lower()
    temp = latest.get("temperature_c")
    ph = latest.get("ph")

    issues: List[Dict[str, str]] = []

    # Sour smell + weak gas is the classic overfeeding / acidification pattern.
    if smell in ("sour", "rotten") and gas in ("low", "none"):
        issues.append({
            "severity": STATUS_PROBLEM,
            "what": "Gas is low and the slurry smells sour.",
            "why": ("This usually means the plant has been fed too much and "
                    "has turned acidic. The bacteria that make gas stop "
                    "working when that happens."),
            "do": ("Stop feeding for 2-3 days, then restart at about half "
                   "your usual amount and build back up slowly."),
        })
    elif gas in ("low", "none") or flame == "weak":
        issues.append({
            "severity": STATUS_ATTENTION,
            "what": "Gas production is lower than usual.",
            "why": ("Common causes are too little feed, feed that is too "
                    "watery, cold weather, or a gas leak."),
            "do": ("Check you fed the usual amount, check the dung-to-water "
                   "mix is about equal, and brush soapy water on the pipe "
                   "joints — bubbles mean a leak."),
        })

    if ph is not None and ph < 6.5:
        issues.append({
            "severity": STATUS_PROBLEM,
            "what": f"Slurry pH is {ph}, which is too acidic.",
            "why": "Gas-producing bacteria need roughly pH 6.8 to 7.5.",
            "do": "Stop feeding for a few days and let it recover.",
        })

    if temp is not None and temp < 20:
        issues.append({
            "severity": STATUS_ATTENTION,
            "what": f"Slurry temperature is {temp}°C, which is cold.",
            "why": ("Gas production drops sharply below about 20°C. This is "
                    "normal in winter and is not a fault."),
            "do": ("Expect less gas until it warms. Covering the dome or "
                   "using slightly warm mixing water helps."),
        })

    if not issues:
        return {
            "status": STATUS_HEALTHY,
            "headline": "Your plant is working normally.",
            "action": "Keep feeding the same amount at the same time each day.",
            "issues": [],
            "readings_used": len(logs),
            "latest_date": latest.get("logged_on"),
        }

    worst = (STATUS_PROBLEM if any(i["severity"] == STATUS_PROBLEM for i in issues)
             else STATUS_ATTENTION)
    return {
        "status": worst,
        "headline": issues[0]["what"],
        "action": issues[0]["do"],
        "issues": issues,
        "readings_used": len(logs),
        "latest_date": latest.get("logged_on"),
    }
