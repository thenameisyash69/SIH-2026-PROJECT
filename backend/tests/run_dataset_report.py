"""
Runs the SAME report logic as scripts/build_training_dataset.py, against
the real NASA FIRMS snapshot data, via the sandbox-only fake DB (see
tests/_sandbox_stub/README.md) — because this sandbox has no persistent
sqlite file with real ingested data. Produces genuine numbers for
docs/TRAINING_DATASET.md, not fabricated ones.
"""
import sys, os, csv, json
from datetime import datetime

STUB_PATH = os.path.join(os.path.dirname(__file__), "_sandbox_stub")
sys.path.insert(0, STUB_PATH)
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.services.pipeline import process_observation
from app.services.landcover_fetcher import tag_land_cover
from app import models
from tests._sandbox_stub.sqlalchemy.orm import FakeSession, _reset_store, _STORE

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

    inserted, duplicates = 0, 0
    for filename, satellite_label in SNAPSHOT_FILES:
        filepath = os.path.join(SNAPSHOT_DIR, filename)
        with open(filepath) as f:
            for row in csv.DictReader(f):
                lat, lon = float(row["latitude"]), float(row["longitude"])
                if not in_bbox(lat, lon):
                    continue
                brightness = float(row.get("brightness") or row.get("bright_ti4", 0))
                confidence_raw = row.get("confidence", "0")
                confidence = {"low": 30.0, "nominal": 60.0, "high": 90.0}.get(
                    str(confidence_raw).lower(), safe_float(confidence_raw))
                frp = safe_float(row.get("frp"), default=None)
                acq_date = parse_acq_datetime(row["acq_date"], row["acq_time"])
                land_cover = tag_land_cover(lat, lon)

                hotspot = process_observation(db, {
                    "lat": lat, "lon": lon, "brightness": brightness, "confidence": confidence,
                    "frp": frp, "acq_date": acq_date, "land_cover": land_cover,
                    "satellite": satellite_label, "source": "nasa_firms",
                })
                if getattr(hotspot, "_was_duplicate", False):
                    duplicates += 1
                else:
                    inserted += 1

    real_rows = _STORE.get("Hotspot", [])
    total = len(real_rows)
    facility_associated = sum(1 for h in real_rows if h.facility_id is not None)
    missing_frp = sum(1 for h in real_rows if h.frp is None)
    missing_brightness = sum(1 for h in real_rows if h.brightness is None)
    dates = [h.acq_date for h in real_rows if h.acq_date]
    states = sorted(set(h.state for h in real_rows if h.state and h.state != "unknown"))
    satellites = {}
    for h in real_rows:
        satellites[h.satellite] = satellites.get(h.satellite, 0) + 1

    report = {
        "generated_at": datetime.utcnow().isoformat(),
        "total_observations": total,
        "unique_observations_after_pipeline_dedup": inserted,
        "duplicates_skipped_by_pipeline": duplicates,
        "facility_associated_observations": facility_associated,
        "verified_labels": 0,   # zero human verifications exist on this snapshot
        "class_distribution_verified": {},
        "missing_feature_counts": {"brightness": missing_brightness, "frp": missing_frp},
        "date_range": {"earliest": min(dates).isoformat() if dates else None,
                        "latest": max(dates).isoformat() if dates else None},
        "geographic_coverage_states_matched_to_facility": states,
        "satellite_distribution": satellites,
    }
    print(json.dumps(report, indent=2, default=str))

    out_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
                             "data-pipeline", "metadata", "dataset_report.json")
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w") as f:
        json.dump(report, f, indent=2, default=str)
    print(f"\nSaved to {out_path}")


if __name__ == "__main__":
    main()
