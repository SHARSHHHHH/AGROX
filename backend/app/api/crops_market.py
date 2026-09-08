"""Crop advisory, market and fertilizer endpoints.

Exposes the deterministic services that previously had no HTTP surface:
    crop_suitability  -> /api/crops/*
    lifecycle         -> /api/crops/lifecycle/*
    market            -> /api/market/*
    fertilizer        -> /api/fertilizer/*

Every response carries the service's own status/disclaimer fields through
unchanged, so the honesty contract (ok / mock / unavailable) survives to the UI.
"""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.security import get_current_user
from app.database.db import get_db
from app.models.models import Farm, SensorReading, SoilTest, User
from app.services import fertilizer as fert_svc
from app.services import lifecycle as lifecycle_svc
from app.services import market as market_svc
from app.services import weather as weather_svc
from app.services.crop_suitability import (MP_CROPS, current_season,
                                           recommend_crops)

crop_router = APIRouter(prefix="/api/crops", tags=["crops"])
market_router = APIRouter(prefix="/api/market", tags=["market"])
fertilizer_router = APIRouter(prefix="/api/fertilizer", tags=["fertilizer"])


# ---------------------------------------------------------------- helpers

def _latest_soil(db: Session, user_id: int):
    return (db.query(SoilTest).filter(SoilTest.user_id == user_id)
            .order_by(SoilTest.created_at.desc()).first())


def _latest_sensor(db: Session, device_id: str):
    return (db.query(SensorReading)
            .filter(SensorReading.device_id == device_id)
            .order_by(SensorReading.created_at.desc()).first())


# ---------------------------------------------------------------- crops

@crop_router.get("/list")
def list_crops():
    """Crops the suitability engine knows about."""
    return [{"key": key, "display": spec["display"],
             "season": spec["season"],
             "duration_days": spec["duration_days"],
             "water_need": spec["water_need"]}
            for key, spec in MP_CROPS.items()]


@crop_router.get("/season")
def season():
    return {"season": current_season()}


@crop_router.get("/recommend")
async def recommend(
    ph: Optional[float] = None,
    nitrogen: Optional[float] = None,
    phosphorus: Optional[float] = None,
    potassium: Optional[float] = None,
    moisture: Optional[float] = None,
    temperature: Optional[float] = None,
    soil_type: str = "",
    season_override: str = Query("", alias="season"),
    use_my_data: bool = True,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Rank crops for the farmer's actual conditions.

    Any value not supplied is pulled from the farmer's own soil test, sensor
    reading and live weather. Anything still missing stays None — the engine
    treats absent data as neutral rather than guessing it.
    """
    sources = {}

    if use_my_data:
        farm = db.query(Farm).filter(Farm.user_id == user.id).first()
        soil_type = soil_type or (farm.soil_type if farm else "")
        device_id = farm.device_id if farm and farm.device_id else "ESP32-001"

        soil = _latest_soil(db, user.id)
        if soil:
            if ph is None:
                ph = soil.ph
            if nitrogen is None:
                nitrogen = soil.nitrogen
            if phosphorus is None:
                phosphorus = soil.phosphorus
            if potassium is None:
                potassium = soil.potassium
            sources["soil_test"] = soil.created_at.isoformat()

        reading = _latest_sensor(db, device_id)
        if reading:
            if moisture is None:
                moisture = reading.soil_moisture
            if temperature is None:
                temperature = reading.temperature
            sources["sensor"] = reading.created_at.isoformat()

        if temperature is None:
            try:
                wx = await weather_svc.get_weather()
                temperature = wx.get("temperature")
                sources["weather"] = wx.get("condition", "live")
            except Exception:
                pass

    result = recommend_crops(
        ph=ph, nitrogen=nitrogen, phosphorus=phosphorus, potassium=potassium,
        moisture=moisture, temperature=temperature, soil_type=soil_type,
        season=season_override)

    result["sources"] = sources
    result["inputs"] = {
        "ph": ph, "nitrogen": nitrogen, "phosphorus": phosphorus,
        "potassium": potassium, "moisture": moisture,
        "temperature": temperature, "soil_type": soil_type,
    }
    return result


@crop_router.get("/lifecycle/{crop}")
def crop_lifecycle(crop: str):
    """Full stage list for a crop."""
    data = lifecycle_svc.get_lifecycle(crop)
    if data is None:
        raise HTTPException(
            404,
            f"No lifecycle data for '{crop}'. Supported: "
            f"{', '.join(lifecycle_svc.supported_crops())}")
    return data


@crop_router.get("/lifecycle/{crop}/stage")
def crop_stage(crop: str, days_after_sowing: int = Query(..., ge=0)):
    """Which stage the crop is in now, with tasks, irrigation and risks."""
    stage = lifecycle_svc.current_stage(crop, days_after_sowing)
    if stage is None:
        raise HTTPException(
            404,
            f"No lifecycle data for '{crop}'. Supported: "
            f"{', '.join(lifecycle_svc.supported_crops())}")
    return stage


@crop_router.get("/lifecycle")
def supported_lifecycles():
    return {"crops": lifecycle_svc.supported_crops()}


# ---------------------------------------------------------------- market

@market_router.get("/price")
async def price(crop: str, state: str = "Madhya Pradesh"):
    """Market price for one crop. Returns status ok|mock|unavailable."""
    return await market_svc.get_price(crop, state)


@market_router.get("/prices")
async def prices(crops: str = Query(..., description="comma-separated crops"),
                 state: str = "Madhya Pradesh"):
    names = [c.strip() for c in crops.split(",") if c.strip()]
    if not names:
        raise HTTPException(400, "No crops supplied")
    return await market_svc.get_prices(names, state)


@market_router.get("/my-crop")
async def my_crop_price(user: User = Depends(get_current_user),
                        db: Session = Depends(get_db)):
    """Price for whatever the farmer is actually growing."""
    farm = db.query(Farm).filter(Farm.user_id == user.id).first()
    if not farm or not farm.crop:
        return {"status": "unavailable",
                "message": "No crop is set on your farm profile yet.",
                "prices": None}
    return await market_svc.get_price(farm.crop, farm.state or "Madhya Pradesh")


# ---------------------------------------------------------------- fertilizer

class ROIIn(BaseModel):
    offer_price: float
    standard_price: float
    bags: int
    distance_km: float
    crop: str = "default"
    acres: float = 1.0
    crop_price_per_tonne: Optional[float] = None


@fertilizer_router.get("/offers")
async def offers(state: str = "Madhya Pradesh", product: str = ""):
    """Available manure/fertiliser offers. status ok|mock|unavailable."""
    return await fert_svc.get_offers(state, product)


@fertilizer_router.post("/roi")
async def roi(data: ROIIn, user: User = Depends(get_current_user),
              db: Session = Depends(get_db)):
    """Itemised ROI for a fertiliser offer.

    If no crop price is supplied we try the market service. When that has no
    real data the yield-boost revenue is counted as zero and the response says
    so, rather than quietly using a mock price in a financial calculation.
    """
    crop_price = data.crop_price_per_tonne
    price_status = "supplied" if crop_price is not None else None

    if crop_price is None and data.crop != "default":
        farm = db.query(Farm).filter(Farm.user_id == user.id).first()
        state = farm.state if farm else "Madhya Pradesh"

        # Use the REAL government mandi feed, not the mock service.
        #
        # Previously this read from the mock price service, which returns
        # `status: mock`, which the ROI engine correctly refuses to use for a
        # financial figure — so yield revenue was always zero and every offer
        # came out "not worth it". Real data makes the calculation meaningful.
        from app.services import mandi_price as mandi
        raw = await mandi.fetch_prices(state=state, commodity=data.crop, limit=100)
        quote = mandi.summarise(raw, data.crop)
        price_status = quote.get("status", "unavailable")

        if price_status == "ok" and quote.get("modal_avg"):
            # Mandi quotes are per quintal; 10 quintals to a tonne.
            crop_price = float(quote["modal_avg"]) * 10

    result = fert_svc.calculate_roi(
        offer_price=data.offer_price, standard_price=data.standard_price,
        bags=data.bags, distance_km=data.distance_km, crop=data.crop,
        acres=data.acres, crop_price_per_tonne=crop_price)

    result["crop_price_source"] = price_status or "unavailable"
    result["crop_price_per_tonne_used"] = crop_price

    if price_status == "ok" and crop_price:
        result["assumptions"].append(
            f"Crop price of INR {crop_price:,.0f} per tonne came from live "
            f"government mandi data (AGMARKNET).")
    elif price_status in ("empty", "unavailable", "not_configured"):
        result["assumptions"].append(
            "No live mandi price was available, so yield-boost revenue is "
            "counted as ZERO. The figure below therefore reflects only the "
            "purchase saving against transport cost — it understates the "
            "true benefit.")
    return result
