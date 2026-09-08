"""Direct farmer-to-buyer produce marketplace API.

Sell flow (farmer): sow date -> predicted maturity date (computed, not
typed) -> "do you plan to sell this?" -> quantity + price -> listed.

Buy flow (buyer): browse available listings -> express interest -> farmer
confirms or declines -> contact details are released once confirmed.
"""

import os
import uuid
from datetime import datetime
from typing import Optional

import aiofiles
from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File
from sqlalchemy.orm import Session

from app.core.security import get_current_user
from app.database.db import get_db
from app.models.models import CropListing, Farm, ProduceOrder, User
from app.schemas.schemas import (CropListingIn, FertilizerListingIn,
                                 MaturityPredictIn, OrderRespondIn,
                                 ProduceOrderIn)
from app.services import manure as mn
from app.services import marketplace as svc
from app.services.machinery import normalise_phone
from app.services.lifecycle import supported_crops

router = APIRouter(prefix="/api/marketplace", tags=["marketplace"])
UPLOAD_DIR = "uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)


def _parse_date(s: Optional[str]) -> Optional[datetime]:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s)
    except ValueError:
        raise HTTPException(400, "Dates must be ISO format yyyy-mm-dd")


@router.get("/crops")
def crops_with_prediction():
    """Which crops we can predict a maturity date for, vs which need the
    farmer's own estimate."""
    return {"predictable": supported_crops()}


@router.get("/crops-available")
def crops_available(product_type: str = "produce", db: Session = Depends(get_db)):
    """Distinct crops with at least one active listing, and how many —
    powers the buyer's crop-icon grid. Only crops with real listings show
    up; nothing is padded in to fill the grid.

    Filtered by product type so a sack of vermicompost never appears in the
    grid of crops a buyer can order. Pass product_type=fertilizer for the
    compost grid instead.
    """
    q = (db.query(CropListing.crop, CropListing.product_name)
         .filter(CropListing.intends_to_sell == True,      # noqa: E712
                 CropListing.status.in_(("growing", "available"))))
    # Rows created before product_type existed are produce, and a NULL from
    # an in-place column addition must not hide them.
    if product_type == "fertilizer":
        q = q.filter(CropListing.product_type == "fertilizer")
    else:
        q = q.filter((CropListing.product_type == "produce")
                     | (CropListing.product_type.is_(None)))

    counts: dict[str, int] = {}
    for crop, _name in q.all():
        if crop:
            counts[crop] = counts.get(crop, 0) + 1
    return sorted([{"crop": c, "listings": n, "product_type": product_type}
                   for c, n in counts.items()],
                  key=lambda r: -r["listings"])


@router.post("/predict-maturity")
def predict_maturity(data: MaturityPredictIn):
    sowing = _parse_date(data.sowing_date)
    if sowing is None:
        raise HTTPException(400, "sowing_date is required")
    return svc.predict_maturity(data.crop, sowing)


# ---------------------------------------------------------------- farmer side

@router.post("/listings")
def create_listing(data: CropListingIn, user: User = Depends(get_current_user),
                   db: Session = Depends(get_db)):
    if user.role not in ("farmer", "balcony"):
        raise HTTPException(403, "Only farmers can list produce for sale")

    sowing = _parse_date(data.sowing_date)
    farmer_override = _parse_date(data.maturity_date)

    predicted, source = None, ""
    if farmer_override:
        predicted, source = farmer_override, "farmer"
    elif sowing:
        pred = svc.predict_maturity(data.crop, sowing)
        if pred["supported"]:
            predicted = datetime.fromisoformat(pred["predicted_maturity_date"])
            source = "lifecycle"

    if data.intends_to_sell and not farmer_override and not predicted:
        raise HTTPException(
            400, "We don't have lifecycle data for this crop yet — please "
                 "enter your own expected harvest date (maturity_date).")

    phone = ""
    if data.intends_to_sell:
        phone = normalise_phone(data.contact_phone) or ""
        if not phone:
            raise HTTPException(
                400, "Enter a valid 10-digit Indian mobile number so buyers can reach you.")

    farm = db.query(Farm).filter(Farm.user_id == user.id).first()

    listing = CropListing(
        farmer_id=user.id, crop=data.crop, variety=data.variety,
        sowing_date=sowing, predicted_maturity_date=predicted,
        maturity_source=source,
        intends_to_sell=data.intends_to_sell,
        quantity_kg=data.quantity_kg, price_per_kg=data.price_per_kg,
        state=(farm.state if farm else user.state) or "",
        district=(farm.district if farm else user.district) or "",
        village=farm.village if farm else "",
        farmer_name=user.name, contact_phone=phone,
    )
    listing.status = svc.compute_status(listing)
    db.add(listing); db.commit(); db.refresh(listing)
    return svc.to_public(listing)


# ------------------------------------------------- fertiliser / compost side
#
# A farmer who composts their dung ends up with something saleable that is
# not produce. It goes through this same table so they have one place to
# manage everything they have offered and buyers have one place to look —
# but with product_type set, because a sack of vermicompost and a crop of
# tomatoes are not the same thing and must not be searched as if they were.

@router.get("/fertilizer/price-suggestion")
def fertilizer_price(method: str = "compost", quantity_kg: Optional[float] = None):
    """An indicative asking price, so a farmer pricing compost for the first
    time is not guessing in the dark. Explicitly a band, not a quote."""
    return mn.suggest_price(method, quantity_kg)


@router.post("/listings/fertilizer")
def create_fertilizer_listing(data: FertilizerListingIn,
                              user: User = Depends(get_current_user),
                              db: Session = Depends(get_db)):
    """List surplus compost, vermicompost, FYM or slurry for sale.

    Unlike produce there is no sowing date to predict from: the farmer either
    has it now or knows roughly when the heap will be ready, so we take that
    date directly rather than inventing one.
    """
    if user.role not in ("farmer", "balcony"):
        raise HTTPException(403, "Only farmers can list fertiliser for sale")

    name = (data.product_name or "").strip()
    if not name:
        raise HTTPException(400, "Give your fertiliser a name buyers will recognise.")
    if not data.quantity_kg or data.quantity_kg <= 0:
        raise HTTPException(400, "Enter how many kg you have to sell.")
    if data.price_per_kg is None or data.price_per_kg <= 0:
        raise HTTPException(400, "Enter the price you want per kg.")

    phone = normalise_phone(data.contact_phone) or ""
    if not phone:
        raise HTTPException(
            400, "Enter a valid 10-digit Indian mobile number so buyers can reach you.")

    ready = _parse_date(data.ready_date)
    farm = db.query(Farm).filter(Farm.user_id == user.id).first()

    listing = CropListing(
        farmer_id=user.id,
        product_type="fertilizer",
        product_name=name,
        source=data.source or "",
        # `crop` carries the method key (compost / vermicompost / fym /
        # liquid) so the buyer's grid can group by material type using the
        # machinery it already has for grouping by crop.
        crop=(data.method or "compost").strip().lower(),
        variety=data.variety,
        predicted_maturity_date=ready,
        maturity_source="farmer" if ready else "",
        intends_to_sell=True,
        quantity_kg=data.quantity_kg,
        price_per_kg=data.price_per_kg,
        state=(farm.state if farm else user.state) or "",
        district=(farm.district if farm else user.district) or "",
        village=farm.village if farm else "",
        farmer_name=user.name, contact_phone=phone,
    )
    listing.status = svc.compute_status(listing)
    db.add(listing); db.commit(); db.refresh(listing)
    return svc.to_public(listing)


@router.post("/listings/{listing_id}/photo")
async def upload_listing_photo(listing_id: int, file: UploadFile = File(...),
                               user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """The farmer's own photo of their produce — shown to buyers browsing
    that crop. Optional; a listing with none simply shows a generic crop
    icon instead of a broken image."""
    listing = (db.query(CropListing)
               .filter(CropListing.id == listing_id, CropListing.farmer_id == user.id).first())
    if not listing:
        raise HTTPException(404, "Listing not found")

    ext = os.path.splitext(file.filename or "")[1].lower()
    if ext not in (".jpg", ".jpeg", ".png", ".webp"):
        raise HTTPException(400, "Please upload a JPG, PNG or WEBP image.")
    path = os.path.join(UPLOAD_DIR, f"listing_{uuid.uuid4().hex}{ext}")
    async with aiofiles.open(path, "wb") as f:
        await f.write(await file.read())

    listing.image_path = path
    db.commit()
    return svc.to_public(listing)


@router.patch("/listings/{listing_id}")
def update_listing(listing_id: int, data: CropListingIn,
                   user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    listing = (db.query(CropListing)
               .filter(CropListing.id == listing_id, CropListing.farmer_id == user.id).first())
    if not listing:
        raise HTTPException(404, "Listing not found")

    sowing = _parse_date(data.sowing_date) or listing.sowing_date
    farmer_override = _parse_date(data.maturity_date)
    if farmer_override:
        listing.predicted_maturity_date = farmer_override
        listing.maturity_source = "farmer"
    elif sowing and sowing != listing.sowing_date:
        pred = svc.predict_maturity(data.crop or listing.crop, sowing)
        if pred["supported"]:
            listing.predicted_maturity_date = datetime.fromisoformat(pred["predicted_maturity_date"])
            listing.maturity_source = "lifecycle"

    listing.crop = data.crop or listing.crop
    listing.variety = data.variety or listing.variety
    listing.sowing_date = sowing
    listing.intends_to_sell = data.intends_to_sell
    if data.quantity_kg is not None:
        listing.quantity_kg = data.quantity_kg
    if data.price_per_kg is not None:
        listing.price_per_kg = data.price_per_kg
    if data.contact_phone:
        phone = normalise_phone(data.contact_phone)
        if phone:
            listing.contact_phone = phone

    listing.status = svc.compute_status(listing)
    db.commit(); db.refresh(listing)
    return svc.to_public(listing)


@router.delete("/listings/{listing_id}")
def withdraw_listing(listing_id: int, user: User = Depends(get_current_user),
                     db: Session = Depends(get_db)):
    listing = (db.query(CropListing)
               .filter(CropListing.id == listing_id, CropListing.farmer_id == user.id).first())
    if not listing:
        raise HTTPException(404, "Listing not found")
    listing.status = "withdrawn"
    db.commit()
    return {"status": "ok"}


@router.get("/listings/mine")
def my_listings(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    rows = (db.query(CropListing).filter(CropListing.farmer_id == user.id)
            .order_by(CropListing.created_at.desc()).all())
    out = []
    for r in rows:
        r.status = svc.compute_status(r)
        item = svc.to_public(r)
        item["contact_phone"] = r.contact_phone   # it's their own listing
        out.append(item)
    db.commit()
    return out


# ---------------------------------------------------------------- buyer side

@router.get("/listings")
def browse_listings(crop: str = "", state: str = "", district: str = "",
                    max_price: Optional[float] = None,
                    product_type: str = "produce",
                    user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    q = db.query(CropListing).filter(CropListing.intends_to_sell == True,  # noqa: E712
                                     CropListing.status.in_(("growing", "available")))
    # Produce and fertiliser are browsed separately. Listings predating the
    # column are produce, and are matched on NULL as well as on the default.
    if product_type == "fertilizer":
        q = q.filter(CropListing.product_type == "fertilizer")
    else:
        q = q.filter((CropListing.product_type == "produce")
                     | (CropListing.product_type.is_(None)))
    if crop:
        q = q.filter(CropListing.crop.ilike(f"%{crop}%"))
    if state:
        q = q.filter(CropListing.state == state)
    if district:
        q = q.filter(CropListing.district == district)
    if max_price is not None:
        q = q.filter(CropListing.price_per_kg <= max_price)

    rows = q.order_by(CropListing.created_at.desc()).limit(100).all()
    changed = False
    for r in rows:
        new_status = svc.compute_status(r)
        if new_status != r.status:
            r.status = new_status
            changed = True
    if changed:
        db.commit()
    return [svc.to_public(r) for r in rows]


@router.post("/listings/{listing_id}/contact")
def reveal_contact(listing_id: int, user: User = Depends(get_current_user),
                   db: Session = Depends(get_db)):
    """Release the farmer's phone number to an authenticated buyer.

    Deliberately a separate POST rather than a field in the browse
    response, so numbers cannot be scraped in bulk.
    """
    listing = db.query(CropListing).filter(CropListing.id == listing_id).first()
    if not listing:
        raise HTTPException(404, "Listing not found")
    listing.views = (listing.views or 0) + 1
    db.commit()
    return {
        "farmer_name": listing.farmer_name,
        "contact_phone": listing.contact_phone,
        "crop": listing.crop,
        "price_per_kg": listing.price_per_kg,
        "safety_note": ("Agree the price, quantity and pickup/delivery details "
                        "directly with the farmer BEFORE any payment. This "
                        "platform lists what farmers submit and does not "
                        "verify produce, quality or delivery."),
    }


@router.post("/listings/{listing_id}/interest")
def express_interest(listing_id: int, data: ProduceOrderIn,
                     user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    listing = db.query(CropListing).filter(CropListing.id == listing_id).first()
    if not listing:
        raise HTTPException(404, "Listing not found")
    if listing.status in ("sold", "withdrawn"):
        raise HTTPException(400, "This listing is no longer available")

    order = ProduceOrder(listing_id=listing_id, buyer_id=user.id,
                         quantity_kg=data.quantity_kg, message=data.message)
    db.add(order); db.commit(); db.refresh(order)
    return {"id": order.id, "status": order.status}


@router.get("/orders/mine")
def my_orders(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """A buyer's own requests, with the listing they were made against."""
    rows = (db.query(ProduceOrder).filter(ProduceOrder.buyer_id == user.id)
            .order_by(ProduceOrder.created_at.desc()).all())
    out = []
    for o in rows:
        item = {"id": o.id, "status": o.status, "quantity_kg": o.quantity_kg,
                "message": o.message, "date": o.created_at.isoformat(),
                "listing": svc.to_public(o.listing) if o.listing else None}
        out.append(item)
    return out


@router.get("/orders/received")
def received_orders(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Requests buyers have made against this farmer's own listings."""
    rows = (db.query(ProduceOrder).join(CropListing, ProduceOrder.listing_id == CropListing.id)
            .filter(CropListing.farmer_id == user.id)
            .order_by(ProduceOrder.created_at.desc()).all())
    out = []
    for o in rows:
        out.append({"id": o.id, "status": o.status, "quantity_kg": o.quantity_kg,
                    "message": o.message, "date": o.created_at.isoformat(),
                    "buyer_name": o.buyer.name if o.buyer else "",
                    "listing": svc.to_public(o.listing) if o.listing else None})
    return out


@router.post("/orders/{order_id}/respond")
def respond_to_order(order_id: int, data: OrderRespondIn,
                     user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    order = (db.query(ProduceOrder).join(CropListing, ProduceOrder.listing_id == CropListing.id)
             .filter(ProduceOrder.id == order_id, CropListing.farmer_id == user.id).first())
    if not order:
        raise HTTPException(404, "Order not found")
    if data.status not in ("confirmed", "declined", "completed"):
        raise HTTPException(400, "status must be confirmed, declined or completed")

    order.status = data.status
    if data.status == "confirmed":
        order.listing.status = "reserved"
    elif data.status == "completed":
        order.listing.status = "sold"
    db.commit()
    return {"status": "ok"}
