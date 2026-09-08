import os
import uuid
import aiofiles
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from sqlalchemy.orm import Session
from app.database.db import get_db
from app.models.models import PlantDiagnosis, Scheme, User, Farm, ChatMessage, SchemeInterest
from app.schemas.schemas import ChatIn, EligibilityIn
from app.core.security import get_current_user
from app.ml.vision import analyze_image
from app.ai import nlp, speech
from app.agents.agent import run_agent
from app.services.schemes import recommend as recommend_schemes, evaluate

UPLOAD_DIR = "uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)

plant_router = APIRouter(prefix="/api/plant", tags=["plant"])
scheme_router = APIRouter(prefix="/api/schemes", tags=["schemes"])
ai_router = APIRouter(prefix="/api/ai", tags=["ai"])
voice_router = APIRouter(prefix="/api/voice", tags=["voice"])


# ---------- PLANT DISEASE ----------
@plant_router.post("/analyze")
async def analyze_plant(crop: str = Form(""), file: UploadFile = File(...),
                        user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ext = os.path.splitext(file.filename)[1] or ".jpg"
    path = os.path.join(UPLOAD_DIR, f"{uuid.uuid4().hex}{ext}")
    async with aiofiles.open(path, "wb") as f:
        await f.write(await file.read())

    result = await analyze_image(path, crop)
    diag = PlantDiagnosis(
        user_id=user.id, crop=crop, image_path=path,
        disease=result["disease"], confidence=result["confidence"],
        severity=result.get("severity", "unknown"),
        recommendation=result.get("recommendation", ""),
        uncertain=result.get("uncertain", False))
    db.add(diag); db.commit(); db.refresh(diag)
    result["id"] = diag.id
    return result


@plant_router.get("/history")
def plant_history(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    rows = (db.query(PlantDiagnosis).filter(PlantDiagnosis.user_id == user.id)
            .order_by(PlantDiagnosis.created_at.desc()).limit(30).all())
    return [{"id": r.id, "crop": r.crop, "disease": r.disease,
             "confidence": r.confidence, "severity": r.severity,
             "recommendation": r.recommendation, "uncertain": r.uncertain,
             "date": r.created_at.isoformat()} for r in rows]


# ---------- SCHEMES ----------
def _profile(user: User, db: Session) -> dict:
    farm = db.query(Farm).filter(Farm.user_id == user.id).first()
    return {
        "state": user.state or (farm.state if farm else ""),
        "farmer_category": farm.farmer_category if farm else "small",
        "land_size_acres": farm.land_size_acres if farm else 1.0,
        "crop": farm.crop if farm else "",
    }


@scheme_router.get("")
def list_schemes(db: Session = Depends(get_db)):
    schemes = db.query(Scheme).all()
    return [{"id": s.id, "name": s.name, "description": s.description,
             "state": s.state, "level": s.level, "benefits": s.benefits,
             "url": s.url, "last_verified": s.last_verified,
             "source": s.source} for s in schemes]


@scheme_router.get("/recommended")
def recommended(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    schemes = db.query(Scheme).all()
    return recommend_schemes(schemes, _profile(user, db))


@scheme_router.post("/check-eligibility")
def check_eligibility(data: EligibilityIn, db: Session = Depends(get_db)):
    schemes = db.query(Scheme).all()
    profile = data.model_dump()
    return [evaluate(s, profile) for s in schemes]


@scheme_router.post("/{scheme_id}/interest")
def mark_scheme_interest(scheme_id: int, user: User = Depends(get_current_user),
                         db: Session = Depends(get_db)):
    """Records that a farmer has chosen to apply for a scheme.

    This is what powers the state-wise admin view of which schemes farmers
    are actually choosing — without it there would be no real data behind
    that number, only eligibility, which is not the same as intent.
    """
    scheme = db.query(Scheme).get(scheme_id)
    if not scheme:
        raise HTTPException(404, "Scheme not found")
    exists = (db.query(SchemeInterest)
              .filter(SchemeInterest.user_id == user.id,
                     SchemeInterest.scheme_id == scheme_id).first())
    if not exists:
        db.add(SchemeInterest(user_id=user.id, scheme_id=scheme_id,
                              state=user.state or ""))
        db.commit()
    return {"status": "ok"}


@scheme_router.get("/mine/interests")
def my_scheme_interests(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Scheme IDs this farmer has already marked as chosen, so the UI can
    show 'Applying' instead of the button again."""
    rows = (db.query(SchemeInterest)
            .filter(SchemeInterest.user_id == user.id).all())
    return [r.scheme_id for r in rows]


# ---------- AI CHAT ----------
@ai_router.post("/chat")
async def chat(data: ChatIn, user: User = Depends(get_current_user),
               db: Session = Depends(get_db)):
    db.add(ChatMessage(user_id=user.id, role="user", content=data.message,
                       language=data.language or user.language or "hi"))
    # Both context signals are forwarded:
    #   page_context  — which screen the farmer is on
    #   ui_language   — the language they picked. This used to be accepted by
    #                   the schema and then dropped, so the agent guessed from
    #                   the message script and answered romanised Hindi or
    #                   Tamil in English.
    result = await run_agent(db, user, data.message,
                             page_context=data.page_context,
                             ui_language=data.language or user.language or "")
    db.add(ChatMessage(user_id=user.id, role="assistant",
                       content=result["answer"], language=result["language"]))
    db.commit()
    return result


@ai_router.get("/history")
def chat_history(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    rows = (db.query(ChatMessage).filter(ChatMessage.user_id == user.id)
            .order_by(ChatMessage.created_at.asc()).limit(50).all())
    return [{"role": r.role, "content": r.content, "language": r.language,
             "date": r.created_at.isoformat()} for r in rows]


# ---------- VOICE ----------
@voice_router.post("/transcribe")
async def transcribe(file: UploadFile = File(...),
                     user: User = Depends(get_current_user)):
    """Accept an audio blob, transcribe with Whisper (multilingual), and run the
    NLP analysis so the client gets transcript + detected language + intent."""
    ext = os.path.splitext(file.filename or "")[1] or ".webm"
    path = os.path.join(UPLOAD_DIR, f"voice_{uuid.uuid4().hex}{ext}")
    async with aiofiles.open(path, "wb") as f:
        await f.write(await file.read())

    stt = speech.transcribe(path)
    text = stt.get("text", "")
    analysis = await nlp.analyze(text) if text else {"language": stt.get("language", "en")}
    return {"transcript": text, **stt, "analysis": analysis}


@ai_router.get("/vision/selftest")
async def vision_selftest(user: User = Depends(get_current_user)):
    """Prove the vision provider works, without needing a photo upload.

    Generates a tiny synthetic leaf image in memory and sends it through the
    live provider. Whatever the model says about a 64x64 green square is
    meaningless agronomically — the point is the round trip: key accepted,
    model id valid, network reachable, JSON parseable.

    This is the endpoint to hit first when photo analysis misbehaves, because
    it separates "the connection is broken" from "the model was unsure about
    that particular photo", which look identical from the UI.
    """
    import tempfile
    from app.ai.vision_providers import (VisionProviderError, describe_active,
                                         get_vision_provider)

    info = describe_active()
    tmp_path = None
    try:
        from PIL import Image, ImageDraw
        img = Image.new("RGB", (128, 128), (34, 120, 45))
        draw = ImageDraw.Draw(img)
        # A few brown blotches, so the request carries something leaf-like
        # rather than a flat colour field.
        for xy in [(30, 30, 55, 52), (70, 60, 95, 88), (45, 90, 62, 108)]:
            draw.ellipse(xy, fill=(120, 78, 30))
        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as fh:
            img.save(fh, format="JPEG")
            tmp_path = fh.name
    except ImportError:
        return {"ok": False, "stage": "image_generation",
                "error": "Pillow is not installed. Run: pip install Pillow",
                "provider": info}

    try:
        provider = get_vision_provider()
        obs = await provider.analyze(tmp_path, crop="tomato")
        return {
            "ok": True,
            "provider": info,
            "round_trip": "success",
            "raw_observation": obs.to_dict(),
            "note": ("The connection works. The observation itself is "
                     "meaningless — this was a synthetic test image, not a "
                     "real leaf."),
        }
    except VisionProviderError as exc:
        return {"ok": False, "stage": "provider", "error_kind": exc.kind,
                "error": str(exc), "provider": info}
    except Exception as exc:                            # noqa: BLE001
        return {"ok": False, "stage": "unexpected",
                "error": f"{type(exc).__name__}: {exc}", "provider": info}
    finally:
        if tmp_path:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
