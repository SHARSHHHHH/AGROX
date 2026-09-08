"""Satellite (Sentinel-2 / Earth Engine) endpoints.

SECURITY BOUNDARY
-----------------
Earth Engine credentials live in backend/.env and are used only inside
app/services/satellite.py, server side. Nothing in this file returns a key, a
key file path, or a service-account email. `/api/satellite/status` deliberately
reports only WHICH credential mode is active, never the credential itself, and
the Google Cloud project id is exposed on the admin-only diagnostics route.

The React app calls these endpoints with a normal bearer token. It never talks
to Google.

NO IMAGERY CROSSES THE NETWORK
------------------------------
Every route below returns numbers. There is no tile endpoint, no thumbnail URL,
no download link, and no raster on disk.
"""

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import get_current_user, require_admin
from app.database.db import get_db
from app.models.models import Farm, SatelliteObservation, User
from app.services import satellite as sat
from app.services import vegetation as veg
from app.services.crop_suitability import MP_CROPS

log = logging.getLogger("agri.api.satellite")

router = APIRouter(prefix="/api/satellite", tags=["satellite"])


# =====================================================================
# Shared helpers
# =====================================================================

NO_LOCATION = {
    "status": "no_location",
    "message": ("No field location is saved yet. Add your farm's latitude and "
                "longitude on the Farm Profile or during onboarding, then "
                "satellite monitoring will switch on automatically."),
    "ndvi": None,
    "observation": None,
}


def _farm(db: Session, user: User) -> Optional[Farm]:
    return db.query(Farm).filter(Farm.user_id == user.id).first()


def _resolve_point(db: Session, user: User,
                   lat: Optional[float] = None,
                   lon: Optional[float] = None) -> Tuple[Optional[float],
                                                         Optional[float],
                                                         str,
                                                         Optional[Farm]]:
    """Coordinates for this request: explicit ones win, else the saved farm.

    Explicit lat/lon are what makes every one of these endpoints usable before
    a farm profile exists — during onboarding, from the assistant, or for a
    plot the farmer is only considering.
    """
    farm = _farm(db, user)
    if lat is not None and lon is not None:
        return float(lat), float(lon), "request", farm
    if farm and farm.latitude is not None and farm.longitude is not None:
        return float(farm.latitude), float(farm.longitude), "farm_profile", farm
    return None, None, "none", farm


def _crop_context(farm: Optional[Farm]) -> Dict[str, Any]:
    """Crop, days after sowing and expected duration from the farm record."""
    if farm is None:
        return {"crop": "", "days_after_sowing": None, "duration_days": None,
                "sowing_date": None}

    crop = (farm.crop or "").strip().lower()
    spec = MP_CROPS.get(crop)
    das = None
    if farm.sowing_date:
        das = (datetime.utcnow() - farm.sowing_date).days
        if das < 0:
            das = None

    return {
        "crop": crop,
        "crop_display": spec["display"] if spec else (farm.crop or ""),
        "days_after_sowing": das,
        "duration_days": spec["duration_days"] if spec else None,
        "sowing_date": (farm.sowing_date.date().isoformat()
                        if farm.sowing_date else None),
    }


def _persist(db: Session, user: User, obs: Dict[str, Any],
             lat: float, lon: float, buffer_m: int,
             ctx: Dict[str, Any]) -> None:
    """Store one observation, keyed by date, so history builds up over time.

    Wrapped so a storage failure can never break a read. The farmer's NDVI is
    already computed and on its way back; losing the history row is a minor
    degradation, while a 500 here would take the whole page down.
    """
    if obs.get("status") not in sat.REAL_STATUSES:
        return
    o = obs.get("observation") or {}
    observed_on = o.get("date")
    if not observed_on:
        return

    try:
        row = (db.query(SatelliteObservation)
               .filter(SatelliteObservation.user_id == user.id,
                       SatelliteObservation.observed_on == observed_on,
                       SatelliteObservation.latitude.between(lat - 1e-4, lat + 1e-4),
                       SatelliteObservation.longitude.between(lon - 1e-4, lon + 1e-4))
               .first())
        if row is None:
            row = SatelliteObservation(user_id=user.id, latitude=lat,
                                       longitude=lon, observed_on=observed_on)
            db.add(row)

        detail = obs.get("ndvi_detail") or {}
        idx = obs.get("indices") or {}
        row.buffer_m = buffer_m
        row.satellite = obs.get("satellite") or "Sentinel-2"
        row.tile = o.get("tile") or ""
        row.ndvi = obs.get("ndvi")
        row.ndvi_min = detail.get("min")
        row.ndvi_max = detail.get("max")
        row.ndvi_stddev = detail.get("stddev")
        row.ndvi_p25 = detail.get("p25")
        row.ndvi_median = detail.get("median")
        row.ndvi_p75 = detail.get("p75")
        row.ndmi = idx.get("ndmi")
        row.ndre = idx.get("ndre")
        row.evi = idx.get("evi")
        row.savi = idx.get("savi")
        row.bsi = idx.get("bsi")
        row.scene_cloud_pct = o.get("scene_cloud_pct")
        row.clear_pixel_fraction = o.get("clear_pixel_fraction")
        row.crop = ctx.get("crop") or ""
        row.days_after_sowing = ctx.get("days_after_sowing")
        db.commit()
    except Exception as exc:                            # noqa: BLE001
        log.warning("could not store satellite observation: %s", exc)
        db.rollback()


def _previous(db: Session, user: User, before_date: Optional[str],
              lat: float, lon: float) -> Optional[Dict[str, Any]]:
    """The most recent stored observation BEFORE this one, for change detection."""
    if not before_date:
        return None
    row = (db.query(SatelliteObservation)
           .filter(SatelliteObservation.user_id == user.id,
                   SatelliteObservation.observed_on < before_date,
                   SatelliteObservation.ndvi.isnot(None),
                   SatelliteObservation.latitude.between(lat - 1e-3, lat + 1e-3),
                   SatelliteObservation.longitude.between(lon - 1e-3, lon + 1e-3))
           .order_by(SatelliteObservation.observed_on.desc())
           .first())
    if row is None:
        return None
    return {"ndvi": row.ndvi, "date": row.observed_on,
            "observation": {"date": row.observed_on}}


def _stored_points(db: Session, user: User, limit: int = 400) -> List[dict]:
    """Stored observations shaped like series points, for reuse offline."""
    rows = (db.query(SatelliteObservation)
            .filter(SatelliteObservation.user_id == user.id,
                    SatelliteObservation.ndvi.isnot(None))
            .order_by(SatelliteObservation.observed_on.asc())
            .limit(limit).all())
    return [{"month": (r.observed_on or "")[:7], "date": r.observed_on,
             "ndvi": r.ndvi, "ndmi": r.ndmi, "ndre": r.ndre} for r in rows]


async def _observe(db: Session, user: User, lat: Optional[float],
                   lon: Optional[float], buffer_m: Optional[int] = None,
                   force_refresh: bool = False) -> Tuple[Dict[str, Any],
                                                         Dict[str, Any]]:
    """Fetch + persist one observation, returning (observation, context)."""
    lat, lon, source, farm = _resolve_point(db, user, lat, lon)
    ctx = _crop_context(farm)
    ctx["location_source"] = source
    ctx["latitude"] = lat
    ctx["longitude"] = lon
    ctx["farm"] = farm

    if lat is None or lon is None:
        return dict(NO_LOCATION), ctx

    buffer_m = int(buffer_m or settings.GEE_BUFFER_M)
    obs = await sat.get_ndvi(lat, lon, buffer_m=buffer_m,
                             force_refresh=force_refresh)
    ctx["buffer_m"] = buffer_m
    _persist(db, user, obs, lat, lon, buffer_m, ctx)
    return obs, ctx


def _location_block(ctx: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "latitude": ctx.get("latitude"),
        "longitude": ctx.get("longitude"),
        "source": ctx.get("location_source"),
        "buffer_m": ctx.get("buffer_m", settings.GEE_BUFFER_M),
    }


def _crop_block(ctx: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "crop": ctx.get("crop"),
        "crop_display": ctx.get("crop_display"),
        "sowing_date": ctx.get("sowing_date"),
        "days_after_sowing": ctx.get("days_after_sowing"),
        "expected_duration_days": ctx.get("duration_days"),
    }


DISCLAIMER = (
    "Satellite readings describe canopy greenness over roughly one hectare "
    "around your field's location, at 10 m resolution. They are an advisory "
    "signal, not a diagnosis, a yield forecast, or an official assessment. "
    "Always confirm anything unusual by walking the field.")


# =====================================================================
# Core: status and raw NDVI
# =====================================================================

@router.get("/status")
def satellite_status(user: User = Depends(get_current_user)):
    """Is satellite monitoring available? Contains no credential material."""
    return sat.status()


@router.get("/ndvi")
async def ndvi(
    lat: Optional[float] = Query(None, ge=-90, le=90),
    lon: Optional[float] = Query(None, ge=-180, le=180),
    buffer_m: int = Query(0, ge=0, le=2000),
    force_refresh: bool = False,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Latest cloud-filtered Sentinel-2 NDVI for a point, plus its metadata.

    Supply lat/lon explicitly, or omit both to use the location saved on the
    farm profile.
    """
    obs, ctx = await _observe(db, user, lat, lon,
                              buffer_m=buffer_m or None,
                              force_refresh=force_refresh)
    obs = dict(obs)
    obs["location"] = _location_block(ctx)
    obs["classification"] = veg.classify_ndvi(obs.get("ndvi"))
    obs["disclaimer"] = DISCLAIMER
    return obs


@router.get("/timeseries")
async def timeseries(
    lat: Optional[float] = Query(None, ge=-90, le=90),
    lon: Optional[float] = Query(None, ge=-180, le=180),
    months: int = Query(12, ge=2, le=24),
    force_refresh: bool = False,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Monthly NDVI / NDMI / NDRE curve for a field."""
    lat, lon, source, farm = _resolve_point(db, user, lat, lon)
    if lat is None or lon is None:
        out = dict(NO_LOCATION)
        out["points"] = []
        return out

    series = await sat.get_series(lat, lon, months=months,
                                  force_refresh=force_refresh)
    series = dict(series)
    series["location"] = {"latitude": lat, "longitude": lon, "source": source}
    series["productivity"] = veg.land_productivity(series.get("points", []))
    series["disclaimer"] = DISCLAIMER
    return series


@router.get("/history")
def history(limit: int = Query(120, ge=1, le=500),
            user: User = Depends(get_current_user),
            db: Session = Depends(get_db)):
    """Observations already stored for this farmer. Costs no Earth Engine quota."""
    rows = (db.query(SatelliteObservation)
            .filter(SatelliteObservation.user_id == user.id)
            .order_by(SatelliteObservation.observed_on.desc())
            .limit(limit).all())
    return {
        "count": len(rows),
        "observations": [{
            "date": r.observed_on, "ndvi": r.ndvi, "ndmi": r.ndmi,
            "ndre": r.ndre, "bsi": r.bsi,
            "ndvi_stddev": r.ndvi_stddev,
            "clear_pixel_fraction": r.clear_pixel_fraction,
            "crop": r.crop, "days_after_sowing": r.days_after_sowing,
            "satellite": r.satellite, "tile": r.tile,
        } for r in rows],
        "note": ("Stored from earlier satellite queries. Reading this history "
                 "does not query Earth Engine again."),
    }


# =====================================================================
# The workhorse: one interpreted field report
# =====================================================================

@router.get("/field")
async def field_report(
    lat: Optional[float] = Query(None, ge=-90, le=90),
    lon: Optional[float] = Query(None, ge=-180, le=180),
    include_series: bool = True,
    months: int = Query(12, ge=2, le=24),
    force_refresh: bool = False,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Everything the satellite can say about this field, interpreted.

    This is the single call the Satellite page and the Dashboard card make.
    Bundling it means one Earth Engine round trip serves the whole screen
    instead of six.
    """
    obs, ctx = await _observe(db, user, lat, lon, force_refresh=force_refresh)

    out: Dict[str, Any] = {
        "status": obs.get("status"),
        "message": obs.get("message"),
        "location": _location_block(ctx),
        "crop_context": _crop_block(ctx),
        "observation": obs.get("observation"),
        "ndvi": obs.get("ndvi"),
        "ndvi_detail": obs.get("ndvi_detail"),
        "indices": obs.get("indices"),
        "index_definitions": obs.get("index_definitions"),
        "recent_passes": obs.get("recent_passes"),
        "cached": obs.get("cached", False),
        "disclaimer": DISCLAIMER,
    }

    if obs.get("status") not in sat.REAL_STATUSES:
        out["classification"] = veg.classify_ndvi(None)
        out["alerts"] = []
        return out

    lat_r = ctx["latitude"]
    lon_r = ctx["longitude"]

    phen = veg.phenology_check(
        ndvi=obs.get("ndvi"), crop=ctx.get("crop", ""),
        days_after_sowing=ctx.get("days_after_sowing"),
        duration_days=ctx.get("duration_days"))
    unif = veg.uniformity(obs)
    water = veg.water_stress(obs)
    nitro = veg.nitrogen_signal(obs, phen)
    prev = _previous(db, user, (obs.get("observation") or {}).get("date"),
                     lat_r, lon_r)
    change = veg.detect_change(obs, prev)

    points: List[dict] = []
    if include_series:
        series = await sat.get_series(lat_r, lon_r, months=months)
        if series.get("status") == "ok":
            points = series.get("points", [])
            out["series"] = series
        else:
            # Fall back to whatever this farmer has already accumulated, so a
            # cloudy month or a quota hiccup does not blank the trend chart.
            points = _stored_points(db, user)
            out["series"] = {"status": series.get("status"),
                             "message": series.get("message"),
                             "points": points, "source": "stored_history"}

    out.update({
        "classification": veg.classify_ndvi(obs.get("ndvi")),
        "phenology": phen,
        "uniformity": unif,
        "water_stress": water,
        "nitrogen_signal": nitro,
        "change": change,
        "scouting": veg.scouting_priority(
            obs=obs, phenology=phen, change=change, uniformity_result=unif),
        "harvest": veg.harvest_readiness(
            obs=obs, series_points=points, crop=ctx.get("crop", ""),
            days_after_sowing=ctx.get("days_after_sowing"),
            duration_days=ctx.get("duration_days")),
        "productivity": veg.land_productivity(points),
        "alerts": veg.build_alerts(obs=obs, phenology=phen, change=change,
                                   water=water, uniformity_result=unif,
                                   crop=ctx.get("crop_display", "")),
    })
    return out


# =====================================================================
# Focused views — one per area of the app that uses satellite data
# =====================================================================

@router.get("/water-stress")
async def water_stress_view(
    lat: Optional[float] = Query(None, ge=-90, le=90),
    lon: Optional[float] = Query(None, ge=-180, le=180),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Canopy moisture for the Water & Irrigation page.

    Advisory only. This never unblocks the pump safety engine — a satellite
    pass from three days ago cannot tell you the tank is full or the sensor is
    live, which is exactly what those gates protect against.
    """
    obs, ctx = await _observe(db, user, lat, lon)
    if obs.get("status") not in sat.REAL_STATUSES:
        return {"status": obs.get("status"), "message": obs.get("message"),
                "location": _location_block(ctx), "water_stress": None}

    water = veg.water_stress(obs)
    return {
        "status": obs.get("status"),
        "location": _location_block(ctx),
        "observation": obs.get("observation"),
        "ndvi": obs.get("ndvi"),
        "water_stress": water,
        "overrides_pump_safety": False,
        "note": ("Complements your soil moisture sensor with a field-wide "
                 "view. The pump safety engine ignores this value entirely."),
        "disclaimer": DISCLAIMER,
    }


@router.get("/uniformity")
async def uniformity_view(
    lat: Optional[float] = Query(None, ge=-90, le=90),
    lon: Optional[float] = Query(None, ge=-180, le=180),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Within-field variability for fertiliser and top-dressing decisions."""
    obs, ctx = await _observe(db, user, lat, lon)
    if obs.get("status") not in sat.REAL_STATUSES:
        return {"status": obs.get("status"), "message": obs.get("message"),
                "location": _location_block(ctx), "uniformity": None}

    phen = veg.phenology_check(
        ndvi=obs.get("ndvi"), crop=ctx.get("crop", ""),
        days_after_sowing=ctx.get("days_after_sowing"),
        duration_days=ctx.get("duration_days"))

    return {
        "status": obs.get("status"),
        "location": _location_block(ctx),
        "crop_context": _crop_block(ctx),
        "observation": obs.get("observation"),
        "uniformity": veg.uniformity(obs),
        "nitrogen_signal": veg.nitrogen_signal(obs, phen),
        "phenology": phen,
        "rate_note": ("The satellite shows WHERE the field is weaker. It "
                      "cannot tell you how many kilograms to apply — take the "
                      "rate from your soil test and the fertiliser "
                      "calculator."),
        "disclaimer": DISCLAIMER,
    }


@router.get("/harvest-readiness")
async def harvest_view(
    lat: Optional[float] = Query(None, ge=-90, le=90),
    lon: Optional[float] = Query(None, ge=-180, le=180),
    months: int = Query(8, ge=3, le=24),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Senescence and harvest timing, for planning machinery hire."""
    obs, ctx = await _observe(db, user, lat, lon)
    if obs.get("status") not in sat.REAL_STATUSES:
        return {"status": obs.get("status"), "message": obs.get("message"),
                "location": _location_block(ctx), "harvest": None}

    series = await sat.get_series(ctx["latitude"], ctx["longitude"],
                                  months=months)
    points = (series.get("points", []) if series.get("status") == "ok"
              else _stored_points(db, user))

    harvest = veg.harvest_readiness(
        obs=obs, series_points=points, crop=ctx.get("crop", ""),
        days_after_sowing=ctx.get("days_after_sowing"),
        duration_days=ctx.get("duration_days"))

    booking = ""
    if harvest.get("stage") == "APPROACHING HARVEST":
        booking = ("Harvesters get booked out quickly at the peak of the "
                   "season. Arranging one now, from the Machinery page, "
                   "avoids paying a premium later.")
    elif harvest.get("stage") == "LATE BUT STILL GREEN":
        booking = ("Hold off booking until the canopy actually starts drying "
                   "down, or you may pay for a machine you cannot use.")

    return {
        "status": obs.get("status"),
        "location": _location_block(ctx),
        "crop_context": _crop_block(ctx),
        "observation": obs.get("observation"),
        "harvest": harvest,
        "series_points": points,
        "booking_advice": booking,
        "disclaimer": DISCLAIMER,
    }


@router.get("/scouting")
async def scouting_view(
    severity: str = "",
    lat: Optional[float] = Query(None, ge=-90, le=90),
    lon: Optional[float] = Query(None, ge=-180, le=180),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Field-scale context for a leaf photo diagnosis.

    Pass the severity a photo analysis returned and this says whether the rest
    of the field is heading the same way — the difference between a spot
    treatment and a spreading outbreak.
    """
    obs, ctx = await _observe(db, user, lat, lon)
    if obs.get("status") not in sat.REAL_STATUSES:
        return {"status": obs.get("status"), "message": obs.get("message"),
                "location": _location_block(ctx), "scouting": None}

    phen = veg.phenology_check(
        ndvi=obs.get("ndvi"), crop=ctx.get("crop", ""),
        days_after_sowing=ctx.get("days_after_sowing"),
        duration_days=ctx.get("duration_days"))
    unif = veg.uniformity(obs)
    prev = _previous(db, user, (obs.get("observation") or {}).get("date"),
                     ctx["latitude"], ctx["longitude"])
    change = veg.detect_change(obs, prev)

    return {
        "status": obs.get("status"),
        "location": _location_block(ctx),
        "observation": obs.get("observation"),
        "ndvi": obs.get("ndvi"),
        "classification": veg.classify_ndvi(obs.get("ndvi")),
        "phenology": phen,
        "uniformity": unif,
        "change": change,
        "scouting": veg.scouting_priority(
            obs=obs, phenology=phen, change=change,
            uniformity_result=unif, severity=severity),
        "photo_severity_used": severity or None,
        "disclaimer": DISCLAIMER,
    }


@router.get("/validate-location")
async def validate_location(
    lat: float = Query(..., ge=-90, le=90),
    lon: float = Query(..., ge=-180, le=180),
    months: int = Query(12, ge=4, le=24),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Do these coordinates look like cultivated land?

    Called from onboarding right after the farmer taps 'use my location'. A pin
    dropped on a rooftop silently poisons every downstream recommendation, and
    this is the cheapest possible moment to catch it.
    """
    obs = await sat.get_ndvi(lat, lon)
    if obs.get("status") not in sat.REAL_STATUSES:
        return {
            "status": obs.get("status"), "message": obs.get("message"),
            "checked": False, "latitude": lat, "longitude": lon,
            "blocking": False,
            "note": ("Could not check these coordinates from satellite right "
                     "now. You can continue — this check is optional."),
        }

    series = await sat.get_series(lat, lon, months=months)
    points = series.get("points", []) if series.get("status") == "ok" else []
    check = veg.land_cover_check(obs, points)

    return {
        "status": obs.get("status"),
        "latitude": lat, "longitude": lon,
        "checked": True,
        "blocking": False,          # advisory only; never blocks onboarding
        "land_cover": check,
        "current_ndvi": obs.get("ndvi"),
        "classification": veg.classify_ndvi(obs.get("ndvi")),
        "observation": obs.get("observation"),
        "months_of_history": len(points),
        "disclaimer": DISCLAIMER,
    }


@router.get("/season-anomaly")
async def season_anomaly_view(
    lat: Optional[float] = Query(None, ge=-90, le=90),
    lon: Optional[float] = Query(None, ge=-180, le=180),
    months: int = Query(18, ge=6, le=24),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """This season against this field's own history.

    Supporting evidence for a crop insurance or drought relief conversation.
    It is not an assessment and produces no loss figure.
    """
    lat, lon, source, farm = _resolve_point(db, user, lat, lon)
    if lat is None or lon is None:
        return dict(NO_LOCATION)

    series = await sat.get_series(lat, lon, months=months)
    points = (series.get("points", []) if series.get("status") == "ok"
              else _stored_points(db, user))
    anomaly = veg.season_anomaly(points)

    return {
        "status": series.get("status"),
        "location": {"latitude": lat, "longitude": lon, "source": source},
        "anomaly": anomaly,
        "points": points,
        "evidence_note": (
            "If you take this to an agriculture officer or an insurance "
            "surveyor, bring the observation dates and the field coordinates "
            "with it. Satellite greenness supports a claim; it does not "
            "substitute for a field inspection."),
        "disclaimer": DISCLAIMER,
    }


@router.get("/alerts")
async def satellite_alerts(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Satellite-derived alerts for this farmer, without writing to the DB.

    The Alerts page persists these through the normal alerts pipeline; this
    route is a read-only preview for the Satellite page.
    """
    obs, ctx = await _observe(db, user, None, None)
    if obs.get("status") not in sat.REAL_STATUSES:
        return {"status": obs.get("status"), "message": obs.get("message"),
                "alerts": []}

    phen = veg.phenology_check(
        ndvi=obs.get("ndvi"), crop=ctx.get("crop", ""),
        days_after_sowing=ctx.get("days_after_sowing"),
        duration_days=ctx.get("duration_days"))
    unif = veg.uniformity(obs)
    water = veg.water_stress(obs)
    prev = _previous(db, user, (obs.get("observation") or {}).get("date"),
                     ctx["latitude"], ctx["longitude"])
    change = veg.detect_change(obs, prev)

    return {
        "status": obs.get("status"),
        "observation": obs.get("observation"),
        "alerts": veg.build_alerts(obs=obs, phenology=phen, change=change,
                                   water=water, uniformity_result=unif,
                                   crop=ctx.get("crop_display", "")),
    }


# =====================================================================
# Admin / government view
# =====================================================================

admin_satellite_router = APIRouter(prefix="/api/admin", tags=["admin"])


@admin_satellite_router.get("/satellite-overview")
def satellite_overview(admin: User = Depends(require_admin),
                       db: Session = Depends(get_db)):
    """District-level canopy picture, built only from already-stored rows.

    No Earth Engine call is made here. An officer opening this dashboard must
    not be able to spend a whole day's quota by refreshing the page, and the
    numbers that matter for a regional view are already on disk.
    """
    rows = (db.query(SatelliteObservation)
            .filter(SatelliteObservation.ndvi.isnot(None))
            .order_by(SatelliteObservation.observed_on.desc())
            .limit(5000).all())

    # Latest row per user, so one heavily-monitored field cannot dominate.
    latest: Dict[int, SatelliteObservation] = {}
    for r in rows:
        if r.user_id not in latest:
            latest[r.user_id] = r

    by_district: Dict[str, List[float]] = {}
    for uid, r in latest.items():
        farm = db.query(Farm).filter(Farm.user_id == uid).first()
        key = (farm.district if farm and farm.district else "Unknown")
        by_district.setdefault(key, []).append(r.ndvi)

    districts = []
    for name, values in sorted(by_district.items()):
        mean = sum(values) / len(values)
        districts.append({
            "district": name,
            "fields_monitored": len(values),
            "mean_ndvi": round(mean, 3),
            "min_ndvi": round(min(values), 3),
            "max_ndvi": round(max(values), 3),
            "band": veg.classify_ndvi(mean)["band"],
            "fields_below_0_3": sum(1 for v in values if v < 0.30),
        })

    all_values = [r.ndvi for r in latest.values()]
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "fields_monitored": len(latest),
        "total_observations_stored": len(rows),
        "mean_ndvi": (round(sum(all_values) / len(all_values), 3)
                      if all_values else None),
        "districts": districts,
        "engine": {
            "ready": sat.status()["ready"],
            "credential_mode": sat.status()["credential_mode"],
            "project": settings.GEE_PROJECT,   # admin-only
            "collection": settings.GEE_COLLECTION,
        },
        "note": ("Aggregated from satellite observations already stored for "
                 "registered farms. Opening this page makes no Earth Engine "
                 "call. It is not a census of district cropland."),
    }


@admin_satellite_router.post("/satellite-cache/clear")
def clear_satellite_cache(admin: User = Depends(require_admin)):
    cleared = sat.clear_cache()
    return {"status": "ok", "entries_cleared": cleared}
