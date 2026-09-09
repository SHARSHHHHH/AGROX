"""Deterministic district pest-outbreak summaries for admin reporting."""
from datetime import datetime, timedelta
from sqlalchemy import func
from sqlalchemy.orm import Session
from app.models.models import Farm, PestObservation


def detect_outbreak(db: Session, state: str, district: str = '', pest_name: str = ''):
    query = db.query(PestObservation.pest_name, func.count(PestObservation.id)).join(
        Farm, Farm.user_id == PestObservation.user_id).filter(Farm.state == state)
    if district:
        query = query.filter(Farm.district == district)
    if pest_name:
        query = query.filter(PestObservation.pest_name == pest_name)
    since = datetime.utcnow() - timedelta(days=30)
    rows = query.filter(PestObservation.created_at >= since).group_by(PestObservation.pest_name).all()
    return [{"pest_name": name or "Unknown", "observations": count, "window_days": 30} for name, count in rows]


def build_outbreak_scenario(db: Session, state: str, district: str = '', pest_name: str = ''):
    rows = detect_outbreak(db, state, district, pest_name)
    return {"state": state, "district": district, "pest_name": pest_name, "outbreaks": rows,
            "data_status": "LIVE", "generated_at": datetime.utcnow().isoformat()}
