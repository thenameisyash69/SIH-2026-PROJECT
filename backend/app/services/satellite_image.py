"""
Builds real satellite image URLs from NASA GIBS (Global Imagery Browse
Services) — completely free, no API key, no signup. This is the same
imagery system behind NASA Worldview.

Docs: https://nasa-gibs.github.io/gibs-api-docs/access-basics/
"""
from datetime import datetime, timedelta

GIBS_BASE = "https://wvs.earthdata.nasa.gov/api/v1/snapshot"
LAYER = "VIIRS_SNPP_CorrectedReflectance_TrueColor"   # true-color daily imagery
PAD_DEGREES = 0.18   # ~20km box around the point — tight enough to show the facility


def build_satellite_image_url(lat: float, lon: float, date: datetime | None = None) -> dict:
    """
    Returns a direct image URL for a lat/lon on a given date.
    GIBS imagery can lag 1-2 days, so we default to 2 days ago, and the
    frontend can let the user step backward if a given date is cloudy/missing.
    """
    if date is None:
        date = datetime.utcnow() - timedelta(days=2)
    date_str = date.strftime("%Y-%m-%d")

    west, south = lon - PAD_DEGREES, lat - PAD_DEGREES
    east, north = lon + PAD_DEGREES, lat + PAD_DEGREES

    url = (
        f"{GIBS_BASE}?REQUEST=GetSnapshot"
        f"&LAYERS={LAYER}"
        f"&CRS=EPSG:4326"
        f"&TIME={date_str}"
        f"&BBOX={south},{west},{north},{east}"
        f"&FORMAT=image/jpeg"
        f"&WIDTH=480&HEIGHT=480"
    )
    return {"url": url, "date": date_str, "source": "NASA GIBS / VIIRS true-color"}
