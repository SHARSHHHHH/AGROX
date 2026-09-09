"""Farm profile, setup gating, and rotation-aware next-crop recommendations.

These endpoints exist so that no screen has to reassemble farm context by
hand. Anything personalised reads /api/farm/profile once and works from that.
"""

import logging
from datetime import timedelta
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.security import get_current_user
from app.database.db import get_db
from app.models.models import Farm, User
from app.services import farm_profile as fp
from app.services import lifecycle as lc
from app.services import rotation
from app.services.crop_suitability import MP_CROPS, current_season, score_crop

log = logging.getLogger("agri.api.farm_profile")

profile_router = APIRouter(prefix="/api/farm", tags=["farm-profile"])


@profile_router.get("/setup/status")
def farm_setup_status(user: User = Depends(get_current_user),
                      db: Session = Depends(get_db)):
    """Has setup been completed? Drives the frontend route guard.

    Deliberately cheap — no weather, no satellite, no external call. The guard
    runs on every protected navigation, so it must not cost a network round
    trip to Google or Open-Meteo.
    """
    return fp.setup_status(db, user)


@profile_router.get("/profile")
async def farm_profile(user: User = Depends(get_current_user),
                       db: Session = Depends(get_db)):
    """The complete normalised farm context, with confidence on every field."""
    return await fp.build_profile(db, user)


@profile_router.get("/current-crop/lifecycle")
def current_crop_lifecycle(user: User = Depends(get_current_user),
                           db: Session = Depends(get_db)):
    """Full lifecycle for the crop actually in the ground, stage highlighted."""
    farm = db.query(Farm).filter(Farm.user_id == user.id).first()
    if not farm or not farm.crop:
        return {"growing": False,
                "message": "No crop is currently registered on your farm."}

    current = fp._current_crop(farm)
    data = lc.get_lifecycle(farm.crop)
    if data is None:
        return {"growing": True, "crop": farm.crop,
                "has_lifecycle": False,
                "message": f"No lifecycle data is available for {farm.crop}."}

    das = (current.get("days_after_sowing") or {}).get("value")
    stages = _annotate_stages(data["stages"], das)

    return {
        "growing": True,
        "is_current_crop": True,
        "crop": current["crop"],
        "display": current["display"],
        "sowing_date": current["sowing_date"],
        "days_after_sowing": current["days_after_sowing"],
        "expected_duration_days": current["expected_duration_days"],
        "expected_harvest_date": current["expected_harvest_date"],
        "current_stage": current["stage"],
        "has_lifecycle": True,
        "stages": stages,
        "note": ("Stage is estimated from your sowing date. Confirm by looking "
                 "at the crop before acting on it."),
    }


@profile_router.get("/crop/{crop_key}/lifecycle")
def explore_crop_lifecycle(crop_key: str,
                           user: User = Depends(get_current_user),
                           db: Session = Depends(get_db)):
    """Lifecycle for ANY crop, clearly labelled current vs merely explored.

    THE POINT OF THIS ENDPOINT
    --------------------------
    A farmer growing rice who opens the cotton lifecycle must not be shown a
    highlighted "current stage" for cotton. There is no cotton in their field,
    so any highlighted stage would be fiction.

    So: `is_current_crop` decides whether stages carry a current marker at
    all, and when it is false the response carries an explicit warning naming
    what they ARE growing.
    """
    key = (crop_key or "").strip().lower()
    resolved = lc.resolve_crop(key) or key
    data = lc.get_lifecycle(resolved)
    if data is None:
        raise HTTPException(
            status_code=404,
            detail=f"No lifecycle data for '{crop_key}'. Supported: "
                   f"{', '.join(lc.supported_crops())}")

    farm = db.query(Farm).filter(Farm.user_id == user.id).first()
    farm_crop = ((farm.crop or "").strip().lower() if farm else "")
    is_current = bool(farm_crop) and lc.resolve_crop(farm_crop) == resolved

    spec = MP_CROPS.get(resolved, {})
    das = None
    if is_current:
        das = (fp._current_crop(farm).get("days_after_sowing") or {}).get("value")

    warning = None
    if not is_current:
        farm_display = (MP_CROPS.get(farm_crop, {}).get("display")
                        or (farm.crop if farm else ""))
        warning = {
            "type": "NOT_YOUR_CURRENT_CROP",
            "explored_crop": spec.get("display", resolved),
            "current_crop": farm_display or None,
            "message": (
                f"You are currently growing {farm_display}. "
                f"You are viewing information about "
                f"{spec.get('display', resolved)}."
                if farm_display else
                f"You are not currently growing "
                f"{spec.get('display', resolved)}. No crop is registered on "
                f"your farm yet."),
            "short": ("This is not your current crop."
                      if farm_display else
                      "This crop is not currently registered on your farm."),
        }

    return {
        "crop": resolved,
        "display": spec.get("display", resolved),
        "is_current_crop": is_current,
        "label": "CURRENT CROP" if is_current else "EXPLORED CROP",
        "warning": warning,
        "days_after_sowing": das,
        "stages": _annotate_stages(data["stages"], das if is_current else None),
        "total_duration_days": data.get("total_duration_days"),
        "stage_count": data.get("stage_count"),
        "suitability": _suitability_for(db, user, resolved),
    }


def _annotate_stages(stages: List[dict],
                     das: Optional[int]) -> List[Dict[str, Any]]:
    """Mark which stage the farmer is in. No day count -> nothing highlighted.

    `is_current` is False on every stage when `das` is None, so an explored
    crop never shows a highlight it has not earned.
    """
    out = []
    for idx, st in enumerate(stages):
        start, end = st.get("start_day"), st.get("end_day")
        is_current = (das is not None and start is not None
                      and end is not None and start <= das <= end)
        out.append({
            "index": idx,
            "stage": st.get("stage"),
            "start_day": start,
            "end_day": end,
            "duration_days": (end - start + 1)
                             if start is not None and end is not None else None,
            "tasks": st.get("tasks", []),
            "irrigation": st.get("irrigation", ""),
            "risks": st.get("risks", []),
            "is_current": is_current,
            "is_past": das is not None and end is not None and das > end,
            "is_future": das is not None and start is not None and das < start,
            # Populated once stage photographs are added under
            # frontend/public/crops/<crop>/<index>-*.jpg
            "image": None,
        })
    return out


def _suitability_for(db: Session, user: User, crop_key: str) -> Dict[str, Any]:
    """Could this farmer grow this crop here? Reuses the existing scorer.

    Answers the natural follow-up to "this is not your current crop": fine,
    but *could* I grow it? Uses the same score_crop() the ranking uses, so the
    verdict is consistent with the recommendations page.
    """
    if crop_key not in MP_CROPS:
        return {"available": False}

    farm = db.query(Farm).filter(Farm.user_id == user.id).first()
    if farm is None:
        return {"available": False,
                "note": "Complete farm setup to check if this crop suits your land."}

    from app.models.models import SoilTest
    soil = (db.query(SoilTest).filter(SoilTest.user_id == user.id)
            .order_by(SoilTest.created_at.desc()).first())

    result = score_crop(
        crop_key,
        ph=soil.ph if soil else None,
        nitrogen=soil.nitrogen if soil else None,
        phosphorus=soil.phosphorus if soil else None,
        potassium=soil.potassium if soil else None,
        soil_type=farm.soil_type or "",
        season=current_season(),
    )
    return {
        "available": True,
        "score": result["score"],
        "verdict": result["verdict"],
        "reasons": result["reasons"],
        "limitations": result["limitations"],
        "season": result["season"],
        "duration_days": result["duration_days"],
        "water_need": result["water_need"],
        "note": ("Advisory suitability for your soil, soil type and the "
                 "current season. It is not a yield forecast."),
    }


def _rank_after(db: Session, farm: Farm, after_crop: str, ranking_season: str,
                caution_crop: str = "", limit: int = 5) -> List[Dict[str, Any]]:
    """Rank every MP crop as a follow-on to `after_crop`.

    Shared by /next-crops (after the crop currently in the ground) and
    /next-crops-for-previous (after a just-finished previous crop, used by
    the onboarding wizard before any current crop is registered). Both are
    the same question — "what suits this land next, given what was just
    growing here" — so the scoring lives in one place.
    """
    from app.models.models import SoilTest
    soil = (db.query(SoilTest).filter(SoilTest.user_id == farm.user_id)
            .order_by(SoilTest.created_at.desc()).first())

    after = (after_crop or "").strip().lower()
    caution = (caution_crop or "").strip().lower()

    ranked = []
    for key, cspec in MP_CROPS.items():
        if key == after:
            continue    # never suggest repeating the crop just harvested
        rot_score, rot_reason = rotation.score_rotation(after, key)
        agro = score_crop(
            key,
            ph=soil.ph if soil else None,
            nitrogen=soil.nitrogen if soil else None,
            phosphorus=soil.phosphorus if soil else None,
            potassium=soil.potassium if soil else None,
            soil_type=farm.soil_type or "",
            season=ranking_season,
        )
        # Rotation weighted heavily here: the question being asked IS a
        # rotation question, unlike the general "what should I grow" ranking.
        combined = round(0.55 * agro["score"] + 45 * rot_score, 1)

        why = list(agro["reasons"][:2])
        why.insert(0, rot_reason)
        if caution and caution != after:
            caution_score, caution_reason = rotation.score_rotation(caution, key)
            if caution_score <= rotation.ROTATION_POOR:
                why.append(f"Caution: {caution_reason}")

        ranked.append({
            "crop": key,
            "display": cspec["display"],
            "score": combined,
            "rotation_score": round(rot_score * 100),
            "agronomy_score": agro["score"],
            "verdict": agro["verdict"],
            "why": why,
            "limitations": agro["limitations"][:3],
            "duration_days": cspec["duration_days"],
            "water_need": cspec["water_need"],
            "family": rotation.family_of(key),
        })

    ranked.sort(key=lambda r: r["score"], reverse=True)
    return ranked[:max(1, min(limit, 15))]


SEASON_LABEL = {
    "kharif": "Kharif (monsoon, June-October)",
    "rabi": "Rabi (winter, November-March)",
    "zaid": "Zaid (summer, April-May)",
}


@profile_router.get("/next-crops")
def next_crops(limit: int = 5,
               user: User = Depends(get_current_user),
               db: Session = Depends(get_db)):
    """What to sow AFTER the crop currently in the ground.

    Distinct from /api/advisor/recommend, which answers "what should I grow
    now". This one chains previous -> current -> next, so the rotation logic
    sees the crop that is actually occupying the field rather than the one
    before it.
    """
    farm = db.query(Farm).filter(Farm.user_id == user.id).first()
    if farm is None:
        return {"available": False,
                "message": "Complete farm setup to get rotation advice."}

    current = (farm.crop or "").strip().lower()
    previous = (farm.previous_crop or "").strip().lower()

    if not current:
        return {"available": False,
                "message": ("No current crop is registered. Add it during farm "
                            "setup to see what suits your land next.")}

    # Season AFTER this crop comes off, not the season now — that is the whole
    # point of a "next crop" question.
    spec = MP_CROPS.get(current, {})
    duration = spec.get("duration_days")
    harvest = (farm.sowing_date + timedelta(days=duration)
               if farm.sowing_date and duration else None)
    next_season = current_season(harvest.date()) if harvest else None

    ranked = _rank_after(db, farm, current, next_season or current_season(),
                         caution_crop=previous, limit=limit)
    n_carry, n_note = rotation.nitrogen_carryover(current)

    now_season = current_season()
    changing = bool(next_season) and next_season != now_season

    return {
        "available": True,
        "current_crop": {"crop": current,
                         "display": spec.get("display", farm.crop)},
        # Stated plainly so the farmer is never left wondering whether we are
        # telling them to uproot what is already in the ground.
        "headline": (
            f"You are currently growing {spec.get('display', farm.crop)}. "
            + (f"After you harvest it"
               + (f" (around {harvest.date().strftime('%B %Y')})" if harvest else "")
               + f", the season will have moved to "
                 f"{SEASON_LABEL.get(next_season, next_season)}"
               if changing else
               f"After you harvest it, these crops suit your land next")
            + "."),
        "season_now": now_season,
        "season_now_label": SEASON_LABEL.get(now_season, now_season),
        "season_changes": changing,
        "next_season_label": SEASON_LABEL.get(next_season, next_season or ""),
        "previous_crop": previous or None,
        "expected_harvest": harvest.date().isoformat() if harvest else None,
        "next_season": next_season,
        "nitrogen_carryover_kg": n_carry,
        "nitrogen_note": n_note,
        "recommendations": ranked,
        "note": ("Ranked for sowing after your current crop is harvested. "
                 "Rotation is weighted heavily here because repeating the "
                 "same family builds up pests and drains the same nutrients."),
    }


@profile_router.get("/next-crops-for-previous")
def next_crops_for_previous(limit: int = 5,
                            user: User = Depends(get_current_user),
                            db: Session = Depends(get_db)):
    """What to sow NOW, given the crop the farmer says just finished.

    Used by the onboarding wizard: once a farmer names a previous crop that
    has genuinely already been harvested (see previous_crop_check in
    /api/onboarding/status), there is no current crop registered yet, so
    /next-crops (which requires one) cannot answer "what next". This ranks
    against previous_crop instead, for the season as of today rather than a
    projected future season, since the field is empty right now.
    """
    farm = db.query(Farm).filter(Farm.user_id == user.id).first()
    previous = (farm.previous_crop or "").strip().lower() if farm else ""
    # "none" is the onboarding wizard's own explicit "no previous crop" pill
    # value, not a crop name.
    if not previous or previous == "none":
        return {"available": False,
                "message": "Add your previous crop during farm setup to see "
                           "what suits your land next."}

    ranked = _rank_after(db, farm, previous, current_season(), limit=limit)
    n_carry, n_note = rotation.nitrogen_carryover(previous)
    prev_spec = MP_CROPS.get(previous, {})
    now_season = current_season()

    return {
        "available": True,
        "previous_crop": {"crop": previous,
                          "display": prev_spec.get("display", farm.previous_crop)},
        "headline": (f"{prev_spec.get('display', farm.previous_crop)} is off the "
                     f"field. These crops suit your land for the current "
                     f"{SEASON_LABEL.get(now_season, now_season)} season."),
        "season_now": now_season,
        "season_now_label": SEASON_LABEL.get(now_season, now_season),
        "nitrogen_carryover_kg": n_carry,
        "nitrogen_note": n_note,
        "recommendations": ranked,
        "note": ("Ranked for sowing now, right after your previous crop. "
                 "Rotation is weighted heavily here because repeating the "
                 "same family builds up pests and drains the same nutrients."),
    }
