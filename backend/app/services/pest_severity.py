"""Deterministic pest-severity engine.

Severity is NOT the LLM's opinion. It is computed from structured inputs:
  - the pest that was detected (and its action threshold)
  - detection confidence
  - visible infestation level and/or % of affected leaves (estimate)
  - crop growth stage (young/flowering stages are more vulnerable)
  - environmental conditions (warm + humid raises pressure for many pests)

Output levels: LOW | MODERATE | HIGH | UNKNOWN.

If inputs are too thin (low confidence, no infestation signal), we return
UNKNOWN and say so rather than pretending an image gives lab-grade counts.
Everywhere, severity from an image is clearly labelled an ESTIMATE.
"""
from __future__ import annotations

from app.ml.pest_knowledge import PEST_KB

LEVELS = ["LOW", "MODERATE", "HIGH"]

# Growth stages considered more vulnerable to pest damage.
_VULNERABLE_STAGES = {"seedling", "germination", "vegetative", "flowering",
                      "fruiting", "transplant", "transplanting"}


def _infestation_score(visible_infestation: str, affected_leaf_pct):
    """Return (score 0-3, basis_text, is_estimate). Higher = worse."""
    # Prefer a numeric % if the model provided one; otherwise use the label.
    if affected_leaf_pct is not None:
        p = affected_leaf_pct
        if p <= 0:
            return 0, "no visibly affected leaves", True
        if p < 10:
            return 1, f"~{int(p)}% of leaves visibly affected", True
        if p < 25:
            return 2, f"~{int(p)}% of leaves visibly affected", True
        return 3, f"~{int(p)}% of leaves visibly affected", True

    label = (visible_infestation or "unknown").lower()
    mapping = {
        "none": (0, "no visible infestation"),
        "low": (1, "light, localised infestation"),
        "moderate": (2, "moderate infestation across several leaves"),
        "high": (3, "heavy, widespread infestation"),
    }
    if label in mapping:
        score, text = mapping[label]
        return score, text, True
    return None, "infestation level unclear from the image", True


def _env_pressure(environment: dict | None) -> int:
    """+1 if conditions favour rapid pest build-up (warm and humid), else 0."""
    if not environment:
        return 0
    temp = environment.get("temperature")
    hum = environment.get("humidity")
    pressure = 0
    try:
        if temp is not None and hum is not None and float(temp) >= 28 and float(hum) >= 60:
            pressure = 1
    except (TypeError, ValueError):
        pressure = 0
    return pressure


def assess_severity(pest_name: str, confidence: float,
                    visible_infestation: str = "unknown",
                    affected_leaf_pct=None,
                    growth_stage: str = "",
                    environment: dict | None = None,
                    detection_confidence_floor: float = 0.55) -> dict:
    """Compute infestation severity from structured signals.

    Returns:
      {
        "level": "LOW|MODERATE|HIGH|UNKNOWN",
        "is_estimate": bool,
        "reason": str,
        "factors": [str, ...],
        "action_threshold": str,      # from PEST_KB for this pest
        "priority_note": str | None,  # environmental escalation note
      }
    """
    factors = []

    # 1) Not confident enough to score severity at all.
    if not pest_name or pest_name not in PEST_KB:
        return _unknown("No confidently identified pest, so severity cannot be estimated.")
    if confidence is None or confidence < detection_confidence_floor:
        return _unknown("Pest identification confidence is too low to estimate severity "
                        "reliably. A clearer image is needed.",
                        action_threshold=PEST_KB[pest_name]["severity_threshold"])

    # 2) Infestation signal.
    inf_score, inf_text, is_estimate = _infestation_score(visible_infestation, affected_leaf_pct)
    if inf_score is None:
        return _unknown("The image doesn't clearly show how widespread the infestation is. "
                        "Severity is left as UNKNOWN to avoid a misleading recommendation.",
                        action_threshold=PEST_KB[pest_name]["severity_threshold"])
    factors.append(f"Infestation: {inf_text}.")

    # 3) Crop growth-stage vulnerability.
    stage = (growth_stage or "").lower().strip()
    stage_bump = 0
    if stage in _VULNERABLE_STAGES:
        stage_bump = 1
        factors.append(f"Crop is at a vulnerable stage ({stage}), which raises the risk.")
    elif stage:
        factors.append(f"Crop growth stage: {stage}.")

    # 4) Environmental pressure.
    env_bump = _env_pressure(environment)
    priority_note = None
    if env_bump:
        factors.append("Warm and humid conditions favour rapid pest build-up.")
        priority_note = ("Warm, humid weather can accelerate this pest — increase "
                         "monitoring frequency.")

    # Combine: base on infestation, nudged by stage and environment, capped.
    combined = inf_score + stage_bump + env_bump
    if inf_score == 0:
        level = "LOW"
        reason = "No active infestation is visible; treat this as preventive monitoring."
    elif combined <= 1:
        level = "LOW"
        reason = "Infestation is light and localised."
    elif combined <= 3:
        level = "MODERATE"
        reason = "Infestation is established across several leaves or conditions raise the risk."
    else:
        level = "HIGH"
        reason = "Infestation is heavy or widespread, or strongly favoured by crop stage and weather."

    return {
        "level": level,
        "is_estimate": True,   # image-derived severity is always an estimate
        "reason": reason,
        "factors": factors,
        "action_threshold": PEST_KB[pest_name]["severity_threshold"],
        "priority_note": priority_note,
    }


def _unknown(reason: str, action_threshold: str = "") -> dict:
    return {
        "level": "UNKNOWN",
        "is_estimate": True,
        "reason": reason,
        "factors": [],
        "action_threshold": action_threshold,
        "priority_note": None,
    }
