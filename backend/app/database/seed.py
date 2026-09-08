"""Seed realistic demo data.

Scheme records use REAL central government schemes with official portal URLs.
Eligibility values are simplified for the demo eligibility engine; the app
always tells users to verify with the official department before applying.
"""
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from app.models.models import (User, Farm, SensorReading, SoilTest, Scheme,
                               PlantDiagnosis, MachineryListing, PestObservation,
                               CropListing, SchemeInterest, Expense,
                               LandListing, LandContract)
from app.core.security import hash_password
from app.services import simulator


REAL_SCHEMES = [
    {
        "name": "PM-KISAN",
        "description": "Income support of ₹6,000/year in three instalments to "
                       "eligible landholding farmer families.",
        "state": "All India", "level": "central",
        "farmer_categories": ["marginal", "small", "medium", "large"],
        "crops": [], "min_land": 0, "max_land": 1000,
        "benefits": "₹6,000 per year direct benefit transfer.",
        "documents": ["Aadhaar", "Land records", "Bank account details"],
        "procedure": "Register at the PM-KISAN portal or nearest CSC.",
        "url": "https://pmkisan.gov.in",
        "last_verified": "2025-01", "source": "pmkisan.gov.in",
    },
    {
        "name": "Pradhan Mantri Fasal Bima Yojana (PMFBY)",
        "description": "Crop insurance against yield loss from natural calamities, "
                       "pests and diseases.",
        "state": "All India", "level": "central",
        "farmer_categories": ["marginal", "small", "medium", "large"],
        "crops": ["rice", "tomato", "chilli", "onion", "potato"],
        "min_land": 0, "max_land": 1000,
        "benefits": "Insurance payout on notified crop loss; low farmer premium.",
        "documents": ["Aadhaar", "Land records", "Sowing certificate", "Bank details"],
        "procedure": "Apply through banks, CSCs, or the PMFBY portal before the "
                     "cut-off date for your crop.",
        "url": "https://pmfby.gov.in",
        "last_verified": "2025-01", "source": "pmfby.gov.in",
    },
    {
        "name": "Soil Health Card Scheme",
        "description": "Provides farmers a soil health card with crop-wise nutrient "
                       "and fertiliser recommendations.",
        "state": "All India", "level": "central",
        "farmer_categories": ["marginal", "small", "medium", "large"],
        "crops": [], "min_land": 0, "max_land": 1000,
        "benefits": "Free soil testing and tailored fertiliser guidance.",
        "documents": ["Aadhaar", "Land records"],
        "procedure": "Request through the local agriculture department / soil "
                     "testing lab.",
        "url": "https://soilhealth.dac.gov.in",
        "last_verified": "2025-01", "source": "soilhealth.dac.gov.in",
    },
    {
        "name": "Per Drop More Crop (PMKSY - Micro Irrigation)",
        "description": "Subsidy for drip and sprinkler micro-irrigation systems to "
                       "improve water-use efficiency.",
        "state": "All India", "level": "central",
        "farmer_categories": ["marginal", "small", "medium"],
        "crops": ["tomato", "chilli", "onion", "cucumber"],
        "min_land": 0.5, "max_land": 1000,
        "benefits": "Up to 55% subsidy for small/marginal farmers on micro-irrigation.",
        "documents": ["Aadhaar", "Land records", "Bank details", "Quotation"],
        "procedure": "Apply via the state horticulture / agriculture department "
                     "under PMKSY.",
        "url": "https://pmksy.gov.in",
        "last_verified": "2025-01", "source": "pmksy.gov.in",
    },
    {
        "name": "Kisan Credit Card (KCC)",
        "description": "Short-term credit for cultivation and allied activities at "
                       "concessional interest.",
        "state": "All India", "level": "central",
        "farmer_categories": ["marginal", "small", "medium", "large"],
        "crops": [], "min_land": 0, "max_land": 1000,
        "benefits": "Low-interest crop loan; interest subvention on timely repayment.",
        "documents": ["Aadhaar", "Land records", "Bank account"],
        "procedure": "Apply at any bank branch or through the KCC portal.",
        "url": "https://www.myscheme.gov.in/schemes/kcc",
        "last_verified": "2025-01", "source": "myscheme.gov.in",
    },
]


def seed(db: Session):
    if db.query(User).first():
        return  # already seeded

    # Admin (government/officer) account
    admin = User(name="Agri Officer", email="admin@agri.gov",
                 hashed_password=hash_password("admin123"), role="admin",
                 mode="farm", language="en", state="Tamil Nadu", district="Chennai")
    db.add(admin)

    # Sample farmer
    farmer = User(name="Ravi Kumar", email="farmer@demo.com",
                  hashed_password=hash_password("demo123"), role="farmer",
                  mode="farm", language="ta", state="Tamil Nadu", district="Coimbatore")
    db.add(farmer)

    # Sample balcony grower
    grower = User(name="Anita", email="balcony@demo.com",
                  hashed_password=hash_password("demo123"), role="balcony",
                  mode="balcony", language="en", state="Karnataka", district="Bengaluru")
    db.add(grower)

    # Sample buyer
    buyer = User(name="Meena Traders", email="buyer@demo.com",
                 hashed_password=hash_password("demo123"), role="buyer",
                 mode="buyer", language="en", state="Tamil Nadu", district="Chennai")
    db.add(buyer)
    db.commit(); db.refresh(farmer); db.refresh(grower); db.refresh(admin); db.refresh(buyer)

    db.add(Farm(user_id=farmer.id, mode="farm", name="Ravi's Farm",
                state="Tamil Nadu", district="Coimbatore", village="Sulur",
                area="2 acres", crop="tomato", variety="Local", growth_stage="flowering",
                soil_type="loamy", irrigation_type="drip", farming_method="conventional",
                device_id="ESP32-001", farmer_category="small", land_size_acres=2.0))
    db.add(Farm(user_id=grower.id, mode="balcony", name="Anita's Balcony",
                location="Bengaluru", crop="chilli", area="12 inch pot",
                growth_stage="vegetative", sunlight="6 hours", growing_medium="potting mix",
                watering_method="manual", device_id="ESP32-002",
                farmer_category="marginal", land_size_acres=0.1))

    # Soil tests (for fertility dashboard)
    db.add(SoilTest(user_id=farmer.id, nitrogen=35, phosphorus=18, potassium=90,
                    ph=6.2, source="manual"))
    db.add(SoilTest(user_id=grower.id, nitrogen=70, phosphorus=40, potassium=60,
                    ph=6.5, source="manual"))

    # Sensor history (simulated, clearly tagged)
    base = datetime.utcnow() - timedelta(hours=12)
    for i in range(24):
        r = simulator.generate("ESP32-001")
        db.add(SensorReading(device_id="ESP32-001", soil_moisture=r["soil_moisture"],
                             temperature=r["temperature"], humidity=r["humidity"],
                             water_level=r["water_level"], water_flow=r["water_flow"],
                             source="simulated", created_at=base + timedelta(minutes=30 * i)))

    # A sample diagnosis (for admin problem stats)
    db.add(PlantDiagnosis(user_id=farmer.id, crop="tomato", image_path="",
                          disease="Early Blight", confidence=0.91, severity="moderate",
                          recommendation="Remove affected leaves; apply fungicide.",
                          uncertain=False))

    # Sample pest reports (for the state-wise admin pest-complaints view)
    db.add(PestObservation(user_id=farmer.id, crop="tomato", pest_name="Fruit borer",
                           confidence=0.86, severity="MODERATE", result_type="pest",
                           recommendation="Install pheromone traps; hand-pick affected fruit."))
    db.add(PestObservation(user_id=farmer.id, crop="tomato", pest_name="Whitefly",
                           confidence=0.78, severity="LOW", result_type="pest",
                           recommendation="Yellow sticky traps; neem-based spray."))

    for s in REAL_SCHEMES:
        db.add(Scheme(**s))
    db.commit()

    # A farmer marking interest in a scheme (for the state-wise "schemes
    # chosen" view — otherwise that panel would always be empty on a fresh
    # install, which looks broken rather than simply unused yet).
    first_scheme = db.query(Scheme).first()
    if first_scheme:
        db.add(SchemeInterest(user_id=farmer.id, scheme_id=first_scheme.id,
                              state=farmer.state))

    # Sample marketplace listings, so the buyer demo account and the admin
    # "most sold crops" / production-trend views have real rows to show
    # instead of an empty page on first run.
    sown = datetime.utcnow() - timedelta(days=100)
    db.add(CropListing(farmer_id=farmer.id, crop="tomato", variety="Local",
                       sowing_date=sown,
                       predicted_maturity_date=sown + timedelta(days=95),
                       maturity_source="lifecycle", intends_to_sell=True,
                       quantity_kg=500, price_per_kg=18.0,
                       state=farmer.state, district=farmer.district, village="Sulur",
                       status="available", farmer_name=farmer.name,
                       contact_phone="9876543210"))
    db.add(CropListing(farmer_id=farmer.id, crop="soybean", variety="JS-335",
                       sowing_date=sown - timedelta(days=20),
                       predicted_maturity_date=sown - timedelta(days=20) + timedelta(days=95),
                       maturity_source="lifecycle", intends_to_sell=True,
                       quantity_kg=1200, price_per_kg=42.0,
                       state=farmer.state, district=farmer.district, village="Sulur",
                       status="sold", farmer_name=farmer.name,
                       contact_phone="9876543210"))

    # Sample expenses, so the demo farmer's Analytics "Spent & earned"
    # dropdown shows a real net figure on first login instead of ₹0 spent
    # (which is honest but looks unfinished for a demo).
    db.add(Expense(user_id=farmer.id, category="seeds", amount=3500,
                   note="Soybean seed (JS-335)", crop="soybean",
                   created_at=sown - timedelta(days=25)))
    db.add(Expense(user_id=farmer.id, category="fertilizer", amount=6200,
                   note="DAP + urea", crop="soybean",
                   created_at=sown - timedelta(days=10)))
    db.add(Expense(user_id=farmer.id, category="labor", amount=4800,
                   note="Sowing and weeding labour", crop="tomato",
                   created_at=sown + timedelta(days=5)))

    db.commit()
    seed_machinery(db, farmer.id)
    seed_vendor_listings(db)
    seed_land_listings(db)
    print("✅ Seeded: admin@agri.gov/admin123, farmer@demo.com/demo123, "
          "balcony@demo.com/demo123, buyer@demo.com/demo123")


# ---------------------------------------------------------------------------
# Demo machinery listings spread across India, so the distance filter has
# something real to sort. Phone numbers are obviously fake demo numbers.
# ---------------------------------------------------------------------------

DEMO_MACHINERY = [
    ("tractor", "Mahindra 575 DI, 47 HP", "Mahindra", 2021, 1400,
     "Madhya Pradesh", "Indore", "Depalpur", 22.85, 75.54, "Ramesh Patidar",
     "9876500001", True, True,
     "Well maintained, regularly serviced. Driver available on request."),
    ("rotavator", "6-feet rotavator, tractor mounted", "Shaktiman", 2022, 1600,
     "Madhya Pradesh", "Indore", "Sanwer", 22.97, 75.83, "Suresh Yadav",
     "9876500002", False, False,
     "Fits 45 HP and above. Blades replaced last season."),
    ("harvester", "Self-propelled combine harvester", "Preet", 2020, 3800,
     "Madhya Pradesh", "Ujjain", "", 23.18, 75.78, "Dinesh Chouhan",
     "9876500003", False, True,
     "Suitable for wheat, soybean and chickpea. Book early for the season."),
    ("seed_drill", "9-tyne seed cum fertiliser drill", "Landforce", 2023, 1100,
     "Madhya Pradesh", "Bhopal", "Berasia", 23.63, 77.43, "Anil Verma",
     "9876500004", False, False,
     "Sows seed and places fertiliser in one pass."),
    ("sprayer", "HTP power sprayer with 100m hose", "Aspee", 2022, 600,
     "Madhya Pradesh", "Dewas", "", 22.96, 76.05, "Prakash Malviya",
     "9876500005", False, False,
     "Includes hose and two spray guns. Please return cleaned."),
    ("laser_leveller", "Laser land leveller with receiver", "KS Group", 2021, 3200,
     "Punjab", "Ludhiana", "", 30.90, 75.85, "Gurpreet Singh",
     "9876500006", False, True,
     "Operator included. Levels roughly 2 acres a day."),
    ("happy_seeder", "Happy Seeder for wheat after paddy", "Amar", 2023, 2800,
     "Punjab", "Patiala", "", 30.34, 76.38, "Jaswinder Singh",
     "9876500007", False, True,
     "Sows straight into paddy stubble. No burning needed."),
    ("drone_sprayer", "10L agricultural spray drone", "Garuda", 2024, 4500,
     "Maharashtra", "Nashik", "", 19.99, 73.79, "Sandeep Pawar",
     "9876500008", False, True,
     "Trained pilot included. Covers around 20 acres a day."),
    ("thresher", "Multi-crop thresher", "Dasmesh", 2019, 1200,
     "Uttar Pradesh", "Meerut", "", 28.98, 77.70, "Rakesh Kumar",
     "9876500009", False, False,
     "Handles wheat, gram and mustard."),
    ("power_tiller", "13 HP power tiller", "VST Shakti", 2022, 750,
     "Tamil Nadu", "Thanjavur", "", 10.79, 79.14, "Murugan S",
     "9876500010", False, False,
     "Ideal for wet paddy fields and small plots."),
    ("water_pump", "5 HP diesel pump set", "Kirloskar", 2020, 500,
     "Karnataka", "Belagavi", "", 15.85, 74.50, "Basavaraj H",
     "9876500011", False, False,
     "Includes 20 feet suction pipe."),
    ("trolley", "Hydraulic tractor trolley, 5 tonne", "Local", 2021, 900,
     "Rajasthan", "Kota", "", 25.21, 75.86, "Mahesh Sharma",
     "9876500012", False, False,
     "Hydraulic tipping. Good for mandi transport."),
    ("baler", "Round straw baler", "New Holland", 2022, 3500,
     "Haryana", "Karnal", "", 29.69, 76.99, "Satbir Dhaka",
     "9876500013", False, True,
     "Makes round bales. Ideal after combine harvest."),
    ("cultivator", "9-tyne spring cultivator", "Fieldking", 2021, 850,
     "Gujarat", "Rajkot", "", 22.30, 70.80, "Bharat Patel",
     "9876500014", False, False,
     "Good for pre-sowing tillage and weeding."),
]


def seed_machinery(db: Session, owner_id: int):
    """Demo listings. Skipped entirely once any listing exists."""
    if db.query(MachineryListing).count() > 0:
        return

    for (key, title, brand, year, rate, state, district, village,
         lat, lon, owner, phone, fuel, operator, desc) in DEMO_MACHINERY:
        db.add(MachineryListing(
            owner_id=owner_id, machine_key=key, title=title, brand=brand,
            model_year=year, daily_rate=rate, state=state, district=district,
            village=village, latitude=lat, longitude=lon, owner_name=owner,
            contact_phone=phone, fuel_included=fuel,
            operator_included=operator, description=desc,
            condition="good", available=True))
    db.commit()
    print(f"Seeded {len(DEMO_MACHINERY)} demo machinery listings")


# 10 vendor profiles x 5 crops = 50 listings, spread across states so the
# buyer's crop-icon grid ("same crop, different states") has something real
# to show on first run. Each vendor is a genuine User row (role=farmer), so
# contact-reveal, interest requests and everything else work exactly like a
# listing any real farmer created — no special-cased demo behaviour.
VENDOR_PROFILES = [
    ("Tamil Nadu", "Coimbatore", "Suresh Kumar", "9900000001"),
    ("Karnataka", "Mysuru", "Ravi Gowda", "9900000002"),
    ("Maharashtra", "Nashik", "Vikram Patil", "9900000003"),
    ("Punjab", "Ludhiana", "Gurpreet Singh", "9900000004"),
    ("Madhya Pradesh", "Indore", "Ramesh Yadav", "9900000005"),
    ("Uttar Pradesh", "Meerut", "Ajay Chaudhary", "9900000006"),
    ("Andhra Pradesh", "Guntur", "Venkatesh Reddy", "9900000007"),
    ("Gujarat", "Rajkot", "Bharat Patel", "9900000008"),
    ("Rajasthan", "Jaipur", "Om Prakash", "9900000009"),
    ("West Bengal", "Nadia", "Bimal Das", "9900000010"),
]
VENDOR_CROPS = ["tomato", "onion", "potato", "wheat", "rice"]
VARIETY_CYCLE = ["Local", "Hybrid", "Organic", "Desi", "Grade-A"]
# Only wheat is in lifecycle.py's supported set (soybean/wheat/chickpea/
# maize/cotton) — the rest use a farmer-estimated typical cycle length,
# honestly tagged maturity_source="farmer" rather than claiming a lifecycle
# calculation we don't actually have for these crops.
TYPICAL_CYCLE_DAYS = {"tomato": 75, "onion": 110, "potato": 90, "wheat": 130, "rice": 120}


def seed_vendor_listings(db: Session):
    """50 hardcoded vendor produce listings for the buyer marketplace's
    crop-icon browsing grid. Skipped once enough listings already exist, so
    re-running the seed script is safe."""
    if db.query(CropListing).count() >= 50:
        return

    now = datetime.utcnow()
    total = 0
    for v_idx, (state, district, name, phone) in enumerate(VENDOR_PROFILES):
        email = f"vendor{v_idx + 1}@marketplace.demo"
        vendor = db.query(User).filter(User.email == email).first()
        if not vendor:
            vendor = User(name=name, email=email,
                          hashed_password=hash_password("vendor123"), role="farmer",
                          mode="farm", language="en", state=state, district=district)
            db.add(vendor); db.commit(); db.refresh(vendor)

        for c_idx, crop in enumerate(VENDOR_CROPS):
            variety = VARIETY_CYCLE[(v_idx + c_idx) % len(VARIETY_CYCLE)]
            sowing = now - timedelta(days=20 + c_idx * 15)
            maturity = sowing + timedelta(days=TYPICAL_CYCLE_DAYS.get(crop, 100))
            status = "available" if maturity <= now else "growing"
            qty = 200 + (v_idx * 37 + c_idx * 19) % 600
            price = round(8.5 + (v_idx * 3 + c_idx * 5) % 40, 2)

            db.add(CropListing(
                farmer_id=vendor.id, crop=crop, variety=variety,
                sowing_date=sowing, predicted_maturity_date=maturity,
                maturity_source="lifecycle" if crop == "wheat" else "farmer",
                intends_to_sell=True, quantity_kg=qty, price_per_kg=price,
                state=state, district=district, village="",
                status=status, farmer_name=name, contact_phone=phone,
            ))
            total += 1
    db.commit()
    print(f"Seeded {total} demo vendor produce listings across {len(VENDOR_PROFILES)} states")


DEMO_LAND = [
    ("Tamil Nadu", "Coimbatore", "Thondamuthur", 5.0, "Red", "Borewell", True, ["Tomato", "Onion"], 12000, "9876543210", 11.0, 76.9),
    ("Karnataka", "Mysuru", "Nanjangud", 12.5, "Black", "Canal", True, ["Cotton"], 15000, "9900000002", 12.3, 76.6),
    ("Maharashtra", "Nashik", "Niphad", 3.0, "Loamy", "Rainfed", False, ["Onion", "Grapes"], 18000, "9900000003", 20.0, 74.1),
    ("Punjab", "Ludhiana", "Jagraon", 8.0, "Alluvial", "Canal", True, ["Wheat", "Rice"], 14000, "9900000004", 30.7, 75.4),
]

def seed_land_listings(db: Session):
    """Seed demo land listings for the new Land Contractors feature."""
    if db.query(LandListing).count() > 0:
        return

    farmer = db.query(User).filter(User.role == "farmer").first()
    buyer = db.query(User).filter(User.role == "buyer").first()
    if not farmer:
        return

    count = 0
    for state, district, village, acreage, soil, water, irr, crops, price, phone, lat, lon in DEMO_LAND:
        listing = LandListing(
            farmer_id=farmer.id,
            state=state,
            district=district,
            village=village,
            area_acres=acreage,
            soil_type=soil,
            water_source=water,
            irrigation_available=irr,
            suitable_crops=crops,
            price_per_acre_per_season=price,
            contact_phone=phone,
            latitude=lat,
            longitude=lon,
            status="available"
        )
        db.add(listing)
        count += 1
    db.commit()

    # Create one dummy contract for the buyer to see
    if count > 0 and buyer:
        first_listing = db.query(LandListing).first()
        if first_listing:
            first_listing.status = "rented"
            contract = LandContract(
                listing_id=first_listing.id,
                buyer_id=buyer.id,
                farmer_id=first_listing.farmer_id,
                start_date=datetime.utcnow(),
                end_date=datetime.utcnow() + timedelta(days=180),
                agreed_crop=first_listing.suitable_crops[0] if first_listing.suitable_crops else "Unknown",
                price_per_acre=first_listing.price_per_acre_per_season,
                total_price=first_listing.price_per_acre_per_season * first_listing.area_acres * 2, # Assuming 2 seasons
                status="active",
                terms_accepted=True,
                buyer_notes="Buyer gets all produce grown during this period."
            )
            db.add(contract)
            db.commit()

    print(f"Seeded {count} demo land listings and 1 contract.")


