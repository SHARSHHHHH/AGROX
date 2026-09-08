"""Integrated Pest Management (IPM) decision engine + sustainable treatment
ranking.

This is deterministic and is the SOURCE OF TRUTH for pest recommendations — the
LLM never decides treatment. It only explains what this engine produces.

IPM ladder (least-harmful first), applied according to severity:

    Monitor -> Cultural -> Mechanical -> Biological -> Chemical

Rules:
  - LOW severity  -> monitoring + prevention/cultural. No chemical.
  - MODERATE      -> cultural + mechanical + biological + closer monitoring.
                     Chemical only mentioned as a threshold-gated last resort.
  - HIGH          -> escalation: containment/removal + biological, and chemical
                     ONLY if the action threshold is exceeded, deferring to the
                     product label and local guidance.
  - UNKNOWN       -> monitor + re-image; no treatment escalation.

Chemical guidance is always category-level and label-deferring: never a product
name, dose or concentration (enforced by the knowledge base content).

Sustainable treatment prioritisation order:

    PREVENTION -> CULTURAL -> MECHANICAL -> BIOLOGICAL -> CHEMICAL
"""
from __future__ import annotations

from app.ml.pest_knowledge import PEST_KB

# Canonical sustainable ordering, least environmental impact first.
SUSTAINABLE_ORDER = ["prevention", "cultural", "mechanical", "biological", "chemical"]

CHEMICAL_SAFETY_NOTE = ("Use only locally registered products and follow the product "
                        "label and local agricultural guidance. Observe pre-harvest "
                        "intervals and protect beneficial insects, pollinators and "
                        "water sources.")

_SPLIT = "|__|"  # internal marker (unused externally)


def _kb(pest_name: str) -> dict:
    return PEST_KB.get(pest_name, {})


def build_ipm(pest_name: str, severity_level: str,
              environment: dict | None = None) -> dict:
    """Produce the IPM plan grouped by control category, gated by severity.

    Returns a dict with lists per category plus monitoring, and flags describing
    whether chemical control is on the table.
    """
    kb = _kb(pest_name)
    level = (severity_level or "UNKNOWN").upper()

    monitoring = []
    cultural = list(kb.get("cultural_control_list") or _as_list(kb.get("cultural_control")))
    mechanical = list(_as_list(kb.get("mechanical_control")))
    biological = list(_as_list(kb.get("biological_control")))
    prevention = list(_as_list(kb.get("prevention")))
    chemical = []           # populated only when justified
    chemical_gated = False  # True when chemical is mentioned but threshold-gated
    escalation = []

    if level == "UNKNOWN":
        monitoring = [
            "Re-check the plants every 2–3 days and photograph the affected leaves.",
            "Upload a clearer close-up so the pest and its spread can be confirmed.",
            "Inspect neighbouring plants for the same symptoms.",
        ]
        return _assemble(pest_name, level, monitoring, prevention, cultural,
                         mechanical, biological, chemical, chemical_gated,
                         escalation, kb)

    if level == "LOW":
        monitoring = [
            "Monitor the affected leaves regularly (every few days).",
            "Check nearby plants so any spread is caught early.",
            "Encourage and protect beneficial insects.",
        ]
        # LOW: prevention + cultural only; explicitly no chemical.
        chemical = []
        chemical_gated = False

    elif level == "MODERATE":
        monitoring = [
            "Increase monitoring frequency (inspect most days).",
            "Track whether the infestation is spreading to new leaves or plants.",
        ]
        # MODERATE: cultural + mechanical + biological. Chemical only as a
        # threshold-gated last resort, not a primary action.
        chemical_gated = True
        chemical = [
            "Only if the infestation exceeds the action threshold below, consider a "
            "threshold-gated chemical option as a last resort. " + CHEMICAL_SAFETY_NOTE
        ]

    elif level == "HIGH":
        monitoring = [
            "Monitor daily until the infestation is clearly declining.",
            "Mark and track the worst-affected plants.",
        ]
        escalation = [
            "Isolate or contain heavily infested plants where appropriate to limit spread.",
            "Remove and destroy the most heavily infested plant material where appropriate.",
        ]
        # HIGH: biological strongly featured; chemical allowed but strictly gated.
        chemical_gated = True
        chemical = [
            "If the action threshold is exceeded, a registered chemical control may be "
            "justified, targeting the most vulnerable pest stage. " + CHEMICAL_SAFETY_NOTE
        ]
        # Prefer the KB's own chemical guidance line as the concrete (still
        # label-deferring) statement, if present.
        kb_chem = kb.get("chemical_control")
        if kb_chem:
            chemical.insert(0, kb_chem)

    # Environmental escalation note (monitoring priority), if provided.
    if environment:
        note = _env_note(environment)
        if note:
            monitoring.insert(0, note)

    return _assemble(pest_name, level, monitoring, prevention, cultural,
                     mechanical, biological, chemical, chemical_gated,
                     escalation, kb)


def rank_sustainable_treatment(pest_name: str, severity_level: str,
                               ipm: dict) -> dict:
    """Produce an ordered, human-facing recommendation that always prioritises
    the least-harmful effective methods and explains WHY.

    Returns:
      {
        "ordered_steps": [ {"category","emoji","action","why"} ... ],
        "summary": str,
        "environmental_considerations": [str, ...],
        "chemical_status": "not_recommended" | "threshold_gated",
      }
    """
    level = (severity_level or "UNKNOWN").upper()
    emojis = {
        "prevention": "🌱", "cultural": "🌾", "mechanical": "🛠",
        "biological": "🪲", "chemical": "🧪", "monitoring": "🔍",
    }
    why = {
        "prevention": "Prevention avoids the problem entirely and has no downside for "
                      "the crop or environment.",
        "cultural": "Cultural methods reduce the pest using how you grow and sanitise "
                    "the crop — cheap, safe and durable.",
        "mechanical": "Mechanical/physical removal directly cuts pest numbers without "
                      "any chemicals.",
        "biological": "Biological control uses natural enemies, protecting pollinators "
                      "and beneficial insects while suppressing the pest.",
        "chemical": "Chemical control is kept for last because it is the most costly to "
                    "beneficial insects, soil and water, and should only be used when "
                    "the action threshold is exceeded.",
    }

    steps = []
    # Always lead with monitoring for context.
    if ipm.get("monitoring"):
        steps.append({
            "category": "monitoring", "emoji": emojis["monitoring"],
            "action": ipm["monitoring"][0],
            "why": "Monitoring confirms whether action is even needed and catches spread early.",
        })

    for cat in SUSTAINABLE_ORDER:
        items = ipm.get(cat) or []
        if not items:
            continue
        # For chemical, only surface it when it is genuinely on the table.
        if cat == "chemical" and ipm.get("chemical_status") == "not_recommended":
            continue
        steps.append({
            "category": cat,
            "emoji": emojis[cat],
            "action": items[0],
            "why": why[cat],
        })

    # Build a short natural-language summary of the ladder actually recommended.
    active = [s["category"] for s in steps if s["category"] != "monitoring"]
    if level == "LOW":
        summary = ("Severity is LOW — focus on monitoring and preventive/cultural "
                   "measures. No pesticide is recommended at this stage.")
    elif level == "MODERATE":
        summary = ("Severity is MODERATE — combine cultural, mechanical and biological "
                   "controls with closer monitoring. Chemical control stays a last "
                   "resort only if the action threshold is exceeded.")
    elif level == "HIGH":
        summary = ("Severity is HIGH — contain and remove the worst-affected material, "
                   "lean on biological control, and use a registered chemical option "
                   "only if the action threshold is exceeded, following the label.")
    else:
        summary = ("Severity is UNKNOWN — keep monitoring and re-image the plant before "
                   "any treatment, so no unnecessary spraying happens.")

    env_considerations = [
        "Protect beneficial insects (lady beetles, lacewings, parasitic wasps) and pollinators.",
        "Avoid unnecessary spraying to prevent harm to soil and water.",
        "Prefer targeted, least-toxic options first to reduce environmental impact.",
    ]

    return {
        "ordered_steps": steps,
        "summary": summary,
        "environmental_considerations": env_considerations,
        "chemical_status": ipm.get("chemical_status", "not_recommended"),
    }


# ----------------- helpers -----------------

def _assemble(pest_name, level, monitoring, prevention, cultural, mechanical,
              biological, chemical, chemical_gated, escalation, kb) -> dict:
    chemical_status = "threshold_gated" if chemical_gated and chemical else "not_recommended"
    return {
        "pest": pest_name,
        "severity": level,
        "monitoring": monitoring,
        "prevention": prevention,
        "cultural": cultural,
        "mechanical": mechanical,
        "biological": biological,
        "chemical": chemical,
        "escalation": escalation,
        "chemical_status": chemical_status,
        "action_threshold": kb.get("severity_threshold", ""),
    }


def _as_list(value) -> list:
    """KB fields are single descriptive strings; wrap into a one-item list so the
    IPM output is uniformly list-shaped and easy to extend to multiple items."""
    if not value:
        return []
    if isinstance(value, list):
        return value
    return [value]


def _env_note(environment: dict) -> str | None:
    temp = environment.get("temperature")
    hum = environment.get("humidity")
    rain = environment.get("rain_probability")
    try:
        if temp is not None and hum is not None and float(temp) >= 28 and float(hum) >= 60:
            return ("Warm, humid conditions right now favour faster pest build-up — "
                    "prioritise monitoring over the next few days.")
    except (TypeError, ValueError):
        pass
    try:
        if rain is not None and float(rain) >= 70:
            return ("Rain is likely soon — time any physical/biological measures around "
                    "the wet weather, and avoid spraying before rain.")
    except (TypeError, ValueError):
        pass
    return None
