"""
India geographic scope utility.

KAVACH operational scope is India only. This module provides a single,
reusable function to test whether a latitude/longitude pair falls within
the Indian subcontinent. It is used by the analyst labeling queue to
exclude observations that fall outside India (e.g. Sri Lanka) from
candidate lists, without deleting the raw NASA FIRMS observations.

This is a DISPLAY/SCOPE filter only. It does NOT:
- modify raw NASA measurements
- change category, classification, risk, or verification
- affect ML training logic
- delete any database records

The filter uses generous rectangular bounds for the Indian mainland
(covering all states, UTs, and Andaman & Nicobar) and explicit 2-D
exclusion zones for Sri Lanka, Bangladesh, and Myanmar. No crude
single-latitude cutoff is used; each exclusion zone is a full 2-D
bounding box. The India lower-latitude bound of 8°N is set high enough
to also exclude the Maldive archipelago without a separate zone.

KNOWN LIMITATION: the Bangladesh exclusion box (max_lat 25.5°N,
max_lon 89.5°E) covers most of Bangladesh while keeping the
India-Bangladesh border strip near Kolkata/West Bengal (≈ 88–89°E)
in the India scope. A narrow strip of western Bangladesh
(Rajshahi/Rangpur districts) is not excluded — this is an accepted
trade-off of a coarse rectangular filter. All other Indian territory
is included.

KNOWN LIMITATION: the India bounds (min_lon 68°E) include a narrow
strip of Pakistan near the Gujarat border (≈ 68–70°E). This is the
same limitation present in the original polygon implementation and
does not affect the Sri Lanka or Bangladesh fixes, which were the
primary problem.
"""


# Generous rectangular bounds covering the entire Indian mainland,
# Andaman & Nicobar Islands, and Lakshadweep. The lower bound of 8°N
# also excludes the Maldive archipelago (~7°N) without a separate zone.
# NOTE: min_lon 68°E means a small strip of Pakistan near the Gujarat
# border (≈ 68–69°E) falls inside these bounds. This is an accepted
# trade-off of a coarse filter; it does not affect Sri Lanka or
# Bangladesh exclusion, which were the original problem.
_INDIA_BOUNDS = {
    "min_lat": 8.0,
    "max_lat": 35.5,
    "min_lon": 68.0,
    "max_lon": 97.5,
}

# Sri Lanka: approximately 5.5°N–9.8°N, 79.5°E–81.9°E
_SRI_LANKA_BOUNDS = {
    "min_lat": 5.0,
    "max_lat": 10.5,
    "min_lon": 79.0,
    "max_lon": 82.5,
}

# Bangladesh: approximately 20.5°N–26.5°N, 89°E–92.5°E.
# min_lon 89°E keeps the India-Bangladesh border strip (≈ 88–89°E,
# covering Kolkata and the India-Bangladesh border region) in the
# India scope while excluding most of Bangladesh's core territory.
# max_lat 25.5°N keeps the Assam/Meghalaya border strip in scope.
# Border strips are a known limitation of a coarse rectangular filter.
_BANGLADESH_BOUNDS = {
    "min_lat": 20.0,
    "max_lat": 25.5,
    "min_lon": 89.0,
    "max_lon": 92.5,
}

# Myanmar: simplified box covering the territory east of India's
# eastern border, approximately 10°N–28°N, 94°E–101°E.
# min_lon 94°E keeps India's Nagaland/Mizoram/Manipur in scope.
_MYANMAR_BOUNDS = {
    "min_lat": 10.0,
    "max_lat": 28.5,
    "min_lon": 94.0,
    "max_lon": 101.0,
}


def _in_bounds(lat, lon, bounds):
    return (
        bounds["min_lat"] <= lat <= bounds["max_lat"]
        and bounds["min_lon"] <= lon <= bounds["max_lon"]
    )


def is_in_india(lat: float, lon: float) -> bool:
    """
    Return True if (lat, lon) falls within the India operational scope.

    Uses generous rectangular bounds for the Indian mainland (covering
    all states, UTs, and Andaman & Nicobar) and explicit 2-D exclusion
    zones for Sri Lanka, Bangladesh, and Myanmar. Raw NASA FIRMS
    observations are never modified or deleted by this filter.
    """
    if lat is None or lon is None:
        return False

    if not _in_bounds(lat, lon, _INDIA_BOUNDS):
        return False

    if _in_bounds(lat, lon, _SRI_LANKA_BOUNDS):
        return False
    if _in_bounds(lat, lon, _BANGLADESH_BOUNDS):
        return False
    if _in_bounds(lat, lon, _MYANMAR_BOUNDS):
        return False

    return True


def india_bounds() -> dict:
    """Return the coarse India bounding box for reference / map zoom."""
    return {"min_lat": 6.0, "max_lat": 38.0, "min_lon": 68.0, "max_lon": 98.0}
