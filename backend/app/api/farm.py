from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.database.db import get_db
from app.models.models import Farm, User
from app.schemas.schemas import FarmIn, FarmOut
from app.core.security import get_current_user

router = APIRouter(prefix="/api/farms", tags=["farm"])


@router.get("", response_model=list[FarmOut])
def list_farms(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return db.query(Farm).filter(Farm.user_id == user.id).all()


@router.post("", response_model=FarmOut)
def create_farm(data: FarmIn, user: User = Depends(get_current_user),
                db: Session = Depends(get_db)):
    farm = Farm(user_id=user.id, **data.model_dump())
    db.add(farm); db.commit(); db.refresh(farm)
    return farm


@router.get("/{farm_id}", response_model=FarmOut)
def get_farm(farm_id: int, user: User = Depends(get_current_user),
             db: Session = Depends(get_db)):
    farm = db.query(Farm).filter(Farm.id == farm_id, Farm.user_id == user.id).first()
    if not farm:
        raise HTTPException(404, "Farm not found")
    return farm


@router.put("/{farm_id}", response_model=FarmOut)
def update_farm(farm_id: int, data: FarmIn, user: User = Depends(get_current_user),
                db: Session = Depends(get_db)):
    """Update a farm, touching ONLY the fields the caller actually sent.

    `model_dump()` fills every unsent field with its schema default, so a
    caller updating just the crop would also write sowing_date=None,
    crop_area_acres=None and previous_crop="" over real data. That was
    survivable while FarmIn listed only a handful of fields; now that it
    carries the full onboarding set, a partial save would quietly destroy the
    farmer's sowing date and sown area — and the lifecycle, harvest date and
    fertiliser quantities computed from them.

    exclude_unset keeps an omitted field omitted.
    """
    farm = db.query(Farm).filter(Farm.id == farm_id, Farm.user_id == user.id).first()
    if not farm:
        raise HTTPException(404, "Farm not found")
    for k, v in data.model_dump(exclude_unset=True).items():
        setattr(farm, k, v)
    db.commit(); db.refresh(farm)
    return farm
