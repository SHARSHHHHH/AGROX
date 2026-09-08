"""Farm machinery knowledge base.

Answers the question a farmer actually has: *which machine do I need, at which
stage, and roughly what should it cost?*

This is verified reference data, not model output. The LLM may summarise an
entry but never invents a machine, a use, or a price band.

PRICE BANDS ARE INDICATIVE
--------------------------
`typical_daily_rate` is a broad national range compiled for this project. Real
rates vary a lot with state, season, fuel price, implement condition and how
far the owner has to travel. Every price shown to a farmer is labelled as an
indicative range, and actual listings always show the owner's own price
instead.
"""

from typing import Dict, List, Optional

# Growth stages, matching the lifecycle service vocabulary.
STAGE_LAND_PREP = "land_preparation"
STAGE_SOWING = "sowing"
STAGE_GROWING = "crop_care"
STAGE_HARVEST = "harvest"
STAGE_POST = "post_harvest"

STAGE_ORDER = [STAGE_LAND_PREP, STAGE_SOWING, STAGE_GROWING,
               STAGE_HARVEST, STAGE_POST]

STAGE_LABELS = {
    STAGE_LAND_PREP: "Land preparation",
    STAGE_SOWING: "Sowing / planting",
    STAGE_GROWING: "Crop care",
    STAGE_HARVEST: "Harvesting",
    STAGE_POST: "After harvest",
}


MACHINERY_KB: Dict[str, dict] = {
    "tractor": {
        "name": "Tractor",
        "category": "power",
        "stage": STAGE_LAND_PREP,
        "icon": "tractor",
        "what_it_does": "The main power unit of the farm. On its own it pulls "
                        "implements; almost every other machine here attaches "
                        "to one.",
        "when_needed": "Throughout the season, but most heavily before sowing.",
        "suits_land": "Above 2 acres. Below that, hiring per hour is usually "
                      "cheaper than owning.",
        "typical_daily_rate": (900, 1800),
        "unit": "per day (fuel usually extra)",
        "crops": ["all"],
        "tip": "Confirm whether the quoted rate includes diesel and the "
               "driver. That single question changes the real cost more than "
               "anything else.",
    },
    "rotavator": {
        "name": "Rotavator",
        "category": "tillage",
        "stage": STAGE_LAND_PREP,
        "icon": "rotavator",
        "what_it_does": "Breaks and mixes the topsoil into a fine seedbed in "
                        "one pass, and chops crop residue back into the soil.",
        "when_needed": "Just before sowing, after the field is cleared.",
        "suits_land": "Any size, tractor-mounted.",
        "typical_daily_rate": (1200, 2500),
        "unit": "per day, or 700-1200 per acre",
        "crops": ["wheat", "soybean", "maize", "cotton", "rice"],
        "tip": "One rotavator pass often replaces two or three cultivator "
               "passes, so it can work out cheaper despite the higher rate.",
    },
    "cultivator": {
        "name": "Cultivator (Tiller)",
        "category": "tillage",
        "stage": STAGE_LAND_PREP,
        "icon": "cultivator",
        "what_it_does": "Loosens soil and uproots weeds between crop rows "
                        "without turning the soil over completely.",
        "when_needed": "Before sowing, and for inter-row weeding after.",
        "suits_land": "Any size.",
        "typical_daily_rate": (700, 1400),
        "unit": "per day",
        "crops": ["all"],
        "tip": "Cheaper than a rotavator but needs more passes on hard soil.",
    },
    "seed_drill": {
        "name": "Seed Drill",
        "category": "sowing",
        "stage": STAGE_SOWING,
        "icon": "seeder",
        "what_it_does": "Places seed at a uniform depth and spacing, and can "
                        "band fertiliser at the same time.",
        "when_needed": "At sowing.",
        "suits_land": "Above 1 acre.",
        "typical_daily_rate": (800, 1600),
        "unit": "per day",
        "crops": ["wheat", "soybean", "chickpea", "maize", "mustard"],
        "tip": "Even sowing depth matters more for germination than seed rate. "
               "Broadcasting by hand wastes seed and gives patchy stands.",
    },
    "happy_seeder": {
        "name": "Happy Seeder",
        "category": "sowing",
        "stage": STAGE_SOWING,
        "icon": "seeder",
        "what_it_does": "Sows directly into standing crop residue, so stubble "
                        "does not have to be burnt or cleared first.",
        "when_needed": "Sowing wheat straight after a rice harvest.",
        "suits_land": "Above 3 acres; needs a higher-horsepower tractor.",
        "typical_daily_rate": (1800, 3500),
        "unit": "per day",
        "crops": ["wheat"],
        "tip": "Avoids stubble burning entirely, which is both illegal in many "
               "states and destroys the organic matter in your own topsoil.",
    },
    "power_tiller": {
        "name": "Power Tiller",
        "category": "power",
        "stage": STAGE_LAND_PREP,
        "icon": "tiller",
        "what_it_does": "A walk-behind two-wheel machine that tills, and can "
                        "drive a pump or thresher.",
        "when_needed": "Land preparation on small or awkward plots.",
        "suits_land": "Under 2 acres, terraces, or wet rice fields where a "
                      "tractor would sink.",
        "typical_daily_rate": (500, 1000),
        "unit": "per day",
        "crops": ["rice", "vegetables"],
        "tip": "The practical choice for a smallholding where a tractor cannot "
               "turn or would compact wet soil.",
    },
    "sprayer": {
        "name": "Power Sprayer",
        "category": "crop_care",
        "stage": STAGE_GROWING,
        "icon": "sprayer",
        "what_it_does": "Applies pesticide, fungicide or foliar nutrients as a "
                        "fine, even spray.",
        "when_needed": "Whenever the IPM plan calls for an application.",
        "suits_land": "Any size. Knapsack for small plots, boom for large.",
        "typical_daily_rate": (300, 800),
        "unit": "per day",
        "crops": ["all"],
        "tip": "Wear gloves and a mask, spray in the late evening when "
               "pollinators are inactive, and never spray if rain is forecast "
               "within a few hours.",
    },
    "drone_sprayer": {
        "name": "Agricultural Drone",
        "category": "crop_care",
        "stage": STAGE_GROWING,
        "icon": "drone",
        "what_it_does": "Sprays from the air, covering ground far faster than "
                        "a person with a knapsack and using less water.",
        "when_needed": "Large areas, or a tall standing crop you cannot walk "
                       "through.",
        "suits_land": "Above 5 acres to be worth the mobilisation cost.",
        "typical_daily_rate": (2500, 6000),
        "unit": "per day, or 400-700 per acre",
        "crops": ["rice", "wheat", "cotton", "sugarcane"],
        "tip": "Usually comes with a trained operator, which is normally "
               "included in the rate. Confirm before booking.",
    },
    "harvester": {
        "name": "Combine Harvester",
        "category": "harvest",
        "stage": STAGE_HARVEST,
        "icon": "harvester",
        "what_it_does": "Cuts, threshes and cleans grain in a single pass.",
        "when_needed": "At harvest, when grain moisture is right.",
        "suits_land": "Above 3 acres; the mobilisation charge dominates on "
                      "smaller plots.",
        "typical_daily_rate": (2500, 5000),
        "unit": "per hour 1500-2500, or per acre",
        "crops": ["wheat", "rice", "soybean", "chickpea"],
        "tip": "Book well ahead. Everyone in a district harvests within the "
               "same fortnight, and late harvest means shattering losses.",
    },
    "thresher": {
        "name": "Thresher",
        "category": "harvest",
        "stage": STAGE_POST,
        "icon": "thresher",
        "what_it_does": "Separates grain from the cut crop after manual "
                        "harvesting.",
        "when_needed": "After harvest, if you did not use a combine.",
        "suits_land": "Any size.",
        "typical_daily_rate": (800, 1800),
        "unit": "per day",
        "crops": ["wheat", "soybean", "chickpea", "maize"],
        "tip": "Cheaper than a combine for a small plot, but needs labour to "
               "cut and carry the crop first.",
    },
    "baler": {
        "name": "Straw Baler",
        "category": "post_harvest",
        "stage": STAGE_POST,
        "icon": "baler",
        "what_it_does": "Compresses loose straw into bales that can be stored, "
                        "sold as fodder, or moved easily.",
        "when_needed": "After combine harvesting, before the next sowing.",
        "suits_land": "Above 5 acres.",
        "typical_daily_rate": (2000, 4000),
        "unit": "per day",
        "crops": ["wheat", "rice"],
        "tip": "Turns residue you might otherwise burn into a second income "
               "from fodder.",
    },
    "laser_leveller": {
        "name": "Laser Land Leveller",
        "category": "tillage",
        "stage": STAGE_LAND_PREP,
        "icon": "leveller",
        "what_it_does": "Levels a field to a precise grade using a laser "
                        "reference, so irrigation water spreads evenly.",
        "when_needed": "Once every few years, before the season starts.",
        "suits_land": "Above 2 acres, especially flood-irrigated fields.",
        "typical_daily_rate": (2000, 4000),
        "unit": "per day, or 800-1500 per acre",
        "crops": ["rice", "wheat", "sugarcane"],
        "tip": "Commonly reported to cut irrigation water use substantially by "
               "removing high and low spots. The benefit lasts several seasons.",
    },
    "water_pump": {
        "name": "Irrigation Pump Set",
        "category": "irrigation",
        "stage": STAGE_GROWING,
        "icon": "pump",
        "what_it_does": "Lifts water from a borewell, canal or tank into the "
                        "field.",
        "when_needed": "Whenever irrigation is due.",
        "suits_land": "Any size.",
        "typical_daily_rate": (300, 900),
        "unit": "per day",
        "crops": ["all"],
        "tip": "Match the pump to your water depth. An oversized pump wastes "
               "diesel; an undersized one will never lift the water at all.",
    },
    "seed_planter": {
        "name": "Potato / Vegetable Planter",
        "category": "sowing",
        "stage": STAGE_SOWING,
        "icon": "seeder",
        "what_it_does": "Plants tubers or seedlings at a set spacing and forms "
                        "ridges in the same pass.",
        "when_needed": "At planting.",
        "suits_land": "Above 1 acre.",
        "typical_daily_rate": (1200, 2500),
        "unit": "per day",
        "crops": ["potato", "onion", "tomato"],
        "tip": "Saves a great deal of labour compared with hand planting on "
               "anything above an acre.",
    },
    "trolley": {
        "name": "Tractor Trolley",
        "category": "transport",
        "stage": STAGE_POST,
        "icon": "trolley",
        "what_it_does": "Carries produce, manure, seed and equipment.",
        "when_needed": "Throughout the season, heaviest at harvest.",
        "suits_land": "Any size.",
        "typical_daily_rate": (500, 1200),
        "unit": "per day",
        "crops": ["all"],
        "tip": "Often the difference between selling at a distant mandi with a "
               "better rate and being stuck with the local price.",
    },
}


CATEGORIES = {
    "power": "Tractors & power units",
    "tillage": "Soil preparation",
    "sowing": "Sowing & planting",
    "crop_care": "Spraying & crop care",
    "irrigation": "Irrigation",
    "harvest": "Harvesting",
    "post_harvest": "After harvest",
    "transport": "Transport",
}


def get_machine(key: str) -> Optional[dict]:
    return MACHINERY_KB.get((key or "").strip().lower())


def list_machines() -> List[dict]:
    return [{"key": k, **v} for k, v in MACHINERY_KB.items()]


def for_stage(stage: str) -> List[dict]:
    return [{"key": k, **v} for k, v in MACHINERY_KB.items()
            if v["stage"] == stage]


def for_crop(crop: str) -> List[dict]:
    """Machines relevant to a crop, ordered by season stage."""
    c = (crop or "").strip().lower()
    out = [{"key": k, **v} for k, v in MACHINERY_KB.items()
           if "all" in v["crops"] or c in v["crops"]]
    out.sort(key=lambda m: STAGE_ORDER.index(m["stage"]))
    return out


def recommend_for_farm(crop: str = "", land_size_acres: Optional[float] = None,
                       stage: str = "") -> dict:
    """Which machines this particular farm plausibly needs, and why.

    Deterministic filtering over the catalogue above — no model involved.
    """
    candidates = for_crop(crop) if crop else list_machines()

    if stage:
        staged = [m for m in candidates if m["stage"] == stage]
        if staged:
            candidates = staged

    recommended, skipped = [], []
    for m in candidates:
        note = ""
        suitable = True

        # Size gate, parsed from the catalogue text rather than hardcoded here.
        if land_size_acres is not None:
            text = m["suits_land"].lower()
            if "above 5 acres" in text and land_size_acres < 5:
                suitable, note = False, (
                    f"Usually only worth it above 5 acres; you have "
                    f"{land_size_acres} acres.")
            elif "above 3 acres" in text and land_size_acres < 3:
                suitable, note = False, (
                    f"The mobilisation charge dominates below 3 acres; you have "
                    f"{land_size_acres} acres.")
            elif "under 2 acres" in text and land_size_acres >= 2:
                suitable, note = False, (
                    "Intended for small or awkward plots; a tractor implement "
                    "will be faster on your area.")

        entry = {**m, "note": note}
        (recommended if suitable else skipped).append(entry)

    recommended.sort(key=lambda m: STAGE_ORDER.index(m["stage"]))

    return {
        "crop": crop,
        "land_size_acres": land_size_acres,
        "recommended": recommended,
        "not_suitable": skipped,
        "disclaimer": ("Rental rates shown are indicative national ranges. "
                       "Actual rates vary with state, season, fuel price and "
                       "distance. Always confirm the price, and whether fuel "
                       "and operator are included, before booking."),
    }
