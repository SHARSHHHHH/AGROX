"""Deterministic irrigation safety guard for automated pump control.

WHY THIS EXISTS SEPARATELY FROM recommendation.py
-------------------------------------------------
`recommendation.recommend_irrigation()` produces ADVICE for a human to read.
This module decides whether a physical pump is allowed to switch on. Those are
different risk levels: bad advice wastes a farmer's afternoon, an unsafe pump
command floods a field, burns out a dry-running pump, or drains a tank.

Nothing here consults the LLM. Every gate is arithmetic over sensor readings.
The LLM cannot reach this code path, and there is deliberately no parameter by
which a model could override a block.

BLOCKING GATES (any one blocks the pump)
    1. Stale sensor data      — acting on an old reading is guesswork
    2. Soil already saturated — over-irrigation causes root rot and leaching
    3. Heavy rain forecast    — wastes water and risks waterlogging
    4. Water source too low   — running a pump dry destroys the impeller
    5. Duration out of bounds — a stuck command must not run indefinitely
"""

from datetime import datetime, timedelta, timezone
from typing import List, Optional

from app.services.recommendation import classify_moisture, recommend_irrigation

# --- Safety limits ---------------------------------------------------------
MAX_SENSOR_AGE_MINUTES = 30      # older than this is not trustworthy
SATURATION_MOISTURE_PCT = 85     # above this the soil cannot take more water
MIN_WATER_LEVEL_PCT = 15         # below this the pump risks running dry
RAIN_BLOCK_PROBABILITY = 70      # percent
MAX_RUN_MINUTES = 45             # hard ceiling on any single command
MIN_RUN_MINUTES = 5              # shorter than this just cycles the motor


class IrrigationDecision:
    """Result of a pump-control safety evaluation."""

    def __init__(self, allowed: bool, duration_min: int = 0,
                 reason: str = "", blocks: Optional[List[str]] = None,
                 priority: str = "LOW", advisory: Optional[dict] = None):
        self.allowed = allowed
        self.duration_min = duration_min
        self.reason = reason
        self.blocks = blocks or []
        self.priority = priority
        self.advisory = advisory or {}

    def to_dict(self) -> dict:
        return {
            "allowed": self.allowed,
            "duration_min": self.duration_min,
            "reason": self.reason,
            "blocks": self.blocks,
            "priority": self.priority,
            "advisory": self.advisory,
            "decided_by": "deterministic_rule_engine",
        }


def _reading_age_minutes(reading_time: Optional[datetime]) -> Optional[float]:
    if reading_time is None:
        return None
    now = datetime.now(timezone.utc)
    if reading_time.tzinfo is None:
        # Sensor rows are stored naive-UTC by the existing models.
        reading_time = reading_time.replace(tzinfo=timezone.utc)
    return (now - reading_time).total_seconds() / 60.0


def evaluate_pump_request(*, soil_moisture: Optional[float],
                          water_level: Optional[float],
                          temperature: Optional[float] = None,
                          humidity: Optional[float] = None,
                          rain_probability: int = 0,
                          crop: str = "default",
                          growth_stage: str = "",
                          soil_type: str = "",
                          reading_time: Optional[datetime] = None,
                          requested_minutes: Optional[int] = None,
                          manual_override: bool = False) -> IrrigationDecision:
    """Decide whether the pump may run, and for how long.

    `manual_override` lets a farmer force irrigation the advisory would not
    recommend — but it does NOT bypass the hardware-safety gates (stale data,
    dry water source, saturated soil). Those exist to protect equipment and
    the field, not to enforce an opinion.
    """
    blocks: List[str] = []

    # --- Gate 1: sensor freshness ---
    age = _reading_age_minutes(reading_time)
    if reading_time is None or soil_moisture is None:
        blocks.append("No sensor reading is available. Automated irrigation "
                      "requires live soil moisture data.")
    elif age is not None and age > MAX_SENSOR_AGE_MINUTES:
        blocks.append(f"Sensor reading is {age:.0f} minutes old (limit "
                      f"{MAX_SENSOR_AGE_MINUTES}). Refusing to act on stale data.")

    # --- Gate 2: saturation ---
    if soil_moisture is not None and soil_moisture >= SATURATION_MOISTURE_PCT:
        blocks.append(f"Soil moisture is {soil_moisture}% (saturation threshold "
                      f"{SATURATION_MOISTURE_PCT}%). More water would cause "
                      f"waterlogging and nutrient leaching.")

    # --- Gate 3: water source ---
    if water_level is None:
        blocks.append("Water level is unknown. Running a pump without knowing "
                      "the source level risks dry-running damage.")
    elif water_level < MIN_WATER_LEVEL_PCT:
        blocks.append(f"Water level is {water_level}% (minimum "
                      f"{MIN_WATER_LEVEL_PCT}%). Running the pump now risks "
                      f"dry-running and impeller damage.")

    # --- Gate 4: rain (advisory gate, overridable by the farmer) ---
    rain_block = rain_probability >= RAIN_BLOCK_PROBABILITY
    if rain_block and not manual_override:
        blocks.append(f"Rain probability is {rain_probability}%. Irrigating now "
                      f"would waste water.")

    # Advisory from the existing engine, for context in the response.
    advisory = {}
    if soil_moisture is not None:
        advisory = recommend_irrigation(
            soil_moisture=soil_moisture,
            temperature=temperature if temperature is not None else 28,
            humidity=humidity if humidity is not None else 60,
            rain_probability=rain_probability,
            crop=crop, growth_stage=growth_stage, soil_type=soil_type)

    if blocks:
        return IrrigationDecision(
            allowed=False, duration_min=0,
            reason="Pump blocked by " + str(len(blocks)) +
                   (" safety check." if len(blocks) == 1 else " safety checks."),
            blocks=blocks, priority="LOW", advisory=advisory)

    # --- Duration ---
    if requested_minutes is not None:
        duration = int(requested_minutes)
    else:
        duration = int(advisory.get("duration_min", 0) or 0)

    if duration <= 0 and not manual_override:
        return IrrigationDecision(
            allowed=False, duration_min=0,
            reason=advisory.get("reason", "Irrigation is not needed right now."),
            blocks=[], priority="LOW", advisory=advisory)

    # --- Gate 5: clamp duration. A stuck command must never run forever. ---
    clamped = max(MIN_RUN_MINUTES, min(MAX_RUN_MINUTES, duration or MIN_RUN_MINUTES))
    note = ""
    if clamped != duration:
        note = (f" Requested {duration} min was clamped to {clamped} min "
                f"(allowed range {MIN_RUN_MINUTES}-{MAX_RUN_MINUTES}).")

    status = classify_moisture(soil_moisture, crop) if soil_moisture is not None else "UNKNOWN"
    priority = advisory.get("priority", "MEDIUM")
    if manual_override and rain_block:
        note += " Manual override applied despite rain forecast."

    return IrrigationDecision(
        allowed=True, duration_min=clamped,
        reason=(f"Safety checks passed. Soil moisture {soil_moisture}% "
                f"({status.lower()}), water level {water_level}%, rain "
                f"probability {rain_probability}%.{note}"),
        blocks=[], priority=priority, advisory=advisory)


def grounded_facts(decision: IrrigationDecision) -> List[str]:
    """Fact lines for the agent's context.

    The wording is emphatic because the model must not reinterpret a block as a
    soft suggestion.
    """
    if decision.allowed:
        facts = [f"Irrigation decision: APPROVED for {decision.duration_min} "
                 f"minutes.", f"Reason: {decision.reason}"]
    else:
        facts = ["Irrigation decision: BLOCKED by the deterministic safety "
                 "engine.", f"Reason: {decision.reason}"]
        facts += [f"Blocking condition: {b}" for b in decision.blocks]
        facts.append("This decision is final. Do NOT tell the farmer to "
                     "irrigate or to override it.")
    return facts
