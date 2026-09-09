"""Deterministic crop suitability engine for Madhya Pradesh.

Scores candidate crops against measured soil and weather values. Every score is
arithmetic over the reference table below — the LLM is never asked which crop to
grow, only to explain a ranking that was already computed here.

REFERENCE DATA CAVEAT
---------------------
The agronomic ranges below are representative values for MP conditions compiled
for this project. They are NOT a substitute for state agricultural university
recommendations. Before production use, have them reviewed against JNKVV
(Jabalpur) or RVSKVV (Gwalior) published package-of-practices.

MP cropping calendar:
    Kharif  June-October     (monsoon sown)
    Rabi    October-March    (winter sown)
    Zaid    March-June       (summer, irrigated only)
"""

from datetime import date
from typing import Dict, List, Optional

# Madhya Pradesh is India's largest producer of soybean and gram; wheat is the
# dominant rabi crop. These five cover the large majority of MP cropped area.
MP_CROPS: Dict[str, dict] = {
    "soybean": {
        "display": "Soybean",
        "season": ["kharif"],
        "ph": (6.0, 7.5),
        "n": (20, 40),          # legume: fixes its own N, low demand
        "p": (25, 60),
        "k": (40, 100),
        "moisture": (45, 75),
        "temp": (25, 32),
        "duration_days": 95,
        "soil_types": ["black", "clay", "loam", "medium black"],
        "water_need": "medium",
        "notes": "MP's principal kharif crop. Needs well-drained black soil; "
                 "waterlogging for more than two days causes severe yield loss.",
    },
    "wheat": {
        "display": "Wheat",
        "season": ["rabi"],
        "ph": (6.0, 7.5),
        "n": (80, 150),
        "p": (30, 60),
        "k": (40, 100),
        "moisture": (40, 65),
        "temp": (15, 25),
        "duration_days": 130,
        "soil_types": ["black", "loam", "clay loam", "alluvial"],
        "water_need": "high",
        "notes": "Dominant rabi crop. Needs 4-6 irrigations; the crown root "
                 "initiation stage around 21 days is the most critical.",
    },
    "chickpea": {
        "display": "Chickpea (Gram)",
        "season": ["rabi"],
        "ph": (6.0, 8.0),
        "n": (15, 40),          # legume
        "p": (30, 60),
        "k": (40, 90),
        "moisture": (35, 55),
        "temp": (18, 28),
        "duration_days": 110,
        "soil_types": ["black", "clay", "loam", "sandy loam"],
        "water_need": "low",
        "notes": "Drought-tolerant and suited to residual soil moisture. "
                 "Excess irrigation causes vegetative growth at the cost of pods.",
    },
    "maize": {
        "display": "Maize",
        "season": ["kharif", "rabi", "zaid"],
        "ph": (5.5, 7.5),
        "n": (90, 160),
        "p": (30, 70),
        "k": (50, 110),
        "moisture": (50, 75),
        "temp": (21, 30),
        "duration_days": 100,
        "soil_types": ["loam", "sandy loam", "black", "alluvial"],
        "water_need": "medium",
        "notes": "Grows in all three seasons under irrigation. Heavy nitrogen "
                 "feeder; sensitive to moisture stress at tasselling.",
    },

    "rice": {
        "display": "Rice (Paddy)",
        "season": ["kharif"],
        "ph": (5.5, 7.0), "n": (80, 150), "p": (25, 55), "k": (40, 100),
        "moisture": (70, 95), "temp": (22, 32),
        "duration_days": 130, "water_need": "high",
        "soil_types": ["clay", "clay loam", "alluvial", "black"],
        "notes": "Needs standing water or assured irrigation. Not suited to "
                 "well-drained uplands without a reliable canal or borewell.",
    },
    "mustard": {
        "display": "Mustard",
        "season": ["rabi"],
        "ph": (6.0, 7.5), "n": (60, 110), "p": (25, 55), "k": (35, 90),
        "moisture": (35, 60), "temp": (10, 25),
        "duration_days": 120, "water_need": "low",
        "soil_types": ["loam", "sandy loam", "alluvial", "black"],
        "notes": "Low water need, good rabi option where irrigation is limited. "
                 "Sensitive to frost at flowering.",
    },
    "groundnut": {
        "display": "Groundnut",
        "season": ["kharif", "zaid"],
        "ph": (6.0, 7.5), "n": (20, 45), "p": (30, 60), "k": (50, 110),
        "moisture": (45, 70), "temp": (25, 33),
        "duration_days": 110, "water_need": "medium",
        "soil_types": ["sandy loam", "loam", "red", "light black"],
        "notes": "Legume, fixes nitrogen. Needs well-drained light soil; heavy "
                 "clay makes pod development and harvesting difficult.",
    },
    "pigeonpea": {
        "display": "Pigeonpea (Tur)",
        "season": ["kharif"],
        "ph": (6.0, 7.5), "n": (15, 40), "p": (30, 60), "k": (40, 100),
        "moisture": (40, 65), "temp": (25, 32),
        "duration_days": 170, "water_need": "low",
        "soil_types": ["black", "loam", "red", "sandy loam"],
        "notes": "Long duration legume, drought tolerant, deep rooting. "
                 "Occupies the field into the rabi season.",
    },
    "sorghum": {
        "display": "Sorghum (Jowar)",
        "season": ["kharif", "rabi"],
        "ph": (6.0, 8.0), "n": (60, 110), "p": (25, 50), "k": (40, 90),
        "moisture": (35, 60), "temp": (25, 33),
        "duration_days": 110, "water_need": "low",
        "soil_types": ["black", "red", "loam", "sandy loam"],
        "notes": "Highly drought tolerant. A dependable choice on rainfed land "
                 "where maize would fail.",
    },
    "onion": {
        "display": "Onion",
        "season": ["rabi", "kharif"],
        "ph": (6.0, 7.5), "n": (70, 130), "p": (35, 70), "k": (60, 130),
        "moisture": (50, 70), "temp": (15, 28),
        "duration_days": 120, "water_need": "medium",
        "soil_types": ["loam", "sandy loam", "alluvial", "black"],
        "notes": "Needs steady moisture but not waterlogging. Prices are "
                 "volatile, so check the mandi rate before committing area.",
    },
    "potato": {
        "display": "Potato",
        "season": ["rabi"],
        "ph": (5.5, 6.5), "n": (100, 180), "p": (50, 90), "k": (80, 150),
        "moisture": (55, 75), "temp": (15, 24),
        "duration_days": 100, "water_need": "high",
        "soil_types": ["sandy loam", "loam", "alluvial"],
        "notes": "Heavy feeder needing cool weather and assured irrigation. "
                 "Prefers slightly acidic, well-drained soil.",
    },
    "tomato": {
        "display": "Tomato",
        "season": ["rabi", "kharif", "zaid"],
        "ph": (6.0, 7.0), "n": (80, 150), "p": (40, 80), "k": (70, 140),
        "moisture": (55, 75), "temp": (20, 30),
        "duration_days": 120, "water_need": "high",
        "soil_types": ["loam", "sandy loam", "red", "alluvial"],
        "notes": "High value but high risk: needs assured irrigation, staking "
                 "and regular pest scouting for fruit borer.",
    },
    "sugarcane": {
        "display": "Sugarcane",
        "season": ["kharif", "zaid"],
        "ph": (6.0, 7.5), "n": (100, 200), "p": (40, 80), "k": (80, 160),
        "moisture": (60, 85), "temp": (24, 34),
        "duration_days": 330, "water_need": "high",
        "soil_types": ["loam", "clay loam", "alluvial", "black"],
        "notes": "Very long duration and very water hungry. Only viable with a "
                 "reliable water source and a mill within reach.",
    },
    "greengram": {
        "display": "Green Gram (Moong)",
        "season": ["kharif", "zaid"],
        "ph": (6.0, 7.5), "n": (15, 40), "p": (25, 55), "k": (35, 85),
        "moisture": (40, 65), "temp": (25, 35),
        "duration_days": 65, "water_need": "low",
        "soil_types": ["loam", "sandy loam", "black", "red"],
        "notes": "Very short duration legume. Useful as a catch crop between "
                 "two main seasons, and it improves soil nitrogen.",
    },
    "cotton": {
        "display": "Cotton",
        "season": ["kharif"],
        "ph": (6.0, 8.0),
        "n": (60, 120),
        "p": (25, 60),
        "k": (50, 120),
        "moisture": (45, 70),
        "temp": (25, 35),
        "duration_days": 165,
        "soil_types": ["black", "medium black", "deep black", "clay"],
        "water_need": "medium",
        "notes": "Long duration, so it occupies the field through the rabi "
                 "window. Deep black soil with good drainage is essential.",
    },
    # NOTE: "chilli" is deliberately NOT here. It is offered in the onboarding
    # wizard's crop dropdown, but this project holds no reviewed duration/
    # pH/NPK reference data or lifecycle stages for it (see lifecycle.py).
    # Adding a duration number without the same agronomic care as the crops
    # above would be exactly the kind of invented data this module's own
    # docstring warns against — better for previous_crop_check and the
    # lifecycle explorer to both say "we don't know" than to guess.
}

# Weight per factor. pH and season dominate because they are the hardest for a
# farmer to change within one cycle; NPK can be corrected with fertiliser.
WEIGHTS = {
    "season": 30,
    "ph": 20,
    "moisture": 15,
    "temp": 15,
    "npk": 12,
    "soil_type": 8,
}


def current_season(on: Optional[date] = None) -> str:
    """MP cropping season for a given date."""
    month = (on or date.today()).month
    if 6 <= month <= 10:
        return "kharif"
    if month >= 11 or month <= 3:
        return "rabi"
    return "zaid"


def _range_score(value: Optional[float], low: float, high: float) -> float:
    """1.0 inside the range, tapering to 0.0 as it moves outside.

    Returns 0.5 (neutral) when the value is missing, so an absent measurement
    neither rewards nor penalises a crop.
    """
    if value is None:
        return 0.5

    if low <= value <= high:
        return 1.0

    span = max(high - low, 1e-6)
    distance = (low - value) if value < low else (value - high)
    # Fully outside by one full span width scores zero.
    return max(0.0, 1.0 - (distance / span))


def score_crop(crop_key: str, *, ph=None, nitrogen=None, phosphorus=None,
               potassium=None, moisture=None, temperature=None,
               soil_type: str = "", season: str = "") -> dict:
    """Score one crop. Returns score 0-100 plus per-factor reasons."""
    spec = MP_CROPS[crop_key]
    season = (season or current_season()).lower()

    reasons: List[str] = []
    limits: List[str] = []

    # --- season ---
    if season in spec["season"]:
        season_score = 1.0
        reasons.append(f"{spec['display']} is a {'/'.join(spec['season'])} crop "
                       f"and the current season is {season}")
    else:
        season_score = 0.0
        limits.append(f"wrong season — {spec['display']} is grown in "
                      f"{'/'.join(spec['season'])}, not {season}")

    # --- pH ---
    ph_score = _range_score(ph, *spec["ph"])
    if ph is not None:
        if ph_score >= 0.99:
            reasons.append(f"soil pH {ph} is inside the ideal "
                           f"{spec['ph'][0]}-{spec['ph'][1]} range")
        else:
            limits.append(f"soil pH {ph} is outside the ideal "
                          f"{spec['ph'][0]}-{spec['ph'][1]} range")

    # --- moisture / temperature ---
    moisture_score = _range_score(moisture, *spec["moisture"])
    temp_score = _range_score(temperature, *spec["temp"])

    if moisture is not None and moisture_score < 0.99:
        limits.append(f"soil moisture {moisture}% is outside the preferred "
                      f"{spec['moisture'][0]}-{spec['moisture'][1]}% band")
    if temperature is not None and temp_score < 0.99:
        limits.append(f"temperature {temperature}°C is outside the preferred "
                      f"{spec['temp'][0]}-{spec['temp'][1]}°C band")

    # --- NPK (averaged; correctable with fertiliser, so weighted lower) ---
    npk_parts = [
        _range_score(nitrogen, *spec["n"]),
        _range_score(phosphorus, *spec["p"]),
        _range_score(potassium, *spec["k"]),
    ]
    npk_score = sum(npk_parts) / len(npk_parts)

    if nitrogen is not None and npk_parts[0] < 0.8:
        if nitrogen < spec["n"][0]:
            limits.append(f"nitrogen {nitrogen} is below the "
                          f"{spec['n'][0]}-{spec['n'][1]} range — correctable "
                          f"with fertiliser")
        else:
            limits.append(f"nitrogen {nitrogen} is above the "
                          f"{spec['n'][0]}-{spec['n'][1]} range")

    # --- soil type ---
    if soil_type:
        matched = any(t in soil_type.lower() for t in spec["soil_types"])
        soil_score = 1.0 if matched else 0.3
        if matched:
            reasons.append(f"{soil_type} soil suits {spec['display']}")
        else:
            limits.append(f"{spec['display']} prefers "
                          f"{', '.join(spec['soil_types'][:3])} soil")
    else:
        soil_score = 0.5

    total = (
        season_score * WEIGHTS["season"]
        + ph_score * WEIGHTS["ph"]
        + moisture_score * WEIGHTS["moisture"]
        + temp_score * WEIGHTS["temp"]
        + npk_score * WEIGHTS["npk"]
        + soil_score * WEIGHTS["soil_type"]
    )
    score = round(total, 1)

    if score >= 75:
        verdict = "HIGHLY SUITABLE"
    elif score >= 55:
        verdict = "SUITABLE"
    elif score >= 35:
        verdict = "MARGINAL"
    else:
        verdict = "NOT RECOMMENDED"

    return {
        "crop": crop_key,
        "display": spec["display"],
        "score": score,
        "verdict": verdict,
        "season": spec["season"],
        "duration_days": spec["duration_days"],
        "water_need": spec["water_need"],
        "notes": spec["notes"],
        "reasons": reasons,
        "limitations": limits,
        "factor_scores": {
            "season": round(season_score, 2),
            "ph": round(ph_score, 2),
            "moisture": round(moisture_score, 2),
            "temperature": round(temp_score, 2),
            "npk": round(npk_score, 2),
            "soil_type": round(soil_score, 2),
        },
    }


def recommend_crops(*, ph=None, nitrogen=None, phosphorus=None, potassium=None,
                    moisture=None, temperature=None, soil_type: str = "",
                    season: str = "", top_n: int = 5) -> dict:
    """Rank all MP crops for the given conditions, best first."""
    season = (season or current_season()).lower()

    ranked = [
        score_crop(key, ph=ph, nitrogen=nitrogen, phosphorus=phosphorus,
                   potassium=potassium, moisture=moisture,
                   temperature=temperature, soil_type=soil_type, season=season)
        for key in MP_CROPS
    ]
    ranked.sort(key=lambda r: r["score"], reverse=True)

    # Be explicit about how much evidence the ranking actually rests on.
    provided = [n for n, v in (("pH", ph), ("nitrogen", nitrogen),
                               ("phosphorus", phosphorus),
                               ("potassium", potassium),
                               ("soil moisture", moisture),
                               ("temperature", temperature)) if v is not None]

    if len(provided) >= 5:
        confidence = "high"
    elif len(provided) >= 3:
        confidence = "medium"
    else:
        confidence = "low"

    return {
        "season": season,
        "recommendations": ranked[:top_n],
        "best": ranked[0] if ranked else None,
        "data_confidence": confidence,
        "data_used": provided,
        "data_missing": [n for n in ("pH", "nitrogen", "phosphorus",
                                     "potassium", "soil moisture",
                                     "temperature") if n not in provided],
        "disclaimer": (
            "Scores are computed from measured values against representative "
            "Madhya Pradesh ranges. Confirm with your local Krishi Vigyan "
            "Kendra before sowing."),
    }
