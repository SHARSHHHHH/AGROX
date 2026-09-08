"""Direct farmer-to-buyer produce marketplace.

MATURITY PREDICTION
--------------------
The predicted maturity date is sowing_date + total_duration_days from the
crop lifecycle service (lifecycle.py) — the same static, stage-by-stage
agronomic reference already used on the Crop Advisor page. It is a typical
duration for Madhya Pradesh conditions, not a guarantee; the UI must say so,
and a farmer can override the date if their crop is ahead of or behind
schedule.

PRIVACY
-------
`contact_phone` is personal data, handled exactly like MachineryListing's:
never included in browse results, released only through a dedicated
authenticated endpoint, one listing at a time.
"""

from datetime import datetime, timedelta
from typing import Any, Dict, Optional

from app.models.models import CropListing
from app.services.lifecycle import get_lifecycle
from app.services.machinery import mask_phone, normalise_phone  # reuse validated pattern


def predict_maturity(crop: str, sowing_date: datetime) -> Dict[str, Any]:
    """Predicted maturity date for a crop sown on a given date.

    Returns supported=False (and no date) for crops outside the five we
    hold lifecycle data for, so the caller can fall back to asking the
    farmer for their own expected date rather than inventing one.
    """
    data = get_lifecycle(crop)
    if data is None:
        return {"supported": False, "predicted_maturity_date": None,
                "total_duration_days": None, "disclaimer": None}
    predicted = sowing_date + timedelta(days=data["total_duration_days"])
    return {
        "supported": True,
        "predicted_maturity_date": predicted.date().isoformat(),
        "total_duration_days": data["total_duration_days"],
        "disclaimer": data["disclaimer"],
    }


def to_public(listing: CropListing) -> Dict[str, Any]:
    """Browse-safe view — no phone number."""
    return {
        "id": listing.id,
        "product_type": listing.product_type or "produce",
        "product_name": listing.product_name or "",
        "source": listing.source or "",
        "crop": listing.crop,
        "variety": listing.variety,
        "sowing_date": listing.sowing_date.date().isoformat() if listing.sowing_date else None,
        "predicted_maturity_date": (listing.predicted_maturity_date.date().isoformat()
                                    if listing.predicted_maturity_date else None),
        "maturity_source": listing.maturity_source,
        "quantity_kg": listing.quantity_kg,
        "price_per_kg": listing.price_per_kg,
        "state": listing.state,
        "district": listing.district,
        "village": listing.village,
        "status": listing.status,
        "farmer_name": listing.farmer_name,
        "contact_phone_masked": mask_phone(listing.contact_phone or ""),
        "image_url": f"/{listing.image_path}" if listing.image_path else None,
        "created_at": listing.created_at.isoformat() if listing.created_at else None,
    }


def compute_status(listing: CropListing) -> str:
    """Recompute a listing's lifecycle status from its dates.

    A farmer says "I plan to sell this" while the crop is still growing; the
    listing only becomes visible to buyers as "available" once the predicted
    (or farmer-confirmed) maturity date has actually arrived. This keeps a
    buyer from reserving produce that doesn't exist yet.
    """
    if listing.status in ("reserved", "sold", "withdrawn"):
        return listing.status
    if not listing.intends_to_sell:
        return "growing"

    target = listing.predicted_maturity_date

    # A fertiliser listing has no sowing date and no harvest. It is either
    # already made — in which case a buyer can have it today — or still
    # rotting, with a ready date the farmer gave us. Running it through the
    # crop rule would leave finished compost stuck at "growing" forever,
    # because there is no maturity date to pass.
    if (listing.product_type or "produce") == "fertilizer":
        if target and target.date() > datetime.utcnow().date():
            return "growing"
        return "available"

    if target and target.date() <= datetime.utcnow().date():
        return "available"
    return "growing"
