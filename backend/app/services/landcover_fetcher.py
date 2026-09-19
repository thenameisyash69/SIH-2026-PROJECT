"""
Tags a coordinate with a land-cover category.

Production version: query Bhuvan (ISRO) LULC WMS or the Overpass API
for OpenStreetMap landuse polygons at (lat, lon).

For hackathon speed, this ships with a lightweight heuristic + an
Overpass fallback, so the pipeline works even without a Bhuvan account.

Results are cached in-memory keyed by a coarse grid cell so that the
wildfire candidate endpoint does not issue one network request per
observation.
"""
import os
import requests

OVERPASS_URL = "https://overpass-api.de/api/interpreter"
_CACHE = {}
_CACHE_MAX = int(os.environ.get("LANDCOVER_CACHE_MAX", "2000"))


def _cache_key(lat: float, lon: float) -> tuple:
    return (round(lat, 2), round(lon, 2))


def tag_land_cover(lat: float, lon: float, cache: dict = None) -> str:
    cache = _CACHE if cache is None else cache
    key = _cache_key(lat, lon)
    if key in cache:
        return cache[key]

    if os.environ.get("LANDCOVER_OFFLINE", "0") == "1":
        result = "unknown"
        cache[key] = result
        return result

    query = f"""
    [out:json][timeout:8];
    (
      way["landuse"](around:500,{lat},{lon});
      way["natural"="wood"](around:500,{lat},{lon});
    );
    out tags 1;
    """
    try:
        resp = requests.post(
            OVERPASS_URL,
            data={"data": query},
            timeout=(3, 8),
        )
        resp.raise_for_status()
        elements = resp.json().get("elements", [])
        if not elements:
            result = "unknown"
        else:
            tags = elements[0].get("tags", {})
            landuse = tags.get("landuse") or tags.get("natural")
            result = _normalize(landuse)
    except requests.RequestException:
        result = "unknown"

    if len(cache) < _CACHE_MAX:
        cache[key] = result
    return result


def _normalize(raw: str) -> str:
    if not raw:
        return "unknown"
    raw = raw.lower()
    if raw in ("industrial", "quarry"):
        return "industrial"
    if raw in ("forest", "wood"):
        return "forest"
    if raw in ("farmland", "farmyard", "agricultural"):
        return "agricultural"
    if raw in ("residential", "commercial", "retail"):
        return "urban"
    return "unknown"