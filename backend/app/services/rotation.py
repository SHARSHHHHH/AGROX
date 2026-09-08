"""Crop rotation knowledge layer.

Kept as data, not logic buried in a UI component, so an agronomist can correct
it without touching code.

WHY ROTATION MATTERS ENOUGH TO SCORE
------------------------------------
Growing the same crop, or a crop from the same family, twice running lets
soil-borne pathogens and host-specific pests build up, and drains the same
nutrients twice. Legumes fix nitrogen and leave the soil richer for a following
cereal — the classic soybean-then-wheat rotation that dominates Madhya Pradesh.

CAVEAT
------
These are widely-cited general principles compiled for this project, not
validated field trials for your specific soil. They are weighted modestly in
the overall score for that reason, and every recommendation carries a
disclaimer pointing to the local Krishi Vigyan Kendra.
"""

from typing import Dict, List, Optional, Tuple

# Botanical family drives most rotation logic: pathogens are usually
# family-specific rather than crop-specific.
CROP_FAMILY: Dict[str, str] = {
    "soybean": "legume",
    "chickpea": "legume",
    "pigeonpea": "legume",
    "groundnut": "legume",
    "greengram": "legume",
    "blackgram": "legume",
    "lentil": "legume",
    "wheat": "cereal",
    "rice": "cereal",
    "maize": "cereal",
    "sorghum": "cereal",
    "millet": "cereal",
    "barley": "cereal",
    "cotton": "fibre",
    "mustard": "oilseed_brassica",
    "tomato": "solanaceae",
    "potato": "solanaceae",
    "brinjal": "solanaceae",
    "chilli": "solanaceae",
    "cabbage": "brassica",
    "cauliflower": "brassica",
    "onion": "allium",
    "sugarcane": "cereal",
}

# Nitrogen left in the soil after harvest, roughly kg/ha. Legumes fix it;
# cereals are heavy feeders and leave the soil depleted.
NITROGEN_EFFECT: Dict[str, int] = {
    "legume": 30,
    "cereal": -25,
    "fibre": -20,
    "solanaceae": -20,
    "brassica": -15,
    "oilseed_brassica": -10,
    "allium": -10,
}

ROTATION_EXCELLENT = 1.0
ROTATION_GOOD = 0.8
ROTATION_NEUTRAL = 0.6
ROTATION_POOR = 0.3
ROTATION_BAD = 0.1


def family_of(crop: str) -> Optional[str]:
    if not crop:
        return None
    return CROP_FAMILY.get(crop.strip().lower())


def score_rotation(previous_crop: str, candidate_crop: str) -> Tuple[float, str]:
    """Return (0-1 score, plain-language reason).

    Returns a NEUTRAL score when the previous crop is unknown, so a farmer who
    has not told us their history is neither rewarded nor punished.
    """
    if not previous_crop:
        return ROTATION_NEUTRAL, (
            "No previous crop recorded, so rotation benefit could not be "
            "assessed. Adding it improves this recommendation.")

    prev = previous_crop.strip().lower()
    cand = candidate_crop.strip().lower()

    prev_family = family_of(prev)
    cand_family = family_of(cand)

    if prev == cand:
        return ROTATION_BAD, (
            f"You grew {previous_crop} last season. Growing it again lets "
            f"soil-borne diseases and pests of {previous_crop} build up, and "
            f"drains the same nutrients twice.")

    if prev_family is None or cand_family is None:
        return ROTATION_NEUTRAL, (
            f"Rotation effect between {previous_crop} and {candidate_crop} is "
            f"not in our knowledge base.")

    if prev_family == cand_family:
        return ROTATION_POOR, (
            f"{previous_crop} and {candidate_crop} are both in the "
            f"{prev_family} family, so they share many pests and diseases. "
            f"A different family would break that cycle.")

    # Legume -> cereal is the strongest rotation in Indian farming.
    if prev_family == "legume" and cand_family == "cereal":
        return ROTATION_EXCELLENT, (
            f"Excellent rotation. {previous_crop} is a legume and leaves "
            f"nitrogen in the soil, which {candidate_crop} needs heavily. This "
            f"can reduce your nitrogen fertiliser requirement.")

    if prev_family == "cereal" and cand_family == "legume":
        return ROTATION_EXCELLENT, (
            f"Excellent rotation. {candidate_crop} is a legume and will "
            f"restore nitrogen that {previous_crop} removed, improving the "
            f"soil for your next cereal.")

    if prev_family == "solanaceae" and cand_family in ("legume", "cereal"):
        return ROTATION_GOOD, (
            f"Good rotation. Moving away from {previous_crop} breaks the "
            f"soil-borne wilt and blight cycle common in that family.")

    return ROTATION_GOOD, (
        f"Reasonable rotation. {candidate_crop} is a different family from "
        f"{previous_crop}, which helps break pest and disease cycles.")


def nitrogen_carryover(previous_crop: str) -> Tuple[int, str]:
    """Approximate nitrogen the previous crop left behind, kg/ha."""
    fam = family_of(previous_crop)
    if fam is None:
        return 0, ""
    effect = NITROGEN_EFFECT.get(fam, 0)
    if effect > 0:
        return effect, (
            f"{previous_crop} is a legume and may have left roughly "
            f"{effect} kg/ha of nitrogen in the soil.")
    if effect < 0:
        return effect, (
            f"{previous_crop} is a heavy feeder and will have drawn down soil "
            f"nitrogen. Plan for replenishment.")
    return 0, ""


def suggested_rotations(previous_crop: str, candidates: List[str]) -> List[dict]:
    """Rank candidates by rotation fit alone. Used for explanation, not ranking."""
    out = []
    for c in candidates:
        score, reason = score_rotation(previous_crop, c)
        out.append({"crop": c, "rotation_score": score, "reason": reason})
    out.sort(key=lambda x: x["rotation_score"], reverse=True)
    return out
