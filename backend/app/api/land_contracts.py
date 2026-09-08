"""Land Contractors API.

Farmer side  — list land for seasonal rent
Buyer side   — browse listings, request a contract, see active contracts
               and what's growing on their rented land

Contract status flow:
    pending  → active    (farmer accepts)
    pending  → cancelled (farmer/buyer cancels)
    active   → completed (end_date reached or closed manually)
    active   → cancelled (early exit)
"""

from datetime import datetime
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.security import get_current_user
from app.database.db import get_db
from app.models.models import LandListing, LandContract, ContractMessage, User

router = APIRouter(prefix="/api/land", tags=["land-contracts"])


# ─── Pydantic schemas ─────────────────────────────────────────────────────────

class LandListingIn(BaseModel):
    title: str = ""
    description: str = ""
    state: str = ""
    district: str = ""
    village: str = ""
    area_acres: float = 1.0
    soil_type: str = ""
    water_source: str = ""
    irrigation_available: bool = False
    suitable_crops: List[str] = []
    price_per_acre_per_season: float = 0.0
    min_season_months: int = 1
    max_season_months: int = 12
    available_from: Optional[str] = None
    contact_phone: str = ""
    latitude: Optional[float] = None
    longitude: Optional[float] = None


class ContractRequestIn(BaseModel):
    listing_id: int
    start_date: str          # ISO date string
    end_date: str            # ISO date string
    agreed_crop: str = ""
    buyer_notes: str = ""
    terms_accepted: bool = False


class ContractRespondIn(BaseModel):
    action: str              # "accept" | "decline"
    farmer_notes: str = ""


class MessageIn(BaseModel):
    content: str


def _parse_date(s: Optional[str]) -> Optional[datetime]:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s)
    except ValueError:
        raise HTTPException(400, "Dates must be ISO format yyyy-mm-dd or yyyy-mm-ddTHH:MM:SS")


def _listing_out(l: LandListing, reveal_phone: bool = False) -> dict:
    return {
        "id": l.id,
        "farmer_id": l.farmer_id,
        "farmer_name": l.farmer.name if l.farmer else "",
        "title": l.title,
        "description": l.description,
        "state": l.state,
        "district": l.district,
        "village": l.village,
        "area_acres": l.area_acres,
        "soil_type": l.soil_type,
        "water_source": l.water_source,
        "irrigation_available": l.irrigation_available,
        "suitable_crops": l.suitable_crops or [],
        "price_per_acre_per_season": l.price_per_acre_per_season,
        "min_season_months": l.min_season_months,
        "max_season_months": l.max_season_months,
        "available_from": l.available_from.isoformat() if l.available_from else None,
        "status": l.status,
        "views": l.views,
        "created_at": l.created_at.isoformat() if l.created_at else None,
        **({"contact_phone": l.contact_phone} if reveal_phone else {}),
    }


def _contract_out(c: LandContract) -> dict:
    return {
        "id": c.id,
        "listing_id": c.listing_id,
        "buyer_id": c.buyer_id,
        "farmer_id": c.farmer_id,
        "start_date": c.start_date.isoformat() if c.start_date else None,
        "end_date": c.end_date.isoformat() if c.end_date else None,
        "agreed_crop": c.agreed_crop,
        "price_per_acre": c.price_per_acre,
        "total_price": c.total_price,
        "status": c.status,
        "terms_accepted": c.terms_accepted,
        "farmer_notes": c.farmer_notes,
        "buyer_notes": c.buyer_notes,
        "created_at": c.created_at.isoformat() if c.created_at else None,
        "updated_at": c.updated_at.isoformat() if c.updated_at else None,
        # Denorm for UI convenience
        "listing_title": c.listing.title if c.listing else "",
        "listing_area_acres": c.listing.area_acres if c.listing else 0,
        "listing_state": c.listing.state if c.listing else "",
        "listing_district": c.listing.district if c.listing else "",
        "listing_village": c.listing.village if c.listing else "",
        "listing_suitable_crops": c.listing.suitable_crops if c.listing else [],
        "farmer_name": c.farmer.name if c.farmer else "",
        "buyer_name": c.buyer.name if c.buyer else "",
    }


# ─── Farmer endpoints ─────────────────────────────────────────────────────────

@router.post("/listings")
def create_listing(
    body: LandListingIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Farmer lists a plot of land available for seasonal rent."""
    if user.role not in ("farmer", "admin"):
        raise HTTPException(403, "Only farmers can create land listings")

    listing = LandListing(
        farmer_id=user.id,
        title=body.title,
        description=body.description,
        state=body.state or user.state,
        district=body.district or user.district,
        village=body.village,
        area_acres=body.area_acres,
        soil_type=body.soil_type,
        water_source=body.water_source,
        irrigation_available=body.irrigation_available,
        suitable_crops=body.suitable_crops,
        price_per_acre_per_season=body.price_per_acre_per_season,
        min_season_months=body.min_season_months,
        max_season_months=body.max_season_months,
        available_from=_parse_date(body.available_from),
        contact_phone=body.contact_phone,
        latitude=body.latitude,
        longitude=body.longitude,
        status="available",
    )
    db.add(listing)
    db.commit()
    db.refresh(listing)
    return _listing_out(listing)


@router.get("/my-listings")
def my_listings(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """All listings posted by the logged-in farmer (includes contact)."""
    rows = db.query(LandListing).filter(
        LandListing.farmer_id == user.id
    ).order_by(LandListing.created_at.desc()).all()
    return [_listing_out(r, reveal_phone=True) for r in rows]


@router.delete("/listings/{listing_id}")
def withdraw_listing(
    listing_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Farmer withdraws a listing (marks it withdrawn, doesn't delete)."""
    listing = db.get(LandListing, listing_id)
    if not listing:
        raise HTTPException(404, "Listing not found")
    if listing.farmer_id != user.id and user.role != "admin":
        raise HTTPException(403, "Not your listing")
    listing.status = "withdrawn"
    db.commit()
    return {"ok": True}


@router.get("/contracts/incoming")
def incoming_contracts(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Farmer sees contract requests sent by buyers for their land."""
    rows = db.query(LandContract).filter(
        LandContract.farmer_id == user.id
    ).order_by(LandContract.created_at.desc()).all()
    return [_contract_out(c) for c in rows]


@router.post("/contracts/{contract_id}/respond")
def respond_to_contract(
    contract_id: int,
    body: ContractRespondIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Farmer accepts or declines a pending contract request."""
    contract = db.get(LandContract, contract_id)
    if not contract:
        raise HTTPException(404, "Contract not found")
    if contract.farmer_id != user.id:
        raise HTTPException(403, "Not your contract")
    if contract.status != "pending":
        raise HTTPException(400, f"Contract is already '{contract.status}'")

    if body.action == "accept":
        contract.status = "active"
        # Mark the listing as rented so it disappears from browse
        listing = db.get(LandListing, contract.listing_id)
        if listing:
            listing.status = "rented"
    elif body.action == "decline":
        contract.status = "cancelled"
    else:
        raise HTTPException(400, "action must be 'accept' or 'decline'")

    contract.farmer_notes = body.farmer_notes
    db.commit()
    db.refresh(contract)
    return _contract_out(contract)


# ─── Buyer endpoints ──────────────────────────────────────────────────────────

@router.get("/browse")
def browse_listings(
    state: Optional[str] = Query(None),
    district: Optional[str] = Query(None),
    soil_type: Optional[str] = Query(None),
    irrigation: Optional[bool] = Query(None),
    crop: Optional[str] = Query(None),
    min_acres: Optional[float] = Query(None),
    max_price: Optional[float] = Query(None),
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    """Buyers browse land available for rent with rich filters."""
    q = db.query(LandListing).filter(LandListing.status == "available")
    if state:
        q = q.filter(LandListing.state.ilike(f"%{state}%"))
    if district:
        q = q.filter(LandListing.district.ilike(f"%{district}%"))
    if soil_type:
        q = q.filter(LandListing.soil_type.ilike(f"%{soil_type}%"))
    if irrigation is not None:
        q = q.filter(LandListing.irrigation_available == irrigation)
    if min_acres:
        q = q.filter(LandListing.area_acres >= min_acres)
    if max_price:
        q = q.filter(LandListing.price_per_acre_per_season <= max_price)

    rows = q.order_by(LandListing.created_at.desc()).limit(100).all()

    # Client-side crop filter (JSON array — SQLite can't query JSON easily)
    if crop:
        crop_lower = crop.lower()
        rows = [r for r in rows
                if any(crop_lower in c.lower() for c in (r.suitable_crops or []))]

    # Increment view counters in bulk
    for r in rows:
        r.views = (r.views or 0) + 1
    db.commit()

    return [_listing_out(r) for r in rows]


@router.get("/listings/{listing_id}")
def listing_detail(
    listing_id: int,
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    """Full listing detail. Contact phone is NOT included here — use /contact."""
    listing = db.get(LandListing, listing_id)
    if not listing:
        raise HTTPException(404, "Listing not found")
    return _listing_out(listing)


@router.get("/listings/{listing_id}/contact")
def reveal_contact(
    listing_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Reveal farmer contact phone after buyer expresses serious intent."""
    listing = db.get(LandListing, listing_id)
    if not listing:
        raise HTTPException(404, "Listing not found")
    return {
        "farmer_name": listing.farmer.name,
        "contact_phone": listing.contact_phone,
        "safety_note": (
            "Always meet at the land in daylight and verify land ownership documents "
            "before transferring any payment."
        ),
    }


@router.post("/contracts")
def request_contract(
    body: ContractRequestIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Buyer submits a contract request for a land listing."""
    listing = db.get(LandListing, body.listing_id)
    if not listing:
        raise HTTPException(404, "Listing not found")
    if listing.status != "available":
        raise HTTPException(400, f"Land is not available (status: {listing.status})")

    start = _parse_date(body.start_date)
    end = _parse_date(body.end_date)
    if not start or not end:
        raise HTTPException(400, "start_date and end_date are required")
    if end <= start:
        raise HTTPException(400, "end_date must be after start_date")

    months = max(1, round((end - start).days / 30))
    total = listing.price_per_acre_per_season * listing.area_acres * (months / 6)

    contract = LandContract(
        listing_id=listing.id,
        buyer_id=user.id,
        farmer_id=listing.farmer_id,
        start_date=start,
        end_date=end,
        agreed_crop=body.agreed_crop,
        price_per_acre=listing.price_per_acre_per_season,
        total_price=total,
        status="pending",
        terms_accepted=body.terms_accepted,
        buyer_notes=body.buyer_notes,
    )
    db.add(contract)
    db.commit()
    db.refresh(contract)
    return _contract_out(contract)


@router.get("/my-contracts")
def my_contracts(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Buyer's own contracts — pending, active, completed, cancelled."""
    rows = db.query(LandContract).filter(
        LandContract.buyer_id == user.id
    ).order_by(LandContract.created_at.desc()).all()
    return [_contract_out(c) for c in rows]


@router.post("/contracts/{contract_id}/cancel")
def cancel_contract(
    contract_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Buyer cancels a pending contract (cannot cancel active ones unilaterally)."""
    contract = db.get(LandContract, contract_id)
    if not contract:
        raise HTTPException(404, "Contract not found")
    if contract.buyer_id != user.id:
        raise HTTPException(403, "Not your contract")
    if contract.status != "pending":
        raise HTTPException(400, "Only pending contracts can be cancelled by the buyer")
    contract.status = "cancelled"
    db.commit()
    db.refresh(contract)
    return _contract_out(contract)


@router.get("/stats")
def land_stats(
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    """Quick summary numbers for the buyer dashboard header."""
    available = db.query(LandListing).filter(LandListing.status == "available").count()
    rented = db.query(LandListing).filter(LandListing.status == "rented").count()
    return {"available_plots": available, "rented_plots": rented}


# ─── Messaging endpoints ──────────────────────────────────────────────────────

@router.get("/contracts/{contract_id}/messages")
def get_contract_messages(
    contract_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Get all messages for a specific contract."""
    contract = db.get(LandContract, contract_id)
    if not contract:
        raise HTTPException(404, "Contract not found")
    if contract.buyer_id != user.id and contract.farmer_id != user.id and user.role != "admin":
        raise HTTPException(403, "Not authorized to view these messages")

    messages = db.query(ContractMessage).filter(
        ContractMessage.contract_id == contract_id
    ).order_by(ContractMessage.created_at.asc()).all()
    
    return [
        {
            "id": m.id,
            "sender_id": m.sender_id,
            "sender_name": m.sender.name if m.sender else "",
            "content": m.content,
            "created_at": m.created_at.isoformat() if m.created_at else None,
            "is_mine": m.sender_id == user.id
        }
        for m in messages
    ]


@router.post("/contracts/{contract_id}/messages")
def send_contract_message(
    contract_id: int,
    body: MessageIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Send a message regarding a specific contract."""
    contract = db.get(LandContract, contract_id)
    if not contract:
        raise HTTPException(404, "Contract not found")
    if contract.buyer_id != user.id and contract.farmer_id != user.id:
        raise HTTPException(403, "Not authorized to send messages for this contract")

    msg = ContractMessage(
        contract_id=contract_id,
        sender_id=user.id,
        content=body.content
    )
    db.add(msg)
    db.commit()
    db.refresh(msg)
    
    return {
        "id": msg.id,
        "sender_id": msg.sender_id,
        "sender_name": user.name,
        "content": msg.content,
        "created_at": msg.created_at.isoformat() if msg.created_at else None,
        "is_mine": True
    }
