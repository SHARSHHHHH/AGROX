"""Machinery rental marketplace API."""

import logging
import os
import uuid
from typing import Optional

import aiofiles
from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from sqlalchemy.orm import Session

from app.core.security import get_current_user
from app.database.db import get_db
from app.ml import machinery_knowledge as kb
from app.models.models import Farm, MachineryListing, User
from app.services import geocode as geocode_svc
from app.services import machinery as svc

log = logging.getLogger("agri.api.machinery")

router = APIRouter(prefix="/api/machinery", tags=["machinery"])

UPLOAD_DIR = "uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)
ALLOWED_EXT = {".jpg", ".jpeg", ".png", ".webp"}
MAX_BYTES = 8 * 1024 * 1024


# ---------------------------------------------------------------- knowledge

@router.get("/catalog")
def catalog():
    """Every machine we know about, for the picker and the guide tab."""
    return {
        "machines": kb.list_machines(),
        "categories": kb.CATEGORIES,
        "stages": kb.STAGE_LABELS,
        "stage_order": kb.STAGE_ORDER,
    }


@router.get("/guide")
def guide(crop: str = "", land_size_acres: Optional[float] = None,
          stage: str = "", use_my_farm: bool = True,
          user: User = Depends(get_current_user),
          db: Session = Depends(get_db)):
    """Which machinery this farm actually needs, and why.

    Falls back to the farmer's stored profile so the guide is personalised
    without asking the same questions twice.
    """
    if use_my_farm and (not crop or land_size_acres is None):
        farm = db.query(Farm).filter(Farm.user_id == user.id).first()
        if farm:
            crop = crop or farm.crop or ""
            if land_size_acres is None:
                land_size_acres = farm.land_size_acres

    return kb.recommend_for_farm(crop=crop, land_size_acres=land_size_acres,
                                 stage=stage)


@router.get("/states")
def states():
    """All Indian states and UTs, for the location filter."""
    return {"states": geocode_svc.list_states(),
            "mp_districts": sorted(d[0] for d in geocode_svc.MP_DISTRICTS)}


# ---------------------------------------------------------------- browse

@router.get("/search")
def search(machine_key: str = "", state: str = "", district: str = "",
           category: str = "", max_rate: Optional[float] = None,
           lat: Optional[float] = None, lon: Optional[float] = None,
           radius_km: Optional[float] = Query(None, ge=1, le=2000),
           sort: str = "distance", limit: int = Query(60, ge=1, le=200),
           user: User = Depends(get_current_user),
           db: Session = Depends(get_db)):
    """Browse machines available to rent, nearest first when location is given."""
    return svc.search(db, machine_key=machine_key, state=state,
                      district=district, category=category, max_rate=max_rate,
                      lat=lat, lon=lon, radius_km=radius_km, sort=sort,
                      limit=limit)


@router.get("/nearby")
async def nearby(lat: float, lon: float,
                 radius_km: float = Query(100, ge=1, le=2000),
                 machine_key: str = "",
                 user: User = Depends(get_current_user),
                 db: Session = Depends(get_db)):
    """Everything within a radius, plus the resolved place name.

    Saves the frontend a second round trip after it gets GPS coordinates.
    """
    place = await geocode_svc.reverse_geocode(lat, lon)
    result = svc.search(db, lat=lat, lon=lon, radius_km=radius_km,
                        machine_key=machine_key, sort="distance")
    result["location"] = place
    return result


@router.get("/listing/{listing_id}")
def listing_detail(listing_id: int, user: User = Depends(get_current_user),
                   db: Session = Depends(get_db)):
    row = db.query(MachineryListing).filter(
        MachineryListing.id == listing_id).first()
    if row is None:
        raise HTTPException(404, "Listing not found")
    svc.record_view(db, listing_id)
    return svc.to_public(row)


@router.post("/listing/{listing_id}/contact")
def contact(listing_id: int, user: User = Depends(get_current_user),
            db: Session = Depends(get_db)):
    """Release the owner's phone number.

    Deliberately a separate authenticated POST rather than a field in the
    browse response, so numbers cannot be scraped in bulk from a listing page.
    """
    result = svc.reveal_contact(db, listing_id)
    if not result.get("ok"):
        raise HTTPException(404, result.get("message", "Listing not found"))
    return result


# ---------------------------------------------------------------- give for rent

@router.post("/listing")
async def create_listing(
    machine_key: str = Form(...),
    daily_rate: float = Form(...),
    contact_phone: str = Form(...),
    state: str = Form(...),
    title: str = Form(""),
    brand: str = Form(""),
    model_year: Optional[int] = Form(None),
    description: str = Form(""),
    condition: str = Form("good"),
    hourly_rate: Optional[float] = Form(None),
    fuel_included: bool = Form(False),
    operator_included: bool = Form(False),
    min_days: int = Form(1),
    owner_name: str = Form(""),
    district: str = Form(""),
    village: str = Form(""),
    latitude: Optional[float] = Form(None),
    longitude: Optional[float] = Form(None),
    photo: UploadFile = File(None),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """List a machine for others to rent."""

    image_path = ""
    if photo is not None and photo.filename:
        ext = os.path.splitext(photo.filename)[1].lower() or ".jpg"
        if ext not in ALLOWED_EXT:
            raise HTTPException(400, f"Unsupported image type: {ext}")
        data = await photo.read()
        if len(data) > MAX_BYTES:
            raise HTTPException(400, "Photo exceeds the 8 MB limit")
        name = f"machinery_{uuid.uuid4().hex}{ext}"
        async with aiofiles.open(os.path.join(UPLOAD_DIR, name), "wb") as f:
            await f.write(data)
        image_path = f"/uploads/{name}"

    payload = {
        "machine_key": machine_key, "daily_rate": daily_rate,
        "contact_phone": contact_phone, "state": state, "title": title,
        "brand": brand, "model_year": model_year, "description": description,
        "condition": condition, "hourly_rate": hourly_rate,
        "fuel_included": fuel_included, "operator_included": operator_included,
        "min_days": min_days, "owner_name": owner_name, "district": district,
        "village": village, "latitude": latitude, "longitude": longitude,
    }

    result = svc.create_listing(db, user, payload, image_path=image_path)
    if not result.get("ok"):
        # 422 with the specific problems, so the form can highlight fields
        # rather than showing a generic failure.
        raise HTTPException(422, {"errors": result["errors"]})
    return result


@router.get("/my-listings")
def my_listings(user: User = Depends(get_current_user),
                db: Session = Depends(get_db)):
    rows = (db.query(MachineryListing)
            .filter(MachineryListing.owner_id == user.id)
            .order_by(MachineryListing.created_at.desc()).all())
    return {
        "count": len(rows),
        "items": [{**svc.to_public(r),
                   # Owners see their own full number.
                   "contact_phone": r.contact_phone,
                   "contact_requests": r.contact_requests} for r in rows],
    }


@router.patch("/listing/{listing_id}/availability")
def set_availability(listing_id: int, available: bool,
                     user: User = Depends(get_current_user),
                     db: Session = Depends(get_db)):
    row = db.query(MachineryListing).filter(
        MachineryListing.id == listing_id).first()
    if row is None:
        raise HTTPException(404, "Listing not found")
    if row.owner_id != user.id:
        raise HTTPException(403, "You can only change your own listings")
    row.available = available
    db.commit()
    return {"ok": True, "id": listing_id, "available": available}


@router.delete("/listing/{listing_id}")
def delete_listing(listing_id: int, user: User = Depends(get_current_user),
                   db: Session = Depends(get_db)):
    row = db.query(MachineryListing).filter(
        MachineryListing.id == listing_id).first()
    if row is None:
        raise HTTPException(404, "Listing not found")
    if row.owner_id != user.id:
        raise HTTPException(403, "You can only delete your own listings")
    db.delete(row)
    db.commit()
    return {"ok": True, "deleted": listing_id}


# =====================================================================
# Type-first browsing
# =====================================================================
# The browse grid used to show individual LISTINGS — every card carrying a
# price and a "Get contact number" button. That put the commercial detail of
# one stranger's tractor in front of a farmer who had not yet decided what
# kind of machine they needed, and it made the page a wall of near-identical
# green cards.
#
# These two endpoints split that into the natural two steps:
#   /types            what kinds of machine exist, and are any available
#   /type/{key}       photos, guidance, and every offer for THAT machine
#
# Price and contact details now live only on the second screen, where the
# farmer has actually chosen a machine.

@router.get("/types")
def machine_types(state: str = "", district: str = "",
                  user: User = Depends(get_current_user),
                  db: Session = Depends(get_db)):
    """Every machine type, with how many are on offer. No prices, no contacts.

    The optional state/district filter makes the counts reflect what the
    farmer can actually hire near them, so a type showing "3 available"
    means three in their area rather than three somewhere in the country.
    """
    from app.services import machinery_photos as photos
    from app.services.machinery import MACHINERY_KB

    listings = svc.search(db, state=state, district=district, limit=500)
    items = listings.get("items", []) if isinstance(listings, dict) else []

    counts: dict = {}
    states_for: dict = {}
    for it in items:
        key = it.get("machine_key") or ""
        if not key:
            continue
        counts[key] = counts.get(key, 0) + 1
        if it.get("state"):
            states_for.setdefault(key, set()).add(it["state"])

    out = []
    for key, spec in MACHINERY_KB.items():
        gallery = photos.photos_for(key)
        out.append({
            "machine_key": key,
            "name": spec["name"],
            "category": spec.get("category", ""),
            "stage": spec.get("stage", ""),
            "icon": spec.get("icon", key),
            "what_it_does": spec.get("what_it_does", ""),
            "suits_land": spec.get("suits_land", ""),
            # Cover image only. Deliberately no rate: the browse page is for
            # choosing a machine type, not comparing offers.
            "cover_photo": gallery[0] if gallery else None,
            "photo_count": len(gallery),
            "available_count": counts.get(key, 0),
            "states": sorted(states_for.get(key, [])),
        })

    out.sort(key=lambda x: (-x["available_count"], x["name"]))
    return {
        "types": out,
        "filtered_by": {"state": state or None, "district": district or None},
        "total_listings": len(items),
        "note": ("Counts reflect machines currently offered for rent. A type "
                 "with none listed is still shown, so you can see what exists "
                 "and ask for it."),
    }


@router.get("/type/{machine_key}")
def machine_type_detail(machine_key: str, state: str = "", district: str = "",
                        max_rate: Optional[float] = None,
                        lat: Optional[float] = None,
                        lon: Optional[float] = None,
                        sort: str = "price",
                        user: User = Depends(get_current_user),
                        db: Session = Depends(get_db)):
    """Photos, guidance, and every offer for ONE machine type.

    This is where prices and owner details belong — the farmer has chosen a
    machine and is now comparing what is on offer for it.
    """
    from app.services import machinery_photos as photos
    from app.services.machinery import MACHINERY_KB

    spec = MACHINERY_KB.get(machine_key)
    if not spec:
        raise HTTPException(
            status_code=404,
            detail=f"Unknown machine type '{machine_key}'.")

    results = svc.search(db, machine_key=machine_key, state=state,
                         district=district, max_rate=max_rate,
                         lat=lat, lon=lon, sort=sort, limit=200)
    offers = results.get("items", []) if isinstance(results, dict) else []

    rates = [o["daily_rate"] for o in offers
             if isinstance(o.get("daily_rate"), (int, float))]

    return {
        "machine_key": machine_key,
        "name": spec["name"],
        "category": spec.get("category", ""),
        "stage": spec.get("stage", ""),
        "icon": spec.get("icon", machine_key),
        "what_it_does": spec.get("what_it_does", ""),
        "when_needed": spec.get("when_needed", ""),
        "suits_land": spec.get("suits_land", ""),
        "typical_daily_rate": spec.get("typical_daily_rate"),
        "unit": spec.get("unit", ""),
        "crops": spec.get("crops", []),
        "tip": spec.get("tip", ""),
        # Representative photos of this machine type, plus whatever owners
        # uploaded for their own listing (shown on each offer card).
        "photos": photos.photos_for(machine_key),
        "offers": offers,
        "offer_count": len(offers),
        "price_range": ({"min": min(rates), "max": max(rates)}
                        if rates else None),
        "filtered_by": {"state": state or None, "district": district or None,
                        "max_rate": max_rate},
        "note": ("Rates are what each owner asks. Always confirm whether "
                 "diesel and a driver are included before agreeing."),
    }


@router.get("/photo-coverage")
def photo_coverage(user: User = Depends(get_current_user)):
    """Which machine types still need photographs, and where to put them."""
    from app.services import machinery_photos as photos
    return photos.coverage()
