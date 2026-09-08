"""Crop advisory engine.

Combines every real signal we have into one ranked recommendation:

    soil (measured or manual)
  + weather (Open-Meteo, live)
  + rotation (previous crop)
  + market (data.gov.in AGMARKNET, live)
        -> deterministic score -> ranked crops -> LLM explains

The score is arithmetic. The LLM never sees a crop until it has already been
ranked, and cannot reorder the result.

HONEST NAMING
-------------
The output field is `advisory_suitability_score`, never "best crop" or
"guaranteed yield". It is an advisory signal computed from the data available,
and every response says so.

DATA PROVENANCE
---------------
Each input is tagged SENSOR / MANUAL / LIVE_API / ESTIMATED / MISSING so the
farmer can see what the advice actually rests on. Estimated values are never
presented as measured.
"""

import asyncio
import logging
from typing import Any, Dict, List, Optional

from app.core.config import settings
from app.services import mandi_price, rotation
from app.services.crop_suitability import MP_CROPS, current_season, score_crop

log = logging.getLogger("agri.advisor")

# How much each signal contributes on top of the agronomic base score.
# Agronomy dominates deliberately: a crop that will not grow well is not made
# a good idea by a high price.
AGRONOMY_WEIGHT = 0.70
ROTATION_WEIGHT = 0.18
MARKET_WEIGHT = 0.12

SOURCE_SENSOR = "SENSOR"
SOURCE_MANUAL = "MANUAL"
SOURCE_LIVE = "LIVE_API"
SOURCE_SATELLITE = "SATELLITE"
SOURCE_ESTIMATED = "ESTIMATED"
SOURCE_MISSING = "MISSING"


def _water_fit(crop_spec: dict, irrigation: str, water_source: str,
               rain_mm: Optional[float]) -> tuple:
    """Can this farmer actually water this crop? Returns (0-1, reason)."""
    need = crop_spec["water_need"]
    src = (water_source or "").strip().lower()
    irr = (irrigation or "").strip().lower()

    assured = any(k in src for k in ("borewell", "canal", "tank", "well")) or \
              any(k in irr for k in ("drip", "sprinkler", "flood", "furrow"))

    if need == "high" and not assured:
        return 0.25, (
            f"{crop_spec['display']} needs high water but no assured "
            f"irrigation source is recorded. On rainfed land this is risky.")
    if need == "high" and assured:
        return 1.0, f"Assured irrigation is available for a high-water crop."
    if need == "low":
        return 1.0, f"{crop_spec['display']} has low water needs and suits rainfed land."
    if not assured and rain_mm is not None and rain_mm < 20:
        return 0.5, "Medium water need with no assured irrigation and little forecast rain."
    return 0.85, f"{crop_spec['display']} has medium water needs, which look manageable."


async def build_advisory(
    *,
    state: str = "",
    district: str = "",
    soil: Optional[Dict[str, Any]] = None,
    soil_source: str = SOURCE_MISSING,
    weather: Optional[Dict[str, Any]] = None,
    previous_crop: str = "",
    irrigation_type: str = "",
    water_source: str = "",
    soil_type: str = "",
    season: str = "",
    land_size_acres: Optional[float] = None,
    include_market: bool = True,
    satellite: Optional[Dict[str, Any]] = None,
    top_n: int = 0,          # 0 = return every crop scored
) -> Dict[str, Any]:
    """Produce a ranked crop advisory. Never raises on missing inputs."""

    soil = soil or {}
    weather = weather or {}
    season = (season or current_season()).lower()

    ph = soil.get("ph")
    n, p, k = soil.get("nitrogen"), soil.get("phosphorus"), soil.get("potassium")
    moisture = soil.get("moisture")
    temperature = weather.get("temperature")
    rain_mm = weather.get("rain_mm")

    # --- provenance, so nothing estimated is shown as measured -----------
    provenance = {
        "soil": soil_source if soil else SOURCE_MISSING,
        "weather": SOURCE_LIVE if weather else SOURCE_MISSING,
        "previous_crop": SOURCE_MANUAL if previous_crop else SOURCE_MISSING,
        "market": SOURCE_MISSING,
        "satellite": (SOURCE_SATELLITE
                      if (satellite or {}).get("status") in ("ok", "stale")
                      else SOURCE_MISSING),
    }

    # --- market data, fetched once for all candidates --------------------
    # ONE bulk call for every candidate crop, not one call per crop.
    #
    # This used to loop over crops issuing a separate request each, with up to
    # 3 retries apiece — up to 15 sequential HTTP round trips before the
    # farmer saw anything. That was the slowness AND the rate-limit
    # ("server busy") problem in one.
    #
    # HARD BUDGET. data.gov.in is slow and flaky, and the fetch retries three
    # times at a 20s read timeout — up to ~65 seconds. Market price is a 12%
    # weight in the ranking; it is not worth a minute of a farmer staring at a
    # spinner. Past the budget the advisory is produced from soil, season,
    # rotation and water alone, and provenance says market data was missing so
    # nothing silently pretends otherwise.
    market_by_crop: Dict[str, Any] = {}
    if include_market and not settings.DEMO_FAST_MODE:
        try:
            market_by_crop = await asyncio.wait_for(
                mandi_price.fetch_bulk_by_commodity(
                    list(MP_CROPS.keys()), state=state, limit=1000),
                timeout=settings.ADVISOR_MARKET_BUDGET_S)
        except asyncio.TimeoutError:
            log.info("mandi lookup exceeded %ss budget; ranking without it",
                     settings.ADVISOR_MARKET_BUDGET_S)
            market_by_crop = {}
        except Exception as exc:                  # never break the advisory
            log.warning("bulk mandi lookup failed: %s", exc)
            market_by_crop = {}

        if any(v.get("status") == "ok" for v in market_by_crop.values()):
            provenance["market"] = SOURCE_LIVE

    # Normalise market prices across candidates so one crop's higher rupee
    # value does not automatically win — we compare each crop against the
    # spread of all crops, not against absolute rupees.
    modals = [v["modal_avg"] for v in market_by_crop.values()
              if v.get("status") == "ok" and v.get("modal_avg")]
    m_lo, m_hi = (min(modals), max(modals)) if modals else (0.0, 0.0)

    results: List[Dict[str, Any]] = []

    for crop_key, spec in MP_CROPS.items():
        agro = score_crop(
            crop_key, ph=ph, nitrogen=n, phosphorus=p, potassium=k,
            moisture=moisture, temperature=temperature,
            soil_type=soil_type, season=season)

        rot_score, rot_reason = rotation.score_rotation(previous_crop, crop_key)
        water_score, water_reason = _water_fit(
            spec, irrigation_type, water_source, rain_mm)

        summary = market_by_crop.get(crop_key, {})
        if summary.get("status") == "ok" and m_hi > m_lo:
            market_score = (summary["modal_avg"] - m_lo) / (m_hi - m_lo)
            market_note = (
                f"Live mandi average INR {summary['modal_avg']:.0f}/quintal "
                f"across {summary['markets_reporting']} market(s). Best: "
                f"{summary['best_market']['market']} at "
                f"INR {summary['best_market']['modal_price']:.0f}.")
        elif summary.get("status") == "empty":
            market_score = 0.5
            market_note = ("No mandi reported arrivals of this crop today, so "
                           "no live price is available.")
        else:
            market_score = 0.5
            market_note = "Live mandi price is currently unavailable for this crop."

        # Agronomy score is 0-100; water gates it rather than adding to it,
        # because you cannot grow a thirsty crop without water however good
        # the soil is.
        agronomy_component = (agro["score"] / 100.0) * water_score

        total = 100.0 * (
            AGRONOMY_WEIGHT * agronomy_component
            + ROTATION_WEIGHT * rot_score
            + MARKET_WEIGHT * market_score
        )
        total = round(total, 1)

        risks: List[str] = []
        if agro["verdict"] == "NOT RECOMMENDED":
            risks.append(f"Agronomic fit is poor: {'; '.join(agro['limitations'][:2])}")
        if water_score < 0.5:
            risks.append(water_reason)
        if rot_score <= rotation.ROTATION_POOR:
            risks.append(rot_reason)
        if summary.get("status") != "ok":
            risks.append("No live market price to check profitability against.")
        if not soil:
            risks.append("No soil test recorded, so nutrient fit is unverified.")

        results.append({
            "crop": crop_key,
            "display": spec["display"],
            "advisory_suitability_score": total,
            "verdict": agro["verdict"],
            "reasons": (agro["reasons"] + [rot_reason, water_reason])[:5],
            "soil_fit": {
                "score": round(agro["factor_scores"]["ph"] * 100),
                "npk_score": round(agro["factor_scores"]["npk"] * 100),
                "note": ("Soil values were provided."
                         if soil else "No soil data provided; treated as neutral."),
                "limitations": agro["limitations"],
            },
            "weather_fit": {
                "score": round(agro["factor_scores"]["temperature"] * 100),
                "note": (f"Current temperature {temperature}°C."
                         if temperature is not None
                         else "No live temperature available."),
            },
            "water_requirement": {
                "need": spec["water_need"],
                "score": round(water_score * 100),
                "note": water_reason,
            },
            "rotation_fit": {
                "score": round(rot_score * 100),
                "note": rot_reason,
            },
            "market_information": {
                "status": summary.get("status", "unavailable"),
                "note": market_note,
                "modal_avg": summary.get("modal_avg"),
                "unit": "INR/quintal",
                "best_market": summary.get("best_market"),
                "latest_date": summary.get("latest_date"),
            },
            "risks": risks,
            "duration_days": spec["duration_days"],
            "notes": spec["notes"],
        })

    results.sort(key=lambda r: r["advisory_suitability_score"], reverse=True)

    for r in results:
        r["alternatives"] = [x["display"] for x in results
                             if x["crop"] != r["crop"]][:2]

    # Be explicit about how much evidence this rests on.
    provided = [name for name, v in (
        ("soil pH", ph), ("nitrogen", n), ("phosphorus", p), ("potassium", k),
        ("soil moisture", moisture), ("temperature", temperature)) if v is not None]
    if previous_crop:
        provided.append("previous crop")
    if provenance["market"] == SOURCE_LIVE:
        provided.append("live mandi prices")
    if provenance["satellite"] == SOURCE_SATELLITE:
        provided.append("satellite field observation")

    confidence = ("high" if len(provided) >= 6
                  else "medium" if len(provided) >= 3 else "low")

    n_carry, n_note = rotation.nitrogen_carryover(previous_crop)

    return {
        "satellite_context": _satellite_context(satellite),
        "season": season,
        "state": state,
        "district": district,
        "recommendations": results[:top_n] if top_n else results,
        "best": results[0] if results else None,
        "data_confidence": confidence,
        "data_used": provided,
        "provenance": provenance,
        "nitrogen_carryover_kg_ha": n_carry,
        "nitrogen_note": n_note,
        "weights": {
            "agronomy": AGRONOMY_WEIGHT,
            "rotation": ROTATION_WEIGHT,
            "market": MARKET_WEIGHT,
        },
        "disclaimer": (
            "This is an AI-assisted advisory suitability score computed from "
            "the data available. It is not an official government "
            "recommendation and not a guaranteed yield or income. Confirm with "
            "your local Krishi Vigyan Kendra before sowing."),
    }


def _satellite_context(satellite: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Field observation as CONTEXT for the ranking, never as an input to it.

    WHY SATELLITE DOES NOT MOVE THE SCORE
    -------------------------------------
    NDVI measures what is growing on this plot RIGHT NOW. The question this
    engine answers is what to sow NEXT. Letting current greenness push a score
    up or down would be a category error — a field that is green today because
    last season's crop is still standing is not thereby better suited to
    soybean in June.

    What the observation genuinely adds is three things, and they are stated
    plainly instead of being buried in a weight the farmer cannot inspect:

      1. Is the plot currently occupied, fallow or bare? That changes when
         land preparation can start.
      2. What canopy has this land historically supported? A plot that has
         never exceeded NDVI 0.35 will not carry a high-input crop.
      3. Does the satellite agree with the soil moisture sensor? Two
         independent sources agreeing raises confidence in the whole advisory.
    """
    from app.services import vegetation as veg

    if not satellite or satellite.get("status") not in ("ok", "stale"):
        return {
            "available": False,
            "status": (satellite or {}).get("status", "missing"),
            "message": ((satellite or {}).get("message")
                        or "No satellite observation was used for this advisory."),
            "influences_ranking": False,
        }

    ndvi = satellite.get("ndvi")
    band = veg.classify_ndvi(ndvi)
    obs = satellite.get("observation") or {}

    if ndvi is not None and ndvi < 0.20:
        occupancy = "BARE OR FALLOW"
        timing = ("The plot currently carries almost no canopy, so land "
                  "preparation and sowing can proceed on your own schedule.")
    elif ndvi is not None and ndvi < 0.40:
        occupancy = "SPARSE COVER"
        timing = ("There is light cover on the plot — crop residue, weeds or "
                  "an early crop. Clear it before the next sowing.")
    else:
        occupancy = "STANDING VEGETATION"
        timing = ("A dense canopy is standing on this plot right now. If a "
                  "crop is still in the ground, the recommendation below "
                  "applies to the season AFTER it comes off.")

    return {
        "available": True,
        "status": satellite.get("status"),
        "ndvi": ndvi,
        "band": band["band"],
        "meaning": band["meaning"],
        "observed_on": obs.get("date"),
        "days_ago": obs.get("days_ago"),
        "field_occupancy": occupancy,
        "timing_note": timing,
        "productivity": satellite.get("productivity"),
        "influences_ranking": False,
        "why_not": ("Satellite greenness shows what is growing on this plot "
                    "today. The ranking answers what to sow next, which is "
                    "decided by soil, season, rotation, water and price — so "
                    "this observation is shown as context and does not change "
                    "any score."),
    }


def grounded_facts(advisory: Dict[str, Any]) -> List[str]:
    """Fact lines for the LLM. It phrases these; it never reorders or invents."""
    if not advisory.get("recommendations"):
        return ["No crop recommendation could be produced."]

    facts = [
        f"Season: {advisory['season']}",
        f"Evidence level: {advisory['data_confidence']} "
        f"(based on {len(advisory['data_used'])} real inputs: "
        f"{', '.join(advisory['data_used']) or 'none'})",
        "RANKING (already computed, do NOT reorder):",
    ]
    for i, r in enumerate(advisory["recommendations"][:3], 1):
        facts.append(
            f"{i}. {r['display']} — advisory suitability "
            f"{r['advisory_suitability_score']}/100. "
            f"Rotation: {r['rotation_fit']['note']} "
            f"Water: {r['water_requirement']['note']} "
            f"Market: {r['market_information']['note']}")

    if advisory.get("nitrogen_note"):
        facts.append(advisory["nitrogen_note"])

    sat_ctx = advisory.get("satellite_context") or {}
    if sat_ctx.get("available"):
        facts.append(
            f"SATELLITE CONTEXT (Sentinel-2, {sat_ctx.get('observed_on')}): the "
            f"plot currently reads NDVI {sat_ctx.get('ndvi')} "
            f"({sat_ctx.get('band')}) — {sat_ctx.get('field_occupancy')}. "
            f"{sat_ctx.get('timing_note')}")
        prod = sat_ctx.get("productivity") or {}
        if prod.get("available"):
            facts.append(f"Historical canopy on this plot: {prod['level']}. "
                         f"{prod['note']}")
        facts.append(
            "The satellite observation is CONTEXT ONLY. It did not change the "
            "ranking above, and you must not claim it did.")

    facts.append(
        "Call this an advisory suitability score. Do NOT call it a guaranteed "
        "best crop, a government recommendation, or a yield prediction. Do NOT "
        "invent any price the market note does not contain.")
    return facts
