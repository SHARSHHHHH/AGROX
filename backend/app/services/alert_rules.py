"""Alert rules. Arithmetic and lookups only — no model is called from here.

WHY NO LLM IN THIS FILE
-----------------------
An alert tells a farmer to irrigate, to cut drainage channels, or that
compensation of a certain amount has been announced. Every one of those is a
factual claim they will act on, sometimes at real cost.

So the facts are computed here from sensors, forecasts, their own farm record
and admin-curated official advisories. The LLM's only job, elsewhere, is to
rephrase a finished alert into the farmer's language. It cannot originate a
number, a district, a scheme or an amount, because it is never asked to.

EVERY RULE RETURNS THE SAME SHAPE
---------------------------------
    {
      type, category, priority, title, message, action,
      dedupe_key,            # identifies the SITUATION, not the alert type
      expires_in_hours,      # how long this occurrence stays valid
      source_name, source_url, source_date, payload
    }

`message` says what happened and why it matters. `action` says what to do.
Keeping them apart lets the UI emphasise the action, and makes an alert with
no useful action immediately obvious rather than hidden in a paragraph.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional

log = logging.getLogger("agri.alert_rules")

CRITICAL, HIGH, MEDIUM, LOW = "CRITICAL", "HIGH", "MEDIUM", "LOW"

# Legacy severity, kept so existing clients and tests keep working.
_SEVERITY = {CRITICAL: "CRITICAL", HIGH: "WARNING",
             MEDIUM: "WARNING", LOW: "INFO"}


def _alert(type_: str, category: str, priority: str, title: str,
           message: str, action: str = "", *, dedupe_key: str,
           expires_in_hours: int = 24, source_name: str = "",
           source_url: str = "", source_date=None,
           payload: Optional[dict] = None) -> Dict[str, Any]:
    return {
        "type": type_, "category": category, "priority": priority,
        "severity": _SEVERITY.get(priority, "INFO"),
        "title": title, "message": message, "action": action,
        "dedupe_key": dedupe_key, "expires_in_hours": expires_in_hours,
        "source_name": source_name, "source_url": source_url,
        "source_date": source_date, "payload": payload or {},
    }


def _today() -> str:
    return date.today().isoformat()


def _bucket(value: Optional[float], size: int = 10) -> str:
    """Round a value into a band for dedup.

    Moisture drifting 31% -> 29% is the same situation and must not produce a
    second alert. Dropping 31% -> 12% is a different, worse situation and
    should. Bucketing gives exactly that behaviour.
    """
    if value is None:
        return "na"
    return str(int(value // size) * size)


# =====================================================================
# 1. Irrigation
# =====================================================================

def irrigation(*, moisture: Optional[float], moisture_status: str,
               crop_display: str, rain_probability: Optional[float],
               rain_mm_5day: Optional[float],
               stage: str = "") -> List[Dict[str, Any]]:
    """Low moisture -> irrigate. Unless rain is coming, in which case wait.

    The forecast check is the whole point. Telling a farmer to irrigate the
    afternoon before 40 mm of rain wastes diesel, wastes water, and waterlogs
    the field. So rain outranks a dry sensor.
    """
    out: List[Dict[str, Any]] = []
    if moisture is None or moisture_status not in ("LOW", "VERY LOW"):
        return out

    rain_soon = (rain_probability or 0) >= 60 or (rain_mm_5day or 0) >= 15
    key_moist = _bucket(moisture)

    if rain_soon:
        out.append(_alert(
            "IRRIGATION_HOLD", "irrigation", MEDIUM,
            "Soil is dry, but rain is expected",
            f"Soil moisture is {moisture}% ({moisture_status.lower()}) for your "
            f"{crop_display}. Rain is forecast "
            f"({int(rain_probability or 0)}% chance"
            + (f", about {round(rain_mm_5day)} mm over 5 days" if rain_mm_5day else "")
            + ").",
            "Hold off irrigating for now and check again after the rain. "
            "Irrigating before rain wastes water and risks waterlogging.",
            dedupe_key=f"irrigation_hold:{_today()}:{key_moist}",
            expires_in_hours=24,
            payload={"moisture": moisture, "rain_probability": rain_probability}))
        return out

    priority = CRITICAL if moisture_status == "VERY LOW" else HIGH
    stage_note = (f" Your crop is at the {stage} stage, when water stress "
                  f"costs the most yield." if stage else "")
    out.append(_alert(
        "IRRIGATION_NEEDED", "irrigation", priority,
        "Your field needs water",
        f"Soil moisture is {moisture}% ({moisture_status.lower()}) for your "
        f"{crop_display}, and no useful rain is forecast.{stage_note}",
        "Irrigate as soon as you can. Check your tank level first, and water "
        "in the early morning or evening to reduce evaporation loss.",
        dedupe_key=f"irrigation_needed:{_today()}:{key_moist}",
        expires_in_hours=18,
        payload={"moisture": moisture, "status": moisture_status}))
    return out


# =====================================================================
# 2. Water tank
# =====================================================================

def water_tank(*, level: Optional[float]) -> List[Dict[str, Any]]:
    """Tank level in both directions: too empty to irrigate, or overflowing."""
    if level is None:
        return []

    key = _bucket(level, 5)

    if level >= 98:
        return [_alert(
            "TANK_FULL", "water_tank", CRITICAL, "Water tank is full",
            f"Tank level is {level}%. It will overflow if filling continues.",
            "Stop the pump or close the inlet now. Overflow wastes water and "
            "can erode the ground around the tank.",
            dedupe_key=f"tank_full:{_today()}:{key}", expires_in_hours=6,
            payload={"level": level})]

    if level >= 90:
        return [_alert(
            "TANK_ALMOST_FULL", "water_tank", MEDIUM, "Water tank almost full",
            f"Tank level is {level}%.",
            "Plan to stop filling shortly to avoid overflow.",
            dedupe_key=f"tank_almost_full:{_today()}:{key}", expires_in_hours=6,
            payload={"level": level})]

    if level < 10:
        return [_alert(
            "TANK_CRITICAL", "water_tank", CRITICAL, "Water tank nearly empty",
            f"Tank level is {level}%. You cannot irrigate from it.",
            "Refill now. If you have an irrigation planned today, arrange "
            "water before it.",
            dedupe_key=f"tank_critical:{_today()}:{key}", expires_in_hours=12,
            payload={"level": level})]

    if level < 25:
        return [_alert(
            "TANK_LOW", "water_tank", HIGH, "Water tank running low",
            f"Tank level is {level}%.",
            "Refill soon so an irrigation is not delayed when the crop needs it.",
            dedupe_key=f"tank_low:{_today()}:{key}", expires_in_hours=12,
            payload={"level": level})]

    return []


# =====================================================================
# 3. Weather
# =====================================================================

def weather(*, temperature: Optional[float], rain_probability: Optional[float],
            rain_mm_5day: Optional[float], wind_kph: Optional[float],
            wet_days_ahead: int = 0, moisture: Optional[float] = None,
            crop_display: str = "your crop") -> List[Dict[str, Any]]:
    """Heat, wind, heavy rain, and the multi-day wet spell."""
    out: List[Dict[str, Any]] = []

    # --- prolonged wet spell: the one the spec calls out explicitly ---
    if wet_days_ahead >= 4:
        wet_note = ""
        if moisture is not None and moisture >= 60:
            wet_note = (f" Your soil moisture is already {moisture}%, so the "
                        f"field has little capacity to absorb more.")
        out.append(_alert(
            "PROLONGED_RAIN", "weather", HIGH,
            f"Heavy rain expected for {wet_days_ahead} days",
            f"Rain is forecast on {wet_days_ahead} of the next days"
            + (f", around {round(rain_mm_5day)} mm in total" if rain_mm_5day else "")
            + f".{wet_note}",
            "Clear and deepen your drainage channels before the rain starts, "
            "and stop irrigating. Standing water for more than two days damages "
            "roots on most crops.",
            dedupe_key=f"prolonged_rain:{_today()}:{wet_days_ahead}",
            expires_in_hours=48,
            payload={"wet_days": wet_days_ahead, "rain_mm_5day": rain_mm_5day,
                     "moisture": moisture}))

    elif (rain_probability or 0) >= 80 or (rain_mm_5day or 0) >= 40:
        out.append(_alert(
            "HEAVY_RAIN", "weather", MEDIUM, "Heavy rain expected",
            f"Rain probability is {int(rain_probability or 0)}%"
            + (f", about {round(rain_mm_5day)} mm expected" if rain_mm_5day else "")
            + ".",
            "Postpone irrigation and any spraying — rain within a few hours "
            "washes most sprays off before they work.",
            dedupe_key=f"heavy_rain:{_today()}:{_bucket(rain_probability)}",
            expires_in_hours=24,
            payload={"rain_probability": rain_probability}))

    # --- heat ---
    if temperature is not None and temperature >= 42:
        out.append(_alert(
            "EXTREME_HEAT", "weather", CRITICAL, "Extreme heat",
            f"Temperature is {temperature}°C. {crop_display} will be under "
            f"severe heat stress, and flowers may drop.",
            "Irrigate in the early morning or after sunset. Do not spray in "
            "the middle of the day. Avoid working in the field at midday.",
            dedupe_key=f"extreme_heat:{_today()}:{_bucket(temperature, 2)}",
            expires_in_hours=18, payload={"temperature": temperature}))
    elif temperature is not None and temperature >= 38:
        out.append(_alert(
            "HIGH_TEMPERATURE", "weather", HIGH, "High temperature",
            f"Temperature is {temperature}°C, high enough to stress "
            f"{crop_display}.",
            "Water in the cooler hours and keep soil covered where you can.",
            dedupe_key=f"high_temp:{_today()}:{_bucket(temperature, 2)}",
            expires_in_hours=18, payload={"temperature": temperature}))

    # --- wind ---
    if wind_kph is not None and wind_kph >= 45:
        out.append(_alert(
            "STRONG_WIND", "weather", HIGH, "Strong wind expected",
            f"Wind of about {round(wind_kph)} km/h is forecast. Tall crops can "
            f"lodge, and spraying will drift.",
            "Do not spray today. Check that staked and trellised crops are "
            "secured, and harvest anything already mature if you can.",
            dedupe_key=f"strong_wind:{_today()}:{_bucket(wind_kph, 10)}",
            expires_in_hours=18, payload={"wind_kph": wind_kph}))

    return out


# =====================================================================
# 4. Nearby pest / disease
# =====================================================================

def nearby_pest(*, reports: List[dict], crop_display: str,
                district: str) -> List[Dict[str, Any]]:
    """Same crop, same pest, a neighbouring district.

    THE WORDING RULE
    ----------------
    This must never read as "your field is infected". It is a report from
    somewhere else. A farmer who sprays on the strength of a neighbouring
    district's outbreak has spent money on a problem they may not have — so
    the message says where it was seen, and the action says scout first.

    `reports` comes from this app's own pest_observations table: other farmers'
    confirmed detections. Real data, already owned, no external source.
    """
    out: List[Dict[str, Any]] = []
    for r in reports:
        pest = r.get("pest_name") or "a pest"
        where = r.get("district") or "a nearby district"
        count = r.get("count", 1)
        out.append(_alert(
            "NEARBY_PEST", "pest_nearby", HIGH,
            f"{pest} reported near you",
            f"{count} farmer(s) growing {crop_display} in {where} have reported "
            f"{pest} in the last two weeks. Your field in {district} has NOT "
            f"been reported as affected — this is a warning about your area, "
            f"not a diagnosis of your crop.",
            f"Walk your field this week and check for early signs of {pest}. "
            f"Confirm what you find before spraying anything — treating a "
            f"problem you do not have costs money and harms beneficial insects.",
            dedupe_key=f"nearby_pest:{r.get('pest_key', pest)}:{where}:"
                       f"{date.today().isocalendar()[1]}",
            expires_in_hours=24 * 10,
            payload={"pest": pest, "reported_in": where, "reports": count,
                     "your_district": district, "is_your_field": False}))
    return out


# =====================================================================
# 5, 6, 7. Official advisories: schemes, flood/disaster, compensation
# =====================================================================

# Priority floor per advisory kind. A flood warning is never "low".
_KIND_META = {
    "scheme": ("scheme", "SCHEME_MATCH", MEDIUM),
    "flood": ("disaster", "FLOOD_WARNING", CRITICAL),
    "disaster": ("disaster", "DISASTER_WARNING", CRITICAL),
    "compensation": ("compensation", "COMPENSATION_ANNOUNCED", HIGH),
    "supplies": ("supplies", "SUPPLY_OFFER", LOW),
}


def official_advisory(adv: dict, *, crop_display: str,
                      district: str) -> Optional[Dict[str, Any]]:
    """Turn one admin-curated official advisory into a personalised alert.

    Every field here comes from the stored row. Nothing is generated: the
    amount, the district and the source URL are copied through verbatim so a
    farmer can carry the link to an officer and have it match.
    """
    kind = (adv.get("kind") or "").lower()
    category, type_, priority = _KIND_META.get(kind, ("general", "ADVISORY", MEDIUM))
    priority = adv.get("priority") or priority

    title = adv.get("title") or "Government advisory"
    message = adv.get("summary") or title
    action = adv.get("action") or ""

    # Money, stated exactly as announced.
    amount = adv.get("amount")
    if amount is not None:
        unit = adv.get("amount_unit") or ""
        message += f"\n\nAnnounced amount: ₹{amount:,.0f} {unit}".rstrip()
        if adv.get("amount_note"):
            message += f" — {adv['amount_note']}"

    if district:
        message += f"\n\nThis applies to your district ({district})."

    if not action:
        action = ("Read the official notice at the source link before acting, "
                  "and take it to your local agriculture office if you need help.")

    return _alert(
        type_, category, priority, title, message, action,
        dedupe_key=f"advisory:{adv.get('id')}",
        expires_in_hours=adv.get("expires_in_hours", 24 * 30),
        source_name=adv.get("source_name", ""),
        source_url=adv.get("source_url", ""),
        source_date=adv.get("published_on"),
        payload={"advisory_id": adv.get("id"), "kind": kind,
                 "amount": amount, "amount_unit": adv.get("amount_unit"),
                 "crop": crop_display, "district": district,
                 "verified_source": True})


# =====================================================================
# 8 & 9. Supplies and machinery already in the app
# =====================================================================

def machinery_nearby(*, listings: List[dict], reason: str,
                     stage: str = "") -> List[Dict[str, Any]]:
    """Rental listings, surfaced when the crop calendar says they are wanted.

    Not a standing advert. It fires when the crop is approaching a stage that
    needs a machine, because that is when the information is useful and when
    machines get booked out.
    """
    if not listings:
        return []
    top = listings[0]
    names = ", ".join(l.get("machine_name", "") for l in listings[:3] if l.get("machine_name"))
    return [_alert(
        "MACHINERY_AVAILABLE", "machinery", LOW,
        "Equipment available near you",
        f"{reason} {len(listings)} listing(s) near you: {names}. "
        f"Nearest is about {top.get('distance_km', '?')} km away.",
        "Book early — machines get reserved quickly at the peak of the season. "
        "Confirm whether diesel and an operator are included in the quoted rate.",
        dedupe_key=f"machinery:{stage or 'general'}:{date.today().isocalendar()[1]}",
        expires_in_hours=24 * 7,
        payload={"listings": listings[:5], "count": len(listings)})]


def supply_offers(*, offers: List[dict]) -> List[Dict[str, Any]]:
    """Fertiliser / manure offers from the app's own marketplace."""
    if not offers:
        return []
    return [_alert(
        "SUPPLY_OFFER", "supplies", LOW,
        "Fertiliser and manure available nearby",
        f"{len(offers)} verified seller(s) near you are offering inputs: "
        + ", ".join(o.get("title", "") for o in offers[:3]) + ".",
        "Compare against your soil test before buying — buying nutrients the "
        "soil already has is wasted money.",
        dedupe_key=f"supplies:{date.today().isocalendar()[1]}",
        expires_in_hours=24 * 7,
        payload={"offers": offers[:5], "count": len(offers)})]


# =====================================================================
# 10. Crop lifecycle
# =====================================================================

# Stages worth interrupting a farmer for. Most stage changes are not.
_KEY_STAGE_WORDS = {
    "flowering": (HIGH, "Flowering is the most water- and nutrient-sensitive "
                        "stage. Stress now cannot be recovered later."),
    "panicle": (HIGH, "Panicle initiation is when the yield potential is set."),
    "pod": (HIGH, "Pod filling decides your final grain weight."),
    "grain filling": (HIGH, "Grain filling decides your final grain weight."),
    "tuber": (HIGH, "Tuber bulking is the heaviest water demand of the crop."),
    "bulb": (HIGH, "Bulb development decides your final size and storage life."),
    "tillering": (MEDIUM, "Tillering sets how many productive shoots you get."),
    "maturity": (HIGH, "The crop is approaching harvest."),
    "harvest": (HIGH, "The crop is at or near harvest."),
}


def lifecycle_stage(*, crop_display: str, stage: dict,
                    days_after_sowing: Optional[int],
                    days_to_harvest: Optional[int]) -> List[Dict[str, Any]]:
    """Fire when the crop reaches a stage that changes what must be done."""
    out: List[Dict[str, Any]] = []
    if not stage or not stage.get("stage"):
        return out

    name = stage["stage"]
    lower = name.lower()
    match = next((v for k, v in _KEY_STAGE_WORDS.items() if k in lower), None)
    if match is None:
        return out
    priority, why = match

    tasks = stage.get("tasks") or []
    action = (" ".join(f"{i+1}. {t}." for i, t in enumerate(tasks[:3]))
              if tasks else "Check the crop lifecycle page for this stage.")

    out.append(_alert(
        "LIFECYCLE_STAGE", "lifecycle", priority,
        f"{crop_display} has reached {name}",
        f"Your {crop_display} is about {days_after_sowing} days after sowing "
        f"and is now estimated to be at the {name} stage. {why}",
        action,
        dedupe_key=f"lifecycle:{crop_display}:{name}",
        # A stage lasts weeks; one alert per stage is the point.
        expires_in_hours=24 * 21,
        payload={"stage": name, "days_after_sowing": days_after_sowing,
                 "tasks": tasks, "estimated": True}))

    if days_to_harvest is not None and 0 < days_to_harvest <= 14:
        out.append(_alert(
            "HARVEST_APPROACHING", "lifecycle", HIGH,
            f"{crop_display} harvest is about {days_to_harvest} days away",
            f"Based on your sowing date and the typical duration for "
            f"{crop_display}, harvest is approaching. This is an estimate — "
            f"confirm by checking the crop.",
            "Arrange labour and machinery now, watch the weather forecast, and "
            "plan where you will dry and store the produce.",
            dedupe_key=f"harvest_soon:{crop_display}:"
                       f"{date.today().isocalendar()[1]}",
            expires_in_hours=24 * 7,
            payload={"days_to_harvest": days_to_harvest, "estimated": True}))

    return out
