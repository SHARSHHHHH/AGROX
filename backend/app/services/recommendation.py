"""Deterministic rule engine — the source of truth for irrigation, soil,
and status decisions. The LLM never overrides these.

Every function returns a structured result answering:
  what is happening / good or bad / why / what to do / how urgent.
"""

# Crop-specific ideal soil-moisture floors (%). Simplified but realistic.
CROP_MOISTURE_FLOOR = {
    "tomato": 40, "rice": 60, "chilli": 35, "brinjal": 40,
    "onion": 35, "potato": 45, "cucumber": 45, "spinach": 40,
    "default": 38,
}

# Crop-specific NPK optimal ranges (kg/ha-ish demo values): (low, high)
CROP_NPK = {
    "tomato":  {"N": (50, 120), "P": (25, 60), "K": (50, 120), "ph": (6.0, 6.8)},
    "rice":    {"N": (80, 150), "P": (20, 50), "K": (40, 100), "ph": (5.5, 6.5)},
    "chilli":  {"N": (60, 120), "P": (25, 55), "K": (60, 120), "ph": (6.0, 7.0)},
    "default": {"N": (50, 120), "P": (20, 55), "K": (45, 110), "ph": (6.0, 7.0)},
}


def classify_moisture(value: float, crop: str) -> str:
    floor = CROP_MOISTURE_FLOOR.get(crop.lower(), CROP_MOISTURE_FLOOR["default"])
    if value < floor - 12:
        return "VERY LOW"
    if value < floor:
        return "LOW"
    if value <= floor + 25:
        return "OPTIMAL"
    return "HIGH"


def recommend_irrigation(soil_moisture: float, temperature: float, humidity: float,
                         rain_probability: int, crop: str = "default",
                         growth_stage: str = "", soil_type: str = "") -> dict:
    """Core irrigation decision. No single hard-coded threshold — combines
    crop floor + weather + temperature context."""
    crop = (crop or "default").lower()
    floor = CROP_MOISTURE_FLOOR.get(crop, CROP_MOISTURE_FLOOR["default"])
    status = classify_moisture(soil_moisture, crop)

    # Rain overrides: if strong rain expected, delay regardless of moisture
    if rain_probability >= 70:
        return {
            "irrigate": False,
            "duration_min": 0,
            "priority": "LOW",
            "reason": (f"Rain probability is {rain_probability}%. Natural rainfall is "
                       f"expected, so irrigation now would waste water."),
            "status": status,
        }

    deficit = floor - soil_moisture
    if deficit <= 0:
        return {
            "irrigate": False,
            "duration_min": 0,
            "priority": "LOW",
            "reason": (f"Soil moisture ({soil_moisture}%) is adequate for {crop} "
                       f"(target ≥{floor}%). No irrigation needed right now."),
            "status": status,
        }

    # Base duration scales with deficit; hot/dry weather increases it
    duration = 8 + deficit * 0.9
    if temperature >= 35:
        duration += 5
    if humidity < 40:
        duration += 3
    duration = int(min(40, max(8, duration)))

    priority = "CRITICAL" if status == "VERY LOW" else ("HIGH" if deficit > 8 else "MEDIUM")
    reason = (f"Soil moisture is {soil_moisture}% ({status.lower()}) versus a target of "
              f"{floor}% for {crop}. Rain probability is only {rain_probability}%")
    if temperature >= 35:
        reason += f", and temperature is high ({temperature}°C) increasing evaporation"
    reason += f". Irrigate for about {duration} minutes."

    return {
        "irrigate": True,
        "duration_min": duration,
        "priority": priority,
        "reason": reason,
        "status": status,
    }


def _band(value, low, high):
    if value < low * 0.6:
        return "VERY LOW"
    if value < low:
        return "LOW"
    if value <= high:
        return "OPTIMAL"
    if value <= high * 1.4:
        return "HIGH"
    return "VERY HIGH"


def analyze_soil(nitrogen, phosphorus, potassium, ph, crop="default") -> dict:
    ref = CROP_NPK.get((crop or "default").lower(), CROP_NPK["default"])
    n_s = _band(nitrogen, *ref["N"])
    p_s = _band(phosphorus, *ref["P"])
    k_s = _band(potassium, *ref["K"])

    if ph < ref["ph"][0]:
        ph_s = "ACIDIC"
    elif ph > ref["ph"][1]:
        ph_s = "ALKALINE"
    else:
        ph_s = "OPTIMAL"

    warnings, suggestions = [], []
    if n_s in ("LOW", "VERY LOW"):
        warnings.append("Nitrogen is low — leaves may yellow and growth may slow.")
        suggestions.append("Apply a nitrogen source (urea or well-rotted manure).")
    if p_s in ("LOW", "VERY LOW"):
        warnings.append("Phosphorus is low — root and flower development may suffer.")
        suggestions.append("Apply single super phosphate (SSP) or bone meal.")
    if k_s in ("LOW", "VERY LOW"):
        warnings.append("Potassium is low — fruit quality and disease resistance drop.")
        suggestions.append("Apply muriate of potash (MOP) or wood ash.")
    if ph_s == "ACIDIC":
        suggestions.append("Soil is acidic — add agricultural lime to raise pH.")
    elif ph_s == "ALKALINE":
        suggestions.append("Soil is alkaline — add gypsum or organic matter to lower pH.")

    scores = {"OPTIMAL": 2, "HIGH": 1, "LOW": 1, "VERY HIGH": 0, "VERY LOW": 0}
    overall_pts = scores.get(n_s, 1) + scores.get(p_s, 1) + scores.get(k_s, 1)
    overall = "Good" if overall_pts >= 5 else ("Fair" if overall_pts >= 3 else "Poor")

    return {
        "nitrogen": {"value": nitrogen, "status": n_s},
        "phosphorus": {"value": phosphorus, "status": p_s},
        "potassium": {"value": potassium, "status": k_s},
        "ph": {"value": ph, "status": ph_s},
        "overall": overall,
        "warnings": warnings,
        "suggestions": suggestions or ["Soil nutrients look balanced for this crop."],
    }
