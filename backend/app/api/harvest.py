"""Harvest calendar and pre-booking API.

Farmers can plan and schedule harvests, allowing buyers to see upcoming
harvests and make advance reservations with agreed pricing and delivery terms.
"""

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.security import get_current_user
from app.database.db import get_db
from app.models.models import HarvestCalendar, HarvestMessage, Notification, PreBooking, Farm, User
from app.services.notifications import create_message_notifications
from app.schemas.schemas import (HarvestCalendarIn, HarvestCalendarOut, 
                                 PreBookingIn, PreBookingOut, PreBookingRespondIn,
                                 HarvestMessageIn)

router = APIRouter(prefix="/api/harvest", tags=["harvest"])


def _parse_date(s: Optional[str]) -> Optional[datetime]:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s)
    except ValueError:
        raise HTTPException(400, "Dates must be ISO format yyyy-mm-dd")


def _to_dict(obj):
    """Convert SQLAlchemy object to dict for JSON serialization."""
    if obj is None:
        return None
    result = {}
    for col in obj.__table__.columns:
        val = getattr(obj, col.name)
        if isinstance(val, datetime):
            result[col.name] = val.isoformat()
        else:
            result[col.name] = val
    return result


# ============================================================== FARMER SIDE

@router.post("/calendar")
def create_harvest(data: HarvestCalendarIn, 
                   user: User = Depends(get_current_user),
                   db: Session = Depends(get_db)):
    """Create a harvest calendar entry for planning."""
    if user.role not in ("farmer", "balcony"):
        raise HTTPException(403, "Only farmers can create harvest plans")
    
    farm = db.query(Farm).filter(Farm.user_id == user.id).first()
    if not farm:
        raise HTTPException(400, "Farm profile not set up. Please complete farm setup first.")
    
    sowing = _parse_date(data.sowing_date)
    harvest = _parse_date(data.expected_harvest_date)
    
    if not harvest:
        raise HTTPException(400, "expected_harvest_date is required")
    
    calendar = HarvestCalendar(
        farm_id=farm.id,
        farmer_id=user.id,
        crop=data.crop,
        variety=data.variety,
        sowing_date=sowing,
        expected_harvest_date=harvest,
        estimated_quantity_kg=data.estimated_quantity_kg,
        expected_min_price=data.expected_min_price,
        expected_max_price=data.expected_max_price,
        plot_size_acres=data.plot_size_acres,
        soil_type=data.soil_type,
        irrigation_type=data.irrigation_type,
        notes=data.notes,
        status="planning"
    )
    db.add(calendar)
    db.commit()
    db.refresh(calendar)
    return _to_dict(calendar)


@router.get("/calendar/{harvest_id:int}")
def get_harvest(harvest_id: int, 
                user: User = Depends(get_current_user),
                db: Session = Depends(get_db)):
    """Get a specific harvest calendar entry."""
    harvest = db.query(HarvestCalendar).filter(HarvestCalendar.id == harvest_id).first()
    if not harvest:
        raise HTTPException(404, "Harvest not found")
    
    # Farmer can view their own, buyers can view if interested
    if user.id != harvest.farmer_id and user.role not in ("admin", "buyer"):
        raise HTTPException(403, "Not authorized to view this harvest")
    
    return _to_dict(harvest)


@router.get("/calendar/farm/{farm_id}")
def list_farm_harvests(farm_id: int,
                       status: Optional[str] = None,
                       user: User = Depends(get_current_user),
                       db: Session = Depends(get_db)):
    """List all harvests for a farm."""
    farm = db.query(Farm).filter(Farm.id == farm_id).first()
    if not farm:
        raise HTTPException(404, "Farm not found")
    
    # Only farmers can see private details of their own harvests
    if user.id != farm.user_id and user.role not in ("admin", "buyer"):
        raise HTTPException(403, "Not authorized")
    
    query = db.query(HarvestCalendar).filter(HarvestCalendar.farm_id == farm_id)
    
    if status:
        query = query.filter(HarvestCalendar.status == status)
    
    harvests = query.order_by(HarvestCalendar.expected_harvest_date).all()
    return [_to_dict(h) for h in harvests]


@router.get("/calendar/my")
def list_my_harvests(status: Optional[str] = None,
                     user: User = Depends(get_current_user),
                     db: Session = Depends(get_db)):
    """List all harvests for logged-in farmer."""
    if user.role not in ("farmer", "balcony"):
        raise HTTPException(403, "Only farmers can view their harvests")
    
    query = db.query(HarvestCalendar).filter(HarvestCalendar.farmer_id == user.id)
    
    if status:
        query = query.filter(HarvestCalendar.status == status)
    
    harvests = query.order_by(HarvestCalendar.expected_harvest_date).all()
    return [_to_dict(h) for h in harvests]


@router.patch("/calendar/{harvest_id:int}")
def update_harvest(harvest_id: int, data: HarvestCalendarIn,
                   user: User = Depends(get_current_user),
                   db: Session = Depends(get_db)):
    """Update a harvest calendar entry."""
    harvest = db.query(HarvestCalendar).filter(
        HarvestCalendar.id == harvest_id,
        HarvestCalendar.farmer_id == user.id
    ).first()
    
    if not harvest:
        raise HTTPException(404, "Harvest not found or not authorized")
    
    # Cannot update if harvest is already harvested
    if harvest.status == "harvested":
        raise HTTPException(400, "Cannot update a harvested crop")
    
    harvest.crop = data.crop
    harvest.variety = data.variety
    if data.sowing_date:
        harvest.sowing_date = _parse_date(data.sowing_date)
    harvest.expected_harvest_date = _parse_date(data.expected_harvest_date)
    harvest.estimated_quantity_kg = data.estimated_quantity_kg
    harvest.expected_min_price = data.expected_min_price
    harvest.expected_max_price = data.expected_max_price
    harvest.plot_size_acres = data.plot_size_acres
    harvest.soil_type = data.soil_type
    harvest.irrigation_type = data.irrigation_type
    harvest.notes = data.notes
    
    db.commit()
    db.refresh(harvest)
    return _to_dict(harvest)


@router.patch("/calendar/{harvest_id:int}/status")
def update_harvest_status(harvest_id: int, status: str,
                          user: User = Depends(get_current_user),
                          db: Session = Depends(get_db)):
    """Update harvest status: planning | growing | ready_for_harvest | harvested | cancelled."""
    harvest = db.query(HarvestCalendar).filter(
        HarvestCalendar.id == harvest_id,
        HarvestCalendar.farmer_id == user.id
    ).first()
    
    if not harvest:
        raise HTTPException(404, "Harvest not found")
    
    valid_statuses = ["planning", "growing", "ready_for_harvest", "harvested", "cancelled"]
    if status not in valid_statuses:
        raise HTTPException(400, f"Invalid status. Must be one of: {', '.join(valid_statuses)}")
    
    harvest.status = status
    db.commit()
    db.refresh(harvest)
    return _to_dict(harvest)


# ============================================================== BUYER SIDE

@router.get("/available")
def list_available_harvests(crop: Optional[str] = None,
                            state: Optional[str] = None,
                            db: Session = Depends(get_db)):
    """List all harvests available for pre-booking, optionally filtered by crop or state."""
    query = db.query(HarvestCalendar).filter(
    HarvestCalendar.status.in_(["planning", "growing", "ready_for_harvest"])
    )
    
    if crop:
        query = query.filter(HarvestCalendar.crop == crop)
    
    if state:
        query = query.join(Farm).filter(Farm.state == state)
    
    harvests = query.order_by(HarvestCalendar.expected_harvest_date).all()
    return [_to_dict(h) for h in harvests]


# ============================================================== PRE-BOOKING SIDE

@router.post("/prebooking")
def create_prebooking(harvest_id: int, data: PreBookingIn,
                      user: User = Depends(get_current_user),
                      db: Session = Depends(get_db)):
    """Create a pre-booking request for an upcoming harvest."""
    if user.role != "buyer":
        raise HTTPException(403, "Only buyers can make pre-bookings")
    
    harvest = db.query(HarvestCalendar).filter(HarvestCalendar.id == harvest_id).first()
    if not harvest:
        raise HTTPException(404, "Harvest not found")
    
    if harvest.status not in ("planning", "growing", "ready_for_harvest"):
        raise HTTPException(400, "This harvest is not available for pre-booking")
    
    # Check if buyer already has a pending request for this harvest
    existing = db.query(PreBooking).filter(
        PreBooking.harvest_id == harvest_id,
        PreBooking.buyer_id == user.id,
        PreBooking.status == "requested"
    ).first()
    
    if existing:
        raise HTTPException(400, "You already have a pending request for this harvest")
    
    delivery = _parse_date(data.delivery_date) if data.delivery_date else None
    
    booking = PreBooking(
        harvest_id=harvest_id,
        buyer_id=user.id,
        quantity_kg=data.quantity_kg,
        agreed_price_per_kg=data.agreed_price_per_kg,
        delivery_date=delivery,
        delivery_location=data.delivery_location,
        buyer_message=data.buyer_message,
        status="requested"
    )
    db.add(booking)
    db.commit()
    db.refresh(booking)
    return _to_dict(booking)


@router.get("/prebooking/{booking_id:int}")
def get_prebooking(booking_id: int,
                   user: User = Depends(get_current_user),
                   db: Session = Depends(get_db)):
    """Get a specific pre-booking."""
    booking = db.query(PreBooking).filter(PreBooking.id == booking_id).first()
    if not booking:
        raise HTTPException(404, "Pre-booking not found")
    
    harvest = booking.harvest
    # Only buyer, farmer, or admin can view
    if (user.id != booking.buyer_id and 
        user.id != harvest.farmer_id and 
        user.role != "admin"):
        raise HTTPException(403, "Not authorized")
    
    return _to_dict(booking)


@router.get("/prebooking/harvest/{harvest_id}")
def list_harvest_prebookings(harvest_id: int,
                             user: User = Depends(get_current_user),
                             db: Session = Depends(get_db)):
    """List all pre-booking requests for a harvest (farmer only)."""
    harvest = db.query(HarvestCalendar).filter(HarvestCalendar.id == harvest_id).first()
    if not harvest:
        raise HTTPException(404, "Harvest not found")
    
    if user.id != harvest.farmer_id:
        raise HTTPException(403, "Only the farmer can view pre-booking requests")
    
    bookings = db.query(PreBooking).filter(PreBooking.harvest_id == harvest_id).all()
    return [_to_dict(b) for b in bookings]


@router.get("/prebooking/my")
def list_my_prebookings(status: Optional[str] = Query(None),
                        user: User = Depends(get_current_user),
                        db: Session = Depends(get_db)):
    """List all pre-bookings for logged-in buyer."""
    if user.role != "buyer":
        raise HTTPException(403, "Only buyers can view pre-bookings")
    
    query = db.query(PreBooking).filter(PreBooking.buyer_id == user.id)
    
    if status:
        query = query.filter(PreBooking.status == status)
    
    bookings = query.order_by(PreBooking.created_at.desc()).all()
    return [_to_dict(b) for b in bookings]


@router.get("/prebooking/farmer/my")
def list_farmer_prebookings(status: Optional[str] = Query(None),
                            user: User = Depends(get_current_user),
                            db: Session = Depends(get_db)):
    """List booking requests for all harvests owned by the logged-in farmer."""
    if user.role not in ("farmer", "balcony"):
        raise HTTPException(403, "Only farmers can view booking requests")

    query = (db.query(PreBooking, HarvestCalendar)
             .join(HarvestCalendar, PreBooking.harvest_id == HarvestCalendar.id)
             .filter(HarvestCalendar.farmer_id == user.id))
    if status:
        query = query.filter(PreBooking.status == status)

    return [
        {
            **_to_dict(booking),
            "crop": harvest.crop,
            "variety": harvest.variety,
        }
        for booking, harvest in query.order_by(PreBooking.created_at.desc()).all()
    ]


def _check_harvest_message_access(harvest_id: int, user: User, db: Session):
    harvest = db.query(HarvestCalendar).filter(HarvestCalendar.id == harvest_id).first()
    if not harvest:
        raise HTTPException(404, "Harvest not found")
    is_farmer = harvest.farmer_id == user.id
    has_booking = db.query(PreBooking).filter(
        PreBooking.harvest_id == harvest_id,
        PreBooking.buyer_id == user.id,
    ).first() is not None
    if not (is_farmer or has_booking or user.role == "admin"):
        raise HTTPException(403, "Create a pre-booking before messaging this farmer")
    return harvest


@router.get("/calendar/{harvest_id:int}/messages")
def get_harvest_messages(harvest_id: int,
                         user: User = Depends(get_current_user),
                         db: Session = Depends(get_db)):
    _check_harvest_message_access(harvest_id, user, db)
    messages = db.query(HarvestMessage).filter(
        HarvestMessage.harvest_id == harvest_id
    ).order_by(HarvestMessage.created_at.asc()).all()
    return [
        {
            "id": message.id,
            "sender_id": message.sender_id,
            "sender_name": message.sender.name if message.sender else "",
            "content": message.content,
            "created_at": message.created_at.isoformat() if message.created_at else None,
            "is_mine": message.sender_id == user.id,
        }
        for message in messages
    ]


@router.post("/calendar/{harvest_id:int}/messages")
def send_harvest_message(harvest_id: int, data: HarvestMessageIn,
                         user: User = Depends(get_current_user),
                         db: Session = Depends(get_db)):
    _check_harvest_message_access(harvest_id, user, db)
    content = data.content.strip()
    if not content:
        raise HTTPException(400, "Message cannot be empty")
    message = HarvestMessage(harvest_id=harvest_id, sender_id=user.id, content=content)
    db.add(message)
    db.flush()
    harvest = db.query(HarvestCalendar).filter(HarvestCalendar.id == harvest_id).first()
    if user.id == harvest.farmer_id:
        recipient_ids = [booking.buyer_id for booking in harvest.pre_bookings]
    else:
        recipient_ids = [harvest.farmer_id]
    create_message_notifications(db, message, recipient_ids)
    db.commit()
    db.refresh(message)
    return {
        "id": message.id,
        "sender_id": message.sender_id,
        "sender_name": user.name,
        "content": message.content,
        "created_at": message.created_at.isoformat() if message.created_at else None,
        "is_mine": True,
    }


@router.delete("/calendar/{harvest_id:int}/messages/{message_id:int}")
def delete_harvest_message(harvest_id: int, message_id: int,
                           user: User = Depends(get_current_user),
                           db: Session = Depends(get_db)):
    harvest = _check_harvest_message_access(harvest_id, user, db)
    message = db.query(HarvestMessage).filter(
        HarvestMessage.id == message_id,
        HarvestMessage.harvest_id == harvest_id,
    ).first()
    if not message:
        raise HTTPException(404, "Message not found")
    if message.sender_id != user.id and user.id != harvest.farmer_id and user.role != "admin":
        raise HTTPException(403, "You cannot delete this message")
    db.query(Notification).filter(Notification.source_message_id == message.id).delete(
        synchronize_session=False
    )
    db.delete(message)
    db.commit()
    return {"deleted": True, "id": message_id}


@router.patch("/prebooking/{booking_id:int}/respond")
def respond_to_prebooking(booking_id: int, data: PreBookingRespondIn,
                          user: User = Depends(get_current_user),
                          db: Session = Depends(get_db)):
    """Farmer responds to a pre-booking request."""
    booking = db.query(PreBooking).filter(PreBooking.id == booking_id).first()
    if not booking:
        raise HTTPException(404, "Pre-booking not found")
    
    harvest = booking.harvest
    if user.id != harvest.farmer_id:
        raise HTTPException(403, "Only the farmer can respond to pre-booking requests")
    
    if booking.status != "requested":
        raise HTTPException(400, "Can only respond to pending requests")
    
    valid_statuses = ["confirmed", "declined"]
    if data.status not in valid_statuses:
        raise HTTPException(400, f"Status must be: {', '.join(valid_statuses)}")
    
    booking.status = data.status
    booking.farmer_response = data.farmer_response
    db.commit()
    db.refresh(booking)
    return _to_dict(booking)


@router.get("/prebooking/buyer/{buyer_id}")
def list_buyer_prebookings(buyer_id: int,
                           status: Optional[str] = None,
                           user: User = Depends(get_current_user),
                           db: Session = Depends(get_db)):
    """List pre-bookings by a specific buyer (admin only)."""
    if user.role != "admin":
        raise HTTPException(403, "Only admins can view other users' pre-bookings")
    
    query = db.query(PreBooking).filter(PreBooking.buyer_id == buyer_id)
    
    if status:
        query = query.filter(PreBooking.status == status)
    
    bookings = query.all()
    return [_to_dict(b) for b in bookings]
