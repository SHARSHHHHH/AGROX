"""Pest pipeline orchestrator.

Runs the full hybrid pipeline end to end and returns one structured,
frontend-friendly result:

    detect_pest (Gemini label, exact or semantic KB match) [ml.pest_vision]
        -> assess_severity            [services.pest_severity]
        -> build_ipm                  [services.ipm]
        -> rank_sustainable_treatment [services.ipm]

    ...or, when nothing matches the curated KB closely enough:

    detect_pest (type=pest_unmatched)
        -> grounded_fallback          [ml.pest_rag_fallback]

The vision model only supplies a label + rough infestation estimate; every
downstream decision for a KB-matched pest is deterministic and grounded in
PEST_KB (exact or semantic match — see ml/pest_vision.py). For a pest outside
the KB, the fallback path is grounded only in the nearest KB reference
entries and is clearly marked unverified. This module is used by BOTH the
/api/pest/analyze endpoint and the AI agent's pest tool, so the two can never
diverge.

CACHING
-------
A small in-memory cache keyed by (pest identity, crop, growth_stage) skips
re-running severity/IPM/generation for a repeat query in the same process —
the deterministic KB path is already sub-second, but this mainly protects
the RAG-fallback path (the one call that can take several seconds) from
paying that cost twice for the same pest+crop combination. Not persisted
across restarts; that's fine for a single-process demo deployment. For a
horizontally scaled deployment, swap this dict for Redis without changing
the call sites.
"""
from __future__ import annotations

from app.ml.pest_vision import detect_pest
from app.ml.pest_rag_fallback import grounded_fallback
from app.services.pest_severity import assess_severity
from app.services.ipm import build_ipm, rank_sustainable_treatment

_CACHE_MAX_ENTRIES = 500
_result_cache: dict[tuple, dict] = {}


def _cache_key(identity: str, crop: str, growth_stage: str) -> tuple:
    return (identity.strip().lower(), (crop or "").strip().lower(),
            (growth_stage or "").strip().lower())


async def run_pest_pipeline(image_path: str, crop: str = "",
                            growth_stage: str = "",
                            environment: dict | None = None) -> dict:
    """Analyze an image and return the complete pest advisory result.

    The returned dict is the canonical schema used by the API and the agent:
      success, type, pest, crop, severity, ipm, sustainable_recommendation,
      environmental_considerations, uncertain, message, grounded_facts,
      verified.
    """
    detection = await detect_pest(image_path, crop)
    dtype = detection.get("type")

    # Pest outside the curated KB -> grounded, hedged fallback rather than a
    # confident-looking guess.
    if dtype == "pest_unmatched":
        return await _run_fallback_path(detection, crop, growth_stage)

    # Non-pest outcomes short-circuit with an honest, structured response.
    if dtype != "pest":
        return {
            "success": True,
            "type": dtype,                         # disease | healthy | uncertain
            "pest": None,
            "crop": crop,
            "confidence": detection.get("confidence", 0.0),
            "severity": {"level": "UNKNOWN", "is_estimate": True,
                         "reason": detection.get("message", ""), "factors": []},
            "ipm": _empty_ipm(),
            "sustainable_recommendation": detection.get("message", ""),
            "environmental_considerations": [],
            "uncertain": bool(detection.get("uncertain", dtype == "uncertain")),
            "message": detection.get("message"),
            "model_guess": detection.get("model_guess"),
            "grounded_facts": _facts_for_non_pest(detection),
            "verified": True,
        }

    pest_name = detection["pest_name"]
    confidence = detection["confidence"]

    # 1) Severity (deterministic).
    severity = assess_severity(
        pest_name=pest_name,
        confidence=confidence,
        visible_infestation=detection.get("visible_infestation", "unknown"),
        affected_leaf_pct=detection.get("affected_leaf_pct"),
        growth_stage=growth_stage,
        environment=environment,
    )

    # 2) IPM plan (deterministic, severity-gated).
    ipm = build_ipm(pest_name, severity["level"], environment)

    # 3) Sustainable treatment ranking (chemical always last / gated).
    ranked = rank_sustainable_treatment(pest_name, severity["level"], ipm)

    kb = detection.get("kb", {}) or {}
    grounded_facts = _facts_for_pest(pest_name, detection, severity, ipm, ranked, kb)

    result = {
        "success": True,
        "type": "pest",
        "pest": {
            "name": pest_name,
            "scientific_name": kb.get("scientific_name", ""),
            "confidence": confidence,
            "affected_crops": kb.get("affected_crops", []),
            "symptoms": kb.get("symptoms", ""),
            "visual_indicators": kb.get("visual_indicators", ""),
            "favorable_conditions": kb.get("favorable_conditions", ""),
        },
        "crop": crop,
        "severity": severity,
        "ipm": {
            "monitoring": ipm["monitoring"],
            "prevention": ipm["prevention"],
            "cultural": ipm["cultural"],
            "mechanical": ipm["mechanical"],
            "biological": ipm["biological"],
            "chemical": ipm["chemical"],
            "escalation": ipm["escalation"],
            "chemical_status": ipm["chemical_status"],
            "action_threshold": ipm["action_threshold"],
            "ordered_steps": ranked["ordered_steps"],
        },
        "sustainable_recommendation": ranked["summary"],
        "environmental_considerations": ranked["environmental_considerations"],
        "uncertain": False,
        "message": None,
        "grounded_facts": grounded_facts,
        "visible_indicators": detection.get("visible_indicators", ""),
        "verified": True,
    }
    if detection.get("matched_via") == "semantic":
        result["matched_via"] = "semantic"
        result["original_guess"] = detection.get("original_guess")
        result["match_similarity"] = detection.get("match_similarity")
    return result


async def _run_fallback_path(detection: dict, crop: str, growth_stage: str) -> dict:
    """Handle a pest that didn't match the curated KB (exact or semantic).
    Cached by (guess, crop, growth_stage) since this is the one path with
    real generation latency worth protecting from repeat cost."""
    identity = detection.get("pest_name") or "unknown_pest"
    key = _cache_key(identity, crop, growth_stage)
    if key in _result_cache:
        return _result_cache[key]

    fallback = await grounded_fallback(
        pest_guess=identity,
        crop=crop,
        visible_indicators=detection.get("visible_indicators", ""),
        nearest=detection.get("nearest_candidates", []),
    )

    result = {
        "success": True,
        "type": "pest_unmatched",
        "pest": {
            "name": identity,
            "scientific_name": "",
            "confidence": detection.get("confidence", 0.0),
            "affected_crops": [],
            "symptoms": "",
            "visual_indicators": detection.get("visible_indicators", ""),
            "favorable_conditions": "",
        },
        "crop": crop,
        "severity": {"level": "UNKNOWN", "is_estimate": True,
                     "reason": "Pest not in the verified database; severity cannot be "
                               "estimated without a confirmed identification.",
                     "factors": []},
        "ipm": _empty_ipm(),
        "sustainable_recommendation": fallback["summary"],
        "environmental_considerations": [],
        "uncertain": True,
        "message": fallback["summary"],
        "grounded_facts": fallback["grounded_facts"],
        "visible_indicators": detection.get("visible_indicators", ""),
        "verified": False,
        "origin": fallback.get("origin", "ai_fallback"),
    }

    if len(_result_cache) >= _CACHE_MAX_ENTRIES:
        _result_cache.pop(next(iter(_result_cache)))
    _result_cache[key] = result
    return result


def _empty_ipm() -> dict:
    return {"monitoring": [], "prevention": [], "cultural": [], "mechanical": [],
            "biological": [], "chemical": [], "escalation": [],
            "chemical_status": "not_recommended", "action_threshold": "",
            "ordered_steps": []}


def _facts_for_non_pest(detection: dict) -> list[str]:
    dtype = detection.get("type")
    if dtype == "disease":
        return ["The image looks like a plant disease rather than an insect pest; "
                "the disease analysis should be used for diagnosis."]
    if dtype == "healthy":
        return ["No obvious pest infestation was detected; routine monitoring is advised."]
    return ["The pest could not be confidently identified from the image; a clearer "
            "photo is needed before any treatment is recommended."]


def _facts_for_pest(pest_name, detection, severity, ipm, ranked, kb) -> list[str]:
    """Compact, grounded bullet facts fed to the LLM for explanation. The LLM
    must use ONLY these — it does not decide any of them."""
    facts = [
        f"Pest identified: {pest_name} (confidence {detection['confidence']:.0%}).",
        f"Infestation severity (estimate from image): {severity['level']}. "
        f"{severity['reason']}",
        f"Action threshold for {pest_name}: {ipm['action_threshold']}",
        f"Sustainable recommendation order (least-harmful first): " +
        ", ".join(s["category"] for s in ranked["ordered_steps"]) + ".",
    ]
    if ipm["chemical_status"] == "not_recommended":
        facts.append("Chemical pesticide is NOT recommended at this severity; use "
                     "monitoring and cultural/preventive measures.")
    else:
        facts.append("Chemical control is only a threshold-gated last resort here, "
                     "using locally registered products per the label.")
    if severity.get("priority_note"):
        facts.append(severity["priority_note"])
    if kb.get("symptoms"):
        facts.append(f"Typical symptoms: {kb['symptoms']}")
    return facts
