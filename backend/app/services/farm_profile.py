"""The unified Farm Profile.

WHY THIS EXISTS
---------------
Before this module, every screen that needed farm context rebuilt it by hand:
the crop advisor queried Farm + SoilTest + SensorReading + weather, the alerts
engine queried nearly the same set, the chat agent queried a third variation.
Three copies of the same joins, drifting apart, each with its own idea of what
"the farmer's situation" means.

Worse, each one decided independently what to do about missing data. One
treated an absent soil test as zero, another as neutral, a third crashed.

This module builds that context ONCE, in a normalised shape, with an explicit
confidence label on every field.

THE CONFIDENCE CONTRACT
-----------------------
Every value carries where it came from:

    CONFIRMED    a real sensor reading, a value the farmer entered, a live
                 weather fetch, or a valid satellite observation
    ESTIMATED    derived from other confirmed data (crop stage from sowing
                 date, harvest date from duration)
    UNAVAILABLE  no sensor, no satellite pass, no soil test

Nothing is ever invented. An unavailable field is reported as unavailable, not
filled with a plausible default, because a farmer acting on a plausible default
is worse off than one told "we don't know".

EVERY EXTERNAL CALL IS OPTIONAL
-------------------------------
Weather, satellite and sensors are each wrapped. Any of them can be down,
unconfigured or slow without breaking profile construction. A profile built
with three unavailable sections is still a valid profile — it just says so.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.models import Farm, SensorReading, SoilTest, User

log = logging.getLogger("agri.farm_profile")

CONFIRMED = "CONFIRMED"
ESTIMATED = "ESTIMATED"
UNAVAILABLE = "UNAVAILABLE"

# A sensor reading older than this is history, not the current state of the
# field. Reporting a four-day-old moisture value as "now" would quietly
# mislead the irrigation advice.
SENSOR_FRESH_HOURS = 12

# Which parts of Farm Setup must be present before the personalised modules
# can produce anything meaningful. Kept deliberately short: blocking a farmer
# from their dashboard over a missing village name would be hostile.
# Deliberately MINIMAL. These were four fields, which meant a farmer who
# skipped soil type during the wizard was bounced back to setup on every
# single navigation, forever, with no way out. That is the worst possible
# failure for a gate: it punishes the farmer for an optional answer.
#
# Now only what is genuinely required to compute anything personalised: where
# the farm is. Everything else is prompted for in place, on the page that
# needs it, without blocking access.
REQUIRED_FIELDS = ("state", "district")
RECOMMENDED_FIELDS = ("land_size_acres", "soil_type", "latitude", "longitude",
                      "irrigation_type", "water_source", "previous_crop")


def _field(value: Any, confidence: str = CONFIRMED,
           note: str = "") -> Dict[str, Any]:
    """Wrap one value with its provenance."""
    if value in (None, "", []):
        return {"value": None, "confidence": UNAVAILABLE,
                "note": note or "Not available"}
    return {"value": value, "confidence": confidence, "note": note}


# =====================================================================
# Setup completeness
# =====================================================================

def setup_status(db: Session, user: User) -> Dict[str, Any]:
    """Has this farmer completed enough setup to get personalised advice?

    Returns the same shape whether or not a Farm row exists, so the route
    guard and the wizard can both rely on it without null checks.
    """
    farm = db.query(Farm).filter(Farm.user_id == user.id).first()

    if farm is None:
        return {
            "completed": False,
            "has_farm": False,
            "completeness": 0,
            "missing_required": list(REQUIRED_FIELDS),
            "missing_recommended": list(RECOMMENDED_FIELDS),
            "message": ("Complete your farm setup to get personalised crop "
                        "recommendations and farm insights."),
            "next_step": "/farm-setup",
        }

    missing_req = [f for f in REQUIRED_FIELDS if not getattr(farm, f, None)]
    missing_rec = [f for f in RECOMMENDED_FIELDS if not getattr(farm, f, None)]

    all_fields = REQUIRED_FIELDS + RECOMMENDED_FIELDS
    present = sum(1 for f in all_fields if getattr(farm, f, None))
    completeness = round(100 * present / len(all_fields))

    completed = not missing_req and bool(farm.onboarded)

    return {
        "completed": completed,
        "has_farm": True,
        # Echoed back so a completed setup can be SHOWN rather than re-asked.
        "summary": {
            "name": farm.name, "state": farm.state, "district": farm.district,
            "village": farm.village,
            "land_size_acres": farm.land_size_acres,
            "area_unit": farm.area_unit,
            "soil_type": farm.soil_type,
            "irrigation_type": farm.irrigation_type,
            "water_source": farm.water_source,
            "water_availability": farm.water_availability,
            "crop": farm.crop, "variety": farm.variety,
            "sowing_date": (farm.sowing_date.date().isoformat()
                            if farm.sowing_date else None),
            "previous_crop": farm.previous_crop,
            "has_coordinates": farm.latitude is not None,
        },
        "completeness": completeness,
        "missing_required": missing_req,
        "missing_recommended": missing_rec,
        "message": ("Your farm setup is complete." if completed else
                    "Complete your farm setup to get personalised crop "
                    "recommendations and farm insights."),
        "next_step": None if completed else "/farm-setup",
        "farm_id": farm.id,
    }


# =====================================================================
# Section builders — each is independently failure-tolerant
# =====================================================================

def _location(farm: Farm) -> Dict[str, Any]:
    return {
        "name": _field(farm.name),
        "state": _field(farm.state),
        "district": _field(farm.district),
        "village": _field(farm.village),
        "latitude": _field(farm.latitude),
        "longitude": _field(farm.longitude),
        "has_coordinates": farm.latitude is not None and farm.longitude is not None,
    }


def _land(farm: Farm) -> Dict[str, Any]:
    acres = farm.land_size_acres
    unit = (farm.area_unit or "acre").lower()
    return {
        "area_acres": _field(acres),
        "area_unit": _field(unit),
        # Shown back in the unit the farmer actually typed, so the number on
        # screen always matches the number they entered.
        "area_as_entered": _field(
            round(acres * 2.4711, 2) if acres and unit == "hectare" else acres,
            CONFIRMED, f"in {unit}s" if acres else ""),
        "water_availability": _field(farm.water_availability),
        # Hectares are derived, never separately stored, so the two can never
        # disagree after an edit.
        "area_hectares": _field(round(acres * 0.4047, 3) if acres else None,
                                ESTIMATED, "Converted from acres"),
        "farmer_category": _field(farm.farmer_category),
        "soil_type": _field(farm.soil_type),
        "irrigation_type": _field(farm.irrigation_type),
        "water_source": _field(farm.water_source),
        "farming_method": _field(farm.farming_method),
    }


def _soil(db: Session, user: User) -> Dict[str, Any]:
    test = (db.query(SoilTest).filter(SoilTest.user_id == user.id)
            .order_by(SoilTest.created_at.desc()).first())
    if test is None:
        return {"available": False,
                "note": ("No soil test on record. Add one for more accurate "
                         "crop and fertiliser advice."),
                "nitrogen": _field(None), "phosphorus": _field(None),
                "potassium": _field(None), "ph": _field(None), "ec": _field(None)}

    src = CONFIRMED
    age_days = (datetime.utcnow() - test.created_at).days if test.created_at else None
    return {
        "available": True,
        "tested_on": test.created_at.date().isoformat() if test.created_at else None,
        "age_days": age_days,
        "source": test.source or "manual",
        "nitrogen": _field(test.nitrogen, src),
        "phosphorus": _field(test.phosphorus, src),
        "potassium": _field(test.potassium, src),
        "ph": _field(test.ph, src),
        "ec": _field(test.ec, src),
        # Soil chemistry drifts. A three-year-old test is a starting point,
        # not a current measurement, and the farmer should know that.
        "note": ("This test is over a year old — consider retesting."
                 if age_days and age_days > 365 else ""),
    }


def _sensors(db: Session, farm: Optional[Farm]) -> Dict[str, Any]:
    """Latest IoT reading, with an explicit connected / not-connected state."""
    q = db.query(SensorReading)
    if farm and farm.device_id:
        q = q.filter(SensorReading.device_id == farm.device_id)
    reading = q.order_by(SensorReading.created_at.desc()).first()

    if reading is None:
        return {"connected": False, "device_id": farm.device_id if farm else None,
                "note": "No sensor is connected to this farm.",
                "soil_moisture": _field(None), "temperature": _field(None),
                "humidity": _field(None), "water_level": _field(None)}

    age_h = None
    stale = False
    if reading.created_at:
        age_h = round((datetime.utcnow() - reading.created_at).total_seconds() / 3600, 1)
        stale = age_h > SENSOR_FRESH_HOURS

    conf = ESTIMATED if stale else CONFIRMED
    note = (f"Last reading was {age_h} hours ago — may not reflect the field "
            f"right now." if stale else "")

    return {
        "connected": True,
        "device_id": reading.device_id,
        "reading_at": reading.created_at.isoformat() if reading.created_at else None,
        "age_hours": age_h,
        "is_stale": stale,
        "source": reading.source or "device",
        "soil_moisture": _field(reading.soil_moisture, conf, note),
        "temperature": _field(reading.temperature, conf, note),
        "humidity": _field(reading.humidity, conf, note),
        "water_level": _field(reading.water_level, conf, note),
        "water_flow": _field(reading.water_flow, conf, note),
        "note": note,
    }


async def _weather(farm: Optional[Farm]) -> Dict[str, Any]:
    from app.services import weather as weather_svc
    try:
        lat = float(farm.latitude) if farm and farm.latitude is not None else 13.08
        lon = float(farm.longitude) if farm and farm.longitude is not None else 80.27
        wx = await weather_svc.get_weather(lat, lon)
        return {
            "available": True,
            "temperature": _field(wx.get("temperature")),
            "humidity": _field(wx.get("humidity")),
            "rain_mm": _field(wx.get("rain_mm")),
            "rain_probability": _field(wx.get("rain_probability")),
            "condition": _field(wx.get("condition")),
            "wind_kph": _field(wx.get("wind_kph")),
            "forecast": wx.get("forecast") or [],
            "used_farm_coordinates": bool(
                farm and farm.latitude is not None),
        }
    except Exception as exc:                            # noqa: BLE001
        log.warning("weather unavailable for profile: %s", exc)
        return {"available": False,
                "note": "Weather service is temporarily unavailable.",
                "temperature": _field(None), "humidity": _field(None),
                "rain_probability": _field(None), "forecast": []}


async def _satellite(farm: Optional[Farm]) -> Dict[str, Any]:
    from app.services import satellite as sat_svc
    from app.services import vegetation as veg

    if not farm or farm.latitude is None or farm.longitude is None:
        return {"available": False,
                "note": ("Add your field coordinates during setup to include "
                         "satellite vegetation data.")}
    try:
        obs = await sat_svc.get_ndvi(float(farm.latitude), float(farm.longitude))
        if obs.get("status") not in sat_svc.REAL_STATUSES:
            return {"available": False, "status": obs.get("status"),
                    "note": obs.get("message", "No satellite reading available.")}

        o = obs.get("observation") or {}
        band = veg.classify_ndvi(obs.get("ndvi"))
        return {
            "available": True,
            "status": obs.get("status"),
            "ndvi": _field(obs.get("ndvi")),
            "ndmi": _field((obs.get("indices") or {}).get("ndmi")),
            "vegetation_condition": band["band"],
            "meaning": band["meaning"],
            "observed_on": o.get("date"),
            "days_ago": o.get("days_ago"),
            "is_stale": o.get("is_stale", False),
        }
    except Exception as exc:                            # noqa: BLE001
        log.warning("satellite unavailable for profile: %s", exc)
        return {"available": False,
                "note": "Satellite service is temporarily unavailable."}


def _current_crop(farm: Optional[Farm]) -> Dict[str, Any]:
    """The crop in the ground now, with an ESTIMATED stage where needed.

    The stage is derived from the sowing date, not asked for, because a
    farmer should not have to re-type "flowering" every week. It is labelled
    ESTIMATED whenever it was computed rather than stated, so the UI can say
    so instead of presenting a calculation as an observation.
    """
    from app.services import lifecycle as lc
    from app.services.crop_suitability import MP_CROPS

    if not farm or not farm.crop:
        return {"growing": False,
                "note": "No crop is currently registered on this farm."}

    key = (farm.crop or "").strip().lower()
    spec = MP_CROPS.get(key)
    duration = spec["duration_days"] if spec else None

    # A sowing date in the FUTURE is a planned sowing, not missing data.
    # Returning None made the card read "Not available", which looks like a
    # bug to the farmer who just typed the date in.
    das = None
    days_until_sowing = None
    if farm.sowing_date:
        delta = (datetime.utcnow() - farm.sowing_date).days
        if delta >= 0:
            das = delta
        else:
            days_until_sowing = abs(delta)

    stage_obj = None
    stage_conf = UNAVAILABLE
    if das is not None:
        stage_obj = lc.current_stage(key, das)
        stage_conf = ESTIMATED
    if farm.growth_stage and not stage_obj:
        stage_obj = {"stage": farm.growth_stage}
        stage_conf = CONFIRMED

    # A harvest date the farmer entered themselves outranks our calculation.
    expected_harvest = None
    harvest_conf = ESTIMATED
    harvest_note = "Estimated from sowing date plus typical crop duration"
    harvest_conflict = None

    derived = ((farm.sowing_date + timedelta(days=duration)).date()
               if farm.sowing_date and duration else None)

    if farm.expected_harvest_date:
        expected_harvest = farm.expected_harvest_date.date().isoformat()
        harvest_conf = CONFIRMED
        harvest_note = "As entered by you"

        # If the entered date is wildly out of step with the crop's duration,
        # SAY SO rather than showing one number here and a different one on
        # the next panel. A 100-day crop harvested 11 days after sowing is a
        # typo, and silently displaying both dates is how a farmer ends up
        # planning against the wrong one.
        if derived:
            gap = abs((farm.expected_harvest_date.date() - derived).days)
            if gap > max(21, duration * 0.25):
                harvest_conflict = (
                    f"The harvest date you entered ({expected_harvest}) is "
                    f"{gap} days away from what this crop's {duration}-day "
                    f"duration suggests ({derived.isoformat()}). Please check "
                    f"the sowing and harvest dates.")
    elif derived:
        expected_harvest = derived.isoformat()

    return {
        "growing": True,
        "crop": key,
        "display": spec["display"] if spec else farm.crop,
        "variety": _field(farm.variety),
        "sowing_date": _field(farm.sowing_date.date().isoformat()
                              if farm.sowing_date else None),
        "days_after_sowing": _field(das, CONFIRMED if das is not None else UNAVAILABLE),
        "days_until_sowing": _field(
            days_until_sowing, CONFIRMED if days_until_sowing else UNAVAILABLE,
            "Sowing date is in the future — this crop is planned, not yet sown."
            if days_until_sowing else ""),
        "not_yet_sown": days_until_sowing is not None,
        "expected_duration_days": _field(duration),
        "expected_harvest_date": _field(expected_harvest, harvest_conf,
                                        harvest_note),
        "harvest_date_conflict": harvest_conflict,
        "derived_harvest_date": derived.isoformat() if derived else None,
        # Distinct from total holding: fertiliser and yield must be computed
        # on the area actually sown, not the whole farm.
        "crop_area_acres": _field(farm.crop_area_acres),
        "stage": {
            "value": (stage_obj or {}).get("stage"),
            "confidence": stage_conf,
            "detail": stage_obj,
            "note": ("Estimated from your sowing date — confirm by looking at "
                     "the crop." if stage_conf == ESTIMATED else ""),
        },
        "has_lifecycle_data": lc.get_lifecycle(key) is not None,
    }


def _previous_crop(farm: Optional[Farm]) -> Dict[str, Any]:
    if not farm or not farm.previous_crop:
        return {"known": False,
                "note": ("No previous crop recorded. Rotation advice will be "
                         "limited without it.")}
    from app.services import rotation
    from app.services.crop_suitability import MP_CROPS

    key = (farm.previous_crop or "").strip().lower()
    spec = MP_CROPS.get(key)
    n_carry, n_note = rotation.nitrogen_carryover(key)
    return {
        "known": True,
        "crop": key,
        "display": spec["display"] if spec else farm.previous_crop,
        "season": _field(farm.previous_season),
        "family": rotation.family_of(key),
        "nitrogen_carryover_kg": n_carry,
        "nitrogen_note": n_note,
        "variety": _field(farm.previous_variety),
        "sowing_date": _field(farm.previous_sowing_date.date().isoformat()
                              if farm.previous_sowing_date else None),
        "harvest_date": _field(farm.previous_harvest_date.date().isoformat()
                               if farm.previous_harvest_date else None),
        "yield_qtl": _field(farm.previous_yield_qtl),
        # Free text from the farmer. Carried through to pest advice, because
        # last season's outbreak is the best predictor of this season's.
        "problems": _field(farm.previous_problems),
        "days_since_harvest": (
            (datetime.utcnow() - farm.previous_harvest_date).days
            if farm.previous_harvest_date else None),
    }


# =====================================================================
# Public entry point
# =====================================================================

async def build_profile(db: Session, user: User) -> Dict[str, Any]:
    """The one normalised context object every personalised module consumes.

    Deliberately returns a profile even when setup is incomplete or every
    external service is down — callers inspect `setup.completed` and the
    per-section `available` flags rather than handling exceptions.
    """
    farm = db.query(Farm).filter(Farm.user_id == user.id).first()
    setup = setup_status(db, user)

    if farm is None:
        return {
            "setup": setup,
            "has_farm": False,
            "message": setup["message"],
            "generated_at": datetime.utcnow().isoformat(),
        }

    # CONCURRENT, AND BUDGETED.
    #
    # These were awaited one after the other with no time limit. Weather can
    # take 15s and Earth Engine up to GEE_TIMEOUT_S (60s), so a single profile
    # request could block for well over a minute — and the Crop Advisor page
    # calls this on mount, which is what made that page appear to take two
    # minutes even after the ranking itself was reduced to half a second.
    #
    # They are independent, so they run together; and neither is allowed to
    # hold up a farm profile, because every field they populate is optional
    # and already degrades to "unavailable" by design.
    async def _budgeted(coro, label, budget):
        if settings.DEMO_FAST_MODE:
            coro.close()          # never awaited; close it to avoid a warning
            return {"available": False,
                    "note": f"{label} not fetched in fast mode."}
        try:
            return await asyncio.wait_for(coro, timeout=budget)
        except asyncio.TimeoutError:
            log.info("%s skipped for profile: exceeded %ss budget",
                     label, budget)
            return {"available": False,
                    "note": (f"{label} took too long and was skipped to keep "
                             f"this page responsive.")}
        except Exception as exc:                        # noqa: BLE001
            log.warning("%s failed for profile: %s", label, exc)
            return {"available": False,
                    "note": f"{label} is temporarily unavailable."}

    with_timer = await asyncio.gather(
        _budgeted(_weather(farm), "Weather",
                  settings.PROFILE_WEATHER_BUDGET_S),
        _budgeted(_satellite(farm), "Satellite",
                  settings.PROFILE_SATELLITE_BUDGET_S),
    )
    weather, satellite = with_timer

    profile = {
        "setup": setup,
        "has_farm": True,
        "farm_id": farm.id,
        "mode": farm.mode,
        "location": _location(farm),
        "land": _land(farm),
        "soil": _soil(db, user),
        "sensors": _sensors(db, farm),
        "weather": weather,
        "satellite": satellite,
        "current_crop": _current_crop(farm),
        "previous_crop": _previous_crop(farm),
        "generated_at": datetime.utcnow().isoformat(),
    }
    profile["data_confidence"] = _confidence_summary(profile)
    return profile


def _confidence_summary(profile: Dict[str, Any]) -> Dict[str, Any]:
    """A one-glance view of what is real, what is derived and what is missing."""
    return {
        "soil_test": (CONFIRMED if profile["soil"]["available"] else UNAVAILABLE),
        "sensors": (CONFIRMED if profile["sensors"]["connected"]
                    and not profile["sensors"].get("is_stale")
                    else ESTIMATED if profile["sensors"]["connected"]
                    else UNAVAILABLE),
        "weather": (CONFIRMED if profile["weather"]["available"] else UNAVAILABLE),
        "satellite": (CONFIRMED if profile["satellite"]["available"] else UNAVAILABLE),
        "current_crop": (CONFIRMED if profile["current_crop"]["growing"]
                         else UNAVAILABLE),
        "crop_stage": profile["current_crop"].get("stage", {}).get(
            "confidence", UNAVAILABLE),
        "previous_crop": (CONFIRMED if profile["previous_crop"]["known"]
                          else UNAVAILABLE),
        "legend": {
            CONFIRMED: "Measured, fetched live, or entered by you.",
            ESTIMATED: "Calculated from other data — treat as a guide.",
            UNAVAILABLE: "Not available. Nothing has been guessed in its place.",
        },
    }


def flatten_for_scoring(profile: Dict[str, Any]) -> Dict[str, Any]:
    """Unwrap the profile into the plain kwargs the scoring engines expect.

    The confidence wrappers are for the UI and the LLM. score_crop() wants
    bare numbers, and this is the single place that unwrapping happens — so
    the engines never learn about the wrapper format.

    Sensor moisture wins over a soil test reading because it is measured now;
    the soil test is a laboratory snapshot from months ago.
    """
    if not profile.get("has_farm"):
        return {}

    soil = profile["soil"]
    sensors = profile["sensors"]
    weather = profile["weather"]

    def v(node):
        return (node or {}).get("value")

    return {
        "state": v(profile["location"]["state"]) or "",
        "district": v(profile["location"]["district"]) or "",
        "latitude": v(profile["location"]["latitude"]),
        "longitude": v(profile["location"]["longitude"]),
        "soil_type": v(profile["land"]["soil_type"]) or "",
        "irrigation_type": v(profile["land"]["irrigation_type"]) or "",
        "water_source": v(profile["land"]["water_source"]) or "",
        "land_size_acres": v(profile["land"]["area_acres"]),
        "nitrogen": v(soil.get("nitrogen")),
        "phosphorus": v(soil.get("phosphorus")),
        "potassium": v(soil.get("potassium")),
        "ph": v(soil.get("ph")),
        "moisture": v(sensors.get("soil_moisture")),
        "temperature": (v(sensors.get("temperature"))
                        or v(weather.get("temperature"))),
        "previous_crop": (profile["previous_crop"].get("crop") or ""),
        "current_crop": (profile["current_crop"].get("crop") or ""),
    }
