"""Mandi prices, farmer onboarding and crop advisory endpoints.

SECURITY: DATA_GOV_API_KEY is used only inside mandi_price.py, server side.
The browser calls /api/market-prices; the key never crosses that boundary.
"""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import get_current_user
from app.database.db import get_db
from app.models.models import Farm, SensorReading, SoilTest, User
from app.services import advisor as advisor_svc
from app.services import lifecycle as lifecycle_svc
from app.services import geocode as geocode_svc
from app.services import mandi_price
from app.services import rotation as rotation_svc
from app.services import satellite as satellite_svc
from app.services import vegetation as vegetation_svc
from app.services import weather as weather_svc
from app.services.crop_suitability import MP_CROPS

log = logging.getLogger("agri.api.advisor")

market_router = APIRouter(prefix="/api/market-prices", tags=["market-prices"])
onboarding_router = APIRouter(prefix="/api/onboarding", tags=["onboarding"])
advisor_router = APIRouter(prefix="/api/crop-advisor", tags=["crop-advisor"])


# =====================================================================
# MARKET PRICES  (data.gov.in AGMARKNET)
# =====================================================================

@market_router.get("")
async def market_prices(
    state: str = "",
    district: str = "",
    market: str = "",
    commodity: str = "",
    arrival_date: str = "",
    limit: int = Query(50, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    user: User = Depends(get_current_user),
):
    """Live mandi prices. Returns status ok | empty | unavailable | not_configured."""
    result = await mandi_price.fetch_prices(
        state=state, district=district, market=market,
        commodity=commodity, arrival_date=arrival_date,
        limit=limit, offset=offset)

    # Defence in depth: the key must never leave the server.
    result.pop("api_key", None)
    return result


@market_router.get("/summary")
async def market_summary(
    commodity: str,
    state: str = "",
    user: User = Depends(get_current_user),
):
    """One headline figure plus the best-paying market for a crop."""
    raw = await mandi_price.fetch_prices(state=state, commodity=commodity, limit=100)
    return mandi_price.summarise(raw, commodity)


@market_router.get("/my-crop")
async def my_crop_price(user: User = Depends(get_current_user),
                        db: Session = Depends(get_db)):
    """Price for whatever this farmer is actually growing, in their own state."""
    farm = db.query(Farm).filter(Farm.user_id == user.id).first()
    if not farm or not farm.crop:
        return {"status": "unavailable", "crop": None,
                "message": "No crop is set on your farm profile yet."}

    raw = await mandi_price.fetch_prices(
        state=farm.state or user.state or "", commodity=farm.crop, limit=100)
    return mandi_price.summarise(raw, farm.crop)


@market_router.get("/commodities")
def known_commodities(user: User = Depends(get_current_user)):
    """Crop keys we can map onto AGMARKNET commodity names."""
    return {
        "commodities": sorted({
            v for v in mandi_price.COMMODITY_ALIASES.values()}),
        "crop_keys": sorted(mandi_price.COMMODITY_ALIASES.keys()),
    }


# =====================================================================
# ONBOARDING
# =====================================================================

class OnboardingIn(BaseModel):
    # step 1 — location
    name: str = ""                         # farm/garden name
    state: str = ""
    district: str = ""
    village: str = ""
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    # step 2 — land (farm mode)
    land_size_acres: Optional[float] = Field(None, ge=0)
    farmer_category: str = "small"
    soil_type: str = ""
    irrigation_type: str = ""
    water_source: str = ""
    # step 2 — balcony/home-garden mode (same step, different fields; the
    # wizard shows one set or the other based on the farmer's registered
    # mode, but both are accepted here since a farmer can switch modes)
    area: str = ""                         # container size, e.g. "12 inch pot"
    sunlight: str = ""
    growing_medium: str = ""
    watering_method: str = ""
    # step 3 — cropping history
    previous_crop: str = ""
    previous_season: str = ""
    previous_variety: str = ""
    previous_sowing_date: Optional[str] = None
    previous_harvest_date: Optional[str] = None
    previous_yield_qtl: Optional[float] = Field(None, ge=0)
    previous_problems: str = ""
    # step 4 — current crop (optional)
    crop: str = ""
    variety: str = ""
    growth_stage: str = ""
    sowing_date: Optional[str] = None      # ISO yyyy-mm-dd
    expected_harvest_date: Optional[str] = None
    # Separate from land_size_acres: a farmer with 4 acres may have sown only
    # 1.5, and fertiliser computed on the whole holding would be far too high.
    crop_area_acres: Optional[float] = Field(None, ge=0)
    area_unit: str = "acre"
    water_availability: str = ""
    # step 5 — soil test (optional)
    nitrogen: Optional[float] = None
    phosphorus: Optional[float] = None
    potassium: Optional[float] = None
    ph: Optional[float] = None
    # sensor linking (optional, either mode)
    device_id: str = ""
    farming_method: str = ""


location_router = APIRouter(prefix="/api/location", tags=["location"])


@location_router.get("/reverse")
async def reverse_geocode(lat: float, lon: float,
                          user: User = Depends(get_current_user)):
    """GPS coordinates -> state and district, so the wizard can auto-fill.

    Offline district table first (instant, no network), OpenStreetMap second.
    """
    return await geocode_svc.reverse_geocode(lat, lon)


@location_router.get("/districts")
def mp_districts(user: User = Depends(get_current_user)):
    """District list for the manual dropdown fallback."""
    return {"state": "Madhya Pradesh",
            "districts": sorted(d[0] for d in geocode_svc.MP_DISTRICTS)}


@onboarding_router.get("/status")
def onboarding_status(user: User = Depends(get_current_user),
                      db: Session = Depends(get_db)):
    """What the farmer has told us, and what is still missing.

    Drives the onboarding wizard and the "your advice is limited because..."
    prompts elsewhere in the app.
    """
    farm = db.query(Farm).filter(Farm.user_id == user.id).first()
    soil = (db.query(SoilTest).filter(SoilTest.user_id == user.id)
            .order_by(SoilTest.created_at.desc()).first())

    if farm is None:
        return {"onboarded": False, "completeness": 0, "missing": [
            "location", "land size", "soil type", "irrigation",
            "previous crop"], "farm": None, "has_soil_test": False}

    checks = {
        "location": bool(farm.state and farm.district),
        "land size": bool(farm.land_size_acres),
        "soil type": bool(farm.soil_type),
        "irrigation": bool(farm.irrigation_type or farm.water_source),
        "previous crop": bool(farm.previous_crop),
        "current crop": bool(farm.crop),
        "sowing date": farm.sowing_date is not None,
        "soil test": soil is not None,
    }
    missing = [k for k, ok in checks.items() if not ok]
    completeness = round(100 * sum(checks.values()) / len(checks))

    return {
        "onboarded": bool(farm.onboarded),
        "completeness": completeness,
        "missing": missing,
        "has_soil_test": soil is not None,
        "farm": {
            "name": farm.name,
            "state": farm.state, "district": farm.district, "village": farm.village,
            "land_size_acres": farm.land_size_acres,
            "farmer_category": farm.farmer_category,
            "soil_type": farm.soil_type, "irrigation_type": farm.irrigation_type,
            "water_source": farm.water_source,
            "area": farm.area, "sunlight": farm.sunlight,
            "growing_medium": farm.growing_medium, "watering_method": farm.watering_method,
            "previous_crop": farm.previous_crop,
            "previous_season": farm.previous_season,
            "crop": farm.crop, "variety": farm.variety, "growth_stage": farm.growth_stage,
            "sowing_date": farm.sowing_date.date().isoformat() if farm.sowing_date else None,
            "latitude": farm.latitude, "longitude": farm.longitude,
            "device_id": farm.device_id, "farming_method": farm.farming_method,
        },
    }


@onboarding_router.post("/save")
def save_onboarding(data: OnboardingIn,
                    user: User = Depends(get_current_user),
                    db: Session = Depends(get_db)):
    """Save onboarding answers. Partial saves allowed — the wizard is resumable.

    Only fields the farmer actually supplied are written. Nothing is defaulted
    to a plausible-looking value, because an invented land size or soil type
    would silently corrupt every downstream recommendation.
    """
    farm = db.query(Farm).filter(Farm.user_id == user.id).first()
    if farm is None:
        farm = Farm(user_id=user.id, mode=user.mode or "farm")
        db.add(farm)

    payload = data.model_dump(exclude_unset=True)

    simple = ("name", "state", "district", "village", "latitude", "longitude",
              "land_size_acres", "farmer_category", "soil_type",
              "irrigation_type", "water_source", "area", "sunlight",
              "growing_medium", "watering_method", "previous_crop",
              "previous_season", "crop", "variety", "growth_stage",
              "device_id", "farming_method",
              "previous_variety", "previous_problems", "previous_yield_qtl",
              "crop_area_acres", "area_unit", "water_availability")
    for field in simple:
        if field in payload and payload[field] not in (None, ""):
            setattr(farm, field, payload[field])

    # All four dates go through the same parse, so one bad value is reported
    # by name instead of failing the whole save with a generic message.
    for field in ("sowing_date", "expected_harvest_date",
                  "previous_sowing_date", "previous_harvest_date"):
        if payload.get(field):
            try:
                setattr(farm, field, datetime.fromisoformat(payload[field]))
            except ValueError:
                raise HTTPException(
                    400, f"{field} must be ISO format yyyy-mm-dd")

    # NOTE: expected_harvest_date is deliberately NOT auto-filled here.
    #
    # Writing a derived date into the same column as a farmer-entered one
    # makes the two indistinguishable afterwards, so the profile would report
    # a calculation as CONFIRMED ("as entered by you"). farm_profile derives
    # it on READ instead and labels it ESTIMATED, which keeps this column
    # meaning exactly one thing: the farmer told us.

    # Mirror location onto the user so pre-login/profile screens agree.
    if farm.state:
        user.state = farm.state
    if farm.district:
        user.district = farm.district

    # Optional soil test in the same step.
    soil_vals = {k: payload.get(k) for k in ("nitrogen", "phosphorus", "potassium", "ph")}
    if any(v is not None for v in soil_vals.values()):
        db.add(SoilTest(
            user_id=user.id,
            nitrogen=soil_vals["nitrogen"] or 0,
            phosphorus=soil_vals["phosphorus"] or 0,
            potassium=soil_vals["potassium"] or 0,
            ph=soil_vals["ph"] or 7.0,
        ))

    # Onboarded once the minimum needed for a real recommendation is present.
    # ONE source of truth for "is setup complete".
    #
    # This line used to hardcode `state and land_size_acres and soil_type`
    # while farm_profile.REQUIRED_FIELDS said something different. When those
    # two drifted apart, `onboarded` stayed False forever — and because the
    # route guard needs BOTH the fields and the flag, the farmer was sent back
    # to setup on every navigation no matter how many times they completed it.
    #
    # Reading the constant means the two can never disagree again.
    from app.services.farm_profile import REQUIRED_FIELDS
    farm.onboarded = all(getattr(farm, f, None) for f in REQUIRED_FIELDS)

    db.commit()
    db.refresh(farm)
    return onboarding_status(user, db)


# =====================================================================
# CROP ADVISOR
# =====================================================================

class AdvisorIn(BaseModel):
    state: str = ""
    district: str = ""
    season: str = ""
    previous_crop: str = ""
    soil_type: str = ""
    irrigation_type: str = ""
    water_source: str = ""
    nitrogen: Optional[float] = None
    phosphorus: Optional[float] = None
    potassium: Optional[float] = None
    ph: Optional[float] = None
    moisture: Optional[float] = None
    include_market: bool = True
    include_satellite: bool = True
    use_my_data: bool = True
    # Optional explicit field coordinates. Supplying these lets a farmer get a
    # satellite-informed advisory for a plot before it exists on their profile.
    latitude: Optional[float] = None
    longitude: Optional[float] = None


@advisor_router.post("/recommend")
async def recommend(data: AdvisorIn,
                    user: User = Depends(get_current_user),
                    db: Session = Depends(get_db)):
    """Ranked crop advisory from soil + weather + rotation + live market."""

    soil: Dict[str, Any] = {}
    soil_source = advisor_svc.SOURCE_MISSING
    state = data.state
    district = data.district
    previous_crop = data.previous_crop
    soil_type = data.soil_type
    irrigation = data.irrigation_type
    water_source = data.water_source

    if data.use_my_data:
        farm = db.query(Farm).filter(Farm.user_id == user.id).first()
        if farm:
            state = state or farm.state
            district = district or farm.district
            previous_crop = previous_crop or farm.previous_crop
            soil_type = soil_type or farm.soil_type
            irrigation = irrigation or farm.irrigation_type
            water_source = water_source or farm.water_source

        test = (db.query(SoilTest).filter(SoilTest.user_id == user.id)
                .order_by(SoilTest.created_at.desc()).first())
        if test:
            soil = {"nitrogen": test.nitrogen, "phosphorus": test.phosphorus,
                    "potassium": test.potassium, "ph": test.ph}
            soil_source = advisor_svc.SOURCE_MANUAL

        device_id = farm.device_id if farm and farm.device_id else "ESP32-001"
        reading = (db.query(SensorReading)
                   .filter(SensorReading.device_id == device_id)
                   .order_by(SensorReading.created_at.desc()).first())
        if reading:
            soil["moisture"] = reading.soil_moisture
            # A live sensor outranks a typed-in test as the moisture source.
            soil_source = advisor_svc.SOURCE_SENSOR

    # Explicit values from the request always win over stored ones.
    for key, val in (("nitrogen", data.nitrogen), ("phosphorus", data.phosphorus),
                     ("potassium", data.potassium), ("ph", data.ph),
                     ("moisture", data.moisture)):
        if val is not None:
            soil[key] = val
            soil_source = advisor_svc.SOURCE_MANUAL

    from app.core.timing import StageTimer
    timer = StageTimer("ADVISOR")

    # Resolve coordinates first so weather and satellite can be launched
    # together. Both are network calls that do not depend on each other, so
    # chaining them just adds their latencies.
    lat, lon = data.latitude, data.longitude
    if lat is None or lon is None:
        farm = db.query(Farm).filter(Farm.user_id == user.id).first()
        if farm and farm.latitude is not None and farm.longitude is not None:
            lat, lon = float(farm.latitude), float(farm.longitude)

    async def _weather_leg():
        if settings.DEMO_FAST_MODE:
            return None
        try:
            return await asyncio.wait_for(
                weather_svc.get_weather(),
                timeout=settings.ADVISOR_WEATHER_BUDGET_S)
        except Exception as exc:                        # noqa: BLE001
            log.warning("weather unavailable for advisory: %s", exc)
            return None

    async def _satellite_leg():
        if settings.DEMO_FAST_MODE:
            return None
        if not data.include_satellite or lat is None or lon is None:
            return None
        try:
            return await asyncio.wait_for(
                satellite_svc.get_ndvi(lat, lon),
                timeout=settings.ADVISOR_SATELLITE_BUDGET_S)
        except asyncio.TimeoutError:
            log.info("satellite skipped for advisory: exceeded %ss budget",
                     settings.ADVISOR_SATELLITE_BUDGET_S)
            return {"status": "skipped",
                    "message": ("Satellite context was skipped to keep this "
                                "page fast. Open the Satellite page for the "
                                "full field view.")}
        except Exception as exc:                        # noqa: BLE001
            log.warning("satellite unavailable for advisory: %s", exc)
            return None

    with timer.stage("weather + satellite (concurrent)"):
        wx, satellite = await asyncio.gather(_weather_leg(), _satellite_leg())

    weather: Dict[str, Any] = {}
    if wx:
        weather = {"temperature": wx.get("temperature"),
                   "humidity": wx.get("humidity"),
                   "rain_mm": wx.get("rain_mm"),
                   "rain_probability": wx.get("rain_probability"),
                   "condition": wx.get("condition")}

    with timer.stage("deterministic ranking + market"):
        result = await advisor_svc.build_advisory(
            state=state, district=district, soil=soil, soil_source=soil_source,
            weather=weather, previous_crop=previous_crop,
            irrigation_type=irrigation, water_source=water_source,
            soil_type=soil_type, season=data.season,
            include_market=data.include_market, satellite=satellite)

    result["weather_used"] = weather or None
    result["timing"] = timer.finish()
    if not weather:
        result["weather_note"] = "Weather data temporarily unavailable."
    return result


@advisor_router.get("/my-crop-stage")
def my_crop_stage(user: User = Depends(get_current_user),
                  db: Session = Depends(get_db)):
    """Lifecycle stage computed from the stored sowing date.

    This is why sowing_date matters: without it nobody can be told what to do
    this week without typing their growth stage in by hand every time.
    """
    farm = db.query(Farm).filter(Farm.user_id == user.id).first()
    if not farm or not farm.crop:
        return {"status": "no_crop",
                "message": "No current crop is set on your farm profile."}

    if not farm.sowing_date:
        data = lifecycle_svc.get_lifecycle(farm.crop)
        return {"status": "no_sowing_date", "crop": farm.crop,
                "message": "Add your sowing date to see which stage your crop "
                           "is in and what to do this week.",
                "lifecycle": data}

    days = (datetime.utcnow() - farm.sowing_date).days
    stage = lifecycle_svc.current_stage(farm.crop, days)
    if stage is None:
        return {"status": "unsupported_crop", "crop": farm.crop,
                "message": f"No lifecycle data for {farm.crop}. Supported: "
                           f"{', '.join(lifecycle_svc.supported_crops())}"}

    return {"status": "ok", "crop": farm.crop,
            "sowing_date": farm.sowing_date.date().isoformat(),
            "days_after_sowing": days, "stage": stage}


@advisor_router.get("/rotation")
def rotation_advice(previous_crop: str,
                    user: User = Depends(get_current_user)):
    """Rank known crops purely by rotation fit against the previous crop."""
    return {
        "previous_crop": previous_crop,
        "family": rotation_svc.family_of(previous_crop),
        "ranked": rotation_svc.suggested_rotations(
            previous_crop, list(MP_CROPS.keys())),
        "nitrogen_carryover_kg_ha": rotation_svc.nitrogen_carryover(previous_crop)[0],
        "nitrogen_note": rotation_svc.nitrogen_carryover(previous_crop)[1],
    }
