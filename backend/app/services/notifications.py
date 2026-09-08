"""Notification delivery.

CHANNELS
--------
Alerts always land in-app: the Alerts page reads the database directly, so an
alert exists whether or not any push is configured. Push is an additional
nudge, never the storage.

    in_app     always, and the source of truth
    web_push   browser notifications, when VAPID keys are configured
    sms        not implemented — the model and dispatcher already accommodate it
    whatsapp   not implemented — likewise

The dispatcher loops over channels, so adding SMS later means writing one
`_send_sms()` and registering it. Nothing else changes.

WHY NOT EVERY ALERT
-------------------
A push for every INFO alert trains farmers to switch notifications off within
a week, and then the CRITICAL one never arrives either. So each subscription
carries a `min_priority` (default HIGH) and low-priority alerts stay in-app.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any, Dict, List

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.models import Alert, PushSubscription

log = logging.getLogger("agri.notifications")

PRIORITY_RANK = {"LOW": 0, "MEDIUM": 1, "HIGH": 2, "CRITICAL": 3}

# Consecutive failures before we stop trying. Browser endpoints die silently
# when a user clears site data, and retrying a dead endpoint forever wastes
# time on every alert run.
MAX_FAILURES = 5


def push_available() -> tuple[bool, str]:
    """Is web push usable? Returns (ok, reason)."""
    if not settings.PUSH_ENABLED:
        return False, "PUSH_ENABLED is false in backend/.env"
    if not settings.VAPID_PRIVATE_KEY or not settings.VAPID_PUBLIC_KEY:
        return False, ("VAPID keys are not set. Generate a pair and set "
                       "VAPID_PUBLIC_KEY and VAPID_PRIVATE_KEY in backend/.env")
    try:
        import pywebpush  # noqa: F401
    except ImportError:
        return False, "pywebpush is not installed. Run: pip install pywebpush"
    return True, "ready"


def status() -> Dict[str, Any]:
    ok, reason = push_available()
    return {
        "in_app": True,
        "web_push": {"ready": ok, "reason": reason,
                     "public_key": settings.VAPID_PUBLIC_KEY or None},
        "sms": {"ready": False, "reason": "Not implemented yet."},
        "whatsapp": {"ready": False, "reason": "Not implemented yet."},
        "note": ("Alerts are always stored in-app. Push is an extra nudge for "
                 "high-priority alerts only."),
    }


def _payload(alert: Alert) -> str:
    """What the service worker receives. Kept small — push payloads are capped."""
    return json.dumps({
        "id": alert.id,
        "title": alert.title,
        "body": (alert.message or "")[:180],
        "priority": alert.priority,
        "category": alert.category,
        "url": "/alerts",
    })


def _send_web_push(sub: PushSubscription, alert: Alert) -> bool:
    from pywebpush import WebPushException, webpush

    try:
        webpush(
            subscription_info={
                "endpoint": sub.endpoint,
                "keys": {"p256dh": sub.p256dh, "auth": sub.auth},
            },
            data=_payload(alert),
            vapid_private_key=settings.VAPID_PRIVATE_KEY,
            vapid_claims={"sub": f"mailto:{settings.VAPID_CONTACT_EMAIL}"},
            timeout=10,
        )
        return True
    except WebPushException as exc:
        # 404 and 410 mean the browser threw the subscription away. That is
        # not an error to retry — it is a signal to stop.
        code = getattr(exc.response, "status_code", None)
        if code in (404, 410):
            sub.active = False
            log.info("push endpoint gone (%s), deactivating sub %s", code, sub.id)
        else:
            log.warning("web push failed for sub %s: %s", sub.id, exc)
        return False
    except Exception as exc:                            # noqa: BLE001
        log.warning("web push error for sub %s: %s", sub.id, exc)
        return False


def dispatch(db: Session, user_id: int, alerts: List[Alert]) -> Dict[str, Any]:
    """Push the alerts worth interrupting someone for. Never raises.

    Called after alert generation. A push failure must not fail the request
    that generated the alert — the alert is already saved and visible in-app,
    which is the part that matters.
    """
    result = {"considered": len(alerts), "pushed": 0, "skipped_low": 0,
              "channels": []}
    if not alerts:
        return result

    ok, reason = push_available()
    if not ok:
        result["web_push_skipped"] = reason
        return result

    subs = (db.query(PushSubscription)
            .filter(PushSubscription.user_id == user_id,
                    PushSubscription.active == True,          # noqa: E712
                    PushSubscription.channel == "web_push")
            .all())
    if not subs:
        result["web_push_skipped"] = "No device is subscribed."
        return result

    for sub in subs:
        floor = PRIORITY_RANK.get(sub.min_priority or "HIGH", 2)
        for alert in alerts:
            if PRIORITY_RANK.get(alert.priority or "MEDIUM", 1) < floor:
                result["skipped_low"] += 1
                continue
            if _send_web_push(sub, alert):
                result["pushed"] += 1
                sub.last_sent_at = datetime.utcnow()
                sub.failure_count = 0
            else:
                sub.failure_count = (sub.failure_count or 0) + 1
                if sub.failure_count >= MAX_FAILURES:
                    sub.active = False

    result["channels"].append("web_push")
    try:
        db.commit()
    except Exception:                                   # noqa: BLE001
        db.rollback()
    return result
