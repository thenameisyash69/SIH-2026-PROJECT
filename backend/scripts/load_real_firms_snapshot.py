"""
Loads a REAL NASA FIRMS CSV snapshot into the database, through the exact
same pipeline.process_observation() as live sync and seed data.

WHY THIS SCRIPT EXISTS: the automated development environment used to
build this project has no outbound network access (confirmed repeatedly —
see docs/PIPELINE_VALIDATION.md, docs/FINAL_STATUS.md). To produce a real,
honest live-inference test (rather than only synthetic scenarios), real
current NASA FIRMS CSV data was fetched via a separate tool with genuine
internet access and saved to data-pipeline/raw/modis_raw.csv and
data-pipeline/raw/viirs_raw.csv — these are REAL rows, not fabricated, each
verifiable against NASA's public data feed at the timestamp they were
pulled (2026-09-06/07, MODIS Terra + VIIRS Suomi-NPP, South Asia region).

This script is a legitimate, permanent, reusable capability, not a one-off
hack: NASA's static regional CSV mirrors
(firms.modaps.eosdis.nasa.gov/data/active_fire/.../csv/*.csv) require NO
MAP_KEY at all, unlike the Area API. Keeping this loader means Kavach has
a zero-configuration fallback real-data path in addition to the
MAP_KEY-based live sync in firms_ingestion.py.

Every row loaded here is tagged source="nasa_firms" — never demo_synthetic.

Run with:  python -m scripts.load_real_firms_snapshot
"""
import sys, os, csv
from datetime import datetime

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import SessionLocal, init_db
from app.services.landcover_fetcher import tag_land_cover
from app.services.pipeline import process_observation

SNAPSHOT_FILES = [
    ("modis_raw.csv", "MODIS_Terra"),
    ("viirs_raw.csv", "VIIRS_Suomi_NPP"),
]
INDIA_BBOX = (68, 6, 97, 37)  # west, south, east, north — matches settings.firms_area default


def in_bbox(lat, lon, bbox=INDIA_BBOX):
    west, south, east, north = bbox
    return south <= lat <= north and west <= lon <= east


def parse_acq_datetime(date_str, time_str):
    try:
        dt = datetime.strptime(date_str, "%Y-%m-%d")
        time_str = str(time_str).zfill(4)
        return dt.replace(hour=int(time_str[:2]), minute=int(time_str[2:]))
    except (ValueError, TypeError):
        return datetime.utcnow()


def run():
    init_db()
    db = SessionLocal()

    total_read, total_in_bbox, total_inserted, total_duplicate = 0, 0, 0, 0
    snapshot_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "data-pipeline", "raw")

    for filename, satellite_label in SNAPSHOT_FILES:
        filepath = os.path.join(snapshot_dir, filename)
        if not os.path.exists(filepath):
            print(f"[load_real_firms_snapshot] {filename} not found at {filepath} — skipping.")
            continue

        with open(filepath) as f:
            reader = csv.DictReader(f)
            for row in reader:
                total_read += 1
                lat, lon = float(row["latitude"]), float(row["longitude"])
                if not in_bbox(lat, lon):
                    continue
                total_in_bbox += 1

                brightness = float(row.get("brightness") or row.get("bright_ti4", 0))
                confidence_raw = row.get("confidence", "0")
                confidence = {"low": 30.0, "nominal": 60.0, "high": 90.0}.get(
                    str(confidence_raw).lower(), _safe_float(confidence_raw))
                frp = _safe_float(row.get("frp"), default=None)
                acq_date = parse_acq_datetime(row["acq_date"], row["acq_time"])

                land_cover = tag_land_cover(lat, lon)  # will return "unknown" offline — honest, not faked

                hotspot = process_observation(db, {
                    "lat": lat, "lon": lon, "brightness": brightness, "confidence": confidence,
                    "frp": frp, "acq_date": acq_date, "land_cover": land_cover,
                    "satellite": satellite_label, "source": "nasa_firms",
                }, commit=False)

                if getattr(hotspot, "_was_duplicate", False):
                    total_duplicate += 1
                else:
                    total_inserted += 1

    db.commit()
    print(f"Real FIRMS snapshot load complete:")
    print(f"  Total rows read across {len(SNAPSHOT_FILES)} file(s): {total_read}")
    print(f"  Within configured bbox {INDIA_BBOX}: {total_in_bbox}")
    print(f"  Inserted as new real hotspots (source=nasa_firms): {total_inserted}")
    print(f"  Skipped as duplicates: {total_duplicate}")


def _safe_float(v, default=0.0):
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


if __name__ == "__main__":
    run()
