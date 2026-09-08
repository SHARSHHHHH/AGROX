"""Circular farming: cattle -> biogas -> digestate -> crops -> residue -> repeat.

The module is presented as ONE continuous plan rather than a set of
calculators. `/api/circular/plan` returns the whole cycle in a single call, so
the UI can render the loop without stitching six requests together.

Every numeric field is an ESTIMATE derived from farmer-entered figures and
published typical yields. Nothing here is measured, and no LLM produces any
quantity — the assistant may rephrase these results later, but it is never
asked to originate one.
"""

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.security import get_current_user
from app.database.db import get_db
from app.models.models import (BiogasAssessment, BiogasLog, BiogasPlant,
                               BiogasTechnician, CircularChoice,
                               CropResidueRecord, DigestateAllocation,
                               ExternalAdvisory, Farm, Livestock, SoilTest,
                               SupplyOffer, User)
from app.services import biogas as bg
from app.services import manure as mn
from app.services.crop_suitability import MP_CROPS

log = logging.getLogger("agri.api.circular")

circular_router = APIRouter(prefix="/api/circular", tags=["circular-farming"])

DISCLAIMER = (
    "These are approximate planning figures based on the information you "
    "entered, not guaranteed production. This is an agricultural planning "
    "aid, not an engineering design. Before building anything, get a site "
    "visit from a qualified biogas installer or your local Krishi Vigyan "
    "Kendra.")


# =====================================================================
# Livestock
# =====================================================================

class LivestockIn(BaseModel):
    animal_type: str = "cow"
    count: int = Field(0, ge=0, le=10000)
    dung_kg_per_day: Optional[float] = Field(None, ge=0)
    collection_regular: bool = True
    housing: str = ""
    notes: str = ""


@circular_router.get("/livestock")
def list_livestock(user: User = Depends(get_current_user),
                   db: Session = Depends(get_db)):
    rows = db.query(Livestock).filter(Livestock.user_id == user.id).all()
    herd = [{"id": r.id, "animal_type": r.animal_type, "count": r.count,
             "dung_kg_per_day": r.dung_kg_per_day,
             "collection_regular": r.collection_regular,
             "housing": r.housing, "notes": r.notes} for r in rows]
    return {"livestock": herd, "dung": bg.dung_from_livestock(herd)}


@circular_router.post("/livestock")
def save_livestock(entries: List[LivestockIn],
                   user: User = Depends(get_current_user),
                   db: Session = Depends(get_db)):
    """Replace the herd in one call — the wizard submits the whole list."""
    db.query(Livestock).filter(Livestock.user_id == user.id).delete()
    farm = db.query(Farm).filter(Farm.user_id == user.id).first()
    for e in entries:
        if e.count <= 0:
            continue
        db.add(Livestock(user_id=user.id, farm_id=farm.id if farm else None,
                         animal_type=e.animal_type.strip().lower(),
                         count=e.count, dung_kg_per_day=e.dung_kg_per_day,
                         collection_regular=e.collection_regular,
                         housing=e.housing, notes=e.notes))
    db.commit()
    return list_livestock(user, db)


# =====================================================================
# The farmer's remembered choice
# =====================================================================
#
# The page opens with one question — biogas, existing plant, or manure — and
# the composting branch asks three more. Keeping those answers only in the
# browser meant every reload started from zero. A farmer who has already told
# the app they are composting, in the shade, with little spare labour, should
# never be asked again unless they want to change it.

class ChoiceIn(BaseModel):
    mode: str = ""                                   # biogas | plant | manure
    has_shade: Optional[bool] = None
    labour: Optional[str] = None                     # low | normal
    urgent: Optional[bool] = None
    answered: Optional[bool] = None
    keep_kg: Optional[float] = Field(None, ge=0)


def _choice_row(db: Session, user: User) -> CircularChoice:
    row = (db.query(CircularChoice)
           .filter(CircularChoice.user_id == user.id).first())
    if row is None:
        row = CircularChoice(user_id=user.id)
        db.add(row)
        db.commit()
        db.refresh(row)
    return row


def _choice_public(row: CircularChoice) -> Dict[str, Any]:
    return {
        "mode": row.mode or "",
        "has_shade": bool(row.has_shade) if row.has_shade is not None else True,
        "labour": row.labour or "normal",
        "urgent": bool(row.urgent),
        "answered": bool(row.answered),
        "keep_kg": row.keep_kg,
    }


@circular_router.get("/choice")
def get_choice(user: User = Depends(get_current_user),
               db: Session = Depends(get_db)):
    """What this farmer already decided, plus their biogas registration state.

    Both travel together so the page can restore the whole entry screen in one
    call and never re-ask a question that has already been answered.
    """
    out = _choice_public(_choice_row(db, user))
    out["biogas"] = _biogas_status(db, user)
    return out


@circular_router.post("/choice")
def save_choice(data: ChoiceIn, user: User = Depends(get_current_user),
                db: Session = Depends(get_db)):
    """Remember the choice. Only fields actually sent are changed, so saving
    a keep-back quantity cannot silently reset the composting answers."""
    row = _choice_row(db, user)

    if data.mode is not None and data.mode != "":
        if data.mode not in ("biogas", "plant", "manure"):
            raise HTTPException(400, "mode must be biogas, plant or manure")
        row.mode = data.mode
    elif data.mode == "" and data.answered is None and data.keep_kg is None \
            and data.has_shade is None and data.labour is None \
            and data.urgent is None:
        # An explicit bare {"mode": ""} is the farmer backing out to the menu.
        row.mode = ""
        row.answered = False

    if data.has_shade is not None:
        row.has_shade = data.has_shade
    if data.labour is not None:
        row.labour = data.labour if data.labour in ("low", "normal") else "normal"
    if data.urgent is not None:
        row.urgent = data.urgent
    if data.answered is not None:
        row.answered = data.answered
    if data.keep_kg is not None:
        row.keep_kg = data.keep_kg

    db.commit()
    db.refresh(row)
    return _choice_public(row)


def _biogas_status(db: Session, user: User) -> Dict[str, Any]:
    """Whether this farmer has a biogas plant on record, and what it yields.

    THE POINT OF THIS FUNCTION
    --------------------------
    Biogas registration and composting were two unrelated branches of the
    page, so a farmer who had already registered a plant and later chose
    "Make Manure" was asked to register all over again — and the composting
    plan ignored the digester entirely, even though a working digester is
    already producing slurry that IS manure.

    Every branch now reads this one function, so registration is asked for
    once, stored once, and honoured everywhere.
    """
    plant = (db.query(BiogasPlant)
             .filter(BiogasPlant.user_id == user.id,
                     BiogasPlant.active == True).first())      # noqa: E712
    if plant is None:
        return {"registered": False, "plant": None,
                "digestate_kg_per_month": None,
                "message": ("No biogas plant is registered yet. Compost is "
                            "made straight from dung and crop residue "
                            "instead.")}

    herd = _herd(db, user)
    dung_mid = bg.dung_from_livestock(herd)["total_kg_per_day"]["mid"]

    # Digestate out is close to what goes in: the digester removes carbon as
    # gas, not mass as water. Feed is dung plus an equal volume of water, and
    # roughly 90-95% of that comes back out as slurry.
    daily_feed = dung_mid * 2 if dung_mid else 0.0
    digestate_month = round(daily_feed * 0.92 * 30) if daily_feed else 0

    last = (db.query(BiogasLog)
            .filter(BiogasLog.plant_id == plant.id)
            .order_by(BiogasLog.logged_on.desc()).first())

    return {
        "registered": True,
        "plant": {"id": plant.id, "size_m3": plant.size_m3,
                  "plant_type": plant.plant_type,
                  "monitoring_mode": plant.monitoring_mode},
        "digestate_kg_per_month": digestate_month,
        "last_logged_on": last.logged_on if last else None,
        "message": (
            f"Your registered biogas plant already produces about "
            f"{digestate_month} kg of slurry a month. That slurry is manure — "
            f"composting it further makes it easier to store and spread."
            if digestate_month else
            "Your biogas plant is registered. Add your cattle to estimate how "
            "much slurry it will produce."),
    }


# =====================================================================
# Shared context
# =====================================================================

def _herd(db: Session, user: User) -> List[dict]:
    return [{"animal_type": r.animal_type, "count": r.count,
             "dung_kg_per_day": r.dung_kg_per_day,
             "collection_regular": r.collection_regular}
            for r in db.query(Livestock).filter(Livestock.user_id == user.id)]


def _residue_available(farm: Optional[Farm]) -> Dict[str, Any]:
    if not farm or not farm.crop:
        return {"available": False,
                "note": "Add your current crop to estimate residue."}
    area = farm.crop_area_acres or farm.land_size_acres
    return bg.residue_available_kg(farm.crop, area)


def _assessment(db: Session, user: User) -> Dict[str, Any]:
    """Feasibility + estimates, computed fresh from current farm state."""
    farm = db.query(Farm).filter(Farm.user_id == user.id).first()
    herd = _herd(db, user)
    dung = bg.dung_from_livestock(herd)
    dung_mid = dung["total_kg_per_day"]["mid"]

    residue = _residue_available(farm)
    residue_total = (residue.get("residue_kg", {}) or {}).get("mid", 0.0) \
        if residue.get("available") else 0.0
    # Residue is a one-off harvest quantity; spread over a season for a daily
    # feed rate rather than pretending it all arrives every day.
    residue_daily = round(residue_total / 120.0, 1) if residue_total else 0.0

    regular = all(h.get("collection_regular", True) for h in herd) if herd else True

    verdict = bg.assess(
        dung_kg_per_day=dung_mid,
        residue_kg_available=residue_daily,
        water_availability=(farm.water_availability if farm else "") or "",
        space_m2=None,
        collection_regular=regular)

    estimates = bg.estimate(dung_kg_per_day=dung_mid,
                            residue_kg_per_day=residue_daily)

    return {"herd": herd, "dung": dung, "residue": residue,
            "residue_daily_kg": residue_daily,
            "feasibility": verdict, "estimates": estimates, "farm": farm}


@circular_router.get("/assessment")
def assessment(user: User = Depends(get_current_user),
               db: Session = Depends(get_db)):
    """Farm resource assessment and biogas potential (spec 2 and 3)."""
    ctx = _assessment(db, user)
    if not ctx["herd"]:
        return {
            "has_livestock": False,
            "message": ("Add your cattle to see whether a biogas setup is "
                        "worth considering on your farm."),
            "disclaimer": DISCLAIMER,
        }

    # Store it so the plan can be shown later without recomputing, and so a
    # farmer can see how the assessment changed as the farm changed.
    try:
        db.add(BiogasAssessment(
            user_id=user.id,
            total_dung_kg_per_day=ctx["dung"]["total_kg_per_day"]["mid"],
            residue_kg_available=ctx["residue_daily_kg"],
            water_availability=(ctx["farm"].water_availability
                                if ctx["farm"] else ""),
            verdict=ctx["feasibility"]["verdict"],
            verdict_reason=ctx["feasibility"]["reason"],
            blockers=ctx["feasibility"]["blockers"],
            est_daily_feed_kg=ctx["estimates"]["daily_feed_kg"]["mid"],
            est_biogas_m3_per_day=ctx["estimates"]["biogas_m3_per_day"]["mid"],
            est_plant_size_m3=ctx["estimates"]["suggested_plant_size_m3"],
            est_digestate_kg_per_day=ctx["estimates"]["digestate_kg_per_day"]["mid"],
            est_digestate_kg_per_month=ctx["estimates"]["digestate_kg_per_month"]["mid"],
            assumptions=ctx["estimates"]["assumptions"]))
        db.commit()
    except Exception as exc:                                # noqa: BLE001
        log.warning("could not store assessment: %s", exc)
        db.rollback()

    return {
        "has_livestock": True,
        "dung": ctx["dung"],
        "residue": ctx["residue"],
        "feasibility": ctx["feasibility"],
        "estimates": ctx["estimates"],
        "confidence": "ESTIMATED",
        "disclaimer": DISCLAIMER,
    }


# =====================================================================
# Digestate allocation  (spec 5, 7, 8)
# =====================================================================

class AllocationIn(BaseModel):
    reserved_own_farm_kg: float = Field(0, ge=0)
    note: str = ""


def _current_period() -> str:
    return datetime.utcnow().strftime("%Y-%m")


@circular_router.get("/digestate")
def digestate(user: User = Depends(get_current_user),
              db: Session = Depends(get_db)):
    """Digestate inventory: total, reserved, surplus.

    Surplus is ALWAYS computed as total minus reserved, never stored. Storing
    it would let the three numbers drift apart after any edit.
    """
    ctx = _assessment(db, user)
    if not ctx["herd"]:
        return {"available": False,
                "message": "Add your cattle to estimate digestate."}

    total = ctx["estimates"]["digestate_kg_per_month"]["mid"]
    period = _current_period()

    row = (db.query(DigestateAllocation)
           .filter(DigestateAllocation.user_id == user.id,
                   DigestateAllocation.period == period).first())
    reserved = row.reserved_own_farm_kg if row else 0.0
    reserved = min(reserved, total)

    return {
        "available": True,
        "period": period,
        "total_available_kg": round(total),
        "reserved_own_farm_kg": round(reserved),
        "potential_surplus_kg": round(max(0.0, total - reserved)),
        "range_kg_per_month": ctx["estimates"]["digestate_kg_per_month"],
        "note": (row.allocation_note if row else ""),
        "confidence": "ESTIMATED",
        "disclaimer": DISCLAIMER,
    }


@circular_router.post("/digestate/allocate")
def allocate(data: AllocationIn, user: User = Depends(get_current_user),
             db: Session = Depends(get_db)):
    """Reserve an amount for the farmer's own fields; the rest is surplus."""
    ctx = _assessment(db, user)
    if not ctx["herd"]:
        raise HTTPException(400, "Add your cattle before allocating digestate.")

    total = ctx["estimates"]["digestate_kg_per_month"]["mid"]
    if data.reserved_own_farm_kg > total:
        raise HTTPException(
            400, f"You cannot reserve more than the estimated "
                 f"{round(total)} kg available this month.")

    period = _current_period()
    row = (db.query(DigestateAllocation)
           .filter(DigestateAllocation.user_id == user.id,
                   DigestateAllocation.period == period).first())
    if row is None:
        row = DigestateAllocation(user_id=user.id, period=period)
        db.add(row)
    row.total_available_kg = total
    row.reserved_own_farm_kg = data.reserved_own_farm_kg
    row.allocation_note = data.note
    db.commit()
    return digestate(user, db)


@circular_router.get("/manure/recommend")
def manure_recommend(crop: str = "", area_acres: Optional[float] = None,
                     user: User = Depends(get_current_user),
                     db: Session = Depends(get_db)):
    """Crop-specific digestate guidance (spec 6).

    Defaults to the farmer's own crop and area. Explicitly per crop: the same
    quantity is NOT appropriate for a legume and a cereal.
    """
    farm = db.query(Farm).filter(Farm.user_id == user.id).first()
    crop = (crop or (farm.crop if farm else "") or "").strip().lower()
    if area_acres is None and farm:
        area_acres = farm.crop_area_acres or farm.land_size_acres

    soil_row = (db.query(SoilTest).filter(SoilTest.user_id == user.id)
                .order_by(SoilTest.created_at.desc()).first())
    soil = ({"nitrogen": soil_row.nitrogen, "phosphorus": soil_row.phosphorus,
             "potassium": soil_row.potassium, "ph": soil_row.ph}
            if soil_row else None)

    inv = digestate(user, db)
    available = inv.get("reserved_own_farm_kg") or inv.get("total_available_kg")

    rec = mn.recommend_for_crop(crop=crop, area_acres=area_acres,
                                available_kg=available, soil=soil)
    return {"recommendation": rec, "digestate_available_kg": available,
            "used_soil_test": soil is not None,
            "disclaimer": DISCLAIMER}


@circular_router.get("/manure/compare")
def manure_compare(area_acres: float = 1.0,
                   user: User = Depends(get_current_user)):
    """Side-by-side rates across crops.

    Exists to make the central point visible: the same digestate suits
    different crops in very different quantities.
    """
    out = []
    for key, spec in MP_CROPS.items():
        r = mn.recommend_for_crop(crop=key, area_acres=area_acres)
        if r.get("available"):
            out.append({"crop": key, "display": spec["display"],
                        "group": r["group"],
                        "rate_kg_per_acre": r["rate_kg_per_acre"],
                        "why": r["why"][0]})
    out.sort(key=lambda x: -x["rate_kg_per_acre"]["mid"])
    return {"area_acres": area_acres, "crops": out,
            "note": ("Rates differ by crop. Legumes fix their own nitrogen and "
                     "need far less; root crops need care because excess "
                     "nitrogen grows tops instead of tubers."),
            "disclaimer": DISCLAIMER}


# =====================================================================
# Crop residue  (spec 10)
# =====================================================================

class ResidueIn(BaseModel):
    crop: str
    area_acres: Optional[float] = None
    chosen_route: str = ""
    note: str = ""


@circular_router.get("/residue")
def residue(crop: str = "", user: User = Depends(get_current_user),
            db: Session = Depends(get_db)):
    """What to do with this crop's residue. Not everything goes to biogas."""
    farm = db.query(Farm).filter(Farm.user_id == user.id).first()
    crop = (crop or (farm.crop if farm else "") or "").strip().lower()
    area = (farm.crop_area_acres or farm.land_size_acres) if farm else None

    herd = _herd(db, user)
    est = bg.residue_available_kg(crop, area)
    residue_kg = (est.get("residue_kg", {}) or {}).get("mid") \
        if est.get("available") else None

    routing = mn.route_residue(
        crop=crop, residue_kg=residue_kg,
        has_biogas=bool(herd),           # a digester is plausible if cattle exist
        has_cattle=bool(herd))

    history = (db.query(CropResidueRecord)
               .filter(CropResidueRecord.user_id == user.id)
               .order_by(CropResidueRecord.created_at.desc()).limit(10).all())

    return {
        "crop": crop, "estimate": est, "routing": routing,
        "history": [{"id": r.id, "crop": r.crop, "route": r.chosen_route,
                     "est_residue_kg": r.est_residue_kg,
                     "date": r.created_at.isoformat() if r.created_at else None}
                    for r in history],
        "disclaimer": DISCLAIMER,
    }


@circular_router.post("/residue")
def save_residue(data: ResidueIn, user: User = Depends(get_current_user),
                 db: Session = Depends(get_db)):
    est = bg.residue_available_kg(data.crop, data.area_acres)
    routing = mn.route_residue(crop=data.crop, has_biogas=True, has_cattle=True)
    row = CropResidueRecord(
        user_id=user.id, crop=data.crop.strip().lower(),
        area_acres=data.area_acres,
        est_residue_kg=((est.get("residue_kg", {}) or {}).get("mid", 0)
                        if est.get("available") else 0),
        chosen_route=data.chosen_route,
        recommended_route=routing.get("recommended_route", ""),
        route_note=data.note)
    db.add(row)
    db.commit()
    return {"status": "saved", "id": row.id,
            "recommended_route": row.recommended_route,
            "chosen_route": row.chosen_route}


# =====================================================================
# Surplus marketplace  (spec 9) — reuses SupplyOffer
# =====================================================================

class SurplusIn(BaseModel):
    quantity_kg: float = Field(..., gt=0)
    material_type: str = "digestate"     # digestate | compost | fdung
    suitable_crops: List[str] = []
    price: Optional[float] = Field(None, ge=0)
    price_unit: str = "per 100 kg"
    availability: str = ""
    notes: str = ""
    # User has no phone column, and a manure listing with no way to contact
    # the seller is useless to the buyer. Asked for explicitly.
    contact_phone: str = ""


@circular_router.post("/surplus/list")
def list_surplus(data: SurplusIn, user: User = Depends(get_current_user),
                 db: Session = Depends(get_db)):
    """Offer surplus digestate to other farmers.

    Reuses SupplyOffer, the same table that carries fertiliser offers, so
    surplus manure appears in the existing supply alerts without a parallel
    marketplace being built.
    """
    inv = digestate(user, db)
    surplus = inv.get("potential_surplus_kg", 0)
    if not inv.get("available"):
        raise HTTPException(400, "Add your cattle before listing surplus.")
    if data.quantity_kg > surplus:
        raise HTTPException(
            400, f"You have about {surplus} kg of surplus after what you "
                 f"reserved for your own farm. Reserve less if you want to "
                 f"list more.")

    farm = db.query(Farm).filter(Farm.user_id == user.id).first()
    crops = ", ".join(data.suitable_crops) if data.suitable_crops else "most crops"
    offer = SupplyOffer(
        seller_id=user.id,
        title=f"{data.quantity_kg:.0f} kg {data.material_type} — suits {crops}",
        category="manure",
        description=(data.notes or "") + (f" Available: {data.availability}"
                                          if data.availability else ""),
        price=data.price, price_unit=data.price_unit,
        quantity_available=f"{data.quantity_kg:.0f} kg",
        seller_name=user.name or "", contact_phone=data.contact_phone.strip(),
        state=(farm.state if farm else ""), district=(farm.district if farm else ""),
        village=(farm.village if farm else ""),
        # Farmer-to-farmer listings still need checking before they are pushed
        # into other farmers' alerts.
        verified=False, active=True)
    db.add(offer)
    db.commit()
    return {"status": "listed", "id": offer.id,
            "verified": False,
            "contact_missing": not data.contact_phone.strip(),
            "note": ("Your listing is saved and will appear to nearby farmers "
                     "once an administrator has checked it.")}


@circular_router.get("/surplus/search")
def search_surplus(crop: str = "", district: str = "",
                   min_kg: Optional[float] = None,
                   user: User = Depends(get_current_user),
                   db: Session = Depends(get_db)):
    """Find manure offered by other farmers, ranked by crop suitability.

    Ranking matters here. Showing every listing would make a farmer growing
    chickpea scroll past high-nitrogen material that is wrong for their crop.
    Listings whose material suits the crop's nitrogen group come first.
    """
    farm = db.query(Farm).filter(Farm.user_id == user.id).first()
    crop = (crop or (farm.crop if farm else "") or "").strip().lower()
    district = district or (farm.district if farm else "")

    q = (db.query(SupplyOffer)
         .filter(SupplyOffer.active == True,                 # noqa: E712
                 SupplyOffer.category.in_(("manure", "compost", "fertilizer"))))
    if district:
        q = q.filter(SupplyOffer.district == district)
    rows = q.order_by(SupplyOffer.created_at.desc()).limit(60).all()

    group = mn.CROP_GROUP.get(crop)
    scored = []
    for o in rows:
        title = (o.title or "").lower()
        score = 0
        if crop and crop in title:
            score += 3
        if group == "low_nitrogen" and "compost" in title:
            # Legumes want organic matter, not a nitrogen hit.
            score += 2
        elif group in ("high_nitrogen", "moderate") and "digestate" in title:
            score += 2
        if o.verified:
            score += 1
        scored.append((score, o))

    scored.sort(key=lambda t: -t[0])
    return {
        "crop": crop, "district": district or None,
        "count": len(scored),
        "offers": [{
            "id": o.id, "title": o.title, "category": o.category,
            "description": o.description, "price": o.price,
            "price_unit": o.price_unit, "quantity": o.quantity_available,
            "seller_name": o.seller_name, "contact_phone": o.contact_phone,
            "location": ", ".join(x for x in (o.village, o.district, o.state) if x),
            "verified": o.verified, "match_score": sc,
        } for sc, o in scored],
        "ranking_note": (
            "Ordered by how well the material suits your crop, not just by "
            "date. Legumes are matched to compost rather than high-nitrogen "
            "digestate."),
        "disclaimer": DISCLAIMER,
    }


# =====================================================================
# The whole cycle  (spec 11 and 15)
# =====================================================================

@circular_router.get("/plan")
def plan(user: User = Depends(get_current_user),
         db: Session = Depends(get_db)):
    """The complete circular farming plan in one call.

    Returned as a single object rather than six endpoints so the UI can draw
    the loop as one continuous flow — the module is meant to feel like a
    resource cycle, not a set of separate calculators.
    """
    farm = db.query(Farm).filter(Farm.user_id == user.id).first()
    ctx = _assessment(db, user)
    has_herd = bool(ctx["herd"])

    inv = digestate(user, db) if has_herd else {"available": False}
    crop = (farm.crop if farm else "") or ""
    area = (farm.crop_area_acres or farm.land_size_acres) if farm else None

    manure_rec = mn.recommend_for_crop(
        crop=crop, area_acres=area,
        available_kg=inv.get("reserved_own_farm_kg")) if crop else \
        {"available": False, "note": "Add your current crop for manure guidance."}

    residue_est = bg.residue_available_kg(crop, area)
    residue_route = mn.route_residue(crop=crop, has_biogas=has_herd,
                                     has_cattle=has_herd) if crop else \
        {"available": False}

    # Anything that would stop a biogas plant working is hoisted to the top
    # of the response. Water scarcity in particular must be said BEFORE the
    # farmer reads a four-step installation guide — a digester needs its own
    # volume in water every single day, and finding that out at step 5 wastes
    # their time.
    upfront = []
    if has_herd:
        for b in (ctx["feasibility"].get("blockers") or []):
            upfront.append({"level": "blocker", "message": b})
        for w in (ctx["feasibility"].get("warnings") or []):
            upfront.append({"level": "warning", "message": w})

    return {
        "upfront_warnings": upfront,
        "steps": {
            "1_feasibility": ctx["feasibility"] if has_herd else {
                "verdict": "NO_DATA",
                "reason": "Add your cattle to assess biogas feasibility."},
            "2_biogas_potential": ctx["estimates"] if has_herd else None,
            "3_preparation": _preparation_steps(),
            "4_digestate": inv,
            "5_crop_use": manure_rec,
            "6_reserved": inv.get("reserved_own_farm_kg") if has_herd else 0,
            "7_surplus": inv.get("potential_surplus_kg") if has_herd else 0,
            "8_residue": {"estimate": residue_est, "routing": residue_route},
            "9_sensors": {
                "required": False,
                "note": ("This plan works entirely from the details you "
                         "entered. Sensors for temperature, pH, gas pressure "
                         "and slurry level can be added later to replace "
                         "estimates with measurements."),
            },
        },
        "cycle": [
            {"node": "cattle", "label": "Cattle",
             "value": sum(h["count"] for h in ctx["herd"]) if has_herd else 0,
             "unit": "animals"},
            {"node": "dung", "label": "Dung",
             "value": ctx["dung"]["total_kg_per_day"]["mid"] if has_herd else 0,
             "unit": "kg/day"},
            {"node": "residue", "label": "Crop residue",
             "value": ctx["residue_daily_kg"], "unit": "kg/day"},
            {"node": "biogas", "label": "Biogas",
             "value": (ctx["estimates"]["biogas_m3_per_day"]["mid"]
                       if has_herd else 0), "unit": "m3/day"},
            {"node": "digestate", "label": "Digestate",
             "value": inv.get("total_available_kg", 0), "unit": "kg/month"},
            {"node": "own_farm", "label": "Own farm",
             "value": inv.get("reserved_own_farm_kg", 0), "unit": "kg"},
            {"node": "surplus", "label": "Surplus",
             "value": inv.get("potential_surplus_kg", 0), "unit": "kg"},
            # The crops node is a NAME, not a quantity, and the diagram used
            # to draw a dash for it because it only knew how to render
            # numbers. It now carries an explicit display string and the sown
            # area, so the farmer sees the crop they actually registered
            # instead of an empty circle on their own farm cycle.
            {"node": "crops", "label": "Crops",
             "value": crop or None,
             "display": (MP_CROPS.get(crop, {}).get("display")
                         or (crop.capitalize() if crop else "Not set")),
             "numeric": area,
             "unit": "acres" if area else "",
             "is_text": True},
        ],
        "has_livestock": has_herd,
        "confidence": "ESTIMATED",
        "disclaimer": DISCLAIMER,
    }


def _preparation_steps() -> List[Dict[str, str]]:
    """The 8-step installation guide.

    One or two plain sentences per step. This is a PLANNING guide so a farmer
    knows what the process involves and what to expect from an installer — it
    is deliberately not a construction manual. Steps 4, 5 and 6 involve
    structural work and gas under pressure, and each says plainly that a
    trained technician must do it.
    """
    return [
        {"n": "1", "icon": "location", "stage": "Choose the spot",
         "detail": ("Pick level ground within about 10 metres of the cattle "
                    "shed and close to water. Keep it away from the house "
                    "foundation, from any well or drinking water source, and "
                    "in a place that gets sun."),
         "who": "farmer"},
        {"n": "2", "icon": "size", "stage": "Decide the size",
         "detail": ("Plant size follows how much dung you can feed every day, "
                    "not how much gas you would like. Around 25 kg of dung a "
                    "day supports about 1 cubic metre of plant."),
         "who": "farmer"},
        {"n": "3", "icon": "prepare", "stage": "Prepare the site",
         "detail": ("Mark and dig the pit, arrange sand, bricks and cement, "
                    "and make sure a vehicle can reach the spot to deliver "
                    "materials."),
         "who": "both"},
        {"n": "4", "icon": "build", "stage": "Build the digester",
         "detail": ("The underground tank where the dung breaks down. It must "
                    "be completely airtight — this is the part that decides "
                    "whether the plant works at all."),
         "who": "technician"},
        # Gas holder and the pipework are one visit by one technician, so
        # splitting them into two steps made the guide look longer than the
        # job actually is.
        {"n": "5", "icon": "gas", "stage": "Fit the gas holder and pipes",
         "detail": ("The dome or drum that stores the gas, plus the inlet "
                    "tank where you mix dung and water, the outlet for the "
                    "slurry, and the gas pipe to your kitchen. All of this is "
                    "safety work and is done in one visit."),
         "who": "technician"},
        {"n": "6", "icon": "feed", "stage": "Start feeding slowly",
         "detail": ("Begin with a smaller load and build up over two to three "
                    "weeks. Gas is usually weak at first and steadies after "
                    "three to six weeks."),
         "who": "farmer"},
        {"n": "7", "icon": "check", "stage": "Feed it every day",
         "detail": ("Feed a similar amount at the same time daily and collect "
                    "the slurry. Gas output drops in cold weather — that is "
                    "normal, not a fault."),
         "who": "farmer"},
    ]


@circular_router.get("/technicians")
def technicians(user: User = Depends(get_current_user),
                db: Session = Depends(get_db)):
    """Verified biogas installers near this farmer.

    Sizing advice with no route to installation is where most of these tools
    stop being useful, so this closes the loop from "a 3 m3 plant suits you"
    to someone who can actually build it.
    """
    farm = db.query(Farm).filter(Farm.user_id == user.id).first()
    q = (db.query(BiogasTechnician)
         .filter(BiogasTechnician.active == True,           # noqa: E712
                 BiogasTechnician.verified == True))        # noqa: E712

    rows = []
    if farm and farm.district:
        rows = q.filter(BiogasTechnician.district == farm.district).all()
    if not rows and farm and farm.state:
        rows = q.filter(BiogasTechnician.state == farm.state).limit(10).all()

    return {
        "count": len(rows),
        "searched": {"district": farm.district if farm else None,
                     "state": farm.state if farm else None},
        "technicians": [{
            "id": t.id, "name": t.name, "organisation": t.organisation,
            "phone": t.phone,
            "location": ", ".join(x for x in (t.village, t.district, t.state) if x),
            "services": t.services or [], "plant_types": t.plant_types or [],
            "size_range_m3": t.size_range_m3,
            "years_experience": t.years_experience,
            "notes": t.notes, "verified": t.verified,
        } for t in rows],
        "empty_note": (
            "No verified installer is listed for your area yet. Your local "
            "Krishi Vigyan Kendra or the district rural development office "
            "can usually point you to an approved one."),
        "safety_note": (
            "Digester construction and gas piping must be done by a trained "
            "technician. Gas under pressure is not work to improvise."),
    }


@circular_router.get("/biogas-scheme")
def biogas_scheme(user: User = Depends(get_current_user),
                  db: Session = Depends(get_db)):
    """Government support for installing a biogas plant.

    Deliberately does NOT hardcode a subsidy amount. Central assistance under
    the MNRE National Bioenergy Programme changes between financial years, and
    states add their own share on top. A stale figure quoted confidently is
    worse than sending the farmer to the live portal.
    """
    farm = db.query(Farm).filter(Farm.user_id == user.id).first()
    matching = (db.query(ExternalAdvisory)
                .filter(ExternalAdvisory.active == True,     # noqa: E712
                        ExternalAdvisory.kind == "scheme")
                .all())
    biogas_advisories = [
        {"id": a.id, "title": a.title, "summary": a.summary,
         "amount": a.amount, "amount_unit": a.amount_unit,
         "source": {"name": a.source_name, "url": a.source_url,
                    "published_on": (a.published_on.date().isoformat()
                                     if a.published_on else None)}}
        for a in matching
        if "biogas" in (a.title or "").lower()
        or "biogas" in (a.summary or "").lower()
    ]

    return {
        "programme": "MNRE National Bioenergy Programme — Biogas Programme",
        "covers": "Small biogas plants of 1 to 25 cubic metres per day.",
        "eligibility": [
            "You own the land or space for the plant "
            "(roughly 50-60 square metres).",
            "You have regular cattle dung or other feedstock available.",
            "You have a regular water supply.",
            "You can fund your own share of the cost.",
        ],
        "documents": [
            "Proof of identity (Aadhaar)",
            "Proof of land ownership or a no-objection letter",
            "Bank account details",
            "Passport photograph",
        ],
        "how_to_apply": [
            "Apply through the MNRE biogas portal or its mobile app.",
            "Your application goes to the state implementing agency.",
            "They inspect the site before approving.",
            "Assistance is released after the plant is built and "
            "commissioned.",
        ],
        "official_portal": "https://biogas.mnre.gov.in/",
        # No amount is stated here on purpose.
        "amount_note": (
            "Central assistance depends on plant size and is revised between "
            "financial years, and many states add their own share. Check the "
            "current figure on the official portal rather than relying on any "
            "amount quoted elsewhere. Registered gaushalas and SC/ST "
            "applicants may receive an additional incentive."),
        "recorded_advisories": biogas_advisories,
        "disclaimer": (
            "Scheme information changes. Always confirm eligibility and the "
            "current assistance amount on the official portal or with your "
            "block agriculture office before applying."),
    }


# =====================================================================
# Manure branch  (spec 7-10)
# =====================================================================

@circular_router.get("/manure/plan")
def manure_plan(has_shade: Optional[bool] = None, labour: Optional[str] = None,
                urgent: Optional[bool] = None,
                user: User = Depends(get_current_user),
                db: Session = Depends(get_db)):
    """A complete composting plan built from what this farm already has.

    Reuses the livestock and crop already on record — the farmer is only asked
    the three things we cannot infer: whether they have shade, how much labour
    they can spare, and whether they need it quickly.

    Those three answers default to whatever the farmer said last time, so
    reopening the page returns the plan they already have instead of asking
    again. Passing any of them explicitly both overrides and updates the
    remembered answer.
    """
    saved = _choice_row(db, user)
    biogas = _biogas_status(db, user)
    if has_shade is None:
        has_shade = bool(saved.has_shade) if saved.has_shade is not None else True
    else:
        saved.has_shade = has_shade
    if labour is None:
        labour = saved.labour or "normal"
    else:
        saved.labour = labour if labour in ("low", "normal") else "normal"
    if urgent is None:
        urgent = bool(saved.urgent)
    else:
        saved.urgent = urgent
    db.commit()

    farm = db.query(Farm).filter(Farm.user_id == user.id).first()
    herd = _herd(db, user)
    dung = bg.dung_from_livestock(herd)
    dung_mid = dung["total_kg_per_day"]["mid"]

    residue = _residue_available(farm)
    residue_kg = ((residue.get("residue_kg", {}) or {}).get("mid", 0.0)
                  if residue.get("available") else 0.0)

    choice = mn.choose_method(dung_kg_per_day=dung_mid, residue_kg=residue_kg,
                              has_shade=has_shade, labour=labour,
                              urgent=urgent)

    # One month of dung plus whatever residue is on hand is a realistic batch.
    batch_kg = dung_mid * 30 + min(residue_kg, dung_mid * 30)
    materials = mn.materials_for(choice["recommended"], batch_kg)
    output = mn.estimate_output(batch_kg, choice["recommended"])

    crop = (farm.crop if farm else "") or ""
    area = (farm.crop_area_acres or farm.land_size_acres) if farm else None
    soil_row = (db.query(SoilTest).filter(SoilTest.user_id == user.id)
                .order_by(SoilTest.created_at.desc()).first())
    soil = ({"nitrogen": soil_row.nitrogen, "ph": soil_row.ph}
            if soil_row else None)

    produced = (output.get("output_kg", {}) or {}).get("low") if output.get("available") else None
    method_key = choice["recommended"]

    # A registered digester is ALREADY making manure. Its slurry counts
    # towards what this farm has to apply and to sell, so a farmer who built
    # a plant is not shown a composting figure that ignores it.
    digestate_month = biogas.get("digestate_kg_per_month") or 0
    compost_only_kg = produced
    if produced is not None and digestate_month:
        produced = round(produced + digestate_month)
    elif produced is None and digestate_month:
        produced = digestate_month

    # How much FINISHED compost this crop wants. Deliberately not
    # recommend_for_crop() — that returns a fresh-digestate slurry rate, and
    # compost is several times more concentrated. Using the slurry figure here
    # was what produced "your farm needs 1,300,000 kg" beside "you will make
    # 1,700 kg", which reads as a broken calculator rather than a plan.
    crop_use = mn.compost_need(crop=crop, area_acres=area, method=method_key,
                               produced_kg=produced, soil=soil)

    need_mid = ((crop_use.get("total_needed_kg") or {}).get("mid")
                if crop_use.get("available") and crop_use.get("unit") == "kg"
                else None)

    # What the farmer chose to hold back, if they have said. Until they do,
    # the sensible default is "as much as your own fields can actually use",
    # capped at what will be made — not the whole batch, or nothing.
    keep = saved.keep_kg
    default_keep = None
    if produced is not None:
        default_keep = round(min(produced, need_mid)) if need_mid else produced
    effective_keep = keep if keep is not None else default_keep
    if effective_keep is not None and produced is not None:
        effective_keep = max(0, min(effective_keep, produced))

    balance = None
    if produced is not None and effective_keep is not None:
        balance = max(0, round(produced - effective_keep))

    price = mn.suggest_price(method_key, balance)

    return {
        "has_livestock": bool(herd),
        # Read by the UI to decide whether to offer registration or to say
        # the plant is already on record. Never asked twice.
        "biogas": biogas,
        "inputs": {
            "dung_kg_per_day": dung["total_kg_per_day"],
            "residue_kg": residue_kg,
            "batch_kg": round(batch_kg),
            "answered": {"has_shade": has_shade, "labour": labour,
                         "urgent": urgent},
        },
        "method": choice,
        "materials": materials,
        "output": output,
        # Where the manure actually comes from, so the two sources are never
        # silently added into one unexplained number.
        "sources": {
            "compost_kg": compost_only_kg,
            "digestate_kg": digestate_month or None,
            "total_kg": produced,
            "from_biogas": bool(digestate_month),
        },
        "farm_use": {
            "crop": crop or None,
            "area_acres": area,
            "needed_kg": need_mid,
            "rate_kg_per_acre": crop_use.get("rate_kg_per_acre"),
            "acres_covered": crop_use.get("acres_covered"),
            "produced_kg": produced,
            # What the farmer decided to keep, and what that leaves to sell.
            "keep_kg": effective_keep,
            "keep_is_default": keep is None,
            "default_keep_kg": default_keep,
            "balance_kg": balance,
            # Kept under the old name so nothing else that reads this
            # endpoint breaks; it is the same quantity.
            "surplus_kg": balance,
            "covers_whole_farm": bool(crop_use.get("covers_whole_farm")),
            "recommendation": crop_use,
        },
        "sell": {
            "quantity_kg": balance,
            "can_sell": bool(balance),
            "product_label": price["product_label"],
            "suggested_name": price["product_label"],
            "price": price,
        },
        "disclaimer": DISCLAIMER,
    }


@circular_router.post("/manure/keep")
def set_manure_keep(data: ChoiceIn, user: User = Depends(get_current_user),
                    db: Session = Depends(get_db)):
    """Record how much finished compost the farmer keeps for their own fields.

    Everything above it is what the sell flow offers, so this is the single
    number that decides whether there is a listing to make at all.
    """
    if data.keep_kg is None:
        raise HTTPException(400, "keep_kg is required")
    row = _choice_row(db, user)
    row.keep_kg = max(0.0, float(data.keep_kg))
    db.commit()
    return manure_plan(user=user, db=db)


# =====================================================================
# Existing plant  (spec 6)
# =====================================================================

class PlantIn(BaseModel):
    size_m3: Optional[float] = Field(None, ge=0)
    plant_type: str = ""
    monitoring_mode: str = "manual"      # manual | sensor
    device_id: str = ""


class LogIn(BaseModel):
    feed_kg: Optional[float] = Field(None, ge=0)
    water_litres: Optional[float] = Field(None, ge=0)
    slurry_out_kg: Optional[float] = Field(None, ge=0)
    gas_level: str = ""                  # good | low | none
    flame_quality: str = ""              # strong | weak | none
    smell: str = ""                      # normal | sour | rotten
    temperature_c: Optional[float] = None
    pressure_cm: Optional[float] = None
    ph: Optional[float] = None
    gas_m3: Optional[float] = None
    note: str = ""


@circular_router.get("/plant")
def my_plant(user: User = Depends(get_current_user),
             db: Session = Depends(get_db)):
    """The farmer's existing plant, its recent logs, and a plain-words status."""
    plant = (db.query(BiogasPlant)
             .filter(BiogasPlant.user_id == user.id,
                     BiogasPlant.active == True).first())      # noqa: E712
    if plant is None:
        return {"has_plant": False,
                "message": "No biogas plant is registered yet."}

    rows = (db.query(BiogasLog)
            .filter(BiogasLog.plant_id == plant.id)
            .order_by(BiogasLog.logged_on.desc()).limit(30).all())
    logs = [{"logged_on": r.logged_on, "feed_kg": r.feed_kg,
             "slurry_out_kg": r.slurry_out_kg, "gas_level": r.gas_level,
             "flame_quality": r.flame_quality, "smell": r.smell,
             "temperature_c": r.temperature_c, "pressure_cm": r.pressure_cm,
             "ph": r.ph, "gas_m3": r.gas_m3, "source": r.source,
             "note": r.note} for r in rows]

    return {
        "has_plant": True,
        "plant": {"id": plant.id, "size_m3": plant.size_m3,
                  "plant_type": plant.plant_type,
                  "monitoring_mode": plant.monitoring_mode,
                  "device_id": plant.device_id},
        "status": bg.plant_status(logs, plant.size_m3),
        "logs": logs[:14],
        "logged_today": bool(rows and rows[0].logged_on ==
                             datetime.utcnow().date().isoformat()),
        "disclaimer": DISCLAIMER,
    }


@circular_router.post("/plant")
def register_plant(data: PlantIn, user: User = Depends(get_current_user),
                   db: Session = Depends(get_db)):
    """Register or update THE farmer's plant. Never creates a second one.

    A farmer can reach this from the biogas branch and again from the manure
    branch. Both must land on the same row: two BiogasPlant records for one
    user would split the logs between them, and the status panel would then
    report on whichever happened to be found first.
    """
    rows = (db.query(BiogasPlant)
            .filter(BiogasPlant.user_id == user.id)
            .order_by(BiogasPlant.id.asc()).all())

    if rows:
        plant = rows[0]
        # Anything beyond the first is a duplicate from before this endpoint
        # was idempotent. Deactivate rather than delete, so no logs are lost.
        for extra in rows[1:]:
            extra.active = False
    else:
        plant = BiogasPlant(user_id=user.id)
        db.add(plant)

    # Only overwrite what was actually supplied. Re-opening the form and
    # saving with a blank size must not erase a size already on record.
    if data.size_m3 is not None:
        plant.size_m3 = data.size_m3
    if data.plant_type:
        plant.plant_type = data.plant_type
    if data.monitoring_mode in ("manual", "sensor"):
        plant.monitoring_mode = data.monitoring_mode
    elif not plant.monitoring_mode:
        plant.monitoring_mode = "manual"
    if data.device_id:
        plant.device_id = data.device_id
    plant.active = True

    # Registering a plant is itself a decision about the farm, so record it —
    # otherwise the entry screen still shows "I already have a plant" as an
    # unanswered question next visit.
    choice = _choice_row(db, user)
    if not choice.mode:
        choice.mode = "plant"

    db.commit()
    return my_plant(user, db)


@circular_router.post("/plant/log")
def add_log(data: LogIn, user: User = Depends(get_current_user),
            db: Session = Depends(get_db)):
    """Record today's reading. One entry per day, updated if repeated."""
    plant = (db.query(BiogasPlant)
             .filter(BiogasPlant.user_id == user.id,
                     BiogasPlant.active == True).first())      # noqa: E712
    if plant is None:
        raise HTTPException(400, "Register your biogas plant first.")

    today = datetime.utcnow().date().isoformat()
    row = (db.query(BiogasLog)
           .filter(BiogasLog.plant_id == plant.id,
                   BiogasLog.logged_on == today).first())
    if row is None:
        row = BiogasLog(plant_id=plant.id, user_id=user.id, logged_on=today)
        db.add(row)

    for field in ("feed_kg", "water_litres", "slurry_out_kg", "gas_level",
                  "flame_quality", "smell", "temperature_c", "pressure_cm",
                  "ph", "gas_m3", "note"):
        value = getattr(data, field)
        if value not in (None, ""):
            setattr(row, field, value)
    row.source = "sensor" if data.gas_m3 is not None else "manual"
    db.commit()
    return my_plant(user, db)
