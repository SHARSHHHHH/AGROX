"""Weather service. Uses Open-Meteo (no API key needed) when online, with a
short cache. Falls back to the simulator's scenario-aligned values offline so
the demo always shows coherent weather. Weather key (if any) stays server-side.
"""
import time
import httpx
from app.core.config import settings
from app.services import simulator

_CACHE = {"ts": 0, "data": None}
_CACHE_TTL = 600  # 10 minutes


async def get_weather(lat: float = 13.08, lon: float = 80.27) -> dict:
    """Default coords: Chennai. Cached to avoid unnecessary API calls."""
    if _CACHE["data"] and time.time() - _CACHE["ts"] < _CACHE_TTL:
        return _CACHE["data"]

    try:
        data = await _fetch_open_meteo(lat, lon)
    except Exception:
        data = _offline_weather()

    _CACHE.update(ts=time.time(), data=data)
    return data


async def _fetch_open_meteo(lat: float, lon: float) -> dict:
    params = {
        "latitude": lat, "longitude": lon,
        "current": "temperature_2m,relative_humidity_2m,precipitation,wind_speed_10m,weather_code",
        "hourly": "precipitation_probability,temperature_2m",
        "daily": "temperature_2m_max,temperature_2m_min,precipitation_probability_max,weather_code",
        "forecast_days": 7, "timezone": "auto",
    }
    timeout = httpx.Timeout(connect=3.0, read=15.0, write=5.0, pool=3.0)
    async with httpx.AsyncClient(timeout=timeout) as c:
        r = await c.get(settings.WEATHER_API_URL, params=params)
        r.raise_for_status()
        j = r.json()

    cur = j.get("current", {})
    daily = j.get("daily", {})
    hourly = j.get("hourly", {})
    rain_prob = 0
    if hourly.get("precipitation_probability"):
        rain_prob = hourly["precipitation_probability"][0]

    forecast = []
    for i in range(min(7, len(daily.get("time", [])))):
        forecast.append({
            "date": daily["time"][i],
            "temp_max": daily["temperature_2m_max"][i],
            "temp_min": daily["temperature_2m_min"][i],
            "rain_prob": daily["precipitation_probability_max"][i],
        })

    return {
        "source": "open-meteo",
        "temperature": cur.get("temperature_2m"),
        "humidity": cur.get("relative_humidity_2m"),
        "rain_probability": rain_prob,
        "rainfall": cur.get("precipitation", 0),
        "wind_speed": cur.get("wind_speed_10m"),
        "condition": _code_to_text(cur.get("weather_code", 0)),
        "forecast": forecast,
        "interpretation": _interpret(rain_prob, cur.get("temperature_2m", 30)),
    }


def _offline_weather() -> dict:
    rp = simulator.rain_probability()
    reading = simulator.generate()
    return {
        "source": "offline-demo",
        "temperature": reading["temperature"],
        "humidity": reading["humidity"],
        "rain_probability": rp,
        "rainfall": 0,
        "wind_speed": 8,
        "condition": "Rain likely" if rp >= 70 else "Partly cloudy",
        "forecast": [],
        "interpretation": _interpret(rp, reading["temperature"]),
    }


def _interpret(rain_prob: int, temp: float) -> str:
    if rain_prob >= 70:
        return "Rain is likely soon. Avoid unnecessary irrigation today."
    if temp >= 37:
        return ("Very hot conditions. Water in early morning or evening and watch "
                "for heat stress.")
    if rain_prob < 20:
        return "Dry conditions expected. Monitor soil moisture and irrigate as needed."
    return "Mild conditions. Normal crop care recommended."


def _code_to_text(code: int) -> str:
    mapping = {0: "Clear", 1: "Mainly clear", 2: "Partly cloudy", 3: "Overcast",
               45: "Fog", 51: "Light drizzle", 61: "Light rain", 63: "Rain",
               65: "Heavy rain", 80: "Rain showers", 95: "Thunderstorm"}
    return mapping.get(code, "Unknown")
