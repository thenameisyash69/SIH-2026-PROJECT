"""
Matches a raw thermal observation to a nearby industrial facility.

Per spec §10: a satellite thermal pixel does NOT exactly identify a
facility — this stores the actual distance and lets downstream logic
(and the UI) reason about confidence honestly, instead of silently
assuming "nearest = owner."
"""
from math import radians, sin, cos, sqrt, atan2
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sqlalchemy.orm import Session  # only needed for type checkers, not at runtime

from app.services.facility_constants import FACILITY_ASSOCIATION_RADIUS_KM

# The single canonical operational association radius (km). A hotspot with
# distance_to_facility_km <= this value is facility-associated. This is
# CONTEXT, never proof that a facility caused the event.
DEFAULT_MAX_MATCH_KM = FACILITY_ASSOCIATION_RADIUS_KM


def haversine_km(lat1, lon1, lat2, lon2) -> float:
    R = 6371.0
    dlat, dlon = radians(lat2 - lat1), radians(lon2 - lon1)
    a = sin(dlat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon / 2) ** 2
    return 2 * R * atan2(sqrt(a), sqrt(1 - a))


def match_facility(db: "Session", lat: float, lon: float, max_km: float = DEFAULT_MAX_MATCH_KM):
    """
    Returns (facility_or_None, distance_km_or_None).
    Does NOT assume the nearest facility within range is definitely the
    source — that judgment belongs to the evidence engine, which weighs
    distance alongside other signals.
    """
    from app import models  # deferred: keeps haversine_km importable with zero dependencies
    facilities = db.query(models.Facility).all()
    best, best_dist = None, float("inf")
    for f in facilities:
        d = haversine_km(lat, lon, f.lat, f.lon)
        if d < best_dist:
            best, best_dist = f, d
    if best and best_dist <= max_km:
        return best, round(best_dist, 3)
    return None, None
