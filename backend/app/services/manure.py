"""Digestate use on crops, and what to do with crop residue.

THE RULE THIS MODULE ENFORCES
-----------------------------
The spec is explicit that the app must never say "all manure can be used for
every crop in the same quantity". That is not a wording preference — it is
agronomically wrong in two directions at once.

Digestate is nitrogen-rich and low in phosphorus. On a legume, which fixes its
own nitrogen, a heavy dose mostly grows leaf at the expense of pods. On a leafy
vegetable it is close to ideal. On a root crop, excess nitrogen gives you tops
instead of tubers. And raw digestate on a standing crop close to harvest is a
food-safety problem, not a nutrition one.

So every recommendation here is per crop, and each carries its own reasoning.

NUTRIENT VALUES ARE THE WEAK LINK
---------------------------------
Fresh digestate is roughly 93% water. Its nutrient content varies with
feedstock, retention time and how it is stored — published figures span a
factor of two or more. So amounts are ranges, every response says testing
would improve it, and nothing here claims a guaranteed nutrient delivery.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

log = logging.getLogger("agri.manure")

# Typical nutrient content of FRESH digestate slurry, % of wet weight.
# Wide ranges deliberately: this is the least certain input in the module.
DIGESTATE_NPK_WET = {
    "n": (0.15, 0.35),
    "p": (0.05, 0.15),
    "k": (0.10, 0.30),
}

# Application rate in tonnes of fresh digestate per acre, by crop response
# group. These are conservative planning figures, not prescriptions.
RATE_T_PER_ACRE = {
    "high_nitrogen":   (4.0, 6.0),   # cereals, leafy, fodder
    "moderate":        (2.5, 4.0),   # most vegetables, cotton, oilseeds
    "low_nitrogen":    (1.0, 2.0),   # legumes — they fix their own N
    "root_careful":    (2.0, 3.5),   # roots/tubers: excess N grows tops
}

CROP_GROUP = {
    "rice": "high_nitrogen", "wheat": "high_nitrogen",
    "maize": "high_nitrogen", "sorghum": "high_nitrogen",
    "sugarcane": "high_nitrogen",
    "cotton": "moderate", "tomato": "moderate", "onion": "moderate",
    "mustard": "moderate",
    "soybean": "low_nitrogen", "chickpea": "low_nitrogen",
    "pigeonpea": "low_nitrogen", "greengram": "low_nitrogen",
    "groundnut": "low_nitrogen",
    "potato": "root_careful",
}

GROUP_REASON = {
    "high_nitrogen": (
        "This crop responds well to nitrogen, which is what digestate mainly "
        "supplies."),
    "moderate": (
        "This crop takes a moderate amount of nitrogen. Digestate suits it, "
        "but balance it against your soil test."),
    "low_nitrogen": (
        "This is a legume and fixes much of its own nitrogen. A heavy dose of "
        "digestate mostly grows leaf at the cost of pods, so apply "
        "sparingly — mainly for the organic matter, not the nitrogen."),
    "root_careful": (
        "For root and tuber crops, too much nitrogen grows tops instead of "
        "tubers. Apply a moderate amount, well before planting."),
}


# =====================================================================
# Food safety — said only when it actually applies
# =====================================================================
#
# WHY THIS IS NOT ONE CONSTANT STRING
# -----------------------------------
# Every crop used to get the same warning: "do not apply to leafy vegetables
# or anything eaten raw within 4-6 weeks of harvest". On wheat, cotton or
# sugarcane that sentence is simply not about the crop the farmer is growing.
#
# A warning that appears on every screen regardless of relevance stops being
# read. Worse, it trains the farmer to skip warnings — so on the day they open
# the page for a crop where raw-consumption really is the risk, the sentence
# they most needed is the one they have already learned to scroll past.
#
# So the note is now attached to the crops it is actually about, and every
# other crop gets nothing rather than boilerplate.
#
# RAW_EATEN: harvested part is routinely eaten uncooked and grows in contact
# with, or close to, the soil. This is where an uncomposted-manure pathogen
# route to a human is real. The value names the part actually eaten, so the
# warning does not tell a spinach grower to keep manure off the "fruit".
RAW_EATEN = {
    "tomato": "fruit", "cucumber": "fruit",
    "onion": "bulb", "carrot": "root", "radish": "root", "beetroot": "root",
    "spinach": "leaves", "coriander": "leaves", "fenugreek": "leaves",
    "lettuce": "leaves", "cabbage": "head", "mint": "leaves",
}

# Cooked before eating, or the edible part never touches the manure — a
# processing or milling step sits between the field and the plate.
COOKED_OR_PROCESSED = {
    "rice", "wheat", "maize", "sorghum", "sugarcane", "cotton", "mustard",
    "soybean", "chickpea", "pigeonpea", "greengram", "groundnut", "potato",
}


def food_safety_note(crop: str, *, composted: bool = False) -> Optional[str]:
    """The food-safety warning for THIS crop, or None if there isn't one.

    Returning None rather than a generic sentence is the point: the caller is
    expected to render nothing at all when there is nothing to say.
    """
    key = (crop or "").strip().lower()
    if not key:
        return None

    part = RAW_EATEN.get(key)
    if part:
        if composted:
            return (
                f"{key.capitalize()} is often eaten raw, so use only fully "
                f"rotted compost on it and keep it off the {part}. If the "
                f"heap is not finished, leave at least 4 weeks between "
                f"applying it and harvesting.")
        return (
            f"{key.capitalize()} is often eaten raw. Do not apply raw slurry "
            f"within about 4-6 weeks of harvest, and keep it off the {part}.")

    if key in COOKED_OR_PROCESSED:
        # Nothing worth saying. Potato is here on purpose: it is a tuber in
        # soil contact, but it is peeled and cooked, so the raw-consumption
        # route does not apply.
        return None

    # An unrecognised crop is the one case where a general caution is honest,
    # because we do not know whether it is eaten raw.
    return (
        "We do not hold food-safety guidance for this crop. If any part of it "
        "is eaten raw, leave 4-6 weeks between applying manure and harvest.")


def _rng(lo: float, hi: float) -> Dict[str, float]:
    return {"low": round(lo, 1), "high": round(hi, 1),
            "mid": round((lo + hi) / 2, 1)}


# =====================================================================
# Finished compost — a DIFFERENT rate from fresh digestate
# =====================================================================
#
# RATE_T_PER_ACRE above is for fresh digestate slurry, which is roughly 93%
# water. Finished compost has had most of that water and about half its mass
# driven off while it rotted, so the same tonnage is several times the
# nutrient load. Reusing the slurry rate for compost overstates what a farm
# needs by a wide margin, and a farmer reading "your farm needs 1,300,000 kg"
# next to "you will make 1,700 kg" concludes the whole exercise is pointless.
#
# So compost gets its own table, in tonnes of FINISHED compost per acre.
# These sit in the range of the usual Indian extension recommendations
# (about 5-12 t/ha depending on crop and material).
COMPOST_RATE_T_PER_ACRE = {
    "high_nitrogen":   (3.0, 4.0),   # cereals, leafy, fodder, sugarcane
    "moderate":        (2.0, 3.0),   # most vegetables, cotton, oilseeds
    "low_nitrogen":    (1.0, 2.0),   # legumes fix their own nitrogen
    "root_careful":    (1.5, 2.5),   # roots/tubers: excess N grows tops
}

# Not every method produces material of the same strength, so the same field
# needs different weights of each. Vermicompost is roughly twice as
# concentrated as an ordinary heap; plain FYM is bulkier and weaker.
METHOD_RATE_FACTOR = {
    "vermicompost": 0.5,
    "compost": 1.0,
    "fym": 1.25,
}

# Liquid manure is not a bulk soil amendment and must not be given a tonnage
# per acre — it is applied as a drench, in litres, repeatedly through the
# season. Quoting it in tonnes would invite someone to try to spread 2 t/acre
# of liquid.
LIQUID_LITRES_PER_ACRE = (150, 250)

# Indicative farm-gate selling prices, rupees per kg. Wide bands on purpose:
# organic manure has no mandi price discovery, and what a farmer actually
# gets swings with district, season, packaging and whether the buyer collects.
# These are a starting point for a conversation, never a quoted rate.
PRICE_RANGE_PER_KG = {
    "vermicompost": (5.0, 10.0),
    "compost": (2.5, 5.0),
    "fym": (1.0, 2.5),
    "liquid": (4.0, 8.0),            # per litre for this one
}

PRODUCT_LABEL = {
    "vermicompost": "Vermicompost",
    "compost": "Compost",
    "fym": "Farmyard manure (FYM)",
    "liquid": "Liquid manure",
}


def compost_need(*, crop: str, area_acres: Optional[float],
                 method: str = "compost",
                 produced_kg: Optional[float] = None,
                 soil: Optional[dict] = None) -> Dict[str, Any]:
    """How much FINISHED compost this farm's crop wants, and what that means
    for the heap the farmer is about to build.

    Returns the per-acre rate, the whole-farm total, and — the number that
    actually matters to someone with 19 cattle and 400 acres — how many acres
    the compost they will make can realistically cover.
    """
    key = (crop or "").strip().lower()
    group = CROP_GROUP.get(key)

    if method == "liquid":
        # Answered in litres, and deliberately not converted to a tonnage.
        lo, hi = LIQUID_LITRES_PER_ACRE
        return {
            "available": True, "unit": "litres", "crop": key or None,
            "method": method, "area_acres": area_acres,
            "rate_per_acre": _rng(lo, hi),
            "note": ("Liquid manure is watered onto the crop through the "
                     "season, not spread once like a heap. Plan on roughly "
                     f"{lo}-{hi} litres per acre per application, every "
                     "2-3 weeks while the crop is growing."),
            "confidence": "ESTIMATED",
        }

    if group is None:
        # No nutrient rate on record, but whether the crop is eaten raw is a
        # SEPARATE question and we may well know the answer. Dropping the
        # safety note here meant spinach — raw-eaten, and exactly the case the
        # warning exists for — silently got no warning at all.
        return {
            "available": False, "crop": key or None, "method": method,
            "food_safety_note": food_safety_note(key, composted=True),
            "note": ("No specific rate is held for this crop. Compost is safe "
                     "as a general soil conditioner — ask your local "
                     "agriculture officer what suits it."),
        }

    lo_t, hi_t = COMPOST_RATE_T_PER_ACRE[group]
    factor = METHOD_RATE_FACTOR.get(method, 1.0)
    reasons: List[str] = [GROUP_REASON[group]]

    if factor < 1.0:
        reasons.append(
            f"{PRODUCT_LABEL.get(method, 'This material')} is more "
            f"concentrated than an ordinary heap, so less of it goes further.")
    elif factor > 1.0:
        reasons.append(
            "Farmyard manure is bulkier and weaker than compost, so the same "
            "field needs a heavier dressing of it.")

    # A soil test moves the rate, exactly as it does for digestate.
    adjust = 1.0
    if soil and soil.get("nitrogen") is not None:
        n = float(soil["nitrogen"])
        if n > 40:
            adjust = 0.7
            reasons.append(
                f"Your soil nitrogen is already {n}, so a lighter dressing is "
                f"enough.")
        elif n < 15:
            adjust = 1.2
            reasons.append(
                f"Your soil nitrogen is low ({n}), so use the upper end of "
                f"the range.")

    per_acre = _rng(lo_t * 1000 * factor * adjust, hi_t * 1000 * factor * adjust)
    total = _rng(per_acre["low"] * area_acres,
                 per_acre["high"] * area_acres) if area_acres else None

    acres_covered = None
    covers_whole_farm = None
    if produced_kg and per_acre["mid"]:
        acres_covered = round(produced_kg / per_acre["mid"], 2)
        if area_acres:
            covers_whole_farm = acres_covered >= area_acres

    return {
        "available": True, "unit": "kg",
        "crop": key, "group": group, "method": method,
        "area_acres": area_acres,
        "rate_kg_per_acre": per_acre,
        "total_needed_kg": total,
        "produced_kg": produced_kg,
        "acres_covered": acres_covered,
        "covers_whole_farm": covers_whole_farm,
        "why": reasons,
        "how_to_apply": [
            "Spread it on a prepared field and mix it into the top 15 cm "
            "within a day — nitrogen escapes to the air if it lies on top.",
            "Apply before sowing or transplanting rather than onto a standing "
            "crop close to harvest.",
            "If you cannot cover everything, put it on your weakest field. "
            "Compost does the most good where organic matter is lowest.",
        ],
        "food_safety_note": food_safety_note(key, composted=True),
        "confidence": "ESTIMATED",
        "caveat": (
            "A planning figure. The nutrient content of home-made compost "
            "varies with what went in and how it was stored, so treat this as "
            "a starting rate and adjust from what you see in the field."),
    }


def suggest_price(method: str, quantity_kg: Optional[float] = None) -> Dict[str, Any]:
    """An indicative asking price for surplus compost.

    Presented as a band with an explicit warning that it is not a quoted
    rate. There is no mandi price discovery for farm compost — the farmer is
    the one who knows what their neighbours pay, and this is only meant to
    stop them pricing at a tenth or ten times the going rate.
    """
    lo, hi = PRICE_RANGE_PER_KG.get(method, (2.0, 5.0))
    unit = "litre" if method == "liquid" else "kg"
    mid = round((lo + hi) / 2, 1)
    return {
        "method": method,
        "product_label": PRODUCT_LABEL.get(method, "Compost"),
        "unit": unit,
        "low": lo, "high": hi, "suggested": mid,
        "estimated_value": (round(quantity_kg * mid) if quantity_kg else None),
        "basis": (
            f"Typical farm-gate rates for {PRODUCT_LABEL.get(method, 'compost')} "
            f"run about Rs {lo:g}-{hi:g} per {unit}. Bagged and delivered "
            f"fetches more; bulk collected from your gate fetches less."),
        "caveat": (
            "This is a rough guide, not a market rate — there is no daily "
            "price for farm compost the way there is for grain. Ask two or "
            "three buyers near you before you settle on a figure."),
    }


def recommend_for_crop(*, crop: str, area_acres: Optional[float],
                       available_kg: Optional[float] = None,
                       soil: Optional[dict] = None) -> Dict[str, Any]:
    """How much digestate suits this crop on this area, and why."""
    key = (crop or "").strip().lower()
    if not key:
        return {"available": False, "food_safety_note": None,
                "note": "No crop selected."}

    group = CROP_GROUP.get(key)
    if group is None:
        return {
            "available": False, "crop": key,
            "food_safety_note": food_safety_note(key, composted=False),
            "note": ("No specific guidance is held for this crop. Digestate "
                     "is generally safe as a soil conditioner, but ask your "
                     "local agriculture officer about the right rate."),
        }

    lo_t, hi_t = RATE_T_PER_ACRE[group]
    reasons: List[str] = [GROUP_REASON[group]]

    # A soil test shifts the rate. Nitrogen already high means less is needed.
    adjust = 1.0
    if soil and soil.get("nitrogen") is not None:
        n = float(soil["nitrogen"])
        if n > 40:
            adjust = 0.7
            reasons.append(
                f"Your soil nitrogen is already {n}, so a lighter application "
                f"is enough.")
        elif n < 15:
            adjust = 1.2
            reasons.append(
                f"Your soil nitrogen is low ({n}), so the upper end of the "
                f"range is appropriate.")

    if soil and soil.get("ph") is not None:
        ph = float(soil["ph"])
        if ph < 5.5:
            reasons.append(
                f"Your soil is acidic (pH {ph}). Digestate helps organic "
                f"matter but will not correct acidity — lime is what does "
                f"that.")

    per_acre = _rng(lo_t * 1000 * adjust, hi_t * 1000 * adjust)
    total = None
    covers = None
    if area_acres:
        total = _rng(per_acre["low"] * area_acres, per_acre["high"] * area_acres)
        if available_kg:
            covers = round(available_kg / per_acre["mid"], 2)

    return {
        "available": True,
        "crop": key,
        "group": group,
        "suitable": True,
        "why": reasons,
        "benefit": (
            "Digestate adds organic matter and slow-release nutrients, "
            "improves how well the soil holds water, and feeds soil life. It "
            "works alongside fertiliser rather than replacing it."),
        "rate_kg_per_acre": per_acre,
        "total_needed_kg": total,
        "area_acres": area_acres,
        "acres_covered_by_available": covers,
        "how_to_apply": [
            "Apply to a prepared field and mix into the soil within a day — "
            "nitrogen is lost to the air if it sits on the surface.",
            "Best applied before sowing or transplanting, not onto a "
            "standing crop close to harvest.",
            "Let fresh digestate settle for one to two weeks before use if "
            "you can; very fresh slurry can scorch young roots.",
            "Keep it away from where you draw drinking water.",
        ],
        # None when the crop carries no raw-consumption risk. The UI renders
        # nothing in that case rather than a warning that is not about them.
        "food_safety_note": food_safety_note(key, composted=False),
        "confidence": "ESTIMATED",
        "caveat": (
            "The nutrient content of digestate varies widely with feedstock "
            "and storage, so this rate is approximate. Testing your soil, and "
            "the digestate itself if you can, would make it considerably more "
            "accurate."),
    }


# =====================================================================
# Crop residue routing
# =====================================================================

ROUTES = {
    "biogas": "Feed into a biogas digester",
    "compost": "Compost it",
    "mulch": "Leave as surface mulch",
    "soil_incorporation": "Plough it back into the soil",
    "fodder": "Use as cattle fodder",
    "sell": "Sell or give to another farmer",
}

# Which routes genuinely suit which residue. Cereal straw makes good fodder
# and mulch; a small digester handles it poorly. Legume residue is nitrogen
# rich and better returned to the soil than burned or sold.
RESIDUE_PROFILE = {
    "rice":      {"best": "soil_incorporation", "good": ["compost", "mulch", "biogas"],
                  "note": "Rice straw is high in silica and breaks down slowly. "
                          "Incorporating it with a decomposer culture works better "
                          "than burning, which is also illegal in many states."},
    "wheat":     {"best": "fodder", "good": ["mulch", "compost"],
                  "note": "Wheat straw is valuable fodder and excellent mulch. "
                          "Feeding a digester with it is usually a waste of a "
                          "better use."},
    "maize":     {"best": "fodder", "good": ["compost", "biogas"],
                  "note": "Maize stover is good fodder. Chopped, it also composts "
                          "quickly."},
    "sugarcane": {"best": "mulch", "good": ["compost", "soil_incorporation"],
                  "note": "Cane trash left as mulch conserves moisture and "
                          "suppresses weeds in the ratoon crop."},
    "cotton":    {"best": "compost", "good": ["soil_incorporation"],
                  "note": "Cotton stalks are woody and slow to break down. Shred "
                          "before composting. Do not leave stalks standing — they "
                          "carry pink bollworm to the next season."},
    "soybean":   {"best": "soil_incorporation", "good": ["compost", "mulch"],
                  "note": "Legume residue is nitrogen rich; returning it to the "
                          "soil feeds the next crop."},
    "chickpea":  {"best": "soil_incorporation", "good": ["compost"],
                  "note": "Legume residue returns nitrogen to the soil."},
    "pigeonpea": {"best": "fodder", "good": ["compost", "biogas"],
                  "note": "Pigeonpea stalks are woody — often used as fuel or "
                          "fencing locally."},
    "greengram": {"best": "soil_incorporation", "good": ["compost", "fodder"],
                  "note": "Short-duration legume residue breaks down fast and "
                          "feeds the following crop."},
    "groundnut": {"best": "fodder", "good": ["compost"],
                  "note": "Groundnut haulm is high-quality fodder and usually "
                          "worth more fed than composted."},
    "potato":    {"best": "compost", "good": ["soil_incorporation"],
                  "note": "Compost potato haulm rather than leaving it — it "
                          "carries late blight to the next crop."},
    "tomato":    {"best": "compost", "good": [],
                  "note": "Compost thoroughly, or remove. Tomato residue carries "
                          "wilt and blight into the next season."},
    "onion":     {"best": "compost", "good": ["soil_incorporation"], "note": ""},
    "mustard":   {"best": "soil_incorporation", "good": ["compost", "biogas"],
                  "note": ""},
    "sorghum":   {"best": "fodder", "good": ["compost", "mulch"],
                  "note": "Sorghum stover is widely used as fodder."},
}


def route_residue(*, crop: str, residue_kg: Optional[float] = None,
                  has_biogas: bool = False,
                  has_cattle: bool = False) -> Dict[str, Any]:
    """Suggest what to do with this crop's residue.

    Deliberately does NOT push everything into biogas. Wheat straw is worth
    more as fodder, rice straw suits soil incorporation, and diseased tomato
    residue must be composted or removed regardless of what a digester could
    take. Forcing all residue into the digester would be a worse outcome
    dressed up as circularity.
    """
    key = (crop or "").strip().lower()
    profile = RESIDUE_PROFILE.get(key)
    if profile is None:
        return {
            "available": False, "crop": key,
            "note": ("No specific residue guidance for this crop. Composting "
                     "is almost always a safe default. Do not burn it."),
        }

    best = profile["best"]
    options = [best] + [r for r in profile["good"] if r != best]

    # Only offer biogas if they actually have or are planning a digester.
    if not has_biogas:
        options = [r for r in options if r != "biogas"]
    if not has_cattle:
        options = [r for r in options if r != "fodder"]
    if not options:
        options = ["compost"]

    recommended = options[0]

    return {
        "available": True,
        "crop": key,
        "residue_kg": residue_kg,
        "recommended_route": recommended,
        "recommended_label": ROUTES.get(recommended, recommended),
        "why": profile.get("note") or "",
        "other_options": [{"route": r, "label": ROUTES[r]} for r in options[1:]],
        "all_routes": [{"route": r, "label": l} for r, l in ROUTES.items()],
        "never": "Do not burn crop residue. It destroys soil organic matter, "
                 "pollutes the air, and is an offence in several states.",
        "caveat": ("A suggestion based on the crop and what your farm has. "
                   "Local practice, labour and fodder prices all matter and "
                   "may point elsewhere."),
    }


# =====================================================================
# Choosing a composting method
# =====================================================================
"""
WHY FOUR METHODS AND NOT ONE
----------------------------
The spec is right that farmers must not all be pushed into the same method.
They genuinely differ in what they need and what they produce:

  * Vermicompost is the most valuable product but needs shade, steady
    moisture, and dung that has already part-decomposed — fresh dung heats up
    and kills the worms. It is the wrong answer for someone with no shade.
  * Plain compost handles bulky crop residue, which vermicompost cannot.
  * Farmyard manure is the lowest-effort option and the right answer for a
    farmer with plenty of dung and no spare labour.
  * Liquid preparations are ready in a week, which matters when a crop needs
    something NOW and a 4-month heap does not help.

So the method is chosen from what the farm actually has.
"""

# C:N ratio is what actually decides whether a heap composts or just sits
# there. Dung is nitrogen-rich, dry residue is carbon-rich, and a workable
# mix needs roughly 25-30 parts carbon to 1 part nitrogen.
TARGET_CN_RATIO = "25-30:1"

COMPOST_METHODS = {
    "vermicompost": {
        "name": "Vermicompost",
        "icon": "worm",
        "product": "Worm castings — the richest of the four",
        "weeks": (7, 9),
        "needs": ["Shade — direct sun kills the worms",
                  "Steady moisture, checked every few days",
                  "Earthworms to start (about 1 kg per 100 kg of waste)"],
        "why_not": "Not suitable without shade or if you cannot water regularly.",
        "materials": [
            ("Cattle dung, part-decomposed", 0.60),
            ("Chopped crop residue or dry leaves", 0.35),
            ("Garden soil", 0.05),
        ],
        "steps": [
            "Leave fresh dung in a heap for 15-20 days first. Fresh dung "
            "heats up and will kill the worms.",
            "Make a bed about 1 metre wide and 30 cm deep in full shade.",
            "Layer the part-rotted dung with chopped residue.",
            "Release the earthworms on top and cover with a gunny sack.",
            "Sprinkle water daily to keep it as damp as a squeezed sponge — "
            "never waterlogged.",
            "Do NOT turn it. The worms do the mixing.",
            "Harvest when the top layer is dark and granular, usually after "
            "7-9 weeks.",
        ],
        "ready_signs": [
            "Dark brown, loose and granular like tea leaves",
            "Smells of earth, not of dung",
            "Worms have moved down to the bottom",
        ],
    },
    "compost": {
        "name": "Compost",
        "icon": "heap",
        "product": "General-purpose compost, good bulk for the soil",
        "weeks": (12, 16),
        "needs": ["Space for a heap or pit about 3 x 2 metres",
                  "Labour to turn it every 2-3 weeks",
                  "Water to keep it damp"],
        "why_not": "Slower than vermicompost and needs turning by hand.",
        "materials": [
            ("Dry crop residue, chopped small", 0.60),
            ("Cattle dung", 0.30),
            ("Green leaves or weeds", 0.08),
            ("Garden soil or old compost", 0.02),
        ],
        "steps": [
            "Chop crop residue small. Whole stalks take a year; chopped "
            "material takes months.",
            "Build the heap in layers: dry residue, then dung, then a "
            "sprinkle of soil. Repeat.",
            "Water each layer as you build so the whole heap is evenly damp.",
            "Cover with soil, mud plaster or an old sack to hold moisture in.",
            "Turn the whole heap every 2-3 weeks. Turning is what keeps air "
            "in it — an unturned heap goes sour and smells.",
            "Keep it as damp as a squeezed sponge throughout.",
        ],
        "ready_signs": [
            "Dark brown to black, crumbles in the hand",
            "You can no longer recognise the original straw or leaves",
            "Smells earthy, not sour or of ammonia",
            "The heap has stopped feeling warm inside",
        ],
    },
    "fym": {
        "name": "Farmyard manure",
        "icon": "shed",
        "product": "Bulk manure — least effort, lowest nutrient value",
        "weeks": (16, 24),
        "needs": ["A pit or covered heap", "Very little labour"],
        "why_not": "Takes the longest and is the weakest of the four.",
        "materials": [
            ("Cattle dung with shed bedding", 0.85),
            ("Crop residue or straw", 0.15),
        ],
        "steps": [
            "Collect dung together with the bedding from the shed.",
            "Heap it in a shallow pit, or on ground you have rammed flat.",
            "Plaster the outside with mud, or cover it, so nitrogen is not "
            "lost to the air and rain does not wash it away.",
            "Leave it. Turn once after about 3 months if you can.",
            "Keep it out of standing water — a waterlogged heap loses most of "
            "its value.",
        ],
        "ready_signs": [
            "Dark and well rotted throughout",
            "No smell of fresh dung",
            "Original bedding no longer recognisable",
        ],
    },
    "liquid": {
        "name": "Liquid organic manure",
        "icon": "drum",
        "product": "A soil drench, ready in about a week",
        "weeks": (1, 2),
        "needs": ["A drum and a shaded spot", "Only a small amount of dung"],
        "why_not": "Feeds soil life rather than supplying bulk nutrition. It "
                   "does not replace compost.",
        "materials": [
            ("Fresh cattle dung", 0.50),
            ("Cattle urine where available", 0.25),
            ("Jaggery", 0.10),
            ("Gram or pulse flour", 0.10),
            ("Handful of undisturbed field soil", 0.05),
        ],
        "steps": [
            "Put dung, urine, jaggery and flour into a 200 litre drum.",
            "Add a handful of soil from an uncultivated field corner — it "
            "carries the microbes that do the work.",
            "Fill with water and stir well.",
            "Stir clockwise twice a day, morning and evening.",
            "Keep the drum in shade, loosely covered — never sealed tight.",
            "Ready in 5-7 days. Use within about a week of that.",
        ],
        "ready_signs": [
            "A froth has formed on the surface",
            "Smells fermented and sour, not putrid",
        ],
    },
}


def choose_method(*, dung_kg_per_day: float = 0.0,
                  residue_kg: float = 0.0,
                  has_shade: bool = True,
                  labour: str = "normal",
                  urgent: bool = False) -> Dict[str, Any]:
    """Pick a composting method from what the farm actually has.

    Returns the recommendation AND the alternatives, with the reason for each,
    so the farmer can overrule it. They know things about their own farm that
    this function does not.
    """
    scores: Dict[str, float] = {k: 1.0 for k in COMPOST_METHODS}
    notes: Dict[str, str] = {}

    # Urgency beats everything: a 4-month heap does not help a crop that needs
    # feeding this month.
    if urgent:
        scores["liquid"] += 4
        notes["liquid"] = "Ready in about a week, which is what you asked for."

    if has_shade and dung_kg_per_day >= 10:
        scores["vermicompost"] += 3
        notes["vermicompost"] = ("You have shade and enough dung, and this "
                                 "gives the most valuable product.")
    elif not has_shade:
        scores["vermicompost"] -= 3
        notes["vermicompost"] = ("Skipped: worms need shade, and without it "
                                 "they will not survive.")

    # Bulky residue is compost's strength and vermicompost's weakness.
    if residue_kg >= 500:
        scores["compost"] += 3
        notes["compost"] = ("You have a lot of crop residue, and a compost "
                            "heap handles bulky material best.")

    if labour == "low":
        scores["fym"] += 3
        scores["compost"] -= 2
        # Vermicompost must be penalised too, not just compost. It needs
        # watering every few days and the worms die if it dries out — that is
        # MORE day-to-day work than a compost heap, not less. Recommending it
        # to someone who said they have no spare labour sets them up to lose
        # the worms.
        scores["vermicompost"] -= 3
        notes["fym"] = ("Chosen because it needs the least work — no turning, "
                        "no daily watering.")
        notes["vermicompost"] = ("Skipped: worms need watering every few days "
                                 "and die if the bed dries out.")
    if dung_kg_per_day >= 40 and labour != "low":
        scores["compost"] += 1

    if dung_kg_per_day < 10:
        scores["fym"] -= 2
        scores["compost"] -= 1
        notes["liquid"] = notes.get(
            "liquid",
            "You have only a small amount of dung, which suits a liquid "
            "preparation better than a heap.")
        scores["liquid"] += 2

    best = max(scores, key=lambda k: scores[k])
    spec = COMPOST_METHODS[best]

    return {
        "recommended": best,
        "name": spec["name"],
        "product": spec["product"],
        "why": notes.get(best, "Best fit for the waste and conditions you have."),
        "weeks": {"low": spec["weeks"][0], "high": spec["weeks"][1]},
        "needs": spec["needs"],
        "steps": spec["steps"],
        "ready_signs": spec["ready_signs"],
        "alternatives": [
            {"key": k, "name": COMPOST_METHODS[k]["name"],
             "product": COMPOST_METHODS[k]["product"],
             "why_not": COMPOST_METHODS[k]["why_not"],
             "note": notes.get(k, ""),
             "weeks": {"low": COMPOST_METHODS[k]["weeks"][0],
                       "high": COMPOST_METHODS[k]["weeks"][1]}}
            for k in COMPOST_METHODS if k != best
        ],
        "caveat": (
            "A suggestion from what your farm has. You know your own "
            "conditions — pick another method if it suits you better."),
    }


def materials_for(method: str, total_input_kg: float) -> Dict[str, Any]:
    """Split a total quantity into the materials this method needs."""
    spec = COMPOST_METHODS.get(method)
    if not spec or total_input_kg <= 0:
        return {"available": False}

    return {
        "available": True,
        "method": method,
        "total_input_kg": round(total_input_kg),
        "materials": [
            {"material": name, "approx_kg": round(total_input_kg * share),
             "share_pct": round(share * 100)}
            for name, share in spec["materials"]
        ],
        "moisture": (
            "Keep it as damp as a squeezed sponge — a handful should hold "
            "together and release a drop or two, not run water."),
        "cn_note": (
            f"Dry residue supplies carbon and dung supplies nitrogen. A "
            f"workable mix is roughly {TARGET_CN_RATIO}. Too much dung goes "
            f"slimy and smells of ammonia; too much straw simply sits there."),
        "caveat": "Approximate proportions. Adjust to what you actually have.",
    }


def estimate_output(total_input_kg: float, method: str) -> Dict[str, Any]:
    """How much finished manure comes out.

    Composting loses a lot of mass — water evaporates and carbon leaves as
    CO2. Typical recovery is 40-50% of what went in, and a farmer who expects
    1:1 will think something has gone wrong.
    """
    spec = COMPOST_METHODS.get(method)
    if not spec or total_input_kg <= 0:
        return {"available": False}

    lo, hi = (0.30, 0.40) if method == "vermicompost" else (0.40, 0.55)
    return {
        "available": True,
        "output_kg": {"low": round(total_input_kg * lo),
                      "high": round(total_input_kg * hi)},
        "ready_in_weeks": {"low": spec["weeks"][0], "high": spec["weeks"][1]},
        "loss_note": (
            "Roughly half the weight is lost as water and gas while it rots. "
            "That is normal — what is left is far more concentrated."),
        "time_note": (
            "Actual time depends on the material, moisture, temperature, how "
            "often you turn it and how small it was chopped. Warm weather is "
            "faster; winter is slower."),
        "confidence": "ESTIMATED",
    }
