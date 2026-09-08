"""Reusable satellite field context for pages that are not about satellites.

Plant Health, Pest Management and the chat agent all want the same thing: a
short, safe answer to "and what is the rest of the field doing?" — without
each of them re-implementing coordinate lookup, crop-stage arithmetic, change
detection against stored history, and the try/except that keeps Earth Engine
failures from breaking an image upload.

This module is the orchestration layer between:
    satellite.py   (fetches numbers from Earth Engine)
    vegetation.py  (interprets numbers, no network)
    the database   (stored history, farm record)

Every function here is best-effort. None of them raise. A page that calls one
of these gets a dict with a `status` and can render whatever it has.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Dict, Optional

from sqlalchemy.orm import Session

from app.core.budget import budgeted
from app.core.config import settings
from app.models.models import Farm, SatelliteObservation
from app.services import satellite as sat
from app.services import vegetation as veg

log = logging.getLogger("agri.field_context")

UNAVAILABLE = {"status": "unavailable", "available": False,
               "message": "Satellite data is temporarily unavailable."}
NO_LOCATION = {"status": "no_location", "available": False,
               "message": ("No field coordinates are saved. Add them on the "
                           "Farm Profile to see how the whole field is doing, "
                           "not just this photo.")}


def crop_stage(farm: Optional[Farm]) -> Dict[str, Any]:
    """Crop key, days after sowing and expected duration from the farm row."""
    if farm is None:
        return {"crop": "", "days_after_sowing": None, "duration_days": None}

    from app.services.crop_suitability import MP_CROPS

    crop = (farm.crop or "").strip().lower()
    spec = MP_CROPS.get(crop)
    das = None
    if farm.sowing_date:
        das = (datetime.utcnow() - farm.sowing_date).days
        if das < 0:
            das = None
    return {
        "crop": crop,
        "days_after_sowing": das,
        "duration_days": spec["duration_days"] if spec else None,
    }


def previous_observation(db: Session, user_id: int,
                         before_date: Optional[str]) -> Optional[Dict[str, Any]]:
    """Most recent stored observation before `before_date`, or None."""
    if not before_date:
        return None
    row = (db.query(SatelliteObservation)
           .filter(SatelliteObservation.user_id == user_id,
                   SatelliteObservation.ndvi.isnot(None),
                   SatelliteObservation.observed_on < before_date)
           .order_by(SatelliteObservation.observed_on.desc())
           .first())
    if row is None:
        return None
    return {"ndvi": row.ndvi, "date": row.observed_on}


async def scouting_context(db: Session, user, *, severity: str = "",
                           diagnosis: str = "") -> Dict[str, Any]:
    """Field-scale corroboration for a leaf-photo diagnosis.

    WHY A PHOTO NEEDS THIS
    ----------------------
    A photo answers "what is wrong with this plant". It cannot answer "how much
    of my field is affected", which is the question that decides whether the
    farmer spot-treats a corner or sprays four hectares. The satellite answers
    exactly that second question and nothing else — it never names the disease,
    and this function never lets it.
    """
    farm = db.query(Farm).filter(Farm.user_id == user.id).first()
    if not farm or farm.latitude is None or farm.longitude is None:
        return dict(NO_LOCATION)

    try:
        lat, lon = float(farm.latitude), float(farm.longitude)
        # Photo pages must return the diagnosis promptly; field-scale context
        # is a bonus, not a blocker.
        obs = await budgeted(sat.get_ndvi(lat, lon),
                             settings.PROFILE_SATELLITE_BUDGET_S,
                             "field context satellite")
        if obs is None:
            return dict(UNAVAILABLE)
        if obs.get("status") not in sat.REAL_STATUSES:
            return {"status": obs.get("status"), "available": False,
                    "message": obs.get("message")}

        ctx = crop_stage(farm)
        phen = veg.phenology_check(
            ndvi=obs.get("ndvi"), crop=ctx["crop"],
            days_after_sowing=ctx["days_after_sowing"],
            duration_days=ctx["duration_days"])
        unif = veg.uniformity(obs)
        prev = previous_observation(
            db, user.id, (obs.get("observation") or {}).get("date"))
        change = veg.detect_change(obs, prev)
        scouting = veg.scouting_priority(
            obs=obs, phenology=phen, change=change,
            uniformity_result=unif, severity=severity)

        spread = _spread_reading(change, unif, severity)

        return {
            "status": obs.get("status"),
            "available": True,
            "ndvi": obs.get("ndvi"),
            "classification": veg.classify_ndvi(obs.get("ndvi")),
            "observation": obs.get("observation"),
            "phenology": phen,
            "uniformity": unif,
            "change": change,
            "scouting": scouting,
            "field_spread": spread,
            "photo_diagnosis": diagnosis or None,
            "photo_severity": severity or None,
            "caveat": ("The satellite measures canopy greenness across the "
                       "whole field. It cannot see the disease in your photo "
                       "and cannot confirm or contradict the diagnosis — it "
                       "only shows whether the rest of the field is also "
                       "losing vigour."),
        }
    except Exception as exc:                            # noqa: BLE001
        log.warning("scouting context failed: %s: %s", type(exc).__name__, exc)
        return dict(UNAVAILABLE)


def _spread_reading(change: Dict[str, Any], unif: Dict[str, Any],
                    severity: str) -> Dict[str, str]:
    """Is this a spot problem or a field-wide one? The treatment differs."""
    declining = (change.get("available")
                 and change.get("direction") in ("DECLINE", "SHARP DECLINE"))
    patchy = unif.get("available") and unif.get("level") == "PATCHY"
    serious = (severity or "").upper() in ("HIGH", "SEVERE", "CRITICAL",
                                           "MODERATE")

    if declining and not patchy:
        return {"pattern": "FIELD WIDE",
                "note": ("Canopy is falling across the whole field fairly "
                         "evenly. Whatever is happening is not confined to "
                         "one corner — plan a full-field response.")}
    if declining and patchy:
        return {"pattern": "SPREADING FROM PATCHES",
                "note": ("Canopy is falling and the field is uneven, which is "
                         "what a problem spreading outward from hotspots looks "
                         "like. Treating the weak patches early may stop it.")}
    if patchy and serious:
        return {"pattern": "LOCALISED",
                "note": ("The photo shows a real problem but the field-wide "
                         "canopy is holding up. This looks localised — spot "
                         "treatment is likely enough for now.")}
    if serious:
        return {"pattern": "NOT YET VISIBLE FROM ORBIT",
                "note": ("The photo shows a problem the satellite cannot see "
                         "yet. That is normal — visible canopy loss lags leaf "
                         "symptoms by days or weeks. Catching it now is the "
                         "best case, not a contradiction.")}
    return {"pattern": "STABLE",
            "note": "Field canopy is steady. No wider spread is visible."}


async def agent_context(db: Session, user) -> Dict[str, Any]:
    """Satellite facts for the chat agent, plus the raw pieces behind them."""
    farm = db.query(Farm).filter(Farm.user_id == user.id).first()
    if not farm or farm.latitude is None or farm.longitude is None:
        out = dict(NO_LOCATION)
        out["facts"] = [
            "The farmer has not saved field coordinates, so no satellite "
            "reading is available. If they ask about satellite or NDVI, tell "
            "them to add their location on the Farm Profile. Do NOT invent a "
            "value."]
        return out

    try:
        lat, lon = float(farm.latitude), float(farm.longitude)
        # Photo pages must return the diagnosis promptly; field-scale context
        # is a bonus, not a blocker.
        obs = await budgeted(sat.get_ndvi(lat, lon),
                             settings.PROFILE_SATELLITE_BUDGET_S,
                             "field context satellite")
        if obs is None:
            return dict(UNAVAILABLE)
        ctx = crop_stage(farm)

        phen = veg.phenology_check(
            ndvi=obs.get("ndvi"), crop=ctx["crop"],
            days_after_sowing=ctx["days_after_sowing"],
            duration_days=ctx["duration_days"])
        water = veg.water_stress(obs)
        unif = veg.uniformity(obs)
        nitro = veg.nitrogen_signal(obs, phen)
        prev = previous_observation(
            db, user.id, (obs.get("observation") or {}).get("date"))
        change = veg.detect_change(obs, prev)

        return {
            "status": obs.get("status"),
            "available": obs.get("status") in sat.REAL_STATUSES,
            "ndvi": obs.get("ndvi"),
            "observation": obs.get("observation"),
            "phenology": phen, "water_stress": water, "uniformity": unif,
            "nitrogen_signal": nitro, "change": change,
            "facts": veg.grounded_facts(
                obs=obs, phenology=phen, water=water, change=change,
                uniformity_result=unif, nitrogen=nitro),
        }
    except Exception as exc:                            # noqa: BLE001
        log.warning("agent satellite context failed: %s", exc)
        out = dict(UNAVAILABLE)
        out["facts"] = ["Satellite data is temporarily unavailable. Do NOT "
                        "state or guess any NDVI value."]
        return out
