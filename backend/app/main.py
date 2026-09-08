"""Sustainable Agriculture AI Advisory Platform — FastAPI entry point."""
import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from app.core.config import settings
from app.database.db import Base, engine, SessionLocal
from app.database.seed import seed

# Import models so tables register, then create them
from app.models import models  # noqa
from app.api.auth import router as auth_router
from app.api.farm import router as farm_router
from app.api.iot import router as iot_router
from app.api.soil_weather import soil_router, weather_router, irrigation_router
from app.api.ai_plant import plant_router, scheme_router, ai_router, voice_router
from app.api.alerts_admin import alerts_router, analytics_router, admin_router
from app.api.diagnostics import router as diagnostics_router
from app.api.crops_market import crop_router, market_router, fertilizer_router
from app.api.machinery import router as machinery_router
from app.api.advisor_api import (market_router as mandi_router,
                                 onboarding_router, advisor_router,
                                 location_router)
from app.api.pest import pest_router
from app.api.marketplace import router as marketplace_router
from app.api.advisories import advisory_router
from app.api.circular import circular_router
from app.api.farm_profile import profile_router
from app.api.satellite import router as satellite_router
from app.api.satellite import admin_satellite_router
from app.api.tts import tts_router
from app.api.land_contracts import router as land_router
from app.api.harvest import router as harvest_router
from app.api.notifications import router as notifications_router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s")
log = logging.getLogger("agri")
logging.getLogger("httpx").setLevel(logging.WARNING)

app = FastAPI(title=settings.APP_NAME, version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # dev only; restrict in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def startup():
    # Database setup is wrapped so a failure here can NEVER stop the server
    # from binding its port.
    #
    # Previously an exception in create_all, ensure_schema or seed propagated
    # out of the startup handler, uvicorn exited, and the frontend showed
    # "ECONNREFUSED" with no clue why. A degraded server that reports its own
    # problem is far more debuggable than one that vanishes.
    try:
        Base.metadata.create_all(bind=engine)
    except Exception as exc:
        log.error("DATABASE CREATE FAILED: %s: %s", type(exc).__name__, exc)

    try:
        # Adds columns present in the models but missing from an older
        # agri.db. Without it, queries fail with "no such column", which
        # looks exactly like lost data.
        from app.database.db import ensure_schema
        added = ensure_schema()
        if added:
            log.info("Schema updated in place: %s", ", ".join(added))
    except Exception as exc:
        log.error("SCHEMA MIGRATION FAILED: %s: %s", type(exc).__name__, exc)

    try:
        db = SessionLocal()
        try:
            seed(db)
        finally:
            db.close()
        # Ensure new tables (LandListing, LandContract) exist
        Base.metadata.create_all(bind=engine)
    except Exception as exc:
        log.error("SEED FAILED (demo data will be missing): %s: %s",
                  type(exc).__name__, exc)
    from app.ai.providers import describe_active

    # Qwen warmup runs in a BACKGROUND THREAD, never inline.
    #
    # Starlette calls a synchronous startup handler directly on the event loop
    # (see Router.startup: `handler()` with no threadpool). Loading a 1.5B
    # model — or worse, downloading 3 GB on first run — inside that handler
    # blocks the loop completely, so uvicorn accepts no connections at all
    # until it finishes. The server looks dead rather than slow.
    #
    # Running it on a daemon thread lets the API come up immediately. The
    # first chat request then waits on the same threading.Lock inside _load()
    # and simply picks up the model once it is ready.
    if settings.LLM_PROVIDER.lower() == "qwen":
        import threading
        from app.ai.providers.qwen import warmup as qwen_warmup

        def _bg_warmup():
            log.info("Qwen loading in background (first run downloads ~3 GB)...")
            result = qwen_warmup()
            if result.get("loaded"):
                log.info("Qwen ready on %s", result.get("device"))
            else:
                log.warning("Qwen NOT loaded: %s", result.get("reason"))

        threading.Thread(target=_bg_warmup, name="qwen-warmup",
                         daemon=True).start()

    # Same treatment for the local vision model. It is far smaller than the
    # LLM (tens of MB), but a first-run download must still not block the loop.
    if settings.VISION_PROVIDER.lower() in ("huggingface", "hf", "local"):
        import threading as _t
        from app.ai.vision_providers.hf_vision import warmup as vision_warmup

        def _bg_vision():
            log.info("Vision model loading in background...")
            r = vision_warmup()
            if r.get("loaded"):
                log.info("Vision ready on %s (%s classes)",
                         r.get("device"), r.get("classes"))
            else:
                log.warning("Vision NOT loaded: %s", r.get("reason"))

        _t.Thread(target=_bg_vision, name="vision-warmup", daemon=True).start()

    log.info("Active LLM provider: %s", describe_active())
    # Loud, unmissable banner. The single most common failure is the
    # frontend proxying to a port the backend is not listening on, so print
    # the exact URL the frontend must target.
    port = os.environ.get("UVICORN_PORT") or os.environ.get("PORT") or "8000"
    log.info("=" * 62)
    log.info("  BACKEND READY")
    log.info("  If you started uvicorn with --port XXXX, the frontend must")
    log.info("  match it. Create frontend/.env.local containing:")
    log.info("      VITE_API_PORT=<the same port>")
    log.info("  Health check:  http://127.0.0.1:%s/api/health", port)
    log.info("  Provider=%s  Demo=%s", settings.LLM_PROVIDER, settings.DEMO_MODE)
    log.info("=" * 62)


@app.on_event("shutdown")
async def shutdown():
    """Close the pooled Gemini HTTP client cleanly."""
    from app.ai.providers import close_all
    await close_all()


@app.get("/api/health")
def health():
    from app.ai.providers import describe_active
    from app.ai.vision_providers import describe_active as describe_vision
    from app.services import satellite as sat
    sat_state = sat.status()
    return {"status": "ok", "app": settings.APP_NAME,
            "llm_provider": settings.LLM_PROVIDER,
            "llm": describe_active(),
            "vision_provider": settings.VISION_PROVIDER,
            "vision": describe_vision(),
            # Satellite readiness belongs in the health check for the same
            # reason the LLM provider does: when the Satellite page is empty,
            # the first question is always "is it even configured?"
            "tts": {"ready": __import__("app.services.tts", fromlist=["status"]).status()["ready"]},
            "satellite": {"enabled": sat_state["enabled"],
                          "ready": sat_state["ready"],
                          "credential_mode": sat_state["credential_mode"],
                          "error": sat_state["error"]},
            "demo_mode": settings.DEMO_MODE}


@app.get("/api/test-gemini")
async def test_gemini():
    """Live check of whichever provider is ACTIVE (not always Gemini).

    Previously this gated on GEMINI_API_KEY, so it reported failure under
    LLM_PROVIDER=qwen even when the local model was working perfectly.
    """
    import time
    from app.ai.providers import ProviderError, get_provider

    provider_name = settings.LLM_PROVIDER

    if provider_name.lower() == "gemini" and not settings.GEMINI_API_KEY:
        return {"status": "failed", "provider": provider_name,
                "error": "GEMINI_API_KEY is not configured in backend/.env"}

    if provider_name.lower() == "qwen":
        from app.ai.providers.qwen import is_loaded
        if not is_loaded():
            # Say so plainly rather than blocking the request for minutes.
            return {"status": "loading", "provider": "qwen",
                    "message": "Qwen is still loading in the background. The "
                               "first run downloads ~3 GB. Check the server "
                               "log, then retry."}

    started = time.perf_counter()
    try:
        provider = get_provider()
        response = await provider.chat(
            "You are a connectivity test. Reply with exactly: Connection successful!",
            "Say: Connection successful!",
            temperature=0.0, max_tokens=32)
    except ProviderError as exc:
        return {"status": "failed", "provider": provider_name,
                "kind": exc.kind, "error": str(exc)}

    return {"status": "connected", "provider": provider_name,
            "latency_s": round(time.perf_counter() - started, 2),
            "message": response}


for r in (auth_router, farm_router, iot_router, soil_router, weather_router,
          irrigation_router, plant_router, scheme_router, ai_router, voice_router,
          alerts_router, analytics_router, admin_router, pest_router,
          diagnostics_router, crop_router, market_router, fertilizer_router,
          mandi_router, onboarding_router, advisor_router,
          location_router, machinery_router, marketplace_router,
          satellite_router, admin_satellite_router, tts_router,
          profile_router, advisory_router, circular_router, land_router, harvest_router,
          notifications_router):
    app.include_router(r)

# Serve uploaded images
import os
os.makedirs("uploads", exist_ok=True)
app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")
