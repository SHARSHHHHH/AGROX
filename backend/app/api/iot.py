from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.database.db import get_db
from app.models.models import SensorReading
from app.schemas.schemas import SensorIn
from app.core.security import get_current_user
from app.services import simulator

router = APIRouter(prefix="/api/iot", tags=["iot"])


@router.post("/sensor-data")
def ingest(data: SensorIn, db: Session = Depends(get_db)):
    """Endpoint the ESP32 posts to. Validates via Pydantic, stores reading."""
    reading = SensorReading(
        device_id=data.device_id, soil_moisture=data.soil_moisture,
        temperature=data.temperature, humidity=data.humidity,
        water_level=data.water_level, water_flow=data.water_flow,
        source="esp32")
    db.add(reading); db.commit(); db.refresh(reading)
    return {"status": "ok", "id": reading.id, "source": "esp32"}


@router.get("/latest")
def latest(device_id: str = "ESP32-001", db: Session = Depends(get_db)):
    r = (db.query(SensorReading).filter(SensorReading.device_id == device_id)
         .order_by(SensorReading.created_at.desc()).first())
    if not r:
        return {"message": "No sensor data received yet."}
    return _serialize(r)


@router.get("/history")
def history(device_id: str = "ESP32-001", limit: int = 50,
            db: Session = Depends(get_db)):
    rows = (db.query(SensorReading).filter(SensorReading.device_id == device_id)
            .order_by(SensorReading.created_at.desc()).limit(limit).all())
    return [_serialize(r) for r in reversed(rows)]


@router.get("/devices")
def devices(db: Session = Depends(get_db)):
    ids = db.query(SensorReading.device_id).distinct().all()
    return {"devices": [i[0] for i in ids] or ["ESP32-001"]}


@router.post("/simulate")
def simulate(device_id: str = "ESP32-001", db: Session = Depends(get_db)):
    """Generate one simulated reading (source='simulated')."""
    payload = simulator.generate(device_id)
    reading = SensorReading(
        device_id=payload["device_id"], soil_moisture=payload["soil_moisture"],
        temperature=payload["temperature"], humidity=payload["humidity"],
        water_level=payload["water_level"], water_flow=payload["water_flow"],
        source="simulated")
    db.add(reading); db.commit(); db.refresh(reading)
    return _serialize(reading)


@router.post("/scenario")
def set_scenario(name: str):
    """Switch demo scenario: normal|dry_soil|heavy_rain|low_water|high_temp."""
    active = simulator.set_scenario(name)
    return {"scenario": active, "available": list(simulator.SCENARIOS.keys())}


@router.post("/pump")
def pump(device_id: str = "ESP32-001", state: str = "OFF"):
    """Pump control. For the prototype this records intent only. A real command
    passes through the deterministic safety layer, NOT the LLM."""
    state = state.upper()
    if state not in ("ON", "OFF"):
        return {"status": "rejected", "reason": "state must be ON or OFF"}
    # Safety layer placeholder: allow manual control only.
    return {"status": "ok", "device_id": device_id, "pump": state,
            "note": "Manual control accepted. Automated LLM-triggered pump control "
                    "is disabled by the safety layer."}


def _serialize(r: SensorReading) -> dict:
    return {
        "id": r.id, "device_id": r.device_id, "soil_moisture": r.soil_moisture,
        "temperature": r.temperature, "humidity": r.humidity,
        "water_level": r.water_level, "water_flow": r.water_flow,
        "source": r.source, "timestamp": r.created_at.isoformat(),
    }
