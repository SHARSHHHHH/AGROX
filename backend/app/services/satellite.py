"""Sentinel-2 satellite service backed by Google Earth Engine.

WHAT THIS DOES
--------------
Given a farmer's latitude/longitude it computes vegetation indices over a small
buffered field footprint and returns NUMBERS ONLY — never imagery.

    lat/lon -> ee.Geometry.Point().buffer() -> Sentinel-2 L2A collection
            -> cloud filter + SCL mask -> per-image reduceRegion()
            -> getInfo() -> a few dozen floats

NOTHING IS DOWNLOADED
---------------------
Every reduction runs on Google's servers. `getInfo()` pulls back a small JSON
object of statistics. No `ee.batch.Export`, no `getDownloadURL`, no GeoTIFF, no
`.tif` on disk anywhere in this file. A whole season of observations for one
field is a few kilobytes of JSON.

CREDENTIALS STAY SERVER SIDE
----------------------------
Earth Engine credentials are read from the environment inside this process and
are never placed in a response body. `status()` reports only *which mode* is
active (user credentials vs service account) and never the key, the file path,
or the service-account email. The React app talks to /api/satellite/*, which
talks to this module. The browser never sees a Google credential.

HONESTY CONTRACT
----------------
Every function returns a dict with an explicit `status`:

    ok              a real, recent, sufficiently cloud-free observation
    stale           a real observation, but older than `stale_after_days`
    no_observation  Earth Engine answered, but every pass was too cloudy
    not_configured  Earth Engine is not set up on this server
    unavailable     Earth Engine errored or timed out

It never raises into a request handler and never invents an NDVI value. A
missing observation is reported as missing, because a farmer acting on a
fabricated greenness reading is worse off than one told "no clear pass yet".
"""

from __future__ import annotations

import asyncio
import json
import logging
import math
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from app.core.config import settings

log = logging.getLogger("agri.satellite")

# ---------------------------------------------------------------- statuses
STATUS_OK = "ok"
STATUS_STALE = "stale"
STATUS_NO_OBSERVATION = "no_observation"
STATUS_NOT_CONFIGURED = "not_configured"
STATUS_UNAVAILABLE = "unavailable"

REAL_STATUSES = (STATUS_OK, STATUS_STALE)

# Sentinel-2 Scene Classification Layer values we refuse to use.
#   1 saturated/defective   3 cloud shadow   8 cloud medium probability
#   9 cloud high probability   10 thin cirrus
# 11 (snow/ice) is also dropped: over an Indian field it is almost always a
# misclassified bright surface, and either way it is not crop canopy.
SCL_REJECT = [1, 3, 8, 9, 10, 11]

# Bands we ask Earth Engine to compute. Each is a documented, standard index.
INDEX_BANDS = ("ndvi", "ndmi", "ndre", "evi", "savi", "bsi")

_EE_LOCK = threading.Lock()
_EE_STATE: Dict[str, Any] = {"ready": False, "mode": None, "error": None,
                             "initialised_at": None}

# One small pool. Earth Engine calls are blocking HTTP; running them on the
# event loop would stall every other request in the app.
_POOL = ThreadPoolExecutor(max_workers=max(1, settings.GEE_MAX_WORKERS),
                           thread_name_prefix="gee")

# key -> (expires_at, payload). Guarded by _CACHE_LOCK.
_CACHE: Dict[str, Tuple[float, dict]] = {}
_CACHE_LOCK = threading.Lock()
# key -> asyncio.Lock, so ten dashboard widgets asking at once produce ONE
# Earth Engine call rather than ten.
_INFLIGHT: Dict[str, asyncio.Lock] = {}


# =====================================================================
# Initialisation
# =====================================================================

def _import_ee():
    """Import earthengine-api, or return None if it is not installed."""
    try:
        import ee  # noqa: WPS433 (deliberate late import)
        return ee
    except ImportError:
        return None


def _initialise() -> Dict[str, Any]:
    """Initialise Earth Engine once per process. Never raises.

    Three credential modes, tried in order:

      1. GEE_SERVICE_ACCOUNT_JSON  — the key material itself in an env var.
         Right for containers and CI, where there is no filesystem to mount.
      2. GEE_SERVICE_ACCOUNT_FILE  — path to a service-account JSON key.
      3. Application default       — whatever `earthengine authenticate`
         stored for this user. This is the mode a developer machine is
         already in, which is why it is the fallback rather than an error.
    """
    if _EE_STATE["ready"]:
        return _EE_STATE

    with _EE_LOCK:
        if _EE_STATE["ready"]:
            return _EE_STATE

        if not settings.GEE_ENABLED:
            _EE_STATE["error"] = "GEE_ENABLED is false in backend/.env"
            return _EE_STATE

        ee = _import_ee()
        if ee is None:
            _EE_STATE["error"] = (
                "earthengine-api is not installed. Run: "
                "pip install earthengine-api")
            return _EE_STATE

        project = settings.GEE_PROJECT.strip()
        if not project:
            _EE_STATE["error"] = "GEE_PROJECT is not set in backend/.env"
            return _EE_STATE

        try:
            if settings.GEE_SERVICE_ACCOUNT_JSON.strip():
                raw = settings.GEE_SERVICE_ACCOUNT_JSON.strip()
                info = json.loads(raw)
                creds = ee.ServiceAccountCredentials(
                    info.get("client_email", ""), key_data=raw)
                ee.Initialize(creds, project=project)
                _EE_STATE["mode"] = "service_account_env"

            elif settings.GEE_SERVICE_ACCOUNT_FILE.strip():
                path = settings.GEE_SERVICE_ACCOUNT_FILE.strip()
                with open(path, "r", encoding="utf-8") as fh:
                    info = json.load(fh)
                creds = ee.ServiceAccountCredentials(
                    info.get("client_email", ""), path)
                ee.Initialize(creds, project=project)
                _EE_STATE["mode"] = "service_account_file"

            else:
                # `earthengine authenticate` credentials from the user's home
                # directory. This is the "already configured" case.
                ee.Initialize(project=project)
                _EE_STATE["mode"] = "user_credentials"

            _EE_STATE["ready"] = True
            _EE_STATE["error"] = None
            _EE_STATE["initialised_at"] = datetime.now(timezone.utc).isoformat()
            log.info("Earth Engine ready (mode=%s)", _EE_STATE["mode"])

        except Exception as exc:                       # noqa: BLE001
            # A bad key, a revoked token, a project without the EE API enabled
            # — all land here. Record it and degrade; never crash the request.
            _EE_STATE["ready"] = False
            _EE_STATE["error"] = f"{type(exc).__name__}: {exc}"
            log.error("Earth Engine init FAILED: %s", _EE_STATE["error"])

        return _EE_STATE


def status() -> Dict[str, Any]:
    """Configuration report. Deliberately contains no credential material.

    Note what is absent: no key, no file path, no service-account email, no
    project id. Those are configuration secrets, and this endpoint is reachable
    by any logged-in farmer.
    """
    state = _initialise()
    return {
        "enabled": settings.GEE_ENABLED,
        "ready": state["ready"],
        "credential_mode": state["mode"],
        "error": state["error"],
        "initialised_at": state["initialised_at"],
        "collection": settings.GEE_COLLECTION,
        "resolution_m": 10,
        "default_buffer_m": settings.GEE_BUFFER_M,
        "max_cloud_pct": settings.GEE_MAX_CLOUD_PCT,
        "lookback_days": settings.GEE_LOOKBACK_DAYS,
        "cache_ttl_s": settings.GEE_CACHE_TTL_S,
        "cached_entries": len(_CACHE),
        "downloads_imagery": False,
        "note": ("All reductions run on Google's servers. Only summary "
                 "statistics cross the network; no imagery is downloaded or "
                 "stored."),
    }


def reset_for_tests() -> None:
    """Clear init state and caches. Used by the test suite only."""
    with _EE_LOCK:
        _EE_STATE.update(ready=False, mode=None, error=None, initialised_at=None)
    clear_cache()


# =====================================================================
# Cache
# =====================================================================

def _cache_key(kind: str, lat: float, lon: float, **kw) -> str:
    """Round coordinates to ~11 m so tiny GPS jitter still hits the cache."""
    parts = [kind, f"{lat:.4f}", f"{lon:.4f}"]
    parts += [f"{k}={kw[k]}" for k in sorted(kw)]
    return "|".join(parts)


def _cache_get(key: str) -> Optional[dict]:
    with _CACHE_LOCK:
        hit = _CACHE.get(key)
        if not hit:
            return None
        expires, payload = hit
        if time.time() >= expires:
            _CACHE.pop(key, None)
            return None
    out = dict(payload)
    out["cached"] = True
    out["cache_age_s"] = round(time.time() - out.get("_stored_at", time.time()))
    return out


def _cache_put(key: str, payload: dict, ttl: float) -> None:
    stored = dict(payload)
    stored["_stored_at"] = time.time()
    with _CACHE_LOCK:
        _CACHE[key] = (time.time() + ttl, stored)


def clear_cache() -> int:
    with _CACHE_LOCK:
        n = len(_CACHE)
        _CACHE.clear()
    return n


def _ttl_for(payload: dict, ok_ttl: float) -> float:
    """A failure is cached briefly; a good observation is cached for hours.

    Sentinel-2 revisits every ~5 days, so re-querying an unchanged field every
    few minutes burns quota for an identical answer. But a transient error must
    not be remembered for six hours, or one network blip disables the feature
    for the rest of the afternoon.
    """
    if payload.get("status") in REAL_STATUSES:
        return ok_ttl
    if payload.get("status") == STATUS_NO_OBSERVATION:
        return min(ok_ttl, settings.GEE_NO_OBS_CACHE_TTL_S)
    return settings.GEE_ERROR_CACHE_TTL_S


# =====================================================================
# Earth Engine computation (runs in a worker thread)
# =====================================================================

def _build_index_image(ee, image):
    """Attach the vegetation indices to one Sentinel-2 scene, cloud-masked.

    Two independent cloud gates are applied, because either alone leaks:

      * SCL classes  — per-pixel scene classification from the L2A processor
      * MSK_CLDPRB   — per-pixel cloud probability, catches thin haze that SCL
                       often labels "vegetation"

    Reflectance is scaled by 1/10000 before EVI, which is the only index here
    with a non-ratio constant term (the +1, 6, -7.5 coefficients assume
    reflectance in 0-1, not raw DN).
    """
    scl = image.select("SCL")
    keep = scl.remap(SCL_REJECT, [0] * len(SCL_REJECT), 1)
    prob = image.select("MSK_CLDPRB")
    keep = keep.And(prob.lt(settings.GEE_MAX_PIXEL_CLOUD_PROB))

    masked = image.updateMask(keep)
    scaled = masked.divide(10000)

    nir = scaled.select("B8")
    red = scaled.select("B4")
    blue = scaled.select("B2")
    green = scaled.select("B3")
    rededge = scaled.select("B5")
    swir = scaled.select("B11")

    ndvi = nir.subtract(red).divide(nir.add(red)).rename("ndvi")
    ndmi = nir.subtract(swir).divide(nir.add(swir)).rename("ndmi")
    ndre = nir.subtract(rededge).divide(nir.add(rededge)).rename("ndre")
    savi = (nir.subtract(red).divide(nir.add(red).add(0.5))
            .multiply(1.5).rename("savi"))
    evi = nir.subtract(red).multiply(2.5).divide(
        nir.add(red.multiply(6)).subtract(blue.multiply(7.5)).add(1)
    ).rename("evi")
    bsi = (swir.add(red).subtract(nir.add(blue))
           .divide(swir.add(red).add(nir).add(blue)).rename("bsi"))

    out = ee.Image.cat([ndvi, ndmi, ndre, evi, savi, bsi])
    # Unmasked constant band: its pixel count is the region's TOTAL pixel
    # count, which is what turns a raw count into a valid-data fraction.
    out = out.addBands(ee.Image.constant(1).rename("footprint"))
    return out.copyProperties(image, image.propertyNames())


def _reducer(ee):
    """mean + min/max + stdDev + count + percentiles, in one pass."""
    return (ee.Reducer.mean()
            .combine(ee.Reducer.minMax(), sharedInputs=True)
            .combine(ee.Reducer.stdDev(), sharedInputs=True)
            .combine(ee.Reducer.count(), sharedInputs=True)
            .combine(ee.Reducer.percentile([10, 25, 50, 75, 90]),
                     sharedInputs=True))


def _collection(ee, geom, start: str, end: str, max_cloud: int):
    return (ee.ImageCollection(settings.GEE_COLLECTION)
            .filterBounds(geom)
            .filterDate(start, end)
            .filter(ee.Filter.lte("CLOUDY_PIXEL_PERCENTAGE", max_cloud)))


def _f(value) -> Optional[float]:
    """Earth Engine returns None for a fully-masked band. Keep that as None."""
    if value is None:
        return None
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(f) or math.isinf(f) else round(f, 4)


def _blocking_observations(lat: float, lon: float, *, buffer_m: int,
                           lookback_days: int, max_cloud: int,
                           max_images: int) -> Dict[str, Any]:
    """Reduce the most recent Sentinel-2 passes over one field. Blocking."""
    ee = _import_ee()
    geom = ee.Geometry.Point([lon, lat]).buffer(buffer_m)

    end = datetime.now(timezone.utc).date() + timedelta(days=1)
    start = end - timedelta(days=lookback_days + 1)

    col = _collection(ee, geom, start.isoformat(), end.isoformat(), max_cloud)
    # Sort newest-first and LIMIT before mapping, so we reduce at most
    # `max_images` scenes rather than every pass in the window.
    col = col.sort("system:time_start", False).limit(max_images)

    reducer = _reducer(ee)

    def per_image(image):
        idx = ee.Image(_build_index_image(ee, image))
        stats = idx.reduceRegion(
            reducer=reducer, geometry=geom, scale=settings.GEE_SCALE_M,
            maxPixels=settings.GEE_MAX_PIXELS, bestEffort=True)
        return ee.Feature(None, stats.combine({
            "date": image.date().format("YYYY-MM-dd"),
            "millis": image.date().millis(),
            "scene_cloud_pct": image.get("CLOUDY_PIXEL_PERCENTAGE"),
            "tile": image.get("MGRS_TILE"),
            "platform": image.get("SPACECRAFT_NAME"),
        }))

    features = ee.FeatureCollection(col.map(per_image)).getInfo()

    rows: List[Dict[str, Any]] = []
    for feat in features.get("features", []):
        p = feat.get("properties", {}) or {}
        total = _f(p.get("footprint_count")) or 0.0
        valid = _f(p.get("ndvi_count")) or 0.0
        rows.append({
            "date": p.get("date"),
            "millis": p.get("millis"),
            "tile": p.get("tile"),
            "platform": p.get("platform"),
            "scene_cloud_pct": _f(p.get("scene_cloud_pct")),
            "valid_pixels": int(valid),
            "total_pixels": int(total),
            "valid_fraction": round(valid / total, 3) if total else 0.0,
            "ndvi": {
                "mean": _f(p.get("ndvi_mean")),
                "min": _f(p.get("ndvi_min")),
                "max": _f(p.get("ndvi_max")),
                "stddev": _f(p.get("ndvi_stdDev")),
                "p10": _f(p.get("ndvi_p10")),
                "p25": _f(p.get("ndvi_p25")),
                "median": _f(p.get("ndvi_p50")),
                "p75": _f(p.get("ndvi_p75")),
                "p90": _f(p.get("ndvi_p90")),
            },
            "ndmi": _f(p.get("ndmi_mean")),
            "ndre": _f(p.get("ndre_mean")),
            "evi": _f(p.get("evi_mean")),
            "savi": _f(p.get("savi_mean")),
            "bsi": _f(p.get("bsi_mean")),
        })

    rows.sort(key=lambda r: r.get("millis") or 0, reverse=True)
    return {"observations": rows}


def _blocking_monthly_series(lat: float, lon: float, *, buffer_m: int,
                             months: int, max_cloud: int) -> Dict[str, Any]:
    """Monthly median NDVI for the last `months` months.

    A monthly median composite rather than every individual pass: it is far
    cheaper to compute, it fills small cloud gaps, and a season curve is what
    the phenology and trend logic actually needs. Individual passes are still
    available from `_blocking_observations`.
    """
    ee = _import_ee()
    geom = ee.Geometry.Point([lon, lat]).buffer(buffer_m)

    today = datetime.now(timezone.utc).date().replace(day=1)
    start_month = today - timedelta(days=31 * (months - 1))
    start_month = start_month.replace(day=1)

    starts = ee.List.sequence(0, months - 1)
    base = ee.Date(start_month.isoformat())

    def month_stats(offset):
        offset = ee.Number(offset)
        m_start = base.advance(offset, "month")
        m_end = m_start.advance(1, "month")
        col = _collection(ee, geom, m_start, m_end, max_cloud)
        composite = ee.Image(ee.Algorithms.If(
            col.size().gt(0),
            ee.ImageCollection(col.map(lambda im: _build_index_image(ee, im)))
              .median(),
            ee.Image.constant([0, 0, 0, 0, 0, 0, 0]).rename(
                list(INDEX_BANDS) + ["footprint"]).selfMask()))
        stats = composite.reduceRegion(
            reducer=ee.Reducer.mean().combine(ee.Reducer.count(),
                                              sharedInputs=True),
            geometry=geom, scale=settings.GEE_SCALE_M,
            maxPixels=settings.GEE_MAX_PIXELS, bestEffort=True)
        return ee.Feature(None, stats.combine({
            "month": m_start.format("YYYY-MM"),
            "scenes": col.size(),
        }))

    features = ee.FeatureCollection(starts.map(month_stats)).getInfo()

    points: List[Dict[str, Any]] = []
    for feat in features.get("features", []):
        p = feat.get("properties", {}) or {}
        valid = _f(p.get("ndvi_count")) or 0.0
        points.append({
            "month": p.get("month"),
            "scenes": int(_f(p.get("scenes")) or 0),
            "ndvi": _f(p.get("ndvi_mean")),
            "ndmi": _f(p.get("ndmi_mean")),
            "ndre": _f(p.get("ndre_mean")),
            "valid_pixels": int(valid),
        })
    points.sort(key=lambda r: r.get("month") or "")
    return {"points": points}


# =====================================================================
# Async wrappers
# =====================================================================

async def _run(fn, *args, **kwargs) -> Any:
    """Run a blocking Earth Engine call in the pool, with a hard timeout."""
    loop = asyncio.get_running_loop()
    fut = loop.run_in_executor(_POOL, lambda: fn(*args, **kwargs))
    return await asyncio.wait_for(fut, timeout=settings.GEE_TIMEOUT_S)


def _inflight_lock(key: str) -> asyncio.Lock:
    lock = _INFLIGHT.get(key)
    if lock is None:
        lock = asyncio.Lock()
        _INFLIGHT[key] = lock
    return lock


def _not_configured(extra: str = "") -> Dict[str, Any]:
    state = _initialise()
    return {
        "status": STATUS_NOT_CONFIGURED,
        "source": "google-earth-engine",
        "message": (extra or state.get("error")
                    or "Earth Engine is not configured on this server."),
        "ndvi": None,
        "observation": None,
    }


def _valid_enough(row: dict, min_fraction: float) -> bool:
    return (row.get("ndvi", {}).get("mean") is not None
            and row.get("valid_fraction", 0) >= min_fraction)


def _shape_observation(row: dict, *, lat: float, lon: float, buffer_m: int,
                       stale_after_days: int) -> Dict[str, Any]:
    """Turn one reduced scene into the public observation payload."""
    ndvi = row["ndvi"]
    obs_date = row.get("date")
    age = None
    if obs_date:
        try:
            age = (datetime.now(timezone.utc).date()
                   - date.fromisoformat(obs_date)).days
        except ValueError:
            age = None

    stale = age is not None and age > stale_after_days
    area_ha = round(math.pi * (buffer_m ** 2) / 10000.0, 3)

    return {
        "status": STATUS_STALE if stale else STATUS_OK,
        "source": "google-earth-engine",
        "satellite": row.get("platform") or "Sentinel-2",
        "collection": settings.GEE_COLLECTION,
        "ndvi": ndvi["mean"],
        "ndvi_detail": ndvi,
        "indices": {
            "ndvi": ndvi["mean"],
            "ndmi": row.get("ndmi"),
            "ndre": row.get("ndre"),
            "evi": row.get("evi"),
            "savi": row.get("savi"),
            "bsi": row.get("bsi"),
        },
        "observation": {
            "date": obs_date,
            "days_ago": age,
            "is_stale": bool(stale),
            "stale_after_days": stale_after_days,
            "tile": row.get("tile"),
            "scene_cloud_pct": row.get("scene_cloud_pct"),
            "clear_pixel_fraction": row.get("valid_fraction"),
            "clear_pixels": row.get("valid_pixels"),
            "total_pixels": row.get("total_pixels"),
            "resolution_m": settings.GEE_SCALE_M,
            "footprint": {
                "latitude": lat, "longitude": lon,
                "buffer_m": buffer_m, "area_ha": area_ha,
                "shape": "circle",
            },
        },
        "index_definitions": {
            "ndvi": "(NIR-Red)/(NIR+Red) — green biomass and canopy vigour",
            "ndmi": "(NIR-SWIR1)/(NIR+SWIR1) — canopy water content",
            "ndre": "(NIR-RedEdge)/(NIR+RedEdge) — chlorophyll, nitrogen proxy",
            "evi": "Enhanced Vegetation Index — resists canopy saturation",
            "savi": "Soil Adjusted Vegetation Index — for sparse canopies",
            "bsi": "Bare Soil Index — rises as soil is exposed",
        },
        "cached": False,
    }


async def get_ndvi(lat: float, lon: float, *,
                   buffer_m: Optional[int] = None,
                   lookback_days: Optional[int] = None,
                   max_cloud: Optional[int] = None,
                   min_valid_fraction: Optional[float] = None,
                   force_refresh: bool = False) -> Dict[str, Any]:
    """Latest usable NDVI observation for one point. Never raises.

    Walks the recent passes newest-first and returns the first one whose
    cloud-free pixel fraction clears `min_valid_fraction`. A pass that is 60%
    cloud over this particular field is skipped even though the scene as a
    whole passed the metadata filter, because the scene-level
    CLOUDY_PIXEL_PERCENTAGE says nothing about this one hectare.
    """
    buffer_m = int(buffer_m or settings.GEE_BUFFER_M)
    lookback_days = int(lookback_days or settings.GEE_LOOKBACK_DAYS)
    max_cloud = int(max_cloud if max_cloud is not None
                    else settings.GEE_MAX_CLOUD_PCT)
    min_valid_fraction = float(min_valid_fraction
                               if min_valid_fraction is not None
                               else settings.GEE_MIN_VALID_FRACTION)

    if not _valid_coords(lat, lon):
        return {"status": STATUS_UNAVAILABLE, "source": "google-earth-engine",
                "message": "Latitude must be -90..90 and longitude -180..180.",
                "ndvi": None, "observation": None}

    key = _cache_key("ndvi", lat, lon, b=buffer_m, d=lookback_days,
                     c=max_cloud, v=min_valid_fraction)

    if not force_refresh:
        hit = _cache_get(key)
        if hit is not None:
            hit.pop("_stored_at", None)
            return hit

    async with _inflight_lock(key):
        # Another coroutine may have filled the cache while we waited.
        if not force_refresh:
            hit = _cache_get(key)
            if hit is not None:
                hit.pop("_stored_at", None)
                return hit

        state = _initialise()
        if not state["ready"]:
            return _not_configured()

        try:
            raw = await _run(
                _blocking_observations, lat, lon,
                buffer_m=buffer_m, lookback_days=lookback_days,
                max_cloud=max_cloud,
                max_images=settings.GEE_MAX_IMAGES_PER_QUERY)
        except asyncio.TimeoutError:
            payload = {
                "status": STATUS_UNAVAILABLE, "source": "google-earth-engine",
                "message": (f"Earth Engine did not respond within "
                            f"{settings.GEE_TIMEOUT_S}s."),
                "ndvi": None, "observation": None}
            _cache_put(key, payload, _ttl_for(payload, settings.GEE_CACHE_TTL_S))
            return payload
        except Exception as exc:                        # noqa: BLE001
            log.warning("NDVI query failed at %.4f,%.4f: %s", lat, lon, exc)
            payload = {
                "status": STATUS_UNAVAILABLE, "source": "google-earth-engine",
                "message": f"Earth Engine error: {type(exc).__name__}",
                "ndvi": None, "observation": None}
            _cache_put(key, payload, _ttl_for(payload, settings.GEE_CACHE_TTL_S))
            return payload

        rows = raw.get("observations", [])
        usable = next((r for r in rows
                       if _valid_enough(r, min_valid_fraction)), None)

        if usable is None:
            attempted = len(rows)
            payload = {
                "status": STATUS_NO_OBSERVATION,
                "source": "google-earth-engine",
                "message": (
                    f"Earth Engine found {attempted} Sentinel-2 pass(es) over "
                    f"this field in the last {lookback_days} days, but none "
                    f"had at least {int(min_valid_fraction * 100)}% "
                    f"cloud-free pixels. During the monsoon this is normal — "
                    f"try again after the next clear day."),
                "ndvi": None,
                "observation": None,
                "passes_examined": attempted,
                "lookback_days": lookback_days,
            }
            _cache_put(key, payload, _ttl_for(payload, settings.GEE_CACHE_TTL_S))
            return payload

        payload = _shape_observation(
            usable, lat=lat, lon=lon, buffer_m=buffer_m,
            stale_after_days=settings.GEE_STALE_AFTER_DAYS)
        payload["passes_examined"] = len(rows)
        payload["recent_passes"] = [
            {"date": r["date"], "ndvi": r["ndvi"]["mean"],
             "clear_fraction": r["valid_fraction"]}
            for r in rows[:settings.GEE_MAX_IMAGES_PER_QUERY]
        ]
        _cache_put(key, payload, _ttl_for(payload, settings.GEE_CACHE_TTL_S))
        return payload


async def get_series(lat: float, lon: float, *,
                     months: int = 12,
                     buffer_m: Optional[int] = None,
                     max_cloud: Optional[int] = None,
                     force_refresh: bool = False) -> Dict[str, Any]:
    """Monthly NDVI/NDMI/NDRE curve for one field. Never raises."""
    months = max(2, min(int(months), settings.GEE_MAX_SERIES_MONTHS))
    buffer_m = int(buffer_m or settings.GEE_BUFFER_M)
    max_cloud = int(max_cloud if max_cloud is not None
                    else settings.GEE_MAX_CLOUD_PCT)

    if not _valid_coords(lat, lon):
        return {"status": STATUS_UNAVAILABLE, "points": [],
                "message": "Latitude must be -90..90 and longitude -180..180."}

    key = _cache_key("series", lat, lon, m=months, b=buffer_m, c=max_cloud)

    if not force_refresh:
        hit = _cache_get(key)
        if hit is not None:
            hit.pop("_stored_at", None)
            return hit

    async with _inflight_lock(key):
        if not force_refresh:
            hit = _cache_get(key)
            if hit is not None:
                hit.pop("_stored_at", None)
                return hit

        state = _initialise()
        if not state["ready"]:
            out = _not_configured()
            out["points"] = []
            return out

        try:
            raw = await _run(_blocking_monthly_series, lat, lon,
                             buffer_m=buffer_m, months=months,
                             max_cloud=max_cloud)
        except asyncio.TimeoutError:
            payload = {"status": STATUS_UNAVAILABLE, "points": [],
                       "source": "google-earth-engine",
                       "message": (f"Earth Engine did not respond within "
                                   f"{settings.GEE_TIMEOUT_S}s.")}
            _cache_put(key, payload, settings.GEE_ERROR_CACHE_TTL_S)
            return payload
        except Exception as exc:                        # noqa: BLE001
            log.warning("NDVI series failed at %.4f,%.4f: %s", lat, lon, exc)
            payload = {"status": STATUS_UNAVAILABLE, "points": [],
                       "source": "google-earth-engine",
                       "message": f"Earth Engine error: {type(exc).__name__}"}
            _cache_put(key, payload, settings.GEE_ERROR_CACHE_TTL_S)
            return payload

        points = [p for p in raw.get("points", []) if p.get("ndvi") is not None]
        payload = {
            "status": STATUS_OK if points else STATUS_NO_OBSERVATION,
            "source": "google-earth-engine",
            "satellite": "Sentinel-2",
            "months_requested": months,
            "months_with_data": len(points),
            "points": points,
            "gaps": [p["month"] for p in raw.get("points", [])
                     if p.get("ndvi") is None],
            "footprint": {"latitude": lat, "longitude": lon,
                          "buffer_m": buffer_m},
            "note": ("Each point is the median of every sufficiently clear "
                     "Sentinel-2 pass in that month. Months with no clear "
                     "pass are listed under 'gaps' rather than interpolated."),
            "cached": False,
        }
        _cache_put(key, payload, settings.GEE_SERIES_CACHE_TTL_S)
        return payload


def _valid_coords(lat: Any, lon: Any) -> bool:
    try:
        lat = float(lat)
        lon = float(lon)
    except (TypeError, ValueError):
        return False
    if math.isnan(lat) or math.isnan(lon):
        return False
    return -90.0 <= lat <= 90.0 and -180.0 <= lon <= 180.0
