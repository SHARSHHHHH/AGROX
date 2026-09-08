from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.security import get_current_user
from app.database.db import get_db
from app.models.models import HarvestCalendar, HarvestMessage, Notification, User

router = APIRouter(prefix="/api/notifications", tags=["notifications"])


@router.get("")
def list_notifications(user: User = Depends(get_current_user),
                       db: Session = Depends(get_db)):
    rows = (db.query(Notification, HarvestCalendar, HarvestMessage)
            .outerjoin(HarvestCalendar, Notification.harvest_id == HarvestCalendar.id)
            .outerjoin(HarvestMessage, Notification.source_message_id == HarvestMessage.id)
            .filter(Notification.recipient_id == user.id)
            .order_by(Notification.created_at.desc())
            .limit(50).all())
    return [
        {
            "id": notification.id,
            "type": notification.notification_type,
            "title": notification.title,
            "message": notification.message,
            "content": notification.message,
            "sender_name": message.sender.name if message and message.sender else "",
            "harvest_id": notification.harvest_id,
            "crop": harvest.crop if harvest else "",
            "url": notification.url,
            "read": notification.read_at is not None,
            "created_at": notification.created_at.isoformat() if notification.created_at else None,
        }
        for notification, harvest, message in rows
    ]


@router.patch("/{notification_id}/read")
def mark_notification_read(notification_id: int,
                           user: User = Depends(get_current_user),
                           db: Session = Depends(get_db)):
    notification = db.query(Notification).filter(
        Notification.id == notification_id,
        Notification.recipient_id == user.id,
    ).first()
    if not notification:
        raise HTTPException(404, "Notification not found")
    notification.read_at = notification.read_at or datetime.utcnow()
    db.commit()
    return {"id": notification.id, "read": True}