"""Crop lifecycle guidance for Madhya Pradesh crops.

Stage-by-stage tasks, irrigation needs and risks, keyed to days after sowing.
This is static reference data, not model output — the LLM may summarise a stage
but never invents one.

Same caveat as crop_suitability: durations are representative for MP and should
be confirmed against JNKVV / RVSKVV package-of-practices before production use.
Actual timing shifts with variety, sowing date and season.
"""

from typing import Dict, List, Optional

# Each stage: (stage name, start day, end day, tasks, irrigation, risks)
LIFECYCLE: Dict[str, List[dict]] = {
    "soybean": [
        {"stage": "Germination", "start_day": 0, "end_day": 10,
         "tasks": ["Ensure seed is treated with Rhizobium and PSB culture",
                   "Maintain 45 cm row spacing",
                   "Check for even emergence by day 7"],
         "irrigation": "Usually rain-fed at sowing. Irrigate only if the "
                       "monsoon breaks for more than 8-10 days.",
         "risks": ["Poor germination from crusted soil after heavy rain",
                   "Cutworm attack on emerging seedlings"]},
        {"stage": "Vegetative", "start_day": 11, "end_day": 35,
         "tasks": ["First weeding at 20-25 days",
                   "Check for girdle beetle and leaf-eating caterpillar",
                   "Ensure drainage channels are clear"],
         "irrigation": "Normally rain-fed. Waterlogging is a bigger risk than "
                       "drought — standing water for over 48 hours kills roots.",
         "risks": ["Waterlogging in black soil", "Girdle beetle", "Semilooper"]},
        {"stage": "Flowering", "start_day": 36, "end_day": 55,
         "tasks": ["Scout twice weekly for pod borer eggs",
                   "Avoid any operation that disturbs flowering",
                   "Do not apply nitrogen — it delays pod set"],
         "irrigation": "Critical stage. If there is a dry spell, one "
                       "irrigation here protects yield more than at any other "
                       "point.",
         "risks": ["Flower drop from moisture stress", "Pod borer",
                   "Yellow mosaic virus spread by whitefly"]},
        {"stage": "Pod filling", "start_day": 56, "end_day": 80,
         "tasks": ["Continue pod borer monitoring",
                   "Keep the field weed-free"],
         "irrigation": "Second critical stage. Moisture stress now directly "
                       "reduces seed weight.",
         "risks": ["Pod borer", "Rust in humid weather"]},
        {"stage": "Maturity", "start_day": 81, "end_day": 95,
         "tasks": ["Harvest when 90-95% pods turn brown",
                   "Do not delay — pods shatter and seed is lost",
                   "Dry to 10-12% moisture before storage"],
         "irrigation": "Stop irrigation completely.",
         "risks": ["Pod shattering from delayed harvest",
                   "Rain damage to harvested crop"]},
    ],

    "wheat": [
        {"stage": "Germination", "start_day": 0, "end_day": 7,
         "tasks": ["Sow at 5 cm depth", "Maintain 20-22 cm row spacing",
                   "Apply full phosphorus and potash as basal dose"],
         "irrigation": "Pre-sowing irrigation (palewa) ensures uniform "
                       "germination.",
         "risks": ["Deep sowing delaying emergence", "Termite attack"]},
        {"stage": "Crown root initiation", "start_day": 18, "end_day": 25,
         "tasks": ["Apply the first nitrogen top-dress",
                   "First weeding"],
         "irrigation": "THE most critical irrigation of the whole crop. "
                       "Missing it can cut yield by 20-30%.",
         "risks": ["Missed irrigation at this stage is unrecoverable",
                   "Weed competition"]},
        {"stage": "Tillering", "start_day": 26, "end_day": 45,
         "tasks": ["Second nitrogen split if the crop looks pale",
                   "Control broadleaf weeds"],
         "irrigation": "Second irrigation around day 40-45.",
         "risks": ["Yellow rust in cool humid weather", "Aphids"]},
        {"stage": "Jointing and booting", "start_day": 46, "end_day": 75,
         "tasks": ["Scout for rust on lower leaves",
                   "Avoid nitrogen after booting"],
         "irrigation": "Third irrigation. Keep moisture steady.",
         "risks": ["Yellow and brown rust", "Lodging if over-fertilised"]},
        {"stage": "Flowering and grain filling", "start_day": 76, "end_day": 110,
         "tasks": ["Monitor for aphids on ears",
                   "Protect from birds where local pressure is high"],
         "irrigation": "Critical. Moisture stress here shrivels grain and "
                       "directly cuts weight.",
         "risks": ["Terminal heat stress if February turns hot early",
                   "Aphid build-up"]},
        {"stage": "Maturity", "start_day": 111, "end_day": 130,
         "tasks": ["Harvest at 20-25% grain moisture",
                   "Dry to 12% before storage"],
         "irrigation": "Stop irrigation about 15 days before harvest.",
         "risks": ["Unseasonal rain and hail", "Grain shattering"]},
    ],

    "chickpea": [
        {"stage": "Germination", "start_day": 0, "end_day": 10,
         "tasks": ["Treat seed with Rhizobium and Trichoderma",
                   "Sow at 8-10 cm depth into residual moisture"],
         "irrigation": "Usually sown on residual moisture; no irrigation needed.",
         "risks": ["Collar rot in warm moist soil", "Poor stand from shallow sowing"]},
        {"stage": "Vegetative", "start_day": 11, "end_day": 40,
         "tasks": ["Weed at 30 days", "Avoid nitrogen — it suppresses nodulation"],
         "irrigation": "Only if the crop shows clear wilting. Chickpea is "
                       "drought-tolerant and over-watering causes excessive "
                       "leafy growth with few pods.",
         "risks": ["Wilt (Fusarium)", "Excess vegetative growth from over-irrigation"]},
        {"stage": "Flowering", "start_day": 41, "end_day": 70,
         "tasks": ["Install pheromone traps for pod borer",
                   "Set up bird perches for natural predation"],
         "irrigation": "One light irrigation if there is a prolonged dry spell.",
         "risks": ["Helicoverpa pod borer — the main threat to this crop",
                   "Flower drop in high temperature"]},
        {"stage": "Pod development", "start_day": 71, "end_day": 95,
         "tasks": ["Continue pod borer monitoring twice weekly"],
         "irrigation": "One irrigation if soil is dry, then stop.",
         "risks": ["Pod borer", "Dry root rot"]},
        {"stage": "Maturity", "start_day": 96, "end_day": 110,
         "tasks": ["Harvest when leaves turn brown and pods rattle",
                   "Dry to 10% moisture"],
         "irrigation": "None.",
         "risks": ["Shattering from delayed harvest"]},
    ],

    "maize": [
        {"stage": "Germination", "start_day": 0, "end_day": 10,
         "tasks": ["Sow at 4-5 cm depth", "Maintain 60 x 20 cm spacing",
                   "Apply basal phosphorus and potash"],
         "irrigation": "Light irrigation if sowing into dry soil.",
         "risks": ["Poor emergence from crusting", "Cutworm", "Birds"]},
        {"stage": "Vegetative", "start_day": 11, "end_day": 40,
         "tasks": ["First nitrogen top-dress at knee-high (~25 days)",
                   "Earthing up at 30-35 days for lodging resistance",
                   "Scout for fall armyworm in whorls"],
         "irrigation": "Every 8-10 days depending on soil.",
         "risks": ["Fall armyworm — check whorls weekly",
                   "Stem borer", "Nitrogen deficiency"]},
        {"stage": "Tasselling and silking", "start_day": 41, "end_day": 65,
         "tasks": ["Second nitrogen split before tasselling",
                   "Do not allow moisture stress"],
         "irrigation": "MOST critical stage. Stress during silking prevents "
                       "pollination and leaves cobs partly unfilled.",
         "risks": ["Moisture stress causing poor grain set",
                   "Heat above 35°C during pollination"]},
        {"stage": "Grain filling", "start_day": 66, "end_day": 90,
         "tasks": ["Maintain steady moisture", "Watch for cob borer"],
         "irrigation": "Every 10-12 days.",
         "risks": ["Cob borer", "Turcicum leaf blight"]},
        {"stage": "Maturity", "start_day": 91, "end_day": 100,
         "tasks": ["Harvest when the black layer forms at the kernel base",
                   "Dry to 12-14% moisture"],
         "irrigation": "Stop.",
         "risks": ["Grain mould if harvested wet"]},
    ],

    "cotton": [
        {"stage": "Germination", "start_day": 0, "end_day": 12,
         "tasks": ["Sow with the onset of monsoon",
                   "Maintain recommended spacing for the hybrid"],
         "irrigation": "Rain-fed at sowing; irrigate if the monsoon is late.",
         "risks": ["Poor germination in cold or waterlogged soil", "Seedling rot"]},
        {"stage": "Vegetative", "start_day": 13, "end_day": 50,
         "tasks": ["First weeding at 20-25 days",
                   "Install pheromone traps for pink bollworm",
                   "Scout for sucking pests on leaf undersides"],
         "irrigation": "Mostly rain-fed. Ensure drainage.",
         "risks": ["Aphids, jassids, whitefly", "Waterlogging"]},
        {"stage": "Squaring and flowering", "start_day": 51, "end_day": 95,
         "tasks": ["Weekly pink bollworm monitoring in green bolls",
                   "Avoid excess nitrogen — it causes rank growth"],
         "irrigation": "Critical. Stress causes square and flower shedding.",
         "risks": ["Pink bollworm — the single biggest threat",
                   "Whitefly-transmitted leaf curl", "Boll shedding"]},
        {"stage": "Boll development", "start_day": 96, "end_day": 140,
         "tasks": ["Continue bollworm monitoring",
                   "Remove and destroy affected bolls"],
         "irrigation": "Maintain steady moisture until bolls open.",
         "risks": ["Pink bollworm", "Boll rot in wet weather"]},
        {"stage": "Maturity and picking", "start_day": 141, "end_day": 165,
         "tasks": ["Pick in 3-4 rounds as bolls open",
                   "Keep pickings dry and free of trash",
                   "Destroy stalks after final picking to break the pest cycle"],
         "irrigation": "Stop before first picking.",
         "risks": ["Staining from rain", "Carry-over pest population in stubble"]},
    ],
}

# Ten crops appear in the MP_CROPS dropdown but had no stage data here, so
# selecting any of them returned "No lifecycle data for <crop>". They live in a
# separate module purely to keep this file readable.
from app.services.lifecycle_data import ADDITIONAL_LIFECYCLE  # noqa: E402

LIFECYCLE.update(ADDITIONAL_LIFECYCLE)


ALIASES = {
    "gram": "chickpea", "chana": "chickpea", "bengal gram": "chickpea",
    "soya": "soybean", "soyabean": "soybean",
    "corn": "maize", "makka": "maize",
    "gehu": "wheat", "gehun": "wheat",
    "kapas": "cotton",
    # Local names for the newly added crops.
    "moong": "greengram", "mung": "greengram", "green gram": "greengram",
    "moong dal": "greengram", "mung bean": "greengram",
    "tur": "pigeonpea", "arhar": "pigeonpea", "toor": "pigeonpea",
    "red gram": "pigeonpea",
    "paddy": "rice", "dhan": "rice", "chawal": "rice",
    "jowar": "sorghum", "juar": "sorghum", "cholam": "sorghum",
    "sarson": "mustard", "rai": "mustard", "toria": "mustard",
    "moongphali": "groundnut", "peanut": "groundnut",
    "mungfali": "groundnut",
    "aloo": "potato", "batata": "potato",
    "pyaz": "onion", "kanda": "onion",
    "tamatar": "tomato",
    "ganna": "sugarcane", "sugar cane": "sugarcane", "karumbu": "sugarcane",
}


def resolve_crop(crop: str) -> Optional[str]:
    if not crop:
        return None
    key = crop.strip().lower()
    if key in LIFECYCLE:
        return key
    return ALIASES.get(key)


def get_lifecycle(crop: str) -> Optional[dict]:
    """Full stage list for a crop, or None if we hold no data for it."""
    key = resolve_crop(crop)
    if key is None:
        return None

    stages = LIFECYCLE[key]
    return {
        "crop": key,
        "total_duration_days": stages[-1]["end_day"],
        "stage_count": len(stages),
        "stages": stages,
        "disclaimer": ("Stage timings are representative for Madhya Pradesh and "
                       "vary with variety, sowing date and season. Confirm with "
                       "your local Krishi Vigyan Kendra."),
    }


def current_stage(crop: str, days_after_sowing: int) -> Optional[dict]:
    """Which stage the crop is in now, plus what comes next."""
    data = get_lifecycle(crop)
    if data is None:
        return None

    stages = data["stages"]
    dae = max(0, int(days_after_sowing))

    active = None
    for stage in stages:
        if stage["start_day"] <= dae <= stage["end_day"]:
            active = stage
            break

    if active is None:
        if dae > stages[-1]["end_day"]:
            return {
                "crop": data["crop"], "days_after_sowing": dae,
                "stage": "Past maturity",
                "message": (f"At {dae} days this crop is past its typical "
                            f"{data['total_duration_days']}-day duration. "
                            f"It should already have been harvested."),
                "next_stage": None, "disclaimer": data["disclaimer"],
            }
        # Gap between listed stages (e.g. wheat days 8-17).
        upcoming = next((s for s in stages if s["start_day"] > dae), None)
        return {
            "crop": data["crop"], "days_after_sowing": dae,
            "stage": "Between stages",
            "message": (f"Day {dae} falls between defined stages. The next "
                        f"stage is {upcoming['stage']} beginning at day "
                        f"{upcoming['start_day']}." if upcoming else ""),
            "next_stage": upcoming, "disclaimer": data["disclaimer"],
        }

    index = stages.index(active)
    upcoming = stages[index + 1] if index + 1 < len(stages) else None

    return {
        "crop": data["crop"],
        "days_after_sowing": dae,
        "stage": active["stage"],
        "stage_number": index + 1,
        "of_stages": len(stages),
        "days_left_in_stage": active["end_day"] - dae,
        "tasks": active["tasks"],
        "irrigation": active["irrigation"],
        "risks": active["risks"],
        "next_stage": ({"stage": upcoming["stage"],
                        "starts_day": upcoming["start_day"],
                        "in_days": upcoming["start_day"] - dae}
                       if upcoming else None),
        "disclaimer": data["disclaimer"],
    }


def supported_crops() -> List[str]:
    return sorted(LIFECYCLE.keys())
