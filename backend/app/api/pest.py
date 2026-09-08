"""Pest management API — image analysis, pest info, severity, IPM.

Follows the existing FastAPI conventions (see api/ai_plant.py): APIRouter with a
prefix, JWT auth via get_current_user, file uploads saved to UPLOAD_DIR, and a
structured JSON response. Persists each analysis as a PestObservation.

Endpoints:
  POST /api/pest/analyze          multipart image -> full pipeline result
  GET  /api/pest/info             list the pest knowledge base
  GET  /api/pest/info/{name}      one pest's KB entry
  GET  /api/pest/history          this user's recent pest observations
  POST /api/pest/severity         recompute severity from structured inputs (no image)
"""
import os
import uuid
import aiofiles
from fastapi import APIRouter, Depends, UploadFile, File, Form, HTTPException
from sqlalchemy.orm import Session
from app.database.db import get_db
from app.models.models import PestObservation, User, Farm
from app.core.security import get_current_user
from app.services.pest_pipeline import run_pest_pipeline
from app.services.pest_severity import assess_severity
from app.services import weather as weather_svc
from app.ml.pest_knowledge import PEST_KB

UPLOAD_DIR = "uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)

pest_router = APIRouter(prefix="/api/pest", tags=["pest"])


@pest_router.post("/analyze")
async def analyze_pest(crop: str = Form(""), file: UploadFile = File(...),
                       user: User = Depends(get_current_user),
                       db: Session = Depends(get_db)):
    """Upload a plant/insect image and run the full pest pipeline.

    Pulls the user's crop + growth stage and current weather so severity and IPM
    are grounded in real context (never invented)."""
    ext = os.path.splitext(file.filename or "")[1] or ".jpg"
    path = os.path.join(UPLOAD_DIR, f"pest_{uuid.uuid4().hex}{ext}")
    async with aiofiles.open(path, "wb") as f:
        await f.write(await file.read())

    farm = db.query(Farm).filter(Farm.user_id == user.id).first()
    crop = crop or (farm.crop if farm else "")
    growth_stage = farm.growth_stage if farm else ""

    # Real environmental context (degrades gracefully to offline demo weather).
    try:
        wx = await weather_svc.get_weather()
        environment = {"temperature": wx.get("temperature"),
                       "humidity": wx.get("humidity"),
                       "rain_probability": wx.get("rain_probability")}
    except Exception:
        environment = None

    result = await run_pest_pipeline(path, crop, growth_stage, environment)

    # Persist observation (works for pest and non-pest outcomes).
    pest_name = result["pest"]["name"] if result.get("pest") else ""
    obs = PestObservation(
        user_id=user.id, crop=crop, image_path=path,
        pest_name=pest_name,
        confidence=result.get("confidence", 0.0) if not result.get("pest")
                   else result["pest"]["confidence"],
        severity=result["severity"]["level"],
        result_type=result["type"],
        recommendation=result.get("sustainable_recommendation", ""),
        ipm=result.get("ipm"),
        uncertain=result.get("uncertain", False))
    db.add(obs); db.commit(); db.refresh(obs)
    result["id"] = obs.id
    return result


@pest_router.get("/info")
def list_pests():
    """Return the pest knowledge base (frontend reference / education)."""
    return [{"name": name, **{k: v for k, v in entry.items()}}
            for name, entry in PEST_KB.items()]


@pest_router.get("/info/{name}")
def pest_info(name: str):
    # Case-insensitive match on the KB keys.
    for key, entry in PEST_KB.items():
        if key.lower() == name.lower():
            return {"name": key, **entry}
    raise HTTPException(404, "Pest not found in knowledge base")


@pest_router.get("/history")
def pest_history(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    rows = (db.query(PestObservation).filter(PestObservation.user_id == user.id)
            .order_by(PestObservation.created_at.desc()).limit(30).all())
    return [{"id": r.id, "crop": r.crop, "pest_name": r.pest_name,
             "confidence": r.confidence, "severity": r.severity,
             "type": r.result_type, "recommendation": r.recommendation,
             "uncertain": r.uncertain, "date": r.created_at.isoformat()}
            for r in rows]


@pest_router.post("/severity")
async def recompute_severity(
        pest_name: str = Form(...), confidence: float = Form(...),
        visible_infestation: str = Form("unknown"),
        affected_leaf_pct: float = Form(None),
        growth_stage: str = Form(""),
        user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Recompute severity from structured inputs without re-uploading an image —
    useful when a farmer refines the % affected or growth stage."""
    if pest_name not in PEST_KB:
        raise HTTPException(400, "Unknown pest name")
    try:
        wx = await weather_svc.get_weather()
        environment = {"temperature": wx.get("temperature"),
                       "humidity": wx.get("humidity"),
                       "rain_probability": wx.get("rain_probability")}
    except Exception:
        environment = None
    return assess_severity(pest_name, confidence, visible_infestation,
                           affected_leaf_pct, growth_stage, environment)
