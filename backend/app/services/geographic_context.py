"""
Geographic context for a thermal observation.

Uses the SAME Overpass API already used by landcover_fetcher.py — no new
external dependency, no API key, no signup. Returns only features that
actually exist near the observation; never invents a place or facility.

Each feature is tagged with a `kind` so the UI can clearly distinguish a
"nearby feature" from a "confirmed source of fire".
"""
import os
import requests

OVERPASS_URL = "https://overpass-api.de/api/interpreter"
_RADIUS_M = int(os.environ.get("GEO_CONTEXT_RADIUS_M", "5000"))

# Overpass element tags we look for, mapped to a human kind + priority.
# Priority is used to pick the single most relevant feature when several
# overlap; the full list is still returned.
_FEATURE_QUERIES = [
    # Industrial / point-of-interest features
    ("industrial_area", "industrial", 1, 'way["landuse"="industrial"]'),
    ("power_plant", "power_plant", 2, 'node["power"="plant"]'),
    ("refinery", "refinery", 2, 'node["industrial"="refinery"]'),
    ("steel_plant", "steel_plant", 2, 'node["industrial"="steel"]'),
    ("mining_area", "mining", 2, 'way["landuse"="quarry"]'),
    ("settlement", "settlement", 3, 'way["landuse"="residential"]'),
    ("major_road", "road", 4, 'way["highway"~"motorway|trunk|primary"]'),
    ("forest", "forest", 5, 'way["natural"="wood"]'),
    ("agricultural", "agricultural", 5, 'way["landuse"="farmland"]'),
    ("water", "water", 6, 'way["natural"="water"]'),
]

_CACHE = {}
_CACHE_MAX = int(os.environ.get("LANDCOVER_CACHE_MAX", "2000"))


def _cache_key(lat: float, lon: float) -> tuple:
    return (round(lat, 2), round(lon, 2))


def _haversine_m(lat1, lon1, lat2, lon2) -> float:
    from math import radians, sin, cos, sqrt, atan2
    R = 6371000.0
    dlat, dlon = radians(lat2 - lat1), radians(lon2 - lon1)
    a = (sin(dlat / 2) ** 2
         + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon / 2) ** 2)
    return 2 * R * atan2(sqrt(a), sqrt(1 - a))


def nearby_features(lat: float, lon: float, radius_m: int = None) -> list:
    """Return nearby mapped geographic features, or an empty list.

    Each item: {name, kind, distance_m, source, tags}. Never fabricated.
    """
    radius_m = radius_m or _RADIUS_M
    key = _cache_key(lat, lon)
    if key in _CACHE:
        return _CACHE[key]

    if os.environ.get("LANDCOVER_OFFLINE", "0") == "1":
        _CACHE[key] = []
        return []

    parts = []
    for _label, kind, _priority, expr in _FEATURE_QUERIES:
        parts.append(f'({expr}(around:{radius_m},{lat},{lon}););')
    query = (
        "[out:json][timeout:10];\n"
        + "".join(parts)
        + "out tags center;"
    )
    try:
        resp = requests.post(OVERPASS_URL, data={"data": query}, timeout=(3, 10))
        resp.raise_for_status()
        elements = resp.json().get("elements", [])
    except requests.RequestException:
        _CACHE[key] = []
        return []

    # Map element id -> (lat, lon) for distance calc; `center` is present on ways.
    seen = set()
    features = []
    for el in elements:
        tags = el.get("tags") or {}
        name = tags.get("name")
        if not name:
            continue
        # Determine kind from the element's tags, preferring a name match.
        kind = _kind_from_tags(tags)
        if el["type"] == "node":
            lat_e, lon_e = el.get("lat"), el.get("lon")
        else:
            center = el.get("center") or {}
            lat_e, lon_e = center.get("lat"), center.get("lon")
        if lat_e is None or lon_e is None:
            continue
        dist = _haversine_m(lat, lon, lat_e, lon_e)
        if dist > radius_m:
            continue
        dedup = (name, kind)
        if dedup in seen:
            continue
        seen.add(dedup)
        features.append({
            "name": name,
            "kind": kind,
            "distance_m": round(dist, 1),
            "source": "OpenStreetMap / Overpass",
            "tags": {k: v for k, v in tags.items() if k in (
                "landuse", "natural", "industrial", "power", "highway", "amenity"
            )},
        })

    # Sort nearest-first; stable.
    features.sort(key=lambda f: f["distance_m"])
    if len(_CACHE) < _CACHE_MAX:
        _CACHE[key] = features
    return features


def _kind_from_tags(tags: dict) -> str:
    industrial = tags.get("industrial")
    if industrial in ("refinery",):
        return "refinery"
    if industrial == "steel":
        return "steel_plant"
    if tags.get("power") == "plant":
        return "power_plant"
    if tags.get("landuse") == "industrial":
        return "industrial_area"
    if tags.get("landuse") == "quarry":
        return "mining_area"
    if tags.get("landuse") in ("residential", "commercial", "retail"):
        return "settlement"
    if tags.get("highway") in ("motorway", "trunk", "primary"):
        return "major_road"
    if tags.get("natural") == "wood":
        return "forest"
    if tags.get("landuse") in ("farmland", "farmyard", "agricultural"):
        return "agricultural"
    if tags.get("natural") == "water":
        return "water"
    return "other"


def summarize(lat: float, lon: float, radius_m: int = None) -> dict:
    """Convenience wrapper returning a small, UI-friendly summary."""
    features = nearby_features(lat, lon, radius_m)
    return {
        "lat": lat,
        "lon": lon,
        "radius_m": radius_m or _RADIUS_M,
        "feature_count": len(features),
        "features": features,
    }