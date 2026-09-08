"""Pydantic request/response models."""
from typing import Optional, List
from pydantic import BaseModel
from datetime import datetime


class RegisterIn(BaseModel):
    name: str
    email: str
    password: str
    mode: str = "farm"
    language: str = "en"
    state: str = ""
    district: str = ""


class LoginIn(BaseModel):
    email: str
    password: str


class UserOut(BaseModel):
    id: int
    name: str
    email: str
    role: str
    mode: str
    language: str
    state: str
    district: str
    class Config:
        from_attributes = True


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


class FarmIn(BaseModel):
    mode: str = "farm"
    name: str = ""
    location: str = ""
    state: str = ""
    district: str = ""
    village: str = ""
    area: str = ""
    crop: str = ""
    variety: str = ""
    growth_stage: str = ""
    soil_type: str = ""
    irrigation_type: str = ""
    farming_method: str = ""
    sunlight: str = ""
    growing_medium: str = ""
    watering_method: str = ""
    device_id: str = "ESP32-001"
    farmer_category: str = "small"
    land_size_acres: float = 1.0

    # --- fields the model has had for a while but the schema never carried ---
    #
    # These were on the Farm model and written by onboarding, but FarmIn/
    # FarmOut did not list them, so Pydantic silently dropped them on the way
    # out. Any screen reading /api/farms therefore saw no sowing date and no
    # crop area — which is why the dashboard showed a crop with blank days,
    # and why fertiliser quantities fell back to the whole holding instead of
    # the area actually sown.
    crop_area_acres: Optional[float] = None
    sowing_date: Optional[datetime] = None
    expected_harvest_date: Optional[datetime] = None
    previous_crop: str = ""
    previous_season: str = ""
    previous_variety: str = ""
    water_source: str = ""
    water_availability: str = ""
    area_unit: str = "acre"
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    onboarded: bool = False


class FarmOut(FarmIn):
    id: int
    class Config:
        from_attributes = True


class SensorIn(BaseModel):
    device_id: str
    soil_moisture: float
    temperature: float
    humidity: float
    water_level: float
    water_flow: float = 0
    timestamp: Optional[str] = None


class SoilTestIn(BaseModel):
    nitrogen: float
    phosphorus: float
    potassium: float
    ph: float
    ec: float = 0


class ChatIn(BaseModel):
    message: str
    language: Optional[str] = None
    page_context: str = ""


class EligibilityIn(BaseModel):
    state: str
    farmer_category: str
    land_size_acres: float
    crop: str = ""
    irrigation_method: str = ""


class MaturityPredictIn(BaseModel):
    crop: str
    sowing_date: str        # ISO yyyy-mm-dd


class CropListingIn(BaseModel):
    crop: str
    variety: str = ""
    sowing_date: Optional[str] = None      # ISO yyyy-mm-dd
    maturity_date: Optional[str] = None    # farmer override, ISO yyyy-mm-dd
    intends_to_sell: bool = False
    quantity_kg: Optional[float] = None
    price_per_kg: Optional[float] = None
    contact_phone: str = ""


class FertilizerListingIn(BaseModel):
    """Surplus compost offered for sale.

    No sowing date and no predicted harvest — the farmer either has the
    material now or knows when the heap will be ready, so `ready_date` is
    taken as given rather than computed from a crop lifecycle.
    """
    product_name: str                      # the farmer's own name for it
    method: str = "compost"                # compost | vermicompost | fym | liquid
    variety: str = ""                      # optional grade / description
    quantity_kg: Optional[float] = None
    price_per_kg: Optional[float] = None
    contact_phone: str = ""
    ready_date: Optional[str] = None       # ISO yyyy-mm-dd; blank = ready now
    source: str = ""                       # e.g. "circular_farming"


class ProduceOrderIn(BaseModel):
    quantity_kg: Optional[float] = None
    message: str = ""


class OrderRespondIn(BaseModel):
    status: str   # confirmed | declined | completed


class HarvestCalendarIn(BaseModel):
    crop: str
    variety: str = ""
    sowing_date: Optional[str] = None
    expected_harvest_date: str
    estimated_quantity_kg: Optional[float] = None
    expected_min_price: Optional[float] = None
    expected_max_price: Optional[float] = None
    plot_size_acres: float = 1.0
    soil_type: str = ""
    irrigation_type: str = ""
    notes: str = ""


class HarvestCalendarOut(HarvestCalendarIn):
    id: int
    farm_id: int
    farmer_id: int
    status: str
    created_at: str
    updated_at: str

    class Config:
        from_attributes = True


class PreBookingIn(BaseModel):
    quantity_kg: Optional[float] = None
    agreed_price_per_kg: Optional[float] = None
    delivery_date: Optional[str] = None
    delivery_location: str = ""
    buyer_message: str = ""


class PreBookingOut(PreBookingIn):
    id: int
    harvest_id: int
    buyer_id: int
    status: str
    farmer_response: str = ""
    created_at: str
    updated_at: str

    class Config:
        from_attributes = True


class PreBookingRespondIn(BaseModel):
    status: str
    farmer_response: str = ""


class HarvestMessageIn(BaseModel):
    content: str
