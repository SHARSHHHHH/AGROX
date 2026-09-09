"""Government funding endpoints for the admin command center."""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.core.security import require_admin
from app.database.db import get_db
from app.models.models import User
from app.services import government_funding as funding

funding_router = APIRouter(prefix="/api/admin/funding", tags=["government-funding"])


@funding_router.get("/overview")
def funding_overview(state: str = "India", _: User = Depends(require_admin), db: Session = Depends(get_db)):
    return funding.overview(db, state)


@funding_router.get("/schemes")
def scheme_budgets(financial_year: str = funding.CURRENT_FY, _: User = Depends(require_admin), db: Session = Depends(get_db)):
    return funding.schemes(db, financial_year)


@funding_router.get("/districts")
def district_funding(state: str = "Madhya Pradesh", financial_year: str = funding.CURRENT_FY,
                    _: User = Depends(require_admin), db: Session = Depends(get_db)):
    return funding.districts(db, state, financial_year)
