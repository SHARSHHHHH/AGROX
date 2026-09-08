"""Database models. PostgreSQL-compatible; runs on SQLite for dev."""
from datetime import datetime
from sqlalchemy import (Column, Integer, String, Float, Boolean, DateTime,
                        ForeignKey, Text, JSON)
from sqlalchemy.orm import relationship
from app.database.db import Base


def now():
    return datetime.utcnow()


class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    email = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    role = Column(String, default="farmer")          # farmer | balcony | buyer | admin
    mode = Column(String, default="farm")             # farm | balcony
    language = Column(String, default="en")
    state = Column(String, default="")
    district = Column(String, default="")
    created_at = Column(DateTime, default=now)
    updated_at = Column(DateTime, default=now, onupdate=now)

    farms = relationship("Farm", back_populates="owner", cascade="all, delete")
    diagnoses = relationship("PlantDiagnosis", back_populates="user", cascade="all, delete")
    alerts = relationship("Alert", back_populates="user", cascade="all, delete")
    machinery_listings = relationship("MachineryListing", back_populates="owner",
                                      cascade="all, delete")


class Farm(Base):
    __tablename__ = "farms"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    mode = Column(String, default="farm")
    name = Column(String, default="")
    location = Column(String, default="")
    state = Column(String, default="")
    district = Column(String, default="")
    village = Column(String, default="")
    area = Column(String, default="")                 # farm area OR container size
    crop = Column(String, default="")
    variety = Column(String, default="")
    growth_stage = Column(String, default="")
    soil_type = Column(String, default="")
    irrigation_type = Column(String, default="")
    farming_method = Column(String, default="")
    sunlight = Column(String, default="")             # balcony
    growing_medium = Column(String, default="")       # balcony
    watering_method = Column(String, default="")      # balcony
    device_id = Column(String, default="")
    farmer_category = Column(String, default="small") # small | marginal | medium | large
    land_size_acres = Column(Float, default=1.0)

    # --- onboarding additions ---------------------------------------
    # Crop rotation needs history. Without previous_crop the recommender
    # cannot avoid suggesting the same family two seasons running.
    previous_crop = Column(String, default="")
    previous_season = Column(String, default="")      # kharif | rabi | zaid
    # Sowing date makes the lifecycle stage computable automatically.
    # Without it, someone has to type the growth stage by hand every time.
    sowing_date = Column(DateTime, nullable=True)
    water_source = Column(String, default="")         # borewell | canal | rainfed | tank
    latitude = Column(Float, nullable=True)
    longitude = Column(Float, nullable=True)
    # --- previous crop detail (spec 2B) ------------------------------
    # Rotation advice is only as good as what we know about the last crop.
    # Season alone cannot tell us whether it was harvested last week or eight
    # months ago, and that changes what can realistically be sown next.
    previous_variety = Column(String, default="")
    previous_sowing_date = Column(DateTime, nullable=True)
    previous_harvest_date = Column(DateTime, nullable=True)
    previous_yield_qtl = Column(Float, nullable=True)      # quintals total
    previous_problems = Column(Text, default="")           # pests, disease, etc.

    # --- current crop detail (spec 2C) --------------------------------
    # Crop area is separate from land_size_acres: a farmer with 4 acres may
    # have sown only 1.5 of them, and fertiliser quantities computed from the
    # whole holding would be nearly three times too high.
    crop_area_acres = Column(Float, nullable=True)
    expected_harvest_date = Column(DateTime, nullable=True)

    # --- land / water (spec 2A) ---------------------------------------
    # Stored as entered plus its unit, rather than silently converting, so the
    # farmer always sees back the number they typed.
    area_unit = Column(String, default="acre")             # acre | hectare
    water_availability = Column(String, default="")        # abundant|adequate|limited|scarce

    onboarded = Column(Boolean, default=False)

    created_at = Column(DateTime, default=now)
    updated_at = Column(DateTime, default=now, onupdate=now)

    owner = relationship("User", back_populates="farms")


class SensorReading(Base):
    __tablename__ = "sensor_readings"
    id = Column(Integer, primary_key=True, index=True)
    device_id = Column(String, index=True)
    soil_moisture = Column(Float)
    temperature = Column(Float)
    humidity = Column(Float)
    water_level = Column(Float)
    water_flow = Column(Float, default=0)
    source = Column(String, default="simulated")      # simulated | esp32
    created_at = Column(DateTime, default=now, index=True)


class SoilTest(Base):
    __tablename__ = "soil_tests"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    nitrogen = Column(Float)
    phosphorus = Column(Float)
    potassium = Column(Float)
    ph = Column(Float)
    ec = Column(Float, default=0)
    source = Column(String, default="manual")
    created_at = Column(DateTime, default=now)


class PlantDiagnosis(Base):
    __tablename__ = "plant_diagnoses"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    crop = Column(String)
    image_path = Column(String)
    disease = Column(String)
    confidence = Column(Float)
    severity = Column(String, default="unknown")
    recommendation = Column(Text)
    uncertain = Column(Boolean, default=False)
    created_at = Column(DateTime, default=now)

    user = relationship("User", back_populates="diagnoses")


class PestObservation(Base):
    """A pest analysis record. Mirrors PlantDiagnosis but for the pest ->
    severity -> IPM pipeline. Stores the grounded outputs so history and the
    admin/analytics views can aggregate pest problems over time."""
    __tablename__ = "pest_observations"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    crop = Column(String, default="")
    image_path = Column(String, default="")
    pest_name = Column(String, default="")
    confidence = Column(Float, default=0.0)
    severity = Column(String, default="UNKNOWN")     # LOW | MODERATE | HIGH | UNKNOWN
    result_type = Column(String, default="pest")      # pest | disease | healthy | uncertain
    recommendation = Column(Text, default="")         # sustainable summary
    ipm = Column(JSON)                                # full grounded IPM plan
    uncertain = Column(Boolean, default=False)
    created_at = Column(DateTime, default=now, index=True)

    user = relationship("User")


class MachineryListing(Base):
    """A machine one farmer is offering to rent out to others.

    PRIVACY: `contact_phone` is personal data. It is stored so renters can get
    in touch, but it is only ever returned to an authenticated user, and only
    through the explicit /contact endpoint — never in the browse listing.
    """
    __tablename__ = "machinery_listings"
    id = Column(Integer, primary_key=True, index=True)
    owner_id = Column(Integer, ForeignKey("users.id"))

    machine_key = Column(String, index=True)     # matches MACHINERY_KB
    title = Column(String, default="")
    brand = Column(String, default="")
    model_year = Column(Integer, nullable=True)
    description = Column(Text, default="")
    condition = Column(String, default="good")   # excellent | good | fair

    daily_rate = Column(Float, default=0.0)      # INR per day
    hourly_rate = Column(Float, nullable=True)
    fuel_included = Column(Boolean, default=False)
    operator_included = Column(Boolean, default=False)
    min_days = Column(Integer, default=1)

    owner_name = Column(String, default="")
    contact_phone = Column(String, default="")   # PII, gated
    state = Column(String, index=True, default="")
    district = Column(String, index=True, default="")
    village = Column(String, default="")
    latitude = Column(Float, nullable=True)
    longitude = Column(Float, nullable=True)

    image_path = Column(String, default="")
    available = Column(Boolean, default=True)
    views = Column(Integer, default=0)
    contact_requests = Column(Integer, default=0)

    created_at = Column(DateTime, default=now, index=True)
    updated_at = Column(DateTime, default=now, onupdate=now)

    owner = relationship("User", back_populates="machinery_listings")


class Scheme(Base):
    __tablename__ = "schemes"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String)
    description = Column(Text)
    state = Column(String, default="All India")
    level = Column(String, default="central")         # central | state
    farmer_categories = Column(JSON)                  # list
    crops = Column(JSON)                              # list, [] = all
    min_land = Column(Float, default=0)
    max_land = Column(Float, default=1000)
    benefits = Column(Text)
    documents = Column(JSON)
    procedure = Column(Text)
    url = Column(String)
    last_verified = Column(String, default="")
    source = Column(String, default="")


class Alert(Base):
    __tablename__ = "alerts"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    type = Column(String, index=True)
    severity = Column(String, default="INFO")         # INFO | WARNING | CRITICAL
    title = Column(String)
    message = Column(Text)
    read = Column(Boolean, default=False)
    created_at = Column(DateTime, default=now, index=True)

    # --- structure (kept additive; `severity` stays for older clients) ---
    # priority is the field the UI sorts and filters on. severity is retained
    # because existing code and tests still write and read it.
    priority = Column(String, default="MEDIUM")       # CRITICAL|HIGH|MEDIUM|LOW
    category = Column(String, default="general", index=True)
    # irrigation | water_tank | weather | pest_nearby | scheme | disaster |
    # compensation | supplies | machinery | lifecycle | satellite | soil

    # "What should I actually do?" — separated from the message so the UI can
    # give it its own emphasis, and so an alert with no action is obvious.
    action = Column(Text, default="")

    # Provenance. Mandatory in practice for anything sourced from outside the
    # farm: a compensation figure with no link is not usable by a farmer
    # standing in a government office.
    source_name = Column(String, default="")
    source_url = Column(String, default="")
    source_date = Column(DateTime, nullable=True)

    # DEDUPLICATION.
    # The old check was `same type AND unread`, which meant that the moment a
    # farmer marked an alert read it regenerated on the next poll — the same
    # sentence, forever, until they stopped reading alerts at all.
    #
    # dedupe_key describes the SITUATION, not the type: it includes the day,
    # the value bucket, the district, whatever makes this occurrence distinct.
    # A new alert is only created when no unexpired alert shares the key,
    # whether or not the old one was read.
    dedupe_key = Column(String, index=True, default="")
    expires_at = Column(DateTime, nullable=True, index=True)

    # Dismiss is distinct from read: read means "I saw it", dismissed means
    # "stop showing me this". Only dismissed alerts leave the list.
    dismissed = Column(Boolean, default=False)
    dismissed_at = Column(DateTime, nullable=True)

    # Structured extras the UI can render (links, amounts, distances).
    payload = Column(JSON, default=dict)

    user = relationship("User", back_populates="alerts")


class ExternalAdvisory(Base):
    """Government / official information, entered by an admin.

    WHY ADMIN-CURATED RATHER THAN SCRAPED
    -------------------------------------
    IMD, CWC and state disaster portals publish HTML pages and PDFs, not clean
    JSON APIs. A scraper against them breaks silently on any layout change —
    and a flood alert that has silently stopped working is far more dangerous
    than one that was never built, because the farmer has learned to rely on it.

    So a human enters it, and every row must carry its source. The rule engine
    reads only from this table, never from a model, so a compensation amount
    can be traced to a URL and a date.

    EXTENSIBILITY
    -------------
    `ingested_by` distinguishes 'admin' from a future 'api:imd' or 'api:cwc'.
    When a real feed appears, it writes rows here in the same shape and nothing
    downstream changes.
    """
    __tablename__ = "external_advisories"
    id = Column(Integer, primary_key=True, index=True)

    kind = Column(String, index=True)      # scheme | flood | compensation |
                                           # disaster | supplies
    title = Column(String)
    summary = Column(Text, default="")
    action = Column(Text, default="")

    # Matching. Empty means "applies everywhere / to every crop".
    state = Column(String, default="", index=True)
    districts = Column(JSON, default=list)          # list[str]
    crops = Column(JSON, default=list)              # list[str]

    # Money, where an official figure was announced. Never inferred.
    amount = Column(Float, nullable=True)
    amount_unit = Column(String, default="")        # "per acre", "per hectare"
    amount_note = Column(Text, default="")

    # Provenance is not optional for this table.
    source_name = Column(String)                    # "IMD", "CWC", "PMFBY"
    source_url = Column(String)
    published_on = Column(DateTime, nullable=True)

    severity = Column(String, default="INFO")
    priority = Column(String, default="MEDIUM")
    active = Column(Boolean, default=True, index=True)
    expires_at = Column(DateTime, nullable=True, index=True)

    ingested_by = Column(String, default="admin")   # admin | api:imd | api:cwc
    created_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, default=now, index=True)


class SupplyOffer(Base):
    """Fertiliser / manure / input offers from verified sellers.

    The spec asked for existing marketplace data, but this project's
    marketplace (CropListing) sells PRODUCE from farmers to buyers — the
    opposite direction. There was no structure for inputs flowing to farmers,
    so this is the "simple seller/admin offer structure" rather than scraping
    random websites for prices nobody can verify.

    `verified` is set by an admin. Only verified offers reach alerts: an
    unverified fertiliser price pushed to farmers is an advertisement we cannot
    stand behind.
    """
    __tablename__ = "supply_offers"
    id = Column(Integer, primary_key=True, index=True)
    seller_id = Column(Integer, ForeignKey("users.id"), nullable=True)

    title = Column(String)
    category = Column(String, default="fertilizer", index=True)
    # fertilizer | manure | compost | seed | bio_input | pesticide
    description = Column(Text, default="")
    brand = Column(String, default="")

    price = Column(Float, nullable=True)
    price_unit = Column(String, default="per bag")   # per bag | per kg | per tonne
    quantity_available = Column(String, default="")

    seller_name = Column(String, default="")
    contact_phone = Column(String, default="")
    state = Column(String, default="", index=True)
    district = Column(String, default="", index=True)
    village = Column(String, default="")

    # Admin-checked. Unverified offers never reach an alert.
    verified = Column(Boolean, default=False, index=True)
    verified_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    active = Column(Boolean, default=True, index=True)
    expires_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=now, index=True)


class Livestock(Base):
    """Cattle on a farm. The feedstock side of the circular farming module.

    Deliberately simple: counts by type, not per-animal records. A farmer
    completing a setup wizard will answer "4 cows, 2 buffalo"; asking for
    breed, age and yield per animal would stop most of them finishing, and
    none of that detail changes a dung estimate.
    """
    __tablename__ = "livestock"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), index=True)
    farm_id = Column(Integer, ForeignKey("farms.id"), nullable=True)

    animal_type = Column(String, default="cow")
    # cow | buffalo | bullock | goat | poultry
    count = Column(Integer, default=0)

    # Farmer's own estimate, when they know it. Otherwise the service derives
    # one from typical per-animal figures — and labels which was used.
    dung_kg_per_day = Column(Float, nullable=True)
    collection_regular = Column(Boolean, default=True)
    housing = Column(String, default="")        # shed | open | mixed
    notes = Column(Text, default="")

    created_at = Column(DateTime, default=now)
    updated_at = Column(DateTime, default=now, onupdate=now)

    user = relationship("User")


class BiogasAssessment(Base):
    """A stored feasibility assessment and set of ESTIMATES for one farm.

    Every numeric field here is an estimate derived from farmer-entered
    figures and published typical yields. None of it is measured. The column
    names say so, and the API returns them wrapped with that caveat, because
    a farmer who reads "produces 2.4 m3/day" as a guarantee may spend real
    money on a plant that under-delivers.
    """
    __tablename__ = "biogas_assessments"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), index=True)

    # Inputs captured at assessment time, so a stored result can be explained
    # later even if the farm record has since changed.
    total_dung_kg_per_day = Column(Float, default=0)
    residue_kg_available = Column(Float, default=0)
    water_availability = Column(String, default="")
    space_available_m2 = Column(Float, nullable=True)

    verdict = Column(String, default="")        # SUITABLE | POSSIBLE | NOT_YET
    verdict_reason = Column(Text, default="")
    blockers = Column(JSON, default=list)

    est_daily_feed_kg = Column(Float, default=0)
    est_biogas_m3_per_day = Column(Float, default=0)
    est_plant_size_m3 = Column(Float, nullable=True)
    est_digestate_kg_per_day = Column(Float, default=0)
    est_digestate_kg_per_month = Column(Float, default=0)

    assumptions = Column(JSON, default=dict)
    created_at = Column(DateTime, default=now, index=True)

    user = relationship("User")


class DigestateAllocation(Base):
    """How much digestate the farmer keeps versus offers to others.

    Surplus is never stored — it is always total minus reserved, computed on
    read. Storing it would let the three numbers drift out of agreement after
    any edit.
    """
    __tablename__ = "digestate_allocations"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), index=True)

    period = Column(String, default="")             # "2026-09"
    total_available_kg = Column(Float, default=0)
    reserved_own_farm_kg = Column(Float, default=0)
    allocation_note = Column(Text, default="")

    created_at = Column(DateTime, default=now)
    updated_at = Column(DateTime, default=now, onupdate=now)

    user = relationship("User")


class CropResidueRecord(Base):
    """Residue from one harvest, and the route the farmer chose for it.

    Routes are deliberately plural. Burning residue is the problem this module
    exists to reduce, but pushing every last kilo into a digester is also
    wrong — some residue is worth more left on the soil as mulch than fed to
    a plant that cannot digest it well.
    """
    __tablename__ = "crop_residue_records"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), index=True)

    crop = Column(String, default="")
    area_acres = Column(Float, nullable=True)
    est_residue_kg = Column(Float, default=0)
    harvest_date = Column(DateTime, nullable=True)

    chosen_route = Column(String, default="")
    # biogas | compost | mulch | soil_incorporation | fodder | sell
    route_note = Column(Text, default="")
    recommended_route = Column(String, default="")

    created_at = Column(DateTime, default=now, index=True)

    user = relationship("User")


class BiogasTechnician(Base):
    """A trained biogas installer or service provider.

    The gap this closes: the app can tell a farmer a 3 m3 plant suits their
    farm, and then leave them with no idea who builds one. Sizing advice with
    no route to installation is where most of these tools stop being useful.

    Entries are admin-entered and `verified` before being shown, for the same
    reason supply offers are: sending a farmer to an unchecked contractor for
    gas-carrying pressure work is not something to do casually.
    """
    __tablename__ = "biogas_technicians"
    id = Column(Integer, primary_key=True, index=True)

    name = Column(String)
    organisation = Column(String, default="")
    phone = Column(String, default="")

    state = Column(String, default="", index=True)
    district = Column(String, default="", index=True)
    village = Column(String, default="")
    latitude = Column(Float, nullable=True)
    longitude = Column(Float, nullable=True)

    services = Column(JSON, default=list)
    # survey | construction | installation | repair | training | subsidy_help
    plant_types = Column(JSON, default=list)     # KVIC | Deenbandhu | prefab
    size_range_m3 = Column(String, default="")
    years_experience = Column(Integer, nullable=True)
    notes = Column(Text, default="")

    # Admin-checked. Gas piping and pressure work are safety-critical.
    verified = Column(Boolean, default=False, index=True)
    active = Column(Boolean, default=True, index=True)
    created_at = Column(DateTime, default=now)


class BiogasPlant(Base):
    """A biogas plant the farmer already owns."""
    __tablename__ = "biogas_plants"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), index=True)

    size_m3 = Column(Float, nullable=True)
    plant_type = Column(String, default="")        # KVIC | Deenbandhu | prefab
    installed_on = Column(DateTime, nullable=True)

    # 'manual' means the farmer types a daily reading; 'sensor' means a device
    # posts them. Manual is the default because almost no small plant in India
    # has instrumentation, and requiring sensors would exclude everyone.
    monitoring_mode = Column(String, default="manual")
    device_id = Column(String, default="")

    active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=now)

    user = relationship("User")


class BiogasLog(Base):
    """One day's reading from a plant, entered by hand or posted by a device.

    Every field is nullable. A farmer who only knows "I fed it and the gas was
    weak today" should still be able to record that — demanding temperature
    and pressure would mean no logs at all.
    """
    __tablename__ = "biogas_logs"
    id = Column(Integer, primary_key=True, index=True)
    plant_id = Column(Integer, ForeignKey("biogas_plants.id"), index=True)
    user_id = Column(Integer, ForeignKey("users.id"), index=True)

    logged_on = Column(String, index=True)         # ISO yyyy-mm-dd
    feed_kg = Column(Float, nullable=True)
    water_litres = Column(Float, nullable=True)
    slurry_out_kg = Column(Float, nullable=True)

    # What the farmer can actually judge without instruments.
    gas_level = Column(String, default="")         # good | low | none
    flame_quality = Column(String, default="")     # strong | weak | none
    smell = Column(String, default="")             # normal | sour | rotten

    # Sensor-only, left empty on manual logs.
    temperature_c = Column(Float, nullable=True)
    pressure_cm = Column(Float, nullable=True)
    ph = Column(Float, nullable=True)
    gas_m3 = Column(Float, nullable=True)

    source = Column(String, default="manual")      # manual | sensor
    note = Column(Text, default="")
    created_at = Column(DateTime, default=now, index=True)


class PushSubscription(Base):
    """A browser push endpoint for one user's device.

    Deliberately generic: `channel` is 'web_push' today, and 'sms' or
    'whatsapp' rows can sit in the same table later with the address in
    `endpoint`. That keeps the notification dispatcher unchanged when those
    arrive — it already loops over channels.
    """
    __tablename__ = "push_subscriptions"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), index=True)
    channel = Column(String, default="web_push")    # web_push | sms | whatsapp
    endpoint = Column(Text)                         # URL, or phone number
    p256dh = Column(String, default="")             # web push only
    auth = Column(String, default="")               # web push only
    user_agent = Column(String, default="")
    active = Column(Boolean, default=True)
    # Minimum priority worth interrupting someone for. A farmer who gets a
    # push for every INFO alert turns notifications off within a week.
    min_priority = Column(String, default="HIGH")
    last_sent_at = Column(DateTime, nullable=True)
    failure_count = Column(Integer, default=0)
    created_at = Column(DateTime, default=now)

    user = relationship("User")


class IrrigationEvent(Base):
    __tablename__ = "irrigation_events"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    duration_min = Column(Float)
    reason = Column(Text)
    created_at = Column(DateTime, default=now, index=True)


class ChatMessage(Base):
    __tablename__ = "chat_messages"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    role = Column(String)                             # user | assistant
    content = Column(Text)
    language = Column(String, default="en")
    created_at = Column(DateTime, default=now)


class CropListing(Base):
    """A farmer's produce, offered for direct sale to buyers through the app.

    The predicted maturity date is computed from the crop lifecycle service
    (see lifecycle.py) applied to the sowing date — the same static,
    stage-by-stage agronomic data already used on the Crop Advisor page, not
    an invented figure. A farmer can adjust it if their crop is running
    ahead of or behind the typical schedule for their variety/season.
    """
    __tablename__ = "crop_listings"
    id = Column(Integer, primary_key=True, index=True)
    farmer_id = Column(Integer, ForeignKey("users.id"))

    crop = Column(String, index=True, default="")
    variety = Column(String, default="")
    sowing_date = Column(DateTime, nullable=True)
    predicted_maturity_date = Column(DateTime, nullable=True)
    maturity_source = Column(String, default="")      # "lifecycle" | "farmer" | ""

    # --- what kind of thing is being sold ----------------------------
    # A farmer composting dung ends up with a saleable product that is not
    # produce. It goes through the same listing table because a buyer wants
    # one place to look and a farmer wants one place to manage what they
    # have offered — but the two must not be silently mixed up, so every
    # listing says which it is.
    #
    #   "produce"    — a crop, with a sowing date and a predicted harvest
    #   "fertilizer" — compost, vermicompost, FYM or slurry from the
    #                  Circular Farming module
    product_type = Column(String, default="produce", index=True)
    # The farmer's own name for the fertiliser ("Vermicompost", "Desi khaad").
    # Kept separate from `crop` so buyer search on crops is not polluted.
    product_name = Column(String, default="")
    # Where the listing came from, so the sell flow can be traced back and a
    # compost listing is not mistaken for something typed in by hand.
    source = Column(String, default="")               # "" | "circular_farming"

    intends_to_sell = Column(Boolean, default=False)
    quantity_kg = Column(Float, nullable=True)
    price_per_kg = Column(Float, nullable=True)

    state = Column(String, index=True, default="")
    district = Column(String, index=True, default="")
    village = Column(String, default="")

    # growing (not for sale yet) | available (ready / listed) |
    # reserved (a buyer's request accepted) | sold | withdrawn
    status = Column(String, default="growing", index=True)
    farmer_name = Column(String, default="")
    contact_phone = Column(String, default="")         # PII, gated like MachineryListing

    views = Column(Integer, default=0)
    image_path = Column(String, default="")            # photo the farmer uploaded, if any

    created_at = Column(DateTime, default=now, index=True)
    updated_at = Column(DateTime, default=now, onupdate=now)

    farmer = relationship("User")


class ProduceOrder(Base):
    """A buyer's request against a CropListing.

    This connects a buyer to a farmer and records the terms they agreed on
    — it is not a payment system; money and delivery are arranged directly
    between the two, the same way MachineryListing's contact-request flow
    works.
    """
    __tablename__ = "produce_orders"
    id = Column(Integer, primary_key=True, index=True)
    listing_id = Column(Integer, ForeignKey("crop_listings.id"))
    buyer_id = Column(Integer, ForeignKey("users.id"))
    quantity_kg = Column(Float, nullable=True)
    message = Column(Text, default="")
    status = Column(String, default="requested")   # requested | confirmed | declined | completed
    created_at = Column(DateTime, default=now, index=True)
    updated_at = Column(DateTime, default=now, onupdate=now)

    listing = relationship("CropListing")
    buyer = relationship("User")


class SchemeInterest(Base):
    """Records that a farmer marked a government scheme as one they intend
    to apply for. This is what lets the state-wise admin view report which
    schemes farmers are actually choosing, rather than only which they are
    eligible for."""
    __tablename__ = "scheme_interests"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    scheme_id = Column(Integer, ForeignKey("schemes.id"))
    state = Column(String, default="")
    created_at = Column(DateTime, default=now, index=True)

    user = relationship("User")
    scheme = relationship("Scheme")


class Expense(Base):
    """A farming expense the farmer logged themselves (seeds, fertiliser,
    labour, machinery hire, etc.) — this is what lets Analytics show real
    "spent vs earned" figures instead of inventing a number. "Earned" comes
    from CropListing sales; there is no separate income model."""
    __tablename__ = "expenses"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    category = Column(String, default="other")   # seeds | fertilizer | labor | machinery | other
    amount = Column(Float, default=0)
    note = Column(String, default="")
    crop = Column(String, default="")
    created_at = Column(DateTime, default=now, index=True)

    user = relationship("User")


class AdminAction(Base):
    """A human-in-the-loop admin action: the platform PROPOSES something
    (e.g. "send a pest advisory to affected farmers") based on real,
    queryable data, and an admin explicitly approves or rejects it before
    anything happens.

    This is a prototype workflow — the platform has no notification/SMS
    system, so an "approved" action is recorded as a decision, not actually
    sent anywhere. That limitation is surfaced in the API response, never
    hidden.
    """
    __tablename__ = "admin_actions"
    id = Column(Integer, primary_key=True, index=True)
    action_type = Column(String, default="")        # pest_advisory | irrigation_support | ...
    title = Column(String, default="")
    description = Column(Text, default="")
    state = Column(String, default="")
    district = Column(String, default="")
    crop = Column(String, default="")
    affected_count = Column(Integer, default=0)
    reasoning = Column(JSON)                         # list[str] — the "why"
    status = Column(String, default="proposed")      # proposed | approved | rejected
    proposed_at = Column(DateTime, default=now, index=True)
    decided_at = Column(DateTime, nullable=True)
    decided_by_id = Column(Integer, ForeignKey("users.id"), nullable=True)

    decided_by = relationship("User")

class SatelliteObservation(Base):
    """One Sentinel-2 NDVI observation over one farmer's field.

    WHY THIS TABLE EXISTS
    ---------------------
    Two things need history that a request-scoped cache cannot provide:

      1. CHANGE DETECTION. "NDVI fell 0.18 since the last pass" is the single
         most actionable satellite signal there is, and it is impossible to
         compute from one reading. Storing each distinct observation date gives
         it to us for free.
      2. ANALYTICS. The season curve on the Analytics page and the anomaly
         evidence on the Schemes page both read from here, so opening those
         pages costs no Earth Engine quota at all.

    WHAT IS NOT STORED
    ------------------
    No imagery. Each row is a handful of floats plus a date. A field observed
    every five days for a full year is a few hundred rows of numbers.

    Rows are keyed by (user, observation date, rounded coordinates), so
    re-querying the same pass updates in place instead of duplicating.
    """
    __tablename__ = "satellite_observations"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), index=True)

    latitude = Column(Float)
    longitude = Column(Float)
    buffer_m = Column(Integer, default=100)

    observed_on = Column(String, index=True)          # ISO yyyy-mm-dd
    satellite = Column(String, default="Sentinel-2")
    tile = Column(String, default="")

    ndvi = Column(Float)
    ndvi_min = Column(Float)
    ndvi_max = Column(Float)
    ndvi_stddev = Column(Float)
    ndvi_p25 = Column(Float)
    ndvi_median = Column(Float)
    ndvi_p75 = Column(Float)

    ndmi = Column(Float, nullable=True)
    ndre = Column(Float, nullable=True)
    evi = Column(Float, nullable=True)
    savi = Column(Float, nullable=True)
    bsi = Column(Float, nullable=True)

    scene_cloud_pct = Column(Float, nullable=True)
    clear_pixel_fraction = Column(Float, nullable=True)

    # Crop context at observation time, so a later comparison against the
    # growth curve does not need to guess what was in the ground back then.
    crop = Column(String, default="")
    days_after_sowing = Column(Integer, nullable=True)

    created_at = Column(DateTime, default=now, index=True)

    user = relationship("User")


class CircularChoice(Base):
    """What this farmer decided to do with their farm waste, remembered.

    WHY THIS TABLE EXISTS
    ---------------------
    The Circular Farming page opens by asking one question: biogas, existing
    plant, or manure? Before this table, that answer lived only in React
    state. Navigating to another page and back — or simply reloading — threw
    it away and asked again, along with the three composting questions
    (shade, labour, urgency) underneath it.

    Being asked the same question every visit is not a small annoyance. It
    tells the farmer the app is not listening, and it makes the module feel
    like a calculator rather than a plan they are working through. The choice
    is a decision about their farm, so it belongs in their farm's record.

    One row per user. The compost answers are stored alongside the mode
    rather than in a second table because they are meaningless without it.
    """
    __tablename__ = "circular_choices"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), unique=True, index=True)

    # "" (undecided) | biogas | plant | manure
    mode = Column(String, default="")

    # The three things the composting plan cannot infer from the farm record.
    has_shade = Column(Boolean, default=True)
    labour = Column(String, default="normal")          # low | normal
    urgent = Column(Boolean, default=False)
    # False until the farmer has actually confirmed the three answers, so a
    # default-valued row is never mistaken for a considered reply.
    answered = Column(Boolean, default=False)

    # How much finished compost the farmer wants to hold back for their own
    # fields. Everything above this is what the sell flow offers.
    keep_kg = Column(Float, nullable=True)

    created_at = Column(DateTime, default=now)
    updated_at = Column(DateTime, default=now, onupdate=now)

    user = relationship("User")
