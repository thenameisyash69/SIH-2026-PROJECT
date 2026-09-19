"""Update stored NASA confidence values using ORM batch updates."""
import sys, os, csv
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.database import SessionLocal, init_db
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

init_db()

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

# Update in batches using ORM
db = SessionLocal()
try:
    nasa_rows = db.query(models.Hotspot).filter(
        models.Hotspot.source == "nasa_firms"
    ).all()
    print(f"  NASA rows to update: {len(nasa_rows)}")

    updated = 0
    not_found = 0
    batch = 0
    for h in nasa_rows:
        # Normalize DB acq_date
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
        else:
            not_found += 1

        batch += 1
        if batch % 500 == 0:
            db.commit()
            print(f"  ... {batch}/{len(nasa_rows)} processed, {updated} updated")

    db.commit()
    print(f"\n  Updated: {updated}, Not found: {not_found}")

    # Verify
    from sqlalchemy import func
    conf_dist = db.query(models.Hotspot.confidence, func.count(models.Hotspot.id)).filter(
        models.Hotspot.source == "nasa_firms"
    ).group_by(models.Hotspot.confidence).order_by(models.Hotspot.confidence).all()
    print(f"\nConfidence distribution:")
    for conf, cnt in conf_dist:
        print(f"  confidence={conf}: {cnt} rows")

    dq_dist = db.query(models.Hotspot.data_quality, func.count(models.Hotspot.id)).filter(
        models.Hotspot.source == "nasa_firms"
    ).group_by(models.Hotspot.data_quality).all()
    print(f"\nData quality distribution:")
    for dq, cnt in dq_dist:
        print(f"  data_quality={dq}: {cnt} rows")
finally:
    db.close()