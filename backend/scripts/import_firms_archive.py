"""
Imports a NASA FIRMS historical archive CSV into the existing Hotspot table.

Reads data/firms_archive/firms_90day_india.csv, parses the standard FIRMS
CSV columns, and bulk-inserts rows with source="nasa_firms". Uses the
same deduplication check as pipeline._find_duplicate() (rounded coords +
exact acq_date + same source) so re-runs are idempotent.

Demo data is never touched.

Run with:
    python -m scripts.import_firms_archive [path]
"""
import sys
import os
import csv
from datetime import datetime

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BACKEND_DIR)

from app.database import SessionLocal, init_db
from app import models

DEFAULT_ARCHIVE_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "data", "firms_archive", "firms_90day_india.csv",
)

BATCH_SIZE = 500


def _parse_confidence(raw):
    # VIIRS gives categorical confidence: 'l'/'n'/'h' (single-letter) or
    # 'low'/'nominal'/'high' (full-word). MODIS gives a 0-100 number.
    # The 30/60/90 values are an internal ordinal encoding of NASA's
    # categorical signal — NOT a calibrated probability or percentage.
    mapping = {
        "l": 30.0, "low": 30.0,
        "n": 60.0, "nominal": 60.0,
        "h": 90.0, "high": 90.0,
    }
    if raw is None:
        return 0.0
    try:
        return mapping.get(str(raw).lower(), float(raw))
    except (ValueError, TypeError):
        return 0.0


def _parse_acq_datetime(date_str, time_str):
    try:
        dt = datetime.strptime(date_str, "%Y-%m-%d")
        if time_str:
            time_str = str(time_str).zfill(4)
            return dt.replace(hour=int(time_str[:2]), minute=int(time_str[2:]))
        return dt
    except (ValueError, TypeError):
        return datetime.utcnow()


def _safe_float(v, default=0.0):
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def _check_duplicate(db, lat, lon, acq_date):
    """Same dedup logic as pipeline._find_duplicate: rounded coords + exact acq_date."""
    lat_r, lon_r = round(lat, 4), round(lon, 4)
    exists = db.query(models.Hotspot.id).filter(
        models.Hotspot.source == "nasa_firms",
        models.Hotspot.lat == lat_r,
        models.Hotspot.lon == lon_r,
        models.Hotspot.acq_date == acq_date,
    ).first()
    return exists is not None


def import_archive(filepath=None, dry_run=False):
    init_db()
    db = SessionLocal()

    path = filepath or DEFAULT_ARCHIVE_PATH
    if not os.path.exists(path):
        print(f"[import_archive] ERROR: file not found: {path}")
        db.close()
        return None

    print(f"[import_archive] Reading {path}")

    stats = {
        "read": 0,
        "inserted": 0,
        "duplicate": 0,
        "invalid": 0,
        "satellites": {},
        "acq_dates": [],
    }

    with open(path, newline="") as f:
        reader = csv.DictReader(f)
        batch = []

        for row in reader:
            stats["read"] += 1

            try:
                lat = float(row["latitude"])
                lon = float(row["longitude"])
                brightness = float(row.get("brightness", 0))
            except (KeyError, ValueError, TypeError):
                stats["invalid"] += 1
                continue

            confidence_raw = row.get("confidence", "0")
            confidence = _parse_confidence(confidence_raw)

            frp_raw = row.get("frp", "")
            frp = _safe_float(frp_raw, default=None) if frp_raw else None

            acq_date = _parse_acq_datetime(
                row.get("acq_date", ""),
                row.get("acq_time", ""),
            )

            satellite = row.get("satellite", "VIIRS_SNPP") or "VIIRS_SNPP"

            stats["satellites"][satellite] = stats["satellites"].get(satellite, 0) + 1
            stats["acq_dates"].append(acq_date)

            if _check_duplicate(db, lat, lon, acq_date):
                stats["duplicate"] += 1
                continue

            record = {
                "lat": round(lat, 4),
                "lon": round(lon, 4),
                "brightness": brightness,
                "confidence": confidence,
                "frp": frp,
                "acq_date": acq_date,
                "satellite": satellite,
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
                    db.bulk_save_objects([models.Hotspot(**r) for r in batch])
                    db.commit()
                stats["inserted"] += len(batch)
                batch.clear()

        if batch:
            if not dry_run:
                db.bulk_save_objects([models.Hotspot(**r) for r in batch])
                db.commit()
            stats["inserted"] += len(batch)

    db.close()

    print(f"\n[import_archive] Complete:")
    print(f"  Read:              {stats['read']}")
    print(f"  Inserted:          {stats['inserted']}")
    print(f"  Duplicates:        {stats['duplicate']}")
    print(f"  Invalid (skipped): {stats['invalid']}")
    if stats["acq_dates"]:
        print(f"  Min acquisition:   {min(stats['acq_dates'])}")
        print(f"  Max acquisition:   {max(stats['acq_dates'])}")
    print(f"  Satellite counts:  {stats['satellites']}")

    return stats


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Import NASA FIRMS archive CSV into Kavach.")
    parser.add_argument("--file", type=str, default=None, help="Path to archive CSV")
    parser.add_argument("--dry-run", action="store_true", help="Count only, do not write")
    args = parser.parse_args()

    import_archive(args.file, dry_run=args.dry_run)