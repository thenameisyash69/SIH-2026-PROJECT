"""
Historical FIRMS backfill — bulk acquisition of real NASA FIRMS observations
for ML dataset construction.

SEPARATE PATH from live ingestion (data-pipeline/ingest_firms.py):
- Live: day_range=1, full intelligence pipeline, alerts, dashboard
- Historical: multi-day fetch, efficient batch storage, raw preservation,
  deferred enrichment, NO automatic classification/anomaly/risk

Every record stored here has source="nasa_firms" — NEVER "demo_synthetic".
Does not modify existing demo_synthetic data or curated_demo facilities.

Run with:
    python data-pipeline/backfill_firms.py --days 5
    python data-pipeline/backfill_firms.py --days 30 --batch-size 500
"""
import sys
import os
import argparse
import time
from datetime import datetime

# Ensure we use the backend's database (backend/sih.db), not data-pipeline/sih.db
BACKEND_DIR = os.path.join(os.path.dirname(__file__), "..", "backend")
sys.path.insert(0, BACKEND_DIR)

# Override DATABASE_URL to point to backend/sih.db BEFORE importing app.database
BACKEND_DB_PATH = os.path.join(BACKEND_DIR, "sih.db")
os.environ["DATABASE_URL"] = f"sqlite:///{BACKEND_DB_PATH}"

from app.database import SessionLocal, init_db, engine
from app import models
from app.config import settings
from app.services.firms_fetcher import fetch_firms_hotspots
from sqlalchemy import text

MAX_DAY_RANGE_PER_REQUEST = 10
DEFAULT_BATCH_SIZE = 500


def ensure_historical_index():
    """Add a composite index for efficient duplicate detection if not exists."""
    with engine.connect() as conn:
        result = conn.execute(text("""
            SELECT name FROM sqlite_master
            WHERE type='index' AND name='ix_hotspots_source_lat_lon_acq'
        """))
        if not result.fetchone():
            conn.execute(text("""
                CREATE INDEX ix_hotspots_source_lat_lon_acq
                ON hotspots (source, lat, lon, acq_date)
            """))
            conn.commit()
            print("[backfill] Created composite index for efficient duplicate detection")


def check_duplicate(db, source: str, lat: float, lon: float, acq_date: datetime) -> bool:
    """Efficient database-side duplicate check using rounded coordinates + exact timestamp."""
    lat_r = round(lat, 4)
    lon_r = round(lon, 4)
    
    exists = db.query(models.Hotspot.id).filter(
        models.Hotspot.source == source,
        models.Hotspot.lat == lat_r,
        models.Hotspot.lon == lon_r,
        models.Hotspot.acq_date == acq_date
    ).first()
    
    return exists is not None


def insert_batch(db, records: list[dict]) -> int:
    """Bulk insert a batch of hotspot records. Returns count inserted."""
    if not records:
        return 0
    
    hotspots = [models.Hotspot(**r) for r in records]
    db.bulk_save_objects(hotspots)
    db.flush()
    return len(hotspots)


def run_backfill(days: int, bbox: str | None, sources: list | None, batch_size: int) -> dict:
    """Main backfill orchestration."""
    if bbox:
        settings.firms_area = bbox
    active_sources = sources or settings.firms_sources
    
    if not settings.firms_configured:
        print("FIRMS_MAP_KEY is not set in backend/.env — cannot backfill real history. "
              "Get a free key at https://firms.modaps.eosdis.nasa.gov/api/ and set it, then re-run.")
        return {"success": False, "error": "FIRMS_MAP_KEY not configured"}
    
    init_db()
    ensure_historical_index()
    db = SessionLocal()
    
    total_fetched = 0
    total_inserted = 0
    total_duplicates = 0
    total_invalid = 0
    start_time = time.time()
    
    remaining_days = days
    chunk_index = 0
    
    print(f"[backfill] Starting historical backfill for {days} day(s)")
    print(f"[backfill] Area: {settings.firms_area}, Sources: {active_sources}")
    print(f"[backfill] Batch size: {batch_size}")
    print(f"[backfill] Land cover: DEFERRED (set to 'unknown') — per spec, no per-observation API calls")
    
    while remaining_days > 0:
        chunk_days = min(MAX_DAY_RANGE_PER_REQUEST, remaining_days)
        chunk_index += 1
        print(f"[backfill] Chunk {chunk_index}: requesting last {chunk_days} day(s)...")
        
        try:
            raw_observations = fetch_firms_hotspots(day_range=chunk_days, sources=active_sources)
        except Exception as e:
            print(f"[backfill] Chunk {chunk_index} FAILED: {e} — stopping.")
            break
        
        print(f"[backfill] Chunk {chunk_index}: fetched {len(raw_observations)} raw observations")
        total_fetched += len(raw_observations)
        
        batch_records = []
        
        for obs in raw_observations:
            # Validate required fields
            required = ["lat", "lon", "brightness", "acq_date"]
            if not all(k in obs and obs[k] is not None for k in required):
                total_invalid += 1
                continue
            
            lat = round(obs["lat"], 4)
            lon = round(obs["lon"], 4)
            acq_date = obs["acq_date"]
            
            # Efficient duplicate check
            if check_duplicate(db, "nasa_firms", lat, lon, acq_date):
                total_duplicates += 1
                continue
            
            # Build raw observation record — NO intelligence processing
            # Land cover DEFERRED per spec: "Otherwise defer it. Use 'unknown' when unavailable."
            record = {
                "lat": lat,
                "lon": lon,
                "brightness": obs["brightness"],
                "confidence": obs.get("confidence", 0.0),
                "frp": obs.get("frp"),
                "acq_date": acq_date,
                "satellite": obs.get("satellite", "VIIRS_SNPP"),
                "source": "nasa_firms",
                "source_resolution_m": 375,
                "land_cover": "unknown",  # DEFERRED — not fetched during historical backfill
                "facility_id": None,  # Deferred — not matched during historical backfill
                "distance_to_facility_km": None,
                "state": "unknown",
                "category": "unknown",  # Deferred — not classified during historical backfill
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
            batch_records.append(record)
            
            # Flush batch when full
            if len(batch_records) >= batch_size:
                inserted = insert_batch(db, batch_records)
                total_inserted += inserted
                db.commit()
                batch_records.clear()
                print(f"[backfill]   Committed batch: {inserted} inserted (running total: {total_inserted})")
        
        # Flush remaining batch
        if batch_records:
            inserted = insert_batch(db, batch_records)
            total_inserted += inserted
            db.commit()
            batch_records.clear()
            print(f"[backfill]   Committed final batch: {inserted} inserted (running total: {total_inserted})")
        
        remaining_days -= chunk_days
    
    duration = time.time() - start_time
    
    print(f"\n[backfill] Complete in {duration:.1f}s:")
    print(f"  Fetched:      {total_fetched}")
    print(f"  Inserted:     {total_inserted}")
    print(f"  Duplicates:   {total_duplicates}")
    print(f"  Invalid:      {total_invalid}")
    
    return {
        "success": True,
        "fetched": total_fetched,
        "inserted": total_inserted,
        "duplicates": total_duplicates,
        "invalid": total_invalid,
        "duration_seconds": round(duration, 1),
    }


def run_dataset_summary() -> dict:
    """Generate a summary of the real vs synthetic dataset composition."""
    init_db()
    db = SessionLocal()
    
    nasa_count = db.query(models.Hotspot).filter(models.Hotspot.source == "nasa_firms").count()
    demo_count = db.query(models.Hotspot).filter(models.Hotspot.source == "demo_synthetic").count()
    facility_count = db.query(models.Facility).count()
    
    # Observations by satellite
    by_satellite = db.query(
        models.Hotspot.satellite,
        models.Hotspot.source
    ).all()
    sat_counts = {}
    for sat, src in by_satellite:
        key = f"{sat} ({src})"
        sat_counts[key] = sat_counts.get(key, 0) + 1
    
    # Observations by acquisition date range
    nasa_dates = db.query(models.Hotspot.acq_date).filter(
        models.Hotspot.source == "nasa_firms"
    ).all()
    if nasa_dates:
        dates = [d[0] for d in nasa_dates if d[0]]
        min_date = min(dates) if dates else None
        max_date = max(dates) if dates else None
    else:
        min_date = max_date = None
    
    # Observations associated with facilities
    with_facility = db.query(models.Hotspot).filter(
        models.Hotspot.source == "nasa_firms",
        models.Hotspot.facility_id.isnot(None)
    ).count()
    without_facility = nasa_count - with_facility
    
    summary = {
        "nasa_firms_observations": nasa_count,
        "demo_synthetic_observations": demo_count,
        "facility_count": facility_count,
        "observations_by_satellite": sat_counts,
        "acquisition_date_range": {
            "min": min_date.isoformat() if min_date else None,
            "max": max_date.isoformat() if max_date else None,
        },
        "nasa_observations_with_facility": with_facility,
        "nasa_observations_without_facility": without_facility,
    }
    
    print("\n=== DATASET SUMMARY ===")
    for key, value in summary.items():
        print(f"  {key}: {value}")
    
    return summary


def main():
    parser = argparse.ArgumentParser(description="Historical NASA FIRMS backfill for Kavach ML dataset.")
    parser.add_argument("--days", type=int, default=30, help="Days of history to pull (default 30)")
    parser.add_argument("--bbox", type=str, default=None, help="Override bounding box, e.g. '68,6,97,37'")
    parser.add_argument("--sources", type=str, default=None, help="Comma-separated FIRMS sensor list")
    parser.add_argument("--batch-size", type=int, default=DEFAULT_BATCH_SIZE, help=f"Batch commit size (default {DEFAULT_BATCH_SIZE})")
    parser.add_argument("--summary-only", action="store_true", help="Only print dataset summary, no backfill")
    
    args = parser.parse_args()
    
    source_list = [s.strip() for s in args.sources.split(",")] if args.sources else None
    
    if args.summary_only:
        run_dataset_summary()
    else:
        result = run_backfill(args.days, args.bbox, source_list, args.batch_size)
        if result.get("success"):
            print("\nBackfill successful.")
        else:
            print(f"\nBackfill failed: {result.get('error')}")
            sys.exit(1)


if __name__ == "__main__":
    main()