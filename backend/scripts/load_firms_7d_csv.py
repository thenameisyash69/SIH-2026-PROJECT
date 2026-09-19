"""
Load the downloaded FIRMS global 7-day CSV into the database.

The static daily CSV mirrors at firms.modaps.eosdis.nasa.gov require NO
MAP_KEY and contain full global daily detections. The 7-day rolling
global CSV is the most practical source for the current environment.

This script:
- Reads the downloaded CSV
- Filters to India bbox (68,6,97,37)
- Deduplicates against existing NASA observations
- Stores source="nasa_firms"
- Preserves raw FIRMS values
- Batch commits
- Reports statistics

Run with:
    python -m scripts.load_firms_7d_csv --file data-pipeline/raw/viirs_global_7d.csv
"""
import sys
import os
import argparse
import csv
from datetime import datetime

BACKEND_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, BACKEND_DIR)

from app.database import SessionLocal, init_db
from app import models

BATCH_SIZE = 500
INDIA_BBOX = (68.0, 6.0, 97.0, 37.0)  # west, south, east, north


def in_bbox(lat, lon):
    west, south, east, north = INDIA_BBOX
    return south <= lat <= north and west <= lon <= east


def parse_confidence(raw):
    mapping = {"low": 30.0, "nominal": 60.0, "high": 90.0}
    if raw is None:
        return 0.0
    try:
        return mapping.get(str(raw).lower(), float(raw))
    except (ValueError, TypeError):
        return 0.0


def parse_acq_datetime(date_str, time_str):
    try:
        dt = datetime.strptime(date_str, "%Y-%m-%d")
        if time_str:
            time_str = str(time_str).zfill(4)
            return dt.replace(hour=int(time_str[:2]), minute=int(time_str[2:]))
        return dt
    except (ValueError, TypeError):
        return datetime.utcnow()


def check_duplicate(db, lat, lon, acq_date):
    lat_r, lon_r = round(lat, 4), round(lon, 4)
    exists = db.query(models.Hotspot.id).filter(
        models.Hotspot.source == "nasa_firms",
        models.Hotspot.lat == lat_r,
        models.Hotspot.lon == lon_r,
        models.Hotspot.acq_date == acq_date,
    ).first()
    return exists is not None


def run_load(filepath: str, dry_run: bool = False) -> dict:
    init_db()
    db = SessionLocal()

    stats = {
        "total_rows": 0,
        "in_bbox": 0,
        "duplicates": 0,
        "inserted": 0,
        "dates": set(),
    }

    print(f"[load_7d] Reading {filepath}")

    with open(filepath) as f:
        reader = csv.DictReader(f)
        batch = []
        for row in reader:
            stats["total_rows"] += 1
            lat, lon = float(row["latitude"]), float(row["longitude"])

            if not in_bbox(lat, lon):
                continue
            stats["in_bbox"] += 1

            acq_date = parse_acq_datetime(row["acq_date"], row.get("acq_time"))
            stats["dates"].add(acq_date.date())

            if check_duplicate(db, lat, lon, acq_date):
                stats["duplicates"] += 1
                continue

            record = {
                "lat": round(lat, 4),
                "lon": round(lon, 4),
                "brightness": float(row.get("bright_ti4", row.get("brightness", 0))),
                "confidence": parse_confidence(row.get("confidence", "0")),
                "frp": float(row["frp"]) if row.get("frp") else None,
                "acq_date": acq_date,
                "satellite": row.get("satellite", "VIIRS_SNPP"),
                "source": "nasa_firms",
                "source_resolution_m": 375,
                "land_cover": "unknown",
                "facility_id": None,
                "distance_to_facility_km": None,
                "state": "unknown",
                "category": "unknown",
                "classification_method": "unclassified",
                "classification_confidence": 0.0,
                "model_version": None,
                "baseline_status": "INSUFFICIENT_HISTORY",
                "z_score": 0.0,
                "deviation_percentage": 0.0,
                "persistence_score": 0.0,
                "is_anomaly": False,
                "reason": "",
                "reason_codes": "DEFERRED_HISTORICAL",
                "risk_score": 0.0,
                "risk_level": "LOW",
                "data_quality": "unknown",
            }
            batch.append(record)

            if len(batch) >= BATCH_SIZE:
                if not dry_run:
                    hotspots = [models.Hotspot(**r) for r in batch]
                    db.bulk_save_objects(hotspots)
                    db.commit()
                stats["inserted"] += len(batch)
                batch.clear()

        if batch:
            if not dry_run:
                hotspots = [models.Hotspot(**r) for r in batch]
                db.bulk_save_objects(hotspots)
                db.commit()
            stats["inserted"] += len(batch)

    db.close()

    print(f"\n[load_7d] Complete:")
    print(f"  Total rows read:     {stats['total_rows']}")
    print(f"  In India bbox:       {stats['in_bbox']}")
    print(f"  Duplicates skipped:  {stats['duplicates']}")
    print(f"  Inserted:            {stats['inserted']}")
    print(f"  Dates:               {sorted(d.isoformat() for d in stats['dates'])}")

    return stats


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Load FIRMS 7-day global CSV into Kavach database.")
    parser.add_argument("--file", type=str, required=True, help="Path to FIRMS CSV file")
    parser.add_argument("--dry-run", action="store_true", help="Count but do not write")
    args = parser.parse_args()

    run_load(args.file, dry_run=args.dry_run)