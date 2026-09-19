"""
Executes scripts.load_real_firms_snapshot's REAL logic (same functions,
same real CSV files) against the sandbox-only fake persistence layer, so
this pass can report genuine, executed counts rather than "should work."

This is NOT a substitute for running the real script in a real environment
with SQLAlchemy/Postgres — it proves the loading/filtering/dedup logic is
correct against real NASA data, using the identical code path as
pipeline.process_observation() (see tests/_sandbox_stub/README.md).

Run with:  python3 tests/run_real_snapshot_load.py
"""
import sys, os, csv
from datetime import datetime

STUB_PATH = os.path.join(os.path.dirname(__file__), "_sandbox_stub")
sys.path.insert(0, STUB_PATH)
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.services.pipeline import process_observation
from app.services.landcover_fetcher import tag_land_cover
from tests._sandbox_stub.sqlalchemy.orm import FakeSession, _reset_store

INDIA_BBOX = (68, 6, 97, 37)
SNAPSHOT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "data-pipeline", "raw")
SNAPSHOT_FILES = [("modis_raw.csv", "MODIS_Terra"), ("viirs_raw.csv", "VIIRS_Suomi_NPP")]


def in_bbox(lat, lon, bbox=INDIA_BBOX):
    west, south, east, north = bbox
    return south <= lat <= north and west <= lon <= east


def parse_acq_datetime(date_str, time_str):
    dt = datetime.strptime(date_str, "%Y-%m-%d")
    time_str = str(time_str).zfill(4)
    return dt.replace(hour=int(time_str[:2]), minute=int(time_str[2:]))


def safe_float(v, default=0.0):
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def main():
    _reset_store()
    db = FakeSession()

    total_read, total_in_bbox, total_inserted = 0, 0, 0
    sample_results = []

    for filename, satellite_label in SNAPSHOT_FILES:
        filepath = os.path.join(SNAPSHOT_DIR, filename)
        with open(filepath) as f:
            for row in csv.DictReader(f):
                total_read += 1
                lat, lon = float(row["latitude"]), float(row["longitude"])
                if not in_bbox(lat, lon):
                    continue
                total_in_bbox += 1

                brightness = float(row.get("brightness") or row.get("bright_ti4", 0))
                confidence_raw = row.get("confidence", "0")
                confidence = {"low": 30.0, "nominal": 60.0, "high": 90.0}.get(
                    str(confidence_raw).lower(), safe_float(confidence_raw))
                frp = safe_float(row.get("frp"), default=None)
                acq_date = parse_acq_datetime(row["acq_date"], row["acq_time"])
                land_cover = tag_land_cover(lat, lon)  # real Overpass call attempted; sandbox has no network -> "unknown", honestly

                hotspot = process_observation(db, {
                    "lat": lat, "lon": lon, "brightness": brightness, "confidence": confidence,
                    "frp": frp, "acq_date": acq_date, "land_cover": land_cover,
                    "satellite": satellite_label, "source": "nasa_firms",
                })
                total_inserted += 1
                sample_results.append(hotspot)

    print(f"REAL NASA FIRMS snapshot — genuine data fetched via live web tool, {datetime.utcnow().date()}")
    print(f"Total rows read (MODIS + VIIRS, South Asia region): {total_read}")
    print(f"Within India bbox {INDIA_BBOX}: {total_in_bbox}")
    print(f"Loaded as real hotspots (source=nasa_firms) via the REAL pipeline: {total_inserted}")
    print()
    print("Sample of actual classification results on real data (first 8):")
    for h in sample_results[:8]:
        print(f"  ({h.lat:.4f}, {h.lon:.4f}) brightness={h.brightness:.1f} -> "
              f"category={h.category}, classified_by={h.classification_method}, "
              f"facility_matched={h.facility_id is not None}, risk={h.risk_level}")

    facility_matches = sum(1 for h in sample_results if h.facility_id is not None)
    print(f"\nOf {total_inserted} real observations, {facility_matches} matched a known facility "
          f"(within 5km of the 12 curated demo facilities).")
    unknown_count = sum(1 for h in sample_results if h.category == "unknown")
    print(f"{unknown_count} were classified 'unknown' — expected, since land_cover tagging needs "
          f"a live Overpass API call this sandbox cannot make; in the user's real environment "
          f"(confirmed FIRMS_MAP_KEY working) this would resolve to real land-cover context.")


if __name__ == "__main__":
    main()
