"""Machinery rental marketplace service.

Search, distance ranking and validation for farmer-to-farmer equipment hire.

DISTANCE
--------
Listings are ranked by real distance from the searcher when coordinates are
available, because a harvester 400 km away is not a usable option however
cheap it is. Where a listing has no GPS we fall back to its state centre and
mark the distance approximate — never presented as exact.

PRIVACY
-------
`contact_phone` is personal data and is never included in browse results. It
is released only through `reveal_contact()`, to an authenticated user, one
listing at a time, and the request is counted so an owner can see interest.
"""

import logging
import re
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from app.ml.machinery_knowledge import MACHINERY_KB, get_machine
from app.models.models import MachineryListing, User
from app.services.geocode import haversine_km, state_coords

log = logging.getLogger("agri.machinery")

# Indian mobile numbers are 10 digits starting 6-9. Optional +91 / 0 prefix.
PHONE_RE = re.compile(r"^(?:\+?91[\-\s]?|0)?([6-9]\d{9})$")

MAX_DAILY_RATE = 100000.0     # a sanity ceiling, not a real limit
CONDITIONS = ("excellent", "good", "fair")


def normalise_phone(raw: str) -> Optional[str]:
    """Return a clean 10-digit number, or None if it is not a valid Indian mobile."""
    if not raw:
        return None
    cleaned = re.sub(r"[\s\-()]", "", str(raw))
    match = PHONE_RE.match(cleaned)
    return match.group(1) if match else None


def mask_phone(phone: str) -> str:
    """Show enough to look real, not enough to dial. Used in browse results."""
    if not phone or len(phone) < 10:
        return ""
    return f"{phone[:2]}xxxxx{phone[-3:]}"


def validate_listing(data: Dict[str, Any]) -> List[str]:
    """Return a list of human-readable problems. Empty means valid."""
    errors: List[str] = []

    if not get_machine(data.get("machine_key", "")):
        errors.append(
            f"Unknown machine type. Choose one of: "
            f"{', '.join(sorted(MACHINERY_KB))}")

    rate = data.get("daily_rate")
    if rate is None or float(rate) <= 0:
        errors.append("Daily rate must be greater than zero.")
    elif float(rate) > MAX_DAILY_RATE:
        errors.append(f"Daily rate looks too high (over {MAX_DAILY_RATE:,.0f}). "
                      f"Please check the amount.")

    if not normalise_phone(data.get("contact_phone", "")):
        errors.append("Enter a valid 10-digit Indian mobile number "
                      "starting with 6, 7, 8 or 9.")

    if not (data.get("state") or "").strip():
        errors.append("State is required so nearby farmers can find your machine.")

    condition = (data.get("condition") or "good").lower()
    if condition not in CONDITIONS:
        errors.append(f"Condition must be one of: {', '.join(CONDITIONS)}")

    return errors


def _listing_coords(listing: MachineryListing):
    """Best available position: exact GPS, else the state centre."""
    if listing.latitude is not None and listing.longitude is not None:
        return listing.latitude, listing.longitude, True
    coords = state_coords(listing.state or "")
    if coords:
        return coords[0], coords[1], False
    return None, None, False


def to_public(listing: MachineryListing, *,
              origin: Optional[tuple] = None) -> Dict[str, Any]:
    """Browse-safe view. Deliberately excludes the full phone number."""
    spec = get_machine(listing.machine_key) or {}

    distance_km = None
    distance_exact = False
    if origin:
        lat, lon, exact = _listing_coords(listing)
        if lat is not None:
            distance_km = round(haversine_km(origin[0], origin[1], lat, lon), 1)
            distance_exact = exact

    return {
        "id": listing.id,
        "machine_key": listing.machine_key,
        "machine_name": spec.get("name", listing.machine_key),
        "icon": spec.get("icon", "tractor"),
        "category": spec.get("category", ""),
        "stage": spec.get("stage", ""),
        "title": listing.title or spec.get("name", ""),
        "brand": listing.brand,
        "model_year": listing.model_year,
        "description": listing.description,
        "condition": listing.condition,
        "daily_rate": listing.daily_rate,
        "hourly_rate": listing.hourly_rate,
        "fuel_included": listing.fuel_included,
        "operator_included": listing.operator_included,
        "min_days": listing.min_days,
        "owner_name": listing.owner_name,
        # Masked, never the real number.
        "contact_preview": mask_phone(listing.contact_phone),
        "state": listing.state,
        "district": listing.district,
        "village": listing.village,
        "distance_km": distance_km,
        "distance_exact": distance_exact,
        "image_path": listing.image_path,
        "available": listing.available,
        "views": listing.views,
        "created_at": listing.created_at.isoformat() if listing.created_at else None,
    }


def search(db: Session, *, machine_key: str = "", state: str = "",
           district: str = "", category: str = "",
           max_rate: Optional[float] = None,
           lat: Optional[float] = None, lon: Optional[float] = None,
           radius_km: Optional[float] = None,
           available_only: bool = True,
           sort: str = "distance", limit: int = 60) -> Dict[str, Any]:
    """Search listings with optional distance filtering."""

    query = db.query(MachineryListing)

    if available_only:
        query = query.filter(MachineryListing.available.is_(True))
    if machine_key:
        query = query.filter(MachineryListing.machine_key == machine_key.strip().lower())
    if state:
        query = query.filter(MachineryListing.state.ilike(state.strip()))
    if district:
        query = query.filter(MachineryListing.district.ilike(district.strip()))
    if max_rate is not None:
        query = query.filter(MachineryListing.daily_rate <= float(max_rate))

    rows = query.all()

    # Category filter needs the knowledge base, so it is applied in Python.
    if category:
        cat = category.strip().lower()
        rows = [r for r in rows
                if (get_machine(r.machine_key) or {}).get("category") == cat]

    origin = (lat, lon) if lat is not None and lon is not None else None
    items = [to_public(r, origin=origin) for r in rows]

    if origin and radius_km:
        # Keep listings with no usable position rather than hiding them; a
        # farmer would rather see an unlocated machine than nothing at all.
        items = [i for i in items
                 if i["distance_km"] is None or i["distance_km"] <= radius_km]

    if sort == "distance" and origin:
        items.sort(key=lambda i: (i["distance_km"] is None,
                                  i["distance_km"] or 0))
    elif sort == "price_low":
        items.sort(key=lambda i: i["daily_rate"])
    elif sort == "price_high":
        items.sort(key=lambda i: -i["daily_rate"])
    else:
        items.sort(key=lambda i: i["created_at"] or "", reverse=True)

    return {
        "count": len(items[:limit]),
        "total_matching": len(items),
        "items": items[:limit],
        "location_used": bool(origin),
        "radius_km": radius_km if origin else None,
        "note": ("Distances are straight-line estimates. Listings without GPS "
                 "are placed at their state centre and marked approximate."),
    }


def create_listing(db: Session, user: User, data: Dict[str, Any],
                   image_path: str = "") -> Dict[str, Any]:
    """Create a listing after validation. Returns {"errors": [...]} on failure."""
    errors = validate_listing(data)
    if errors:
        return {"ok": False, "errors": errors}

    phone = normalise_phone(data["contact_phone"])

    listing = MachineryListing(
        owner_id=user.id,
        machine_key=data["machine_key"].strip().lower(),
        title=(data.get("title") or "").strip(),
        brand=(data.get("brand") or "").strip(),
        model_year=data.get("model_year"),
        description=(data.get("description") or "").strip(),
        condition=(data.get("condition") or "good").lower(),
        daily_rate=float(data["daily_rate"]),
        hourly_rate=data.get("hourly_rate"),
        fuel_included=bool(data.get("fuel_included", False)),
        operator_included=bool(data.get("operator_included", False)),
        min_days=int(data.get("min_days") or 1),
        owner_name=(data.get("owner_name") or user.name or "").strip(),
        contact_phone=phone,
        state=(data.get("state") or "").strip(),
        district=(data.get("district") or "").strip(),
        village=(data.get("village") or "").strip(),
        latitude=data.get("latitude"),
        longitude=data.get("longitude"),
        image_path=image_path,
        available=True,
    )
    db.add(listing)
    db.commit()
    db.refresh(listing)
    return {"ok": True, "listing": to_public(listing)}


def reveal_contact(db: Session, listing_id: int) -> Dict[str, Any]:
    """Release the owner's phone number to an authenticated renter."""
    listing = db.query(MachineryListing).filter(
        MachineryListing.id == listing_id).first()
    if listing is None:
        return {"ok": False, "message": "Listing not found."}

    listing.contact_requests = (listing.contact_requests or 0) + 1
    db.commit()

    return {
        "ok": True,
        "owner_name": listing.owner_name,
        "contact_phone": listing.contact_phone,
        "machine_name": (get_machine(listing.machine_key) or {}).get(
            "name", listing.machine_key),
        "daily_rate": listing.daily_rate,
        "safety_note": (
            "Agree the price, dates and whether fuel and an operator are "
            "included BEFORE any payment. Inspect the machine yourself. This "
            "platform lists what owners submit and does not verify machines, "
            "owners or prices."),
    }


def record_view(db: Session, listing_id: int) -> None:
    listing = db.query(MachineryListing).filter(
        MachineryListing.id == listing_id).first()
    if listing:
        listing.views = (listing.views or 0) + 1
        db.commit()
