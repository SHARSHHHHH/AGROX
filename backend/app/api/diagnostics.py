"""Runtime diagnostics.

Surfaces the REAL upstream error to an authenticated admin instead of the
generic fallback sentence the chat endpoint returns. Restricted to admins
because the responses include configuration detail.
"""

import time

from fastapi import APIRouter, Depends, HTTPException

from app.ai import llm
from app.core.config import settings
from app.core.security import get_current_user
from app.models.models import User

router = APIRouter(prefix="/api/diagnostics", tags=["diagnostics"])


def _admin_only(user: User):
    if getattr(user, "role", "") != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")


@router.get("/gemini")
async def gemini_status(user: User = Depends(get_current_user)):
    """Full Gemini health report: key, model access, latency, tool use."""
    _admin_only(user)

    key = settings.GEMINI_API_KEY
    report = {
        "configured_model": settings.GEMINI_MODEL,
        "thinking_budget": settings.GEMINI_THINKING_BUDGET,
        "max_output_tokens": settings.GEMINI_MAX_OUTPUT_TOKENS,
        "api_key_present": bool(key),
        "api_key_length": len(key),
        "api_key_prefix": key[:4] + "…" if key else "",
        "checks": [],
        "healthy": False,
    }

    if not key:
        report["checks"].append({
            "name": "api_key", "ok": False,
            "detail": "GEMINI_API_KEY is not set in backend/.env",
        })
        return report

    report["checks"].append({"name": "api_key", "ok": True,
                             "detail": "key present"})

    # --- model access ---
    try:
        models = await llm.list_models()
    except llm.GeminiError as exc:
        report["checks"].append({"name": "model_access", "ok": False,
                                 "kind": exc.kind, "detail": str(exc)})
        return report

    available = settings.GEMINI_MODEL in models
    report["available_models"] = models
    report["checks"].append({
        "name": "model_access",
        "ok": available,
        "detail": (f"'{settings.GEMINI_MODEL}' is available"
                   if available else
                   f"'{settings.GEMINI_MODEL}' not found among "
                   f"{len(models)} accessible models"),
    })
    if not available:
        return report

    # --- live generation ---
    started = time.perf_counter()
    try:
        text = await llm.chat_strict("Answer in one short sentence.",
                                     "Say OK if you can read this.",
                                     temperature=0.0)
    except llm.GeminiError as exc:
        report["checks"].append({"name": "generation", "ok": False,
                                 "kind": exc.kind, "detail": str(exc)})
        return report

    elapsed = round(time.perf_counter() - started, 2)
    report["latency_s"] = elapsed
    report["checks"].append({
        "name": "generation", "ok": True,
        "detail": f"responded in {elapsed}s",
        "sample": text[:120],
    })

    if elapsed > 8:
        report["checks"].append({
            "name": "latency_warning", "ok": False,
            "detail": f"{elapsed}s is slow. Set GEMINI_THINKING_BUDGET=0 "
                      f"in backend/.env to remove reasoning overhead.",
        })

    report["healthy"] = True
    return report


@router.get("/models")
async def available_models(user: User = Depends(get_current_user)):
    """List model IDs this key can access — use it to fix a wrong GEMINI_MODEL."""
    _admin_only(user)
    try:
        models = await llm.list_models()
    except llm.GeminiError as exc:
        raise HTTPException(status_code=502,
                            detail=f"[{exc.kind}] {exc}")
    return {"count": len(models), "models": models,
            "configured": settings.GEMINI_MODEL}
