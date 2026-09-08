"""Deterministic government-scheme eligibility engine.

Rules only — never claims final government eligibility. The LLM is not allowed
to invent schemes; it can only explain results from this engine over the
verified scheme database.
"""
from app.models.models import Scheme


def evaluate(scheme: Scheme, profile: dict) -> dict:
    """Return eligibility verdict for one scheme against a user profile."""
    reasons, missing = [], []
    state = (profile.get("state") or "").strip().lower()
    category = (profile.get("farmer_category") or "").strip().lower()
    land = profile.get("land_size_acres")
    crop = (profile.get("crop") or "").strip().lower()

    matches = 0
    total = 0

    # State check
    total += 1
    s_state = (scheme.state or "All India").lower()
    if s_state in ("all india", "all", ""):
        matches += 1
        reasons.append("Available across India.")
    elif state and state in s_state:
        matches += 1
        reasons.append(f"Your state ({profile.get('state')}) is covered.")
    elif not state:
        missing.append("state")
    else:
        reasons.append(f"This scheme targets {scheme.state}.")

    # Farmer category
    cats = [c.lower() for c in (scheme.farmer_categories or [])]
    if cats:
        total += 1
        if category and category in cats:
            matches += 1
            reasons.append(f"Your farmer category ({category}) qualifies.")
        elif not category:
            missing.append("farmer_category")
        else:
            reasons.append(f"Targets categories: {', '.join(cats)}.")

    # Land size
    if scheme.min_land is not None and scheme.max_land is not None:
        total += 1
        if land is None:
            missing.append("land_size_acres")
        elif scheme.min_land <= land <= scheme.max_land:
            matches += 1
            reasons.append(f"Your land size ({land} acres) is within range "
                           f"({scheme.min_land}–{scheme.max_land}).")
        else:
            reasons.append(f"Land requirement is {scheme.min_land}–{scheme.max_land} acres.")

    # Crop applicability
    crops = [c.lower() for c in (scheme.crops or [])]
    if crops:
        total += 1
        if crop and crop in crops:
            matches += 1
            reasons.append(f"Applicable to your crop ({crop}).")
        elif not crop:
            missing.append("crop")
        else:
            reasons.append(f"Applies to: {', '.join(crops)}.")

    ratio = matches / total if total else 0
    if missing and ratio < 0.75:
        verdict = "Missing information"
    elif ratio >= 0.75:
        verdict = "Likely eligible"
    elif ratio >= 0.4:
        verdict = "Possibly eligible"
    else:
        verdict = "Not eligible"

    return {
        "scheme_id": scheme.id,
        "scheme_name": scheme.name,
        "verdict": verdict,
        "match_ratio": round(ratio, 2),
        "why": reasons,
        "missing": missing,
        "note": "Likely eligible — verify with the official department before applying."
                if verdict in ("Likely eligible", "Possibly eligible") else "",
        "url": scheme.url,
    }


def recommend(schemes: list[Scheme], profile: dict) -> list[dict]:
    results = [evaluate(s, profile) for s in schemes]
    order = {"Likely eligible": 0, "Possibly eligible": 1,
             "Missing information": 2, "Not eligible": 3}
    results.sort(key=lambda r: (order.get(r["verdict"], 9), -r["match_ratio"]))
    return results
