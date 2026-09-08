"""Reverse geocoding: GPS coordinates -> Indian state and district.

WHY THIS EXISTS
---------------
The onboarding wizard captured latitude and longitude and then did nothing
with them. The farmer granted location permission and still had to type their
state and district by hand, which makes the GPS button look broken.

APPROACH
--------
Two tiers, so this works even with no network:

1. OFFLINE first. A small table of Madhya Pradesh district centroids resolves
   the common case instantly, with no API call, no key and no rate limit.
   Nearest centroid within a sane radius wins.

2. ONLINE fallback. OpenStreetMap Nominatim covers the rest of India. It is
   free and needs no key, but its usage policy requires a real User-Agent and
   at most one request per second, so it is used only when the offline table
   does not match.

Accuracy is honest: the response says which tier answered and how far the
nearest centroid was, so the UI can show "Indore (approximate)" rather than
implying survey precision.
"""

import logging
import math
from typing import Any, Dict, List, Optional, Tuple

import httpx

log = logging.getLogger("agri.geo")

# District centroids for Madhya Pradesh (approximate, degrees).
# Enough to resolve a farmer standing in their field to the right district.
MP_DISTRICTS: List[Tuple[str, float, float]] = [
    ("Bhopal", 23.2599, 77.4126), ("Indore", 22.7196, 75.8577),
    ("Jabalpur", 23.1815, 79.9864), ("Gwalior", 26.2183, 78.1828),
    ("Ujjain", 23.1765, 75.7885), ("Sagar", 23.8388, 78.7378),
    ("Dewas", 22.9676, 76.0534), ("Satna", 24.5854, 80.8322),
    ("Ratlam", 23.3315, 75.0367), ("Rewa", 24.5362, 81.2961),
    ("Katni", 23.8343, 80.3894), ("Singrauli", 24.1997, 82.6739),
    ("Burhanpur", 21.3145, 76.2291), ("Khandwa", 21.8335, 76.3522),
    ("Bhind", 26.5646, 78.7875), ("Chhindwara", 22.0574, 78.9382),
    ("Guna", 24.6469, 77.3113), ("Shivpuri", 25.4358, 77.6544),
    ("Vidisha", 23.5251, 77.8081), ("Chhatarpur", 24.9180, 79.5881),
    ("Damoh", 23.8315, 79.4420), ("Mandsaur", 24.0768, 75.0680),
    ("Khargone", 21.8236, 75.6100), ("Neemuch", 24.4739, 74.8706),
    ("Pithampur", 22.6027, 75.6944), ("Hoshangabad", 22.7533, 77.7228),
    ("Itarsi", 22.6142, 77.7626), ("Sehore", 23.2020, 77.0856),
    ("Betul", 21.9010, 77.9010), ("Seoni", 22.0868, 79.5430),
    ("Datia", 25.6667, 78.4667), ("Nagda", 23.4467, 75.4167),
    ("Dhar", 22.5990, 75.3030), ("Balaghat", 21.8125, 80.1850),
    ("Shahdol", 23.2964, 81.3600), ("Narsinghpur", 22.9480, 79.1930),
    ("Barwani", 22.0362, 74.8977), ("Harda", 22.3441, 77.0954),
    ("Tikamgarh", 24.7449, 78.8317), ("Sheopur", 25.6667, 76.7000),
    ("Rajgarh", 24.0079, 76.7300), ("Shajapur", 23.4265, 76.2734),
    ("Panna", 24.7180, 80.1819), ("Umaria", 23.5245, 80.8371),
    ("Ashoknagar", 24.5766, 77.7300), ("Anuppur", 23.1055, 81.6900),
    ("Dindori", 22.9410, 81.0780), ("Mandla", 22.5983, 80.3711),
    ("Sidhi", 24.4055, 81.8828), ("Morena", 26.5017, 78.0011),
    ("Alirajpur", 22.3130, 74.3640), ("Jhabua", 22.7676, 74.5905),
    ("Agar Malwa", 23.7124, 76.0157), ("Niwari", 25.3600, 78.8100),
]

# Beyond this the nearest centroid is not a credible answer for a district.
MAX_OFFLINE_KM = 60.0

# Major city coordinates for every Indian state and UT, so distance filtering
# works nationwide rather than only inside Madhya Pradesh.
INDIA_STATES: Dict[str, Tuple[float, float]] = {
    "Andhra Pradesh": (16.5062, 80.6480),
    "Arunachal Pradesh": (27.0844, 93.6053),
    "Assam": (26.1445, 91.7362),
    "Bihar": (25.5941, 85.1376),
    "Chhattisgarh": (21.2514, 81.6296),
    "Goa": (15.4909, 73.8278),
    "Gujarat": (23.0225, 72.5714),
    "Haryana": (30.7333, 76.7794),
    "Himachal Pradesh": (31.1048, 77.1734),
    "Jharkhand": (23.3441, 85.3096),
    "Karnataka": (12.9716, 77.5946),
    "Keralam": (8.5241, 76.9366),
    "Madhya Pradesh": (23.2599, 77.4126),
    "Maharashtra": (19.0760, 72.8777),
    "Manipur": (24.8170, 93.9368),
    "Meghalaya": (25.5788, 91.8933),
    "Mizoram": (23.7271, 92.7176),
    "Nagaland": (25.6751, 94.1086),
    "Odisha": (20.2961, 85.8245),
    "Punjab": (30.7333, 76.7794),
    "Rajasthan": (26.9124, 75.7873),
    "Sikkim": (27.3314, 88.6138),
    "Tamil Nadu": (13.0827, 80.2707),
    "Telangana": (17.3850, 78.4867),
    "Tripura": (23.8315, 91.2868),
    "Uttar Pradesh": (26.8467, 80.9462),
    "Uttarakhand": (30.3165, 78.0322),
    "West Bengal": (22.5726, 88.3639),
    "Delhi": (28.6139, 77.2090),
    "Jammu and Kashmir": (34.0837, 74.7973),
    "Ladakh": (34.1526, 77.5771),
    "Puducherry": (11.9416, 79.8083),
    "Chandigarh": (30.7333, 76.7794),
    "Andaman and Nicobar Islands": (11.6234, 92.7265),
    "Dadra and Nagar Haveli and Daman and Diu": (20.3974, 72.8328),
    "Lakshadweep": (10.5667, 72.6417),
}


def state_coords(state: str) -> Optional[Tuple[float, float]]:
    """Approximate centre for a state, used when a listing has no GPS."""
    if not state:
        return None
    key = state.strip().title()
    if key in INDIA_STATES:
        return INDIA_STATES[key]
    for name, coords in INDIA_STATES.items():
        if name.lower() == state.strip().lower():
            return coords
    return None


def list_states() -> List[str]:
    return sorted(INDIA_STATES.keys())


NOMINATIM_URL = "https://nominatim.openstreetmap.org/reverse"
# Nominatim's usage policy requires an identifying User-Agent.
USER_AGENT = "SustainableAgricultureAdvisory/1.0 (farmer advisory app)"


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in kilometres."""
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = (math.sin(dp / 2) ** 2
         + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2)
    return 2 * r * math.asin(math.sqrt(a))


def nearest_mp_district(lat: float, lon: float) -> Optional[Dict[str, Any]]:
    """Nearest MP district centroid, or None if nothing is close enough."""
    best_name, best_km = None, float("inf")
    for name, dlat, dlon in MP_DISTRICTS:
        km = haversine_km(lat, lon, dlat, dlon)
        if km < best_km:
            best_name, best_km = name, km

    if best_name is None or best_km > MAX_OFFLINE_KM:
        return None

    return {
        "state": "Madhya Pradesh",
        "district": best_name,
        "distance_km": round(best_km, 1),
        "source": "offline_district_table",
        "accuracy": "approximate",
    }


async def _nominatim(lat: float, lon: float, timeout: float = 8.0
                     ) -> Optional[Dict[str, Any]]:
    """OpenStreetMap reverse geocode. Free, no key, rate limited."""
    params = {"lat": lat, "lon": lon, "format": "json", "zoom": 10,
              "addressdetails": 1}
    headers = {"User-Agent": USER_AGENT, "Accept-Language": "en"}

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.get(NOMINATIM_URL, params=params, headers=headers)
    except httpx.HTTPError as exc:
        log.warning("nominatim unreachable: %s", type(exc).__name__)
        return None

    if resp.status_code != 200:
        log.warning("nominatim returned HTTP %s", resp.status_code)
        return None

    try:
        addr = (resp.json() or {}).get("address", {}) or {}
    except ValueError:
        return None

    district = (addr.get("state_district") or addr.get("county")
                or addr.get("district") or "")
    # OSM often suffixes " District"; the mandi API does not use that form.
    district = district.replace(" District", "").replace(" district", "").strip()

    state = (addr.get("state") or "").strip()
    if not state and not district:
        return None

    return {
        "state": state,
        "district": district,
        "village": (addr.get("village") or addr.get("town")
                    or addr.get("suburb") or "").strip(),
        "source": "openstreetmap_nominatim",
        "accuracy": "approximate",
    }


async def reverse_geocode(lat: float, lon: float) -> Dict[str, Any]:
    """Resolve coordinates to state/district. Never raises.

    Offline table first (instant, no network), Nominatim second.
    """
    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        return {"status": "invalid",
                "message": "Latitude or longitude is out of range.",
                "state": "", "district": ""}

    offline = nearest_mp_district(lat, lon)
    if offline:
        return {"status": "ok", "latitude": lat, "longitude": lon, **offline}

    online = await _nominatim(lat, lon)
    if online:
        return {"status": "ok", "latitude": lat, "longitude": lon, **online}

    # Offline nationwide fallback. Coarser than a district, but a farmer in
    # Punjab with no network still gets their state filled in rather than
    # nothing at all.
    best_state, best_km = None, float("inf")
    for name, (slat, slon) in INDIA_STATES.items():
        km = haversine_km(lat, lon, slat, slon)
        if km < best_km:
            best_state, best_km = name, km
    if best_state and best_km <= 400:
        return {"status": "ok", "latitude": lat, "longitude": lon,
                "state": best_state, "district": "",
                "distance_km": round(best_km, 1),
                "source": "offline_state_table",
                "accuracy": "state_only"}

    return {
        "status": "unavailable",
        "latitude": lat, "longitude": lon,
        "state": "", "district": "",
        "message": ("Could not resolve your coordinates to a district. Please "
                    "select your state and district manually."),
    }
