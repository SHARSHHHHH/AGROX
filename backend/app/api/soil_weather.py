import logging

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.database.db import get_db
from app.models.models import SoilTest, SensorReading, Farm, User, IrrigationEvent
from app.schemas.schemas import SoilTestIn
from app.core.security import get_current_user
from app.services.recommendation import analyze_soil, recommend_irrigation
from app.core.budget import budgeted
from app.core.config import settings
from app.services import satellite as satellite_svc
from app.services import vegetation as vegetation_svc
from app.services import weather as weather_svc

log = logging.getLogger("agri.api.soil_weather")

soil_router = APIRouter(prefix="/api/soil", tags=["soil"])
weather_router = APIRouter(prefix="/api/weather", tags=["weather"])
irrigation_router = APIRouter(prefix="/api/irrigation", tags=["irrigation"])


# ---------- SOIL ----------
@soil_router.get("")
def get_soil(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    farm = db.query(Farm).filter(Farm.user_id == user.id).first()
    crop = farm.crop if farm else "default"
    soil = (db.query(SoilTest).filter(SoilTest.user_id == user.id)
            .order_by(SoilTest.created_at.desc()).first())
    if not soil:
        return {"message": "No soil test yet. Enter your soil test results.",
                "has_data": False}
    res = analyze_soil(soil.nitrogen, soil.phosphorus, soil.potassium, soil.ph, crop)
    res["has_data"] = True
    res["measured_at"] = soil.created_at.isoformat()
    return res


@soil_router.post("/test")
def add_soil_test(data: SoilTestIn, user: User = Depends(get_current_user),
                  db: Session = Depends(get_db)):
    st = SoilTest(user_id=user.id, **data.model_dump(), source="manual")
    db.add(st); db.commit(); db.refresh(st)
    farm = db.query(Farm).filter(Farm.user_id == user.id).first()
    crop = farm.crop if farm else "default"
    return analyze_soil(st.nitrogen, st.phosphorus, st.potassium, st.ph, crop)


@soil_router.get("/history")
def soil_history(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    rows = (db.query(SoilTest).filter(SoilTest.user_id == user.id)
            .order_by(SoilTest.created_at.desc()).limit(20).all())
    return [{"nitrogen": r.nitrogen, "phosphorus": r.phosphorus,
             "potassium": r.potassium, "ph": r.ph,
             "date": r.created_at.isoformat()} for r in rows]


# ---------- WEATHER ----------
@weather_router.get("/current")
async def current_weather():
    return await weather_svc.get_weather()


@weather_router.get("/forecast")
async def forecast():
    wx = await weather_svc.get_weather()
    return {"forecast": wx.get("forecast", []),
            "interpretation": wx.get("interpretation", "")}


# ---------- IRRIGATION ----------
@irrigation_router.get("/recommendation")
async def irrigation_recommendation(user: User = Depends(get_current_user),
                                    db: Session = Depends(get_db)):
    farm = db.query(Farm).filter(Farm.user_id == user.id).first()
    device_id = farm.device_id if farm and farm.device_id else "ESP32-001"
    crop = farm.crop if farm else "default"
    reading = (db.query(SensorReading).filter(SensorReading.device_id == device_id)
               .order_by(SensorReading.created_at.desc()).first())
    wx = await weather_svc.get_weather()
    if not reading:
        return {"message": "No sensor data available for a recommendation."}
    rec = recommend_irrigation(
        reading.soil_moisture, reading.temperature, reading.humidity,
        wx["rain_probability"], crop,
        farm.growth_stage if farm else "", farm.soil_type if farm else "")
    rec["inputs"] = {
        "soil_moisture": reading.soil_moisture, "temperature": reading.temperature,
        "humidity": reading.humidity, "rain_probability": wx["rain_probability"],
        "crop": crop}

    # --- satellite canopy moisture, as a SECOND OPINION ---------------
    # The soil probe measures one point at one depth. The satellite measures
    # water held in the canopy across the whole plot. When they disagree, that
    # is worth knowing: a wet probe with a stressed canopy usually means the
    # probe is sitting in a wet patch, or the roots are not reaching the water.
    #
    # It is attached alongside the recommendation, never merged into it. The
    # duration and the irrigate/do-not-irrigate decision are unchanged, because
    # a reading that may be several days old must not move a pump command.
    rec["satellite"] = await _satellite_water_context(farm, reading.soil_moisture)
    return rec


async def _satellite_water_context(farm, sensor_moisture):
    """Canopy moisture from Sentinel-2, plus an agree/disagree note."""
    if not farm or farm.latitude is None or farm.longitude is None:
        return {"status": "no_location",
                "message": ("Add your field's coordinates to compare your "
                            "sensor against a field-wide satellite view.")}
    try:
        # A second opinion must not delay the irrigation recommendation it is
        # commenting on.
        obs = await budgeted(
            satellite_svc.get_ndvi(float(farm.latitude), float(farm.longitude)),
            settings.PROFILE_SATELLITE_BUDGET_S, "irrigation satellite")
        if not obs:
            return {"status": "skipped",
                    "message": ("Satellite check was skipped to keep this "
                                "page fast.")}
        if obs.get("status") not in satellite_svc.REAL_STATUSES:
            return {"status": obs.get("status"), "message": obs.get("message")}

        water = vegetation_svc.water_stress(obs)
        o = obs.get("observation") or {}

        agreement = ""
        if water.get("available") and sensor_moisture is not None:
            stressed_canopy = water["level"] in ("MILD STRESS", "STRESSED")
            wet_soil = sensor_moisture >= 50
            if stressed_canopy and wet_soil:
                agreement = (
                    "Your sensor reads moist soil but the canopy looks "
                    "stressed from orbit. Check whether the sensor sits in a "
                    "wetter patch than the rest of the field, and whether "
                    "roots are reaching that moisture.")
            elif not stressed_canopy and sensor_moisture < 30:
                agreement = (
                    "Your sensor reads dry but the canopy still holds water. "
                    "The crop may be drawing from deeper moisture than the "
                    "probe reaches.")
            else:
                agreement = "The satellite view agrees with your soil sensor."

        return {
            "status": obs.get("status"),
            "observed_on": o.get("date"),
            "days_ago": o.get("days_ago"),
            "ndvi": obs.get("ndvi"),
            "water_stress": water,
            "agreement": agreement,
            "affects_recommendation": False,
            "note": ("Field-wide second opinion. It does not change the "
                     "irrigation decision above and never overrides a pump "
                     "safety block."),
        }
    except Exception as exc:                            # noqa: BLE001
        log.warning("satellite context unavailable: %s", exc)
        return {"status": "unavailable",
                "message": "Satellite data is temporarily unavailable."}


@irrigation_router.post("/event")
def log_irrigation(duration_min: float, reason: str = "manual",
                   user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ev = IrrigationEvent(user_id=user.id, duration_min=duration_min, reason=reason)
    db.add(ev); db.commit(); db.refresh(ev)
    return {"status": "logged", "id": ev.id}
