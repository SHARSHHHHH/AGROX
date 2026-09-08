"""Realistic sensor simulator. Supports scenario presets for demos.

This produces SIMULATED data and every reading is tagged source='simulated'
so the UI can clearly distinguish it from real ESP32 hardware data.
"""
import random
from datetime import datetime

# Current scenario state (in-memory, per-process — fine for a demo)
_SCENARIO = {"name": "normal"}

SCENARIOS = {
    "normal":       {"soil": (35, 55), "temp": (26, 32), "hum": (55, 70), "water": (55, 85), "rain_bias": 15},
    "dry_soil":     {"soil": (12, 24), "temp": (33, 38), "hum": (30, 45), "water": (40, 70), "rain_bias": 8},
    "heavy_rain":   {"soil": (60, 80), "temp": (24, 28), "hum": (80, 95), "water": (80, 100), "rain_bias": 85},
    "low_water":    {"soil": (30, 45), "temp": (30, 35), "hum": (50, 65), "water": (5, 18), "rain_bias": 20},
    "high_temp":    {"soil": (20, 35), "temp": (37, 42), "hum": (25, 40), "water": (45, 75), "rain_bias": 10},
}


def set_scenario(name: str):
    if name in SCENARIOS:
        _SCENARIO["name"] = name
    return _SCENARIO["name"]


def current_scenario() -> str:
    return _SCENARIO["name"]


def generate(device_id: str = "ESP32-001") -> dict:
    s = SCENARIOS[_SCENARIO["name"]]
    return {
        "device_id": device_id,
        "soil_moisture": round(random.uniform(*s["soil"]), 1),
        "temperature": round(random.uniform(*s["temp"]), 1),
        "humidity": round(random.uniform(*s["hum"]), 1),
        "water_level": round(random.uniform(*s["water"]), 1),
        "water_flow": round(random.uniform(0, 2), 2),
        "source": "simulated",
        "timestamp": datetime.utcnow().isoformat(),
    }


def rain_probability() -> int:
    """Rain probability aligned with the active scenario (for offline demo)."""
    bias = SCENARIOS[_SCENARIO["name"]]["rain_bias"]
    return max(0, min(100, bias + random.randint(-8, 8)))
