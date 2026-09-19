"""Update stored NASA confidence values using ORM with explicit flush."""
import sys, os, csv
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.database import SessionLocal, init_db, engine
from app import models
from datetime import datetime

ARCHIVE_CSV = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data", "firms_archive", "firms_90day_india.csv",
)

CONFIDENCE_MAP = {
    "l": 30.0, "low": 30.0,
    "n": 60.0, "nominal": 60.0,
    "h": 90.0, "high": 90.0,
}

def parse_conf(raw):
    if raw is None:
        return 0.0
    try:
        return CONFIDENCE_MAP.get(str(raw).lower(), float(raw))
    except (ValueError, TypeError):
        return 0.0

# Build lookup
print("Building confidence lookup from CSV...")
lookup = {}
with open(ARCHIVE_CSV, newline="") as f:
    reader = csv.DictReader(f)
    for row in reader:
        try:
            lat = round(float(row["latitude"]), 4)
            lon = round(float(row["longitude"]), 4)
            acq_date = datetime.strptime(row["acq_date"], "%Y-%m-%d")
            if row.get("acq_time"):
                t = str(row["acq_time"]).zfill(4)
                acq_date = acq_date.replace(hour=int(t[:2]), minute=int(t[2:]))
            conf = parse_conf(row.get("confidence", ""))
            key = (lat, lon, acq_date.strftime("%Y-%m-%d %H:%M:%S"))
            lookup[key] = conf
        except (KeyError, ValueError):
            continue

print(f"  Lookup entries: {len(lookup)}")

# Use ORM with explicit flush and expire
db = SessionLocal()
try:
    total = db.query(models.Hotspot).filter(
        models.Hotspot.source == "nasa_firms"
    ).count()
    print(f"  NASA rows to update: {total}")

    updated = 0
    offset = 0
    BATCH = 500
    while offset < total:
        batch = db.query(models.Hotspot).filter(
            models.Hotspot.source == "nasa_firms"
        ).order_by(models.Hotspot.id).offset(offset).limit(BATCH).all()

        for h in batch:
            acq = h.acq_date
            if hasattr(acq, 'strftime'):
                db_key = acq.strftime("%Y-%m-%d %H:%M:%S")
            elif isinstance(acq, str):
                db_key = acq.split('.')[0] if '.' in acq else acq
            else:
                db_key = str(acq)

            key = (round(float(h.lat), 4), round(float(h.lon), 4), db_key)
            if key in lookup:
                h.confidence = lookup[key]
                updated += 1

        db.commit()
        db.flush()
        offset += len(batch)
        if offset % 5000 == 0:
            print(f"  ... {offset}/{total} processed, {updated} updated")

    print(f"\n  Total updated: {updated}")

    # Force refresh and verify
    db.expire_all()
    from sqlalchemy import func
    conf_dist = db.query(models.Hotspot.confidence, func.count(models.Hotspot.id)).filter(
        models.Hotspot.source == "nasa_firms"
    ).group_by(models.Hotspot.confidence).order_by(models.Hotspot.confidence).all()
    print("\nConfidence distribution (after expire_all):")
    for conf, cnt in conf_dist:
        print(f"  confidence={conf}: {cnt} rows")
finally:
    db.close()

# Verify with fresh engine connection
print("\nVerifying with fresh engine connection...")
from sqlalchemy import text
with engine.connect() as conn:
    result = conn.execute(text("SELECT confidence, COUNT(*) FROM hotspots WHERE source = 'nasa_firms' GROUP BY confidence ORDER BY confidence"))
    print("Confidence distribution:")
    for row in result:
        print(f"  confidence={row[0]}: {row[1]} rows")