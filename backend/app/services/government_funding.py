"""Admin funding summaries backed by stored scheme and district data."""
from datetime import datetime
from sqlalchemy.orm import Session
from app.models.models import DistrictFunding, Scheme, SchemeBudget, StateFunding

CURRENT_FY = "2026-27"


def _row(row):
    return {
        "id": row.id,
        "financial_year": row.financial_year,
        "allocated_cr": row.allocated_cr,
        "released_cr": row.released_cr,
        "utilized_cr": row.utilized_cr,
        "beneficiaries": row.beneficiaries,
        "data_status": row.data_status,
        "source": row.source,
        "source_url": row.source_url,
    }


def overview(db: Session, state: str = "India"):
    budgets = db.query(SchemeBudget).filter(SchemeBudget.financial_year == CURRENT_FY).all()
    states = db.query(StateFunding).filter(StateFunding.financial_year == CURRENT_FY).all()
    return {
        "state": state,
        "financial_year": CURRENT_FY,
        "scheme_count": db.query(Scheme).count(),
        "budget_total_cr": round(sum((r.budget_estimate_cr or 0) for r in budgets), 2),
        "allocated_total_cr": round(sum((r.allocated_cr or 0) for r in states), 2),
        "data_status": "DEMO" if not budgets and not states else "MIXED",
        "generated_at": datetime.utcnow().isoformat(),
    }


def schemes(db: Session, financial_year: str = CURRENT_FY):
    rows = db.query(SchemeBudget).filter(SchemeBudget.financial_year == financial_year).all()
    return [{**_row(r), "scheme_name": r.scheme.name if r.scheme else ""} for r in rows]


def districts(db: Session, state: str, financial_year: str = CURRENT_FY):
    return [{**_row(r), "state": r.state, "district": r.district}
            for r in db.query(DistrictFunding).filter(
                DistrictFunding.state == state,
                DistrictFunding.financial_year == financial_year).all()]
