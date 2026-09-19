"""
90-day historical FIRMS backfill using NASA's static daily CSV mirrors.

These mirrors require NO MAP_KEY and contain full global daily detections,
making them the only viable source for genuine multi-day historical
backfill (the Area API's day_range always counts back from 'now' and NRT
retention is ~5 days).

Every record stored here has source="nasa_firms" — NEVER "demo_synthetic".
Does not modify existing demo_synthetic data or curated_demo facilities.

Run with:
    python -m scripts.backfill_firms_90d --days 90
    python -m scripts.backfill_firms_90d --days 90 --sensor VIIRS_NOAA21_NRT
    python -m scripts.backfill_firms_90d --days 90 --dry-run
"""
import sys
import os
import argparse
import time
from datetime import datetime, timedelta

BACKEND_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, BACKEND_DIR)

from app.database import SessionLocal, init_db
from app import models
from app.services.firms_fetcher import fetch_firms_static_csv

BATCH_SIZE = 500


def in_india(lat, lon):
    """India bounding box — matches settings.firms_area default (68,6,97,37)."""
    west, south, east, north = 68.0, 6.0, 97.0, 37.0
    return south <= lat <= north and west <= lon <= east


def check_duplicate(db, lat, lon, acq_date):
    """Check if this observation already exists in the database."""
    lat_r, lon_r = round(lat, 4), round(lon, 4)
    exists = db.query(models.Hotspot.id).filter(
        models.Hotspot.source == "nasa_firms",
        models.Hotspot.lat == lat_r,
        models.Hotspot.lon == lon_r,
        models.Hotspot.acq_date == acq_date,
    ).first()
    return exists is not None


def run_backfill(days: int, sensor: str, dry_run: bool = False) -> dict:
    init_db()
    db = SessionLocal()

    today = datetime.utcnow().date()
    start_date = today - timedelta(days=days - 1)

    stats = {
        "requested_days": days,
        "successful_days": 0,
        "empty_days": 0,
        "failed_days": 0,
        "fetched": 0,
        "inserted": 0,
        "duplicates": 0,
        "date_range": None,
    }

    stored_dates = []

    print(f"[backfill_90d] Requesting {days} days of FIRMS data from {start_date} to {today}")
    print(f"[backfill_90d] Sensor: {sensor}, BBOX: India (68,6,97,37)")
    print(f"[backfill_90d] Dry run: {dry_run}")

    current = start_date
    while current <= today:
        try:
            raw = fetch_firms_static_csv(current, sensor)
        except Exception as e:
            print(f"[backfill_90d]   {current}: FAILED — {e}")
            stats["failed_days"] += 1
            current += timedelta(days=1)
            continue

        if not raw:
            stats["empty_days"] += 1
            current += timedelta(days=1)
            continue

        stats["successful_days"] += 1
        stats["fetched"] += len(raw)
        stored_dates.append(current)

        batch = []
        for obs in raw:
            if not in_india(obs["lat"], obs["lon"]):
                continue
            if check_duplicate(db, obs["lat"], obs["lon"], obs["acq_date"]):
                stats["duplicates"] += 1
                continue

            record = {
                "lat": round(obs["lat"], 4),
                "lon": round(obs["lon"], 4),
                "brightness": obs["brightness"],
                "confidence": obs.get("confidence", 0.0),
                "frp": obs.get("frp"),
                "acq_date": obs["acq_date"],
                "satellite": obs.get("satellite", "VIIRS_SNPP"),
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

        current += timedelta(days=1)

    if stored_dates:
        stats["date_range"] = {
            "min": min(stored_dates).isoformat(),
            "max": max(stored_dates).isoformat(),
        }

    db.close()

    print(f"\n[backfill_90d] Complete:")
    print(f"  Requested days:      {stats['requested_days']}")
    print(f"  Successful days:     {stats['successful_days']}")
    print(f"  Empty days:          {stats['empty_days']}")
    print(f"  Failed days:         {stats['failed_days']}")
    print(f"  Fetched observations: {stats['fetched']}")
    print(f"  Inserted:            {stats['inserted']}")
    print(f"  Duplicates:          {stats['duplicates']}")
    print(f"  Date range stored:   {stats['date_range']}")

    return stats


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="90-day historical NASA FIRMS backfill via static CSV mirrors."
    )
    parser.add_argument("--days", type=int, default=90, help="Days of history to pull (default 90)")
    parser.add_argument("--sensor", type=str, default="VIIRS_NOAA21_NRT",
                        help="FIRMS sensor (default VIIRS_NOAA21_NRT)")
    parser.add_argument("--dry-run", action="store_true", help="Fetch but do not write to database")
    args = parser.parse_args()

    run_backfill(args.days, args.sensor, dry_run=args.dry_run)