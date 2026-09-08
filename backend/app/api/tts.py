"""Text-to-speech endpoints.

The frontend asks this for audio whenever the farmer's language is Tamil or
Hindi, because the browser cannot be trusted to have those voices. It falls
back to browser speech only when this returns 503.
"""

import logging

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel
from starlette.concurrency import run_in_threadpool

from app.core.security import get_current_user, require_admin
from app.models.models import User
from app.services import tts as tts_svc

log = logging.getLogger("agri.api.tts")

tts_router = APIRouter(prefix="/api/tts", tags=["tts"])


class SpeakIn(BaseModel):
    text: str
    language: str = "hi"


@tts_router.get("/status")
def tts_status(user: User = Depends(get_current_user)):
    """Can the server speak? The client uses this to decide its strategy."""
    return tts_svc.status()


@tts_router.post("/speak")
async def speak(data: SpeakIn, user: User = Depends(get_current_user)):
    """Synthesise speech and return an MP3.

    Returns 503 (not 500) when synthesis is unavailable, because that is the
    signal the client uses to fall back to browser speech. An unavailable
    voice is a degraded feature, not a server fault.
    """
    text = (data.text or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="No text to speak.")

    lang = (data.language or user.language or "hi").strip().lower()[:2]

    # Synthesis is blocking network I/O; keep it off the event loop.
    path = await run_in_threadpool(tts_svc.synthesize, text, lang)

    if path is None:
        ok, reason = tts_svc.available()
        raise HTTPException(
            status_code=503,
            detail={
                "error": "speech_unavailable",
                "reason": reason,
                "fallback": ("The app will try your device's built-in voice "
                             "instead, which may not support this language."),
            })

    return FileResponse(
        path, media_type="audio/mpeg", filename=f"speech_{lang}.mp3",
        headers={"Cache-Control": "public, max-age=86400"})


@tts_router.post("/cache/clear")
def clear_tts_cache(admin: User = Depends(require_admin)):
    return {"status": "ok", "clips_removed": tts_svc.clear_cache()}
