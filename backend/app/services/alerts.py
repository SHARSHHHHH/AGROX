"""Alert generation and persistence.

Rules live in alert_rules.py (pure, no DB, no network, no LLM). This module
gathers the inputs, runs the rules, and decides what actually reaches the
farmer.

DEDUPLICATION AND EXPIRY
------------------------
The previous check was:

    same type AND unread -> skip

which meant that the moment a farmer marked an alert read, the identical alert
regenerated on the next poll. Same sentence, forever. Farmers respond to that
by ignoring the alerts page entirely, which costs them the alerts that matter.

Now every alert carries a `dedupe_key` describing the SITUATION — the day, the
value bucket, the district, the stage — plus an `expires_at`. A new row is only
written when no unexpired, undismissed alert shares that key, regardless of
read state. When the situation genuinely changes (moisture 31% -> 12% crosses a
bucket) the key changes and a new alert is correctly raised.
"""

import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from app.core.budget import budgeted
from app.core.config import settings

from app.models.models import (Alert, ExternalAdvisory, Farm, MachineryListing,
                               PestObservation, SensorReading, SoilTest,
                               SupplyOffer, User)
from app.services import alert_rules as rules
from app.services import satellite as satellite_svc
from app.services import vegetation as veg
from app.services import weather as weather_svc
from app.services.recommendation import analyze_soil, classify_moisture

log = logging.getLogger("agri.alerts")


def _add(db: Session, user_id: int, type_: str, severity: str, title: str,
         msg: str):
    """Legacy helper. Kept because other modules still call it."""
    return _persist(db, user_id, {
        "type": type_, "category": "general", "priority": "MEDIUM",
        "severity": severity, "title": title, "message": msg, "action": "",
        "dedupe_key": f"{type_}:{datetime.utcnow().date().isoformat()}",
        "expires_in_hours": 24, "source_name": "", "source_url": "",
        "source_date": None, "payload": {},
    })


def _persist(db: Session, user_id: int, spec: Dict[str, Any]) -> Optional[Alert]:
    """Write one alert unless an equivalent live one already exists."""
    key = spec.get("dedupe_key") or spec["type"]
    now = datetime.utcnow()

    existing = (db.query(Alert)
                .filter(Alert.user_id == user_id,
                        Alert.dedupe_key == key,
                        Alert.dismissed == False)          # noqa: E712
                .order_by(Alert.created_at.desc())
                .first())
    if existing is not None:
        # Still live -> suppress. Expired -> fall through and raise it again,
        # because the situation has recurred.
        if existing.expires_at is None or existing.expires_at > now:
            return None

    alert = Alert(
        user_id=user_id,
        type=spec["type"],
        category=spec.get("category", "general"),
        priority=spec.get("priority", "MEDIUM"),
        severity=spec.get("severity", "INFO"),
        title=spec["title"],
        message=spec["message"],
        action=spec.get("action", ""),
        source_name=spec.get("source_name", ""),
        source_url=spec.get("source_url", ""),
        source_date=spec.get("source_date"),
        dedupe_key=key,
        expires_at=now + timedelta(hours=spec.get("expires_in_hours", 24)),
        payload=spec.get("payload") or {},
    )
    db.add(alert)
    return alert


# =====================================================================
# Input gathering
# =====================================================================

def _crop_context(farm: Optional[Farm]) -> Dict[str, Any]:
    from app.services import lifecycle as lc
    from app.services.crop_suitability import MP_CROPS

    if not farm or not farm.crop:
        return {"crop": "", "crop_display": "your crop", "stage": None,
                "days_after_sowing": None, "days_to_harvest": None}

    key = (farm.crop or "").strip().lower()
    spec = MP_CROPS.get(key)
    das = None
    if farm.sowing_date:
        das = (datetime.utcnow() - farm.sowing_date).days
        if das < 0:
            das = None

    stage = lc.current_stage(key, das) if das is not None else None
    duration = spec["duration_days"] if spec else None
    dth = (duration - das) if duration and das is not None else None

    return {"crop": key,
            "crop_display": spec["display"] if spec else farm.crop,
            "stage": stage, "days_after_sowing": das, "days_to_harvest": dth}


def _forecast_shape(wx: Dict[str, Any]) -> Dict[str, Any]:
    """Collapse the forecast into the few numbers the rules need."""
    forecast = wx.get("forecast") or []
    rain_5day = 0.0
    wet_days = 0
    for day in forecast[:5]:
        mm = day.get("rain_mm") or day.get("precipitation") or 0
        try:
            mm = float(mm)
        except (TypeError, ValueError):
            mm = 0.0
        rain_5day += mm
        # 5 mm is roughly the point at which field work becomes difficult.
        if mm >= 5:
            wet_days += 1
    return {"rain_mm_5day": round(rain_5day, 1) if forecast else None,
            "wet_days_ahead": wet_days}


def _nearby_pest_reports(db: Session, farm: Optional[Farm],
                         crop: str) -> List[dict]:
    """Same crop, confirmed recently, by farmers in OTHER districts.

    Uses this application's own pest_observations — real detections by real
    users, not an external feed. Deliberately excludes the farmer's own
    district: a report from their own area is not "nearby", it is here, and
    they would already know.
    """
    if not farm or not farm.district or not crop:
        return []

    since = datetime.utcnow() - timedelta(days=14)
    rows = (db.query(PestObservation, Farm)
            .join(Farm, Farm.user_id == PestObservation.user_id)
            .filter(PestObservation.crop == crop,
                    PestObservation.created_at >= since,
                    PestObservation.result_type.in_(("pest", "disease")),
                    PestObservation.uncertain == False,      # noqa: E712
                    Farm.state == farm.state,
                    Farm.district != farm.district)
            .all())

    grouped: Dict[tuple, dict] = {}
    for obs, other in rows:
        k = ((obs.pest_name or "").lower(), other.district)
        if k not in grouped:
            grouped[k] = {"pest_name": obs.pest_name or "a pest",
                          "pest_key": k[0], "district": other.district,
                          "count": 0}
        grouped[k]["count"] += 1
    return sorted(grouped.values(), key=lambda r: -r["count"])[:3]


def _matching_advisories(db: Session, farm: Optional[Farm],
                         crop: str) -> List[dict]:
    """Admin-curated official advisories that apply to this farmer."""
    now = datetime.utcnow()
    q = (db.query(ExternalAdvisory)
         .filter(ExternalAdvisory.active == True)            # noqa: E712
         .filter((ExternalAdvisory.expires_at.is_(None))
                 | (ExternalAdvisory.expires_at > now)))

    state = (farm.state if farm else "") or ""
    district = (farm.district if farm else "") or ""

    out = []
    for adv in q.all():
        # Empty state/district/crops means "applies to everyone".
        if adv.state and state and adv.state.lower() != state.lower():
            continue
        districts = [d.lower() for d in (adv.districts or [])]
        if districts and district and district.lower() not in districts:
            continue
        crops = [c.lower() for c in (adv.crops or [])]
        if crops and crop and crop.lower() not in crops:
            continue

        out.append({
            "id": adv.id, "kind": adv.kind, "title": adv.title,
            "summary": adv.summary, "action": adv.action,
            "amount": adv.amount, "amount_unit": adv.amount_unit,
            "amount_note": adv.amount_note,
            "source_name": adv.source_name, "source_url": adv.source_url,
            "published_on": adv.published_on, "priority": adv.priority,
        })
    return out


def _verified_supply_offers(db: Session, farm: Optional[Farm]) -> List[dict]:
    """Admin-verified fertiliser/manure offers in the farmer's district.

    Unverified offers are excluded deliberately. Pushing an unchecked price to
    a farmer is an advertisement we cannot stand behind.
    """
    if not farm or not farm.district:
        return []
    now = datetime.utcnow()
    rows = (db.query(SupplyOffer)
            .filter(SupplyOffer.active == True,              # noqa: E712
                    SupplyOffer.verified == True,            # noqa: E712
                    SupplyOffer.district == farm.district)
            .filter((SupplyOffer.expires_at.is_(None))
                    | (SupplyOffer.expires_at > now))
            .limit(5).all())
    return [{"id": o.id, "title": o.title, "category": o.category,
             "price": o.price, "price_unit": o.price_unit} for o in rows]


def _nearby_machinery(db: Session, farm: Optional[Farm]) -> List[dict]:
    if not farm or not farm.district:
        return []
    rows = (db.query(MachineryListing)
            .filter(MachineryListing.district == farm.district)
            .limit(5).all())
    return [{"machine_name": getattr(r, "title", "") or r.machine_key,
             "machine_key": r.machine_key,
             "distance_km": "—"} for r in rows]


# =====================================================================
# Orchestration
# =====================================================================

async def generate_for_user(db: Session, user) -> List[Alert]:
    """Run every rule family. One failing family must not stop the others."""
    farm = db.query(Farm).filter(Farm.user_id == user.id).first()
    device_id = farm.device_id if farm and farm.device_id else "ESP32-001"
    ctx = _crop_context(farm)
    crop = ctx["crop"]
    crop_display = ctx["crop_display"]

    specs: List[Dict[str, Any]] = []

    reading = (db.query(SensorReading)
               .filter(SensorReading.device_id == device_id)
               .order_by(SensorReading.created_at.desc()).first())

    wx: Dict[str, Any] = {}
    try:
        lat = float(farm.latitude) if farm and farm.latitude is not None else 13.08
        lon = float(farm.longitude) if farm and farm.longitude is not None else 80.27
        # /api/alerts is polled from the alerts page; an unbudgeted 15s
        # weather call there is felt on every single load.
        if settings.DEMO_FAST_MODE:
            raise RuntimeError("fast mode: weather skipped")
        wx = await budgeted(weather_svc.get_weather(lat, lon),
                            settings.ALERTS_WEATHER_BUDGET_S, "weather") or {}
    except Exception as exc:                                # noqa: BLE001
        log.warning("weather unavailable for alerts: %s", exc)

    fc = _forecast_shape(wx)

    # --- 1 irrigation, 2 tank, 3 weather ---
    if reading is not None:
        try:
            specs += rules.irrigation(
                moisture=reading.soil_moisture,
                moisture_status=classify_moisture(reading.soil_moisture, crop or "default"),
                crop_display=crop_display,
                rain_probability=wx.get("rain_probability"),
                rain_mm_5day=fc["rain_mm_5day"],
                stage=(ctx["stage"] or {}).get("stage", "") if ctx["stage"] else "")
            specs += rules.water_tank(level=reading.water_level)
        except Exception as exc:                            # noqa: BLE001
            log.warning("sensor rules failed: %s", exc)

    try:
        specs += rules.weather(
            temperature=(wx.get("temperature")
                         if wx else (reading.temperature if reading else None)),
            rain_probability=wx.get("rain_probability"),
            rain_mm_5day=fc["rain_mm_5day"],
            wind_kph=wx.get("wind_kph"),
            wet_days_ahead=fc["wet_days_ahead"],
            moisture=reading.soil_moisture if reading else None,
            crop_display=crop_display)
    except Exception as exc:                                # noqa: BLE001
        log.warning("weather rules failed: %s", exc)

    # --- 4 nearby pest ---
    try:
        specs += rules.nearby_pest(
            reports=_nearby_pest_reports(db, farm, crop),
            crop_display=crop_display,
            district=(farm.district if farm else "") or "your district")
    except Exception as exc:                                # noqa: BLE001
        log.warning("nearby pest rules failed: %s", exc)

    # --- 5, 6, 7 official advisories ---
    try:
        for adv in _matching_advisories(db, farm, crop):
            spec = rules.official_advisory(
                adv, crop_display=crop_display,
                district=(farm.district if farm else "") or "")
            if spec:
                specs.append(spec)
    except Exception as exc:                                # noqa: BLE001
        log.warning("advisory rules failed: %s", exc)

    # --- 10 lifecycle, and 9 machinery keyed off it ---
    try:
        if ctx["stage"]:
            specs += rules.lifecycle_stage(
                crop_display=crop_display, stage=ctx["stage"],
                days_after_sowing=ctx["days_after_sowing"],
                days_to_harvest=ctx["days_to_harvest"])

            dth = ctx["days_to_harvest"]
            if dth is not None and 0 < dth <= 21:
                specs += rules.machinery_nearby(
                    listings=_nearby_machinery(db, farm),
                    reason=f"Your {crop_display} harvest is about {dth} days away.",
                    stage="harvest")
    except Exception as exc:                                # noqa: BLE001
        log.warning("lifecycle rules failed: %s", exc)

    # --- 8 fertiliser / manure offers ---
    try:
        specs += rules.supply_offers(offers=_verified_supply_offers(db, farm))
    except Exception as exc:                                # noqa: BLE001
        log.warning("supply offer rules failed: %s", exc)

    # --- soil, kept from the original implementation ---
    created: List[Alert] = []
    soil = (db.query(SoilTest).filter(SoilTest.user_id == user.id)
            .order_by(SoilTest.created_at.desc()).first())
    if soil:
        res = analyze_soil(soil.nitrogen, soil.phosphorus, soil.potassium,
                           soil.ph, crop or "default")
        if res["warnings"]:
            specs.append({
                "type": "NUTRIENT_DEFICIENCY", "category": "soil",
                "priority": "MEDIUM", "severity": "WARNING",
                "title": "Possible nutrient deficiency",
                "message": res["warnings"][0],
                "action": "Confirm with a soil test before buying fertiliser.",
                "dedupe_key": f"nutrient:{soil.id}",
                "expires_in_hours": 24 * 14, "payload": {}})

    for spec in specs:
        row = _persist(db, user.id, spec)
        if row is not None:
            created.append(row)

    created += await _satellite_alerts(db, user, farm, crop)

    db.commit()
    return [c for c in created if c]


async def _satellite_alerts(db: Session, user, farm, crop: str) -> list:
    """Alerts the ground sensors physically cannot produce.

    A soil probe measures one point. These come from the whole field: a canopy
    collapse across the plot, growth falling behind the expected curve, patchy
    establishment.

    Wrapped end to end: Earth Engine being slow, unconfigured or down must
    never stop the sensor and weather alerts above from reaching the farmer.
    """
    from app.models.models import SatelliteObservation

    if settings.DEMO_FAST_MODE:
        return []
    if not farm or farm.latitude is None or farm.longitude is None:
        return []

    try:
        # Satellite alerts are valuable but never urgent enough to make the
        # alerts page wait a minute. Past the budget they simply appear on the
        # next poll, once Earth Engine has warmed its cache.
        obs = await budgeted(
            satellite_svc.get_ndvi(float(farm.latitude), float(farm.longitude)),
            settings.ALERTS_SATELLITE_BUDGET_S, "satellite alerts")
        if not obs or obs.get("status") not in satellite_svc.REAL_STATUSES:
            return []

        observed_on = (obs.get("observation") or {}).get("date")

        prev_row = (db.query(SatelliteObservation)
                    .filter(SatelliteObservation.user_id == user.id,
                            SatelliteObservation.ndvi.isnot(None),
                            SatelliteObservation.observed_on < (observed_on or ""))
                    .order_by(SatelliteObservation.observed_on.desc())
                    .first())
        previous = ({"ndvi": prev_row.ndvi, "date": prev_row.observed_on}
                    if prev_row else None)

        duration = None
        das = None
        if farm.crop:
            from app.services.crop_suitability import MP_CROPS
            spec = MP_CROPS.get(farm.crop.strip().lower())
            duration = spec["duration_days"] if spec else None
        if farm.sowing_date:
            das = (datetime.utcnow() - farm.sowing_date).days

        phen = veg.phenology_check(ndvi=obs.get("ndvi"), crop=farm.crop or "",
                                   days_after_sowing=das,
                                   duration_days=duration)
        payloads = veg.build_alerts(
            obs=obs, phenology=phen,
            change=veg.detect_change(obs, previous),
            water=veg.water_stress(obs),
            uniformity_result=veg.uniformity(obs),
            crop=farm.crop or crop)

        out = []
        for p in payloads:
            row = _persist(db, user.id, {
                "type": p["type"], "category": "satellite",
                "priority": ("CRITICAL" if p["severity"] == "CRITICAL"
                             else "HIGH" if p["severity"] == "WARNING" else "LOW"),
                "severity": p["severity"], "title": p["title"],
                "message": p["message"],
                "action": "Walk the field to confirm before acting.",
                "source_name": "Sentinel-2 (Copernicus)",
                "dedupe_key": f"{p['type']}:{observed_on}",
                "expires_in_hours": 24 * 7, "payload": {},
            })
            if row is not None:
                out.append(row)
        return out

    except Exception as exc:                                # noqa: BLE001
        log.warning("satellite alerts skipped: %s: %s", type(exc).__name__, exc)
        return []


def expire_old(db: Session, user_id: int) -> int:
    """Mark expired alerts read so the unread count reflects live issues only."""
    now = datetime.utcnow()
    rows = (db.query(Alert)
            .filter(Alert.user_id == user_id, Alert.read == False,   # noqa: E712
                    Alert.expires_at.isnot(None), Alert.expires_at < now)
            .all())
    for r in rows:
        r.read = True
    if rows:
        db.commit()
    return len(rows)
