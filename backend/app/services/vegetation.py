"""Interpretation of satellite vegetation indices. No network, no Earth Engine.

satellite.py fetches numbers. This module decides what those numbers MEAN for a
farmer, and it does so with arithmetic only — no LLM is consulted anywhere in
this file. The model is later asked to phrase these conclusions in the farmer's
language; it never produces them.

Keeping the two apart matters:

  * satellite.py can be mocked in tests with a plain dict, so every rule below
    is testable without a Google credential or a network call.
  * A wrong Earth Engine answer degrades to "unavailable"; it can never turn
    into a confident but invented recommendation.

WHAT NDVI CAN AND CANNOT TELL YOU
---------------------------------
It measures how much green, photosynthesising canopy is present in a 10 m
pixel. It is genuinely good at: canopy vigour, emergence, within-field
variability, sudden decline, and senescence timing.

It cannot identify a disease, name a pest, measure soil nitrogen in kg/ha, or
predict yield on its own. Every function below is worded to respect that. NDRE
is described as a chlorophyll proxy that flags WHERE to look and WHEN to
consider a top-dressing, never as a fertiliser dose.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

# =====================================================================
# NDVI classification
# =====================================================================

# (upper_bound_exclusive, band, farmer-facing meaning)
NDVI_BANDS: List[Tuple[float, str, str]] = [
    (0.10, "BARE", "Bare soil, water or a freshly prepared field. Almost no "
                   "green canopy is present."),
    (0.20, "VERY LOW", "Very little green cover. Normal just after sowing; a "
                       "concern if the crop should already be established."),
    (0.30, "LOW", "Sparse canopy. Either early growth, poor germination, or a "
                  "stressed crop."),
    (0.45, "MODERATE", "Canopy is developing but has not closed."),
    (0.60, "GOOD", "Healthy, actively growing canopy."),
    (0.75, "VERY GOOD", "Dense, vigorous canopy with good ground cover."),
    (1.01, "EXCELLENT", "Very dense canopy at or near peak vegetative growth."),
]


def classify_ndvi(ndvi: Optional[float]) -> Dict[str, str]:
    """NDVI value -> band label and a plain-language meaning."""
    if ndvi is None:
        return {"band": "UNKNOWN",
                "meaning": "No cloud-free satellite reading is available."}
    for upper, band, meaning in NDVI_BANDS:
        if ndvi < upper:
            return {"band": band, "meaning": meaning}
    return {"band": "EXCELLENT", "meaning": NDVI_BANDS[-1][2]}


# =====================================================================
# Crop phenology — what NDVI SHOULD look like at this point in the cycle
# =====================================================================

# Fraction of the crop cycle -> expected NDVI for a well-managed crop.
# Shape: near-bare at sowing, steep rise through vegetative growth, plateau
# around flowering, decline through grain filling into senescence.
BASE_CURVE: List[Tuple[float, float]] = [
    (0.00, 0.15), (0.08, 0.22), (0.18, 0.38), (0.30, 0.56),
    (0.45, 0.70), (0.60, 0.75), (0.72, 0.70), (0.85, 0.52),
    (0.95, 0.35), (1.00, 0.25),
]

# Multiplier on the curve's peak. Flooded rice closes a very dense canopy;
# chickpea and mustard peak considerably lower even when the crop is perfect.
# Comparing a healthy chickpea against a rice curve would flag it as stressed
# every single season, which is exactly the false alarm that makes farmers
# ignore an advisory.
CROP_VIGOUR: Dict[str, float] = {
    "rice": 1.10, "maize": 1.05, "wheat": 1.00, "soybean": 1.00,
    "groundnut": 0.98, "cotton": 0.98, "pigeonpea": 0.95,
    "chickpea": 0.88, "mustard": 0.85, "lentil": 0.85,
}

# How far below the expected curve counts as a real signal rather than noise.
# Sentinel-2 NDVI over a small field carries roughly +/-0.05 of atmospheric and
# geometric noise; 0.12 keeps false alarms rare.
NDVI_TOLERANCE = 0.12

# A drop this large between two clear passes is not noise.
DECLINE_ALERT = 0.10
DECLINE_SEVERE = 0.20


def expected_ndvi(crop: str, days_after_sowing: Optional[int],
                  duration_days: Optional[int]) -> Optional[float]:
    """Expected NDVI for a healthy crop at this point in its cycle.

    Returns None when we do not know the crop's duration or the sowing date,
    because a comparison against a guessed baseline is worse than no comparison.
    """
    if days_after_sowing is None or not duration_days or duration_days <= 0:
        return None
    if days_after_sowing < 0:
        return None

    fraction = min(1.0, days_after_sowing / float(duration_days))

    value = BASE_CURVE[-1][1]
    for i in range(len(BASE_CURVE) - 1):
        f0, v0 = BASE_CURVE[i]
        f1, v1 = BASE_CURVE[i + 1]
        if f0 <= fraction <= f1:
            span = (f1 - f0) or 1.0
            value = v0 + (v1 - v0) * ((fraction - f0) / span)
            break

    vigour = CROP_VIGOUR.get((crop or "").strip().lower(), 1.0)
    return round(min(0.95, value * vigour), 3)


def phenology_check(*, ndvi: Optional[float], crop: str,
                    days_after_sowing: Optional[int],
                    duration_days: Optional[int]) -> Dict[str, Any]:
    """Compare the measured canopy against the expected growth curve."""
    expected = expected_ndvi(crop, days_after_sowing, duration_days)

    if ndvi is None:
        return {"comparable": False, "expected_ndvi": expected,
                "verdict": "UNKNOWN",
                "note": "No cloud-free satellite reading to compare."}

    if expected is None:
        return {
            "comparable": False, "expected_ndvi": None, "verdict": "UNKNOWN",
            "note": ("Add your crop and sowing date on the Farm Profile to "
                     "compare this reading against the expected growth curve."),
        }

    delta = round(ndvi - expected, 3)
    fraction = min(1.0, (days_after_sowing or 0) / float(duration_days))

    if delta < -DECLINE_SEVERE:
        verdict = "WELL BELOW EXPECTED"
        note = (f"Canopy is far below the {expected:.2f} expected {days_after_sowing} "
                f"days after sowing. Worth walking the field this week.")
    elif delta < -NDVI_TOLERANCE:
        verdict = "BELOW EXPECTED"
        note = (f"Canopy is below the {expected:.2f} typical for this stage. "
                f"Common causes are moisture stress, poor establishment or "
                f"nutrient shortage.")
    elif delta > NDVI_TOLERANCE:
        verdict = "ABOVE EXPECTED"
        note = (f"Canopy is denser than the {expected:.2f} typical for this "
                f"stage — usually a good sign, though in a legume it can also "
                f"mean excess vegetative growth at the cost of pods.")
    else:
        verdict = "ON TRACK"
        note = (f"Canopy matches the {expected:.2f} expected at day "
                f"{days_after_sowing}.")

    return {
        "comparable": True,
        "expected_ndvi": expected,
        "measured_ndvi": ndvi,
        "difference": delta,
        "cycle_fraction": round(fraction, 2),
        "verdict": verdict,
        "note": note,
    }


# =====================================================================
# Within-field uniformity  (drives variable-rate fertiliser advice)
# =====================================================================

CV_UNIFORM = 0.10
CV_PATCHY = 0.20


def uniformity(obs: Dict[str, Any]) -> Dict[str, Any]:
    """How even the canopy is across the field, from the NDVI distribution.

    The coefficient of variation (stddev / mean) is the useful number here
    rather than the raw stddev: a stddev of 0.06 is trivial on a dense 0.75
    canopy and severe on a sparse 0.20 one.
    """
    detail = (obs or {}).get("ndvi_detail") or {}
    mean = detail.get("mean")
    stddev = detail.get("stddev")

    if mean is None or stddev is None or mean <= 0.05:
        return {"available": False,
                "note": "Not enough clear pixels to measure field uniformity."}

    cv = round(stddev / mean, 3)
    p10, p25 = detail.get("p10"), detail.get("p25")
    p75, p90 = detail.get("p75"), detail.get("p90")
    spread = (round(p90 - p10, 3) if p10 is not None and p90 is not None
              else None)

    if cv < CV_UNIFORM:
        level, advice = "UNIFORM", (
            "The canopy is even across the field. A single uniform rate of "
            "top-dressing is appropriate.")
    elif cv < CV_PATCHY:
        level, advice = "SLIGHTLY VARIABLE", (
            "There is mild variation across the field. Walk the weaker corners "
            "before deciding whether they need different treatment.")
    else:
        level, advice = "PATCHY", (
            "The field is markedly uneven. Splitting it into a stronger and a "
            "weaker zone and treating them separately will usually beat a "
            "single blanket rate.")

    return {
        "available": True,
        "coefficient_of_variation": cv,
        "level": level,
        "advice": advice,
        "ndvi_mean": mean,
        "ndvi_stddev": stddev,
        "percentiles": {"p10": p10, "p25": p25, "median": detail.get("median"),
                        "p75": p75, "p90": p90},
        "inner_spread": spread,
        "weak_zone_threshold": p25,
        "strong_zone_threshold": p75,
        "zone_note": (
            f"About a quarter of the field reads below NDVI {p25} and a "
            f"quarter above {p75}." if p25 is not None and p75 is not None
            else "Zone thresholds need a clearer pass."),
        "caveat": ("Uniformity is measured from canopy greenness. It shows "
                   "WHERE the field differs, not WHY. Soil depth, water "
                   "logging, nutrient shortage and pest patches all look "
                   "similar from orbit — confirm on the ground."),
    }


# =====================================================================
# Canopy water status  (drives irrigation advice)
# =====================================================================

def water_stress(obs: Dict[str, Any]) -> Dict[str, Any]:
    """Canopy moisture from NDMI, with an explicit statement of its limits."""
    indices = (obs or {}).get("indices") or {}
    ndmi = indices.get("ndmi")
    ndvi = indices.get("ndvi")

    if ndmi is None:
        return {"available": False, "level": "UNKNOWN",
                "note": "No cloud-free satellite reading of canopy moisture."}

    if ndvi is not None and ndvi < 0.20:
        return {
            "available": True, "ndmi": ndmi, "level": "NOT APPLICABLE",
            "note": ("There is too little canopy for a moisture reading to "
                     "mean anything — this index measures water inside "
                     "leaves, and there are barely any leaves yet."),
            "irrigation_hint": "",
        }

    if ndmi >= 0.35:
        level = "WELL WATERED"
        note = "Canopy water content is high."
        hint = ("No moisture stress is visible from orbit. Follow your sensor "
                "and the weather forecast.")
    elif ndmi >= 0.20:
        level = "ADEQUATE"
        note = "Canopy water content is in the normal range."
        hint = "No satellite evidence of water stress."
    elif ndmi >= 0.05:
        level = "MILD STRESS"
        note = "Canopy water content is on the low side."
        hint = ("Early moisture stress may be developing. Check soil moisture "
                "at root depth before the next irrigation decision.")
    else:
        level = "STRESSED"
        note = "Canopy water content is low."
        hint = ("The canopy looks water-stressed. Confirm with your soil "
                "moisture sensor — if it agrees, irrigation is likely needed.")

    return {
        "available": True, "ndmi": ndmi, "level": level, "note": note,
        "irrigation_hint": hint,
        "caveat": ("This measures water in the leaf canopy, not water in the "
                   "soil. It complements your soil moisture sensor; it does "
                   "not replace it, and it never overrides a pump safety "
                   "block."),
    }


# =====================================================================
# Chlorophyll / nitrogen signal  (drives fertiliser TIMING, never a dose)
# =====================================================================

def nitrogen_signal(obs: Dict[str, Any],
                    phenology: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Red-edge chlorophyll status. Explicitly NOT a fertiliser rate."""
    indices = (obs or {}).get("indices") or {}
    ndre = indices.get("ndre")
    ndvi = indices.get("ndvi")

    if ndre is None or ndvi is None:
        return {"available": False, "level": "UNKNOWN",
                "note": "No cloud-free red-edge reading available."}

    if ndvi < 0.25:
        return {"available": True, "ndre": ndre, "level": "NOT APPLICABLE",
                "note": ("Canopy is too sparse for a chlorophyll reading to "
                         "be meaningful."),
                "action": ""}

    if ndre >= 0.30:
        level = "STRONG"
        note = "Red-edge chlorophyll signal is strong for this canopy density."
        action = "No sign of nitrogen shortage from the satellite."
    elif ndre >= 0.20:
        level = "MODERATE"
        note = "Red-edge chlorophyll signal is moderate."
        action = ("Nothing alarming. If a top-dressing is already planned for "
                  "this stage, keep to it.")
    else:
        level = "WEAK"
        note = ("Red-edge chlorophyll signal is weak relative to how much "
                "canopy is present.")
        action = ("Consistent with a nitrogen shortage. Check leaf colour in "
                  "the field, and consider bringing a planned top-dressing "
                  "forward — but base the RATE on your soil test, not on this "
                  "reading.")

    if phenology and phenology.get("verdict") == "BELOW EXPECTED" and level == "WEAK":
        action += (" The canopy is also behind the expected growth curve, "
                   "which strengthens the case for scouting this week.")

    return {
        "available": True, "ndre": ndre, "ndvi": ndvi, "level": level,
        "note": note, "action": action,
        "caveat": ("Red-edge reflectance tracks leaf chlorophyll. Chlorophyll "
                   "falls with nitrogen shortage, but also with sulphur or "
                   "magnesium shortage, waterlogging, root disease and normal "
                   "senescence. This flags WHERE and WHEN to look. It cannot "
                   "give you a dose in kg per hectare — only a soil or leaf "
                   "test can."),
    }


# =====================================================================
# Change detection  (drives alerts and scouting priority)
# =====================================================================

def detect_change(current: Dict[str, Any],
                  previous: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Compare two observations of the same field."""
    cur_ndvi = (current or {}).get("ndvi")
    prev_ndvi = (previous or {}).get("ndvi")

    if cur_ndvi is None or prev_ndvi is None:
        return {"available": False,
                "note": "Need two clear satellite passes to detect a change."}

    cur_date = ((current.get("observation") or {}).get("date")
                or current.get("date"))
    prev_date = ((previous.get("observation") or {}).get("date")
                 or previous.get("date"))

    days_between = None
    if cur_date and prev_date:
        try:
            from datetime import date as _date
            days_between = (_date.fromisoformat(cur_date)
                            - _date.fromisoformat(prev_date)).days
        except (ValueError, TypeError):
            days_between = None

    delta = round(cur_ndvi - prev_ndvi, 3)

    if delta <= -DECLINE_SEVERE:
        direction, severity = "SHARP DECLINE", "CRITICAL"
        note = ("Canopy greenness has fallen sharply between two clear "
                "passes. Something changed in the field.")
        causes = ["pest or disease outbreak spreading across the field",
                  "waterlogging or flooding after heavy rain",
                  "lodging from wind or hail",
                  "severe moisture stress",
                  "the crop was harvested, cut for fodder, or grazed"]
    elif delta <= -DECLINE_ALERT:
        direction, severity = "DECLINE", "WARNING"
        note = "Canopy greenness has dropped noticeably since the last pass."
        causes = ["early pest or disease pressure",
                  "moisture stress between irrigations",
                  "the crop entering natural senescence",
                  "nutrient shortage"]
    elif delta >= DECLINE_ALERT:
        direction, severity = "GROWTH", "INFO"
        note = "Canopy greenness has increased since the last pass."
        causes = []
    else:
        direction, severity = "STABLE", "INFO"
        note = "Canopy greenness is essentially unchanged since the last pass."
        causes = []

    return {
        "available": True,
        "current_ndvi": cur_ndvi,
        "previous_ndvi": prev_ndvi,
        "change": delta,
        "percent_change": (round(100 * delta / prev_ndvi, 1)
                           if prev_ndvi else None),
        "current_date": cur_date,
        "previous_date": prev_date,
        "days_between": days_between,
        "direction": direction,
        "severity": severity,
        "note": note,
        "possible_causes": causes,
        "caveat": ("The satellite sees THAT the canopy changed, never WHY. "
                   "A drop is a reason to walk the field, not a diagnosis."),
    }


# =====================================================================
# Harvest readiness  (drives machinery booking timing)
# =====================================================================

def harvest_readiness(*, obs: Dict[str, Any], series_points: List[dict],
                      crop: str, days_after_sowing: Optional[int],
                      duration_days: Optional[int]) -> Dict[str, Any]:
    """Is this crop senescing towards harvest?

    Two independent signals must agree before we say "approaching harvest":
    the calendar (days after sowing against the crop's duration) and the
    satellite (NDVI falling away from its seasonal peak, bare soil index
    rising). Either alone is easily fooled — a mid-season pest attack also
    drops NDVI, and a delayed sowing also reaches day 100.
    """
    ndvi = (obs or {}).get("ndvi")
    bsi = ((obs or {}).get("indices") or {}).get("bsi")

    if ndvi is None:
        return {"available": False, "stage": "UNKNOWN",
                "note": "No cloud-free satellite reading available."}
    if not duration_days:
        return {"available": False, "stage": "UNKNOWN",
                "note": ("Set your crop on the Farm Profile so the expected "
                         "duration is known.")}

    values = [p["ndvi"] for p in (series_points or []) if p.get("ndvi") is not None]
    peak = max(values) if values else None
    from_peak = round(ndvi - peak, 3) if peak is not None else None

    calendar_frac = (min(1.5, days_after_sowing / float(duration_days))
                     if days_after_sowing is not None else None)
    calendar_late = calendar_frac is not None and calendar_frac >= 0.85
    senescing = (peak is not None and peak >= 0.45
                 and from_peak is not None and from_peak <= -0.15)

    if calendar_late and senescing:
        stage = "APPROACHING HARVEST"
        note = ("The calendar and the satellite agree: the crop is late in its "
                "cycle and the canopy is drying down. This is the window to "
                "book a harvester and watch the weather.")
        days_est = max(0, int(round(duration_days - (days_after_sowing or 0))))
    elif calendar_late and not senescing:
        stage = "LATE BUT STILL GREEN"
        note = ("The crop is late by the calendar, but the canopy is still "
                "green. Either sowing was later than recorded, or maturity is "
                "running behind. Check the field before booking machinery.")
        days_est = None
    elif senescing and not calendar_late:
        stage = "EARLY DECLINE"
        note = ("The canopy is falling away from its seasonal peak well before "
                "the expected harvest window. Early senescence is usually "
                "stress, disease or moisture shortage — not maturity. Walk the "
                "field.")
        days_est = None
    else:
        stage = "IN GROWTH"
        note = "The crop is still in its growing phase."
        days_est = (max(0, int(round(duration_days - days_after_sowing)))
                    if days_after_sowing is not None else None)

    return {
        "available": True,
        "stage": stage,
        "note": note,
        "current_ndvi": ndvi,
        "season_peak_ndvi": peak,
        "drop_from_peak": from_peak,
        "bare_soil_index": bsi,
        "days_after_sowing": days_after_sowing,
        "expected_duration_days": duration_days,
        "estimated_days_to_harvest": days_est,
        "caveat": ("An indicative window from canopy greenness and the "
                   "calendar. Grain moisture at harvest must be judged in the "
                   "field, not from orbit."),
    }


# =====================================================================
# Land cover sanity check  (onboarding coordinate validation)
# =====================================================================

def land_cover_check(obs: Dict[str, Any],
                     series_points: Optional[List[dict]] = None) -> Dict[str, Any]:
    """Do these coordinates plausibly point at cropland?

    A farmer who taps 'use my location' while standing in their village, or
    mistypes a coordinate, gets every downstream recommendation computed for
    the wrong place — silently. A seasonal greenness cycle is decent evidence
    of cultivation; a permanently flat, low signal is not.
    """
    ndvi = (obs or {}).get("ndvi")
    if ndvi is None:
        return {"checked": False,
                "note": "No cloud-free satellite reading to check against."}

    values = [p["ndvi"] for p in (series_points or []) if p.get("ndvi") is not None]
    seasonal_range = (round(max(values) - min(values), 3)
                      if len(values) >= 4 else None)
    peak = max(values) if values else None

    if seasonal_range is not None and seasonal_range >= 0.25 and (peak or 0) >= 0.45:
        return {
            "checked": True, "verdict": "LIKELY CROPLAND", "confidence": "high",
            "current_ndvi": ndvi, "seasonal_range": seasonal_range,
            "peak_ndvi": peak,
            "note": ("Greenness at this location rises and falls with the "
                     "seasons, which is what cultivated land looks like from "
                     "orbit."),
        }

    if (peak or ndvi) >= 0.45:
        return {
            "checked": True, "verdict": "VEGETATED", "confidence": "medium",
            "current_ndvi": ndvi, "seasonal_range": seasonal_range,
            "peak_ndvi": peak,
            "note": ("Dense vegetation, but without a clear seasonal cycle. "
                     "This could be cropland, an orchard, or permanent "
                     "vegetation such as trees."),
        }

    if ndvi < 0.15 and (peak is None or peak < 0.25):
        return {
            "checked": True, "verdict": "NOT VEGETATED", "confidence": "medium",
            "current_ndvi": ndvi, "seasonal_range": seasonal_range,
            "peak_ndvi": peak,
            "note": ("Almost no green cover here in any month. This may be a "
                     "building, road, water body or bare ground rather than a "
                     "field. Worth checking the pin is on your land."),
        }

    return {
        "checked": True, "verdict": "SPARSE OR FALLOW", "confidence": "low",
        "current_ndvi": ndvi, "seasonal_range": seasonal_range,
        "peak_ndvi": peak,
        "note": ("Sparse green cover. Normal for a fallow field between "
                 "seasons or just after sowing."),
    }


# =====================================================================
# Season anomaly  (evidence for insurance / relief claims)
# =====================================================================

def season_anomaly(series_points: List[dict],
                   current_ndvi: Optional[float] = None) -> Dict[str, Any]:
    """This season's peak greenness against the same field's own history.

    The comparison is the field against ITSELF in earlier months, never
    against a neighbour or a district average, so it says nothing about
    anyone else's land.
    """
    values = [(p["month"], p["ndvi"]) for p in (series_points or [])
              if p.get("ndvi") is not None]

    if len(values) < 6:
        return {"available": False,
                "note": ("At least six months of clear satellite readings are "
                         "needed before this field can be compared with its "
                         "own history.")}

    recent = values[-3:]
    history = values[:-3]
    recent_peak = max(v for _, v in recent)
    history_peak = max(v for _, v in history)
    history_mean = sum(v for _, v in history) / len(history)

    delta = round(recent_peak - history_peak, 3)
    ratio = round(recent_peak / history_peak, 3) if history_peak else None

    if delta <= -0.20:
        level = "SEVERELY BELOW"
        note = ("Recent greenness is far below anything this field reached "
                "earlier in the record.")
    elif delta <= -0.10:
        level = "BELOW"
        note = "Recent greenness is below this field's own earlier peaks."
    elif delta >= 0.10:
        level = "ABOVE"
        note = "Recent greenness is above this field's earlier peaks."
    else:
        level = "NORMAL"
        note = "Recent greenness is in line with this field's own history."

    return {
        "available": True,
        "level": level,
        "note": note,
        "recent_peak_ndvi": round(recent_peak, 3),
        "historical_peak_ndvi": round(history_peak, 3),
        "historical_mean_ndvi": round(history_mean, 3),
        "difference": delta,
        "ratio": ratio,
        "months_compared": len(values),
        "use": ("A shortfall here is supporting evidence when you approach an "
                "agriculture officer or a crop insurance surveyor. It is not "
                "itself a claim, an assessment, or a loss figure."),
        "caveat": ("Compares this field with its own past months only. A low "
                   "reading can also mean the field was left fallow, sown "
                   "late, or planted with a lower-canopy crop."),
    }


# =====================================================================
# Site productivity  (context for the Crop Advisor)
# =====================================================================

def land_productivity(series_points: List[dict]) -> Dict[str, Any]:
    """How much canopy this land has historically supported.

    Deliberately NOT used to reorder the crop ranking. Which crop to sow next
    season is decided by soil, season, rotation, water and price. What history
    adds is context — a plot that has never exceeded NDVI 0.35 will not
    suddenly support a high-input crop, and that is worth saying out loud
    rather than silently down-weighting a score the farmer cannot inspect.
    """
    values = [p["ndvi"] for p in (series_points or []) if p.get("ndvi") is not None]
    if len(values) < 4:
        return {"available": False,
                "note": ("Not enough clear satellite history yet to describe "
                         "this plot's past productivity.")}

    peak = max(values)
    mean = sum(values) / len(values)

    if peak >= 0.70:
        level = "HIGH"
        note = ("This plot has supported a dense canopy in the past, so it can "
                "carry a high-input crop if water and nutrients allow.")
    elif peak >= 0.50:
        level = "MODERATE"
        note = "This plot has supported a moderate canopy in the past."
    elif peak >= 0.30:
        level = "LOW"
        note = ("Canopy on this plot has stayed thin in every month on record. "
                "Check whether water, soil depth or salinity is the limit "
                "before committing to a demanding crop.")
    else:
        level = "VERY LOW"
        note = ("Very little canopy has ever been recorded here. Confirm the "
                "field location is correct before relying on this.")

    return {
        "available": True,
        "level": level,
        "note": note,
        "peak_ndvi": round(peak, 3),
        "mean_ndvi": round(mean, 3),
        "months_observed": len(values),
        "influences_ranking": False,
        "caveat": ("Historical greenness is context, not a yield forecast. It "
                   "does not change the crop ranking, which is computed from "
                   "soil, season, rotation, water and market data."),
    }


# =====================================================================
# Scouting priority  (Plant Health / Pest Management corroboration)
# =====================================================================

def scouting_priority(*, obs: Dict[str, Any],
                      phenology: Optional[Dict[str, Any]] = None,
                      change: Optional[Dict[str, Any]] = None,
                      uniformity_result: Optional[Dict[str, Any]] = None,
                      severity: str = "") -> Dict[str, Any]:
    """How urgently should this field be walked, and where should you start?

    A leaf photo answers "what is wrong with THIS plant". The satellite answers
    "is the rest of the field going the same way". Those two together are worth
    much more than either alone: a confirmed disease on one leaf with a stable,
    uniform canopy is a spot treatment, while the same leaf with a field-wide
    canopy decline is a spreading outbreak.
    """
    reasons: List[str] = []
    score = 0

    if (change or {}).get("available"):
        if change["direction"] == "SHARP DECLINE":
            score += 3
            reasons.append(
                f"Field canopy fell {abs(change['change']):.2f} NDVI between "
                f"satellite passes.")
        elif change["direction"] == "DECLINE":
            score += 2
            reasons.append(
                f"Field canopy is down {abs(change['change']):.2f} NDVI since "
                f"the last pass.")

    if (phenology or {}).get("comparable"):
        if phenology["verdict"] == "WELL BELOW EXPECTED":
            score += 3
            reasons.append("Canopy is well below the expected growth curve.")
        elif phenology["verdict"] == "BELOW EXPECTED":
            score += 2
            reasons.append("Canopy is below the expected growth curve.")

    if (uniformity_result or {}).get("available") and \
            uniformity_result["level"] == "PATCHY":
        score += 1
        reasons.append("Canopy is patchy, so the problem is not field-wide.")

    sev = (severity or "").upper()
    if sev in ("HIGH", "SEVERE", "CRITICAL"):
        score += 3
        reasons.append(f"Photo analysis returned {sev} severity.")
    elif sev in ("MODERATE", "MEDIUM"):
        score += 1
        reasons.append(f"Photo analysis returned {sev} severity.")

    if score >= 5:
        priority, window = "HIGH", "Walk the field within 1-2 days."
    elif score >= 3:
        priority, window = "MEDIUM", "Walk the field within the week."
    elif score >= 1:
        priority, window = "LOW", "Keep to your normal scouting round."
    else:
        priority, window = "ROUTINE", "Nothing unusual visible from orbit."
        reasons.append("Field canopy looks stable and on track.")

    start_here = ""
    u = uniformity_result or {}
    if u.get("available") and u.get("level") == "PATCHY" \
            and u.get("weak_zone_threshold") is not None:
        start_here = (
            f"Start with the weakest parts of the field — roughly the quarter "
            f"reading below NDVI {u['weak_zone_threshold']}.")

    return {
        "priority": priority,
        "score": score,
        "window": window,
        "reasons": reasons,
        "start_here": start_here,
        "caveat": ("Scouting priority combines a leaf photo with field-scale "
                   "canopy behaviour. It ranks urgency; it does not diagnose."),
    }


# =====================================================================
# Alerts
# =====================================================================

def build_alerts(*, obs: Dict[str, Any],
                 phenology: Optional[Dict[str, Any]] = None,
                 change: Optional[Dict[str, Any]] = None,
                 water: Optional[Dict[str, Any]] = None,
                 uniformity_result: Optional[Dict[str, Any]] = None,
                 crop: str = "") -> List[Dict[str, str]]:
    """Alert dicts ready for the existing Alert table. Empty list is normal."""
    out: List[Dict[str, str]] = []
    crop_label = crop or "your crop"

    if (obs or {}).get("status") not in ("ok", "stale"):
        return out

    if (change or {}).get("available") and change["direction"] == "SHARP DECLINE":
        out.append({
            "type": "SATELLITE_NDVI_DROP", "severity": "CRITICAL",
            "title": "Sharp drop in field greenness",
            "message": (
                f"Satellite greenness over your field fell from "
                f"{change['previous_ndvi']} to {change['current_ndvi']} "
                f"between {change['previous_date']} and {change['current_date']}. "
                f"Walk the field and check for pest damage, waterlogging or "
                f"lodging."),
        })
    elif (change or {}).get("available") and change["direction"] == "DECLINE":
        out.append({
            "type": "SATELLITE_NDVI_DECLINE", "severity": "WARNING",
            "title": "Field greenness is falling",
            "message": (
                f"Satellite greenness dropped {abs(change['change'])} NDVI "
                f"since {change['previous_date']}. If {crop_label} is not yet "
                f"near maturity this is worth investigating."),
        })

    if (phenology or {}).get("comparable") and \
            phenology["verdict"] == "WELL BELOW EXPECTED":
        out.append({
            "type": "SATELLITE_BELOW_CURVE", "severity": "WARNING",
            "title": "Crop canopy behind schedule",
            "message": (
                f"Satellite NDVI is {phenology['measured_ndvi']} against "
                f"{phenology['expected_ndvi']} expected for {crop_label} at "
                f"this stage. Check establishment, moisture and nutrition."),
        })

    if (water or {}).get("available") and water["level"] == "STRESSED":
        out.append({
            "type": "SATELLITE_WATER_STRESS", "severity": "WARNING",
            "title": "Canopy looks water stressed",
            "message": (
                f"Satellite canopy moisture (NDMI {water['ndmi']}) is low. "
                f"Confirm against your soil moisture sensor before irrigating."),
        })

    if (uniformity_result or {}).get("available") and \
            uniformity_result["level"] == "PATCHY":
        out.append({
            "type": "SATELLITE_PATCHY_FIELD", "severity": "INFO",
            "title": "Field growth is uneven",
            "message": (
                f"Canopy varies noticeably across the field "
                f"(variation {uniformity_result['coefficient_of_variation']}). "
                f"{uniformity_result['advice']}"),
        })

    return out


# =====================================================================
# Grounded facts for the LLM
# =====================================================================

def grounded_facts(*, obs: Dict[str, Any],
                   phenology: Optional[Dict[str, Any]] = None,
                   water: Optional[Dict[str, Any]] = None,
                   change: Optional[Dict[str, Any]] = None,
                   uniformity_result: Optional[Dict[str, Any]] = None,
                   nitrogen: Optional[Dict[str, Any]] = None) -> List[str]:
    """Fact lines for the agent. The model phrases these; it never adds to them."""
    status = (obs or {}).get("status")

    if status == "not_configured":
        return ["Satellite monitoring is not configured on this server. Say "
                "so plainly if the user asks about it. Do NOT state or guess "
                "any NDVI value."]
    if status == "no_observation":
        return [obs.get("message", "No clear satellite pass was available."),
                "Do NOT state or guess an NDVI value. There is no reading."]
    if status not in ("ok", "stale"):
        return ["Satellite data is temporarily unavailable. Do NOT state or "
                "guess any NDVI value."]

    o = obs.get("observation") or {}
    band = classify_ndvi(obs.get("ndvi"))
    facts = [
        f"SATELLITE (Sentinel-2, {o.get('date')}, {o.get('days_ago')} days "
        f"ago, {int((o.get('clear_pixel_fraction') or 0) * 100)}% cloud-free "
        f"over the field):",
        f"Field NDVI is {obs.get('ndvi')} — {band['band']}. {band['meaning']}",
    ]

    if o.get("is_stale"):
        facts.append(
            f"This reading is {o.get('days_ago')} days old. Say so; do not "
            f"present it as today's condition.")

    if (phenology or {}).get("comparable"):
        facts.append(f"Growth curve check: {phenology['verdict']}. "
                     f"{phenology['note']}")
    if (change or {}).get("available") and change["direction"] != "STABLE":
        facts.append(f"Change since last pass: {change['direction']} "
                     f"({change['change']:+.3f} NDVI). {change['note']}")
    if (water or {}).get("available") and water["level"] not in ("UNKNOWN",):
        facts.append(f"Canopy moisture: {water['level']}. "
                     f"{water.get('irrigation_hint', '')}")
    if (uniformity_result or {}).get("available"):
        facts.append(f"Field uniformity: {uniformity_result['level']}. "
                     f"{uniformity_result['advice']}")
    if (nitrogen or {}).get("available") and nitrogen["level"] == "WEAK":
        facts.append(f"Chlorophyll signal: WEAK. {nitrogen['action']}")

    facts.append(
        "RULES FOR SATELLITE DATA: quote only the NDVI value given above and "
        "state its date. The satellite shows canopy greenness — it cannot "
        "name a disease or pest, cannot measure soil nutrients, and cannot "
        "predict yield. Recommend walking the field to confirm anything "
        "unusual. Never override an irrigation safety block with it.")
    return facts
