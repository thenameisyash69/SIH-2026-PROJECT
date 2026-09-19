"""Update stored NASA confidence values from raw archive CSV."""
import sys, os, csv
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.database import SessionLocal, init_db
from app import models
from sqlalchemy import update

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
db = SessionLocal()

# Build lookup: (lat_r, lon_r, acq_date) -> confidence
print("Building confidence lookup from CSV...")
lookup = {}
with open(ARCHIVE_CSV, newline="") as f:
    reader = csv.DictReader(f)
    for row in reader:
        try:
            lat = round(float(row["latitude"]), 4)
            lon = round(float(row["longitude"]), 4)
            from datetime import datetime
            acq_date = datetime.strptime(row["acq_date"], "%Y-%m-%d")
            if row.get("acq_time"):
                t = str(row["acq_time"]).zfill(4)
                acq_date = acq_date.replace(hour=int(t[:2]), minute=int(t[2:]))
            conf = parse_conf(row.get("confidence", ""))
            lookup[(lat, lon, acq_date)] = conf
        except (KeyError, ValueError):
            continue

print(f"  Lookup entries: {len(lookup)}")

# Update NASA rows one at a time with explicit flush
nasa_rows = db.query(models.Hotspot).filter(
    models.Hotspot.source == "nasa_firms"
).all()

updated = 0
not_found = 0
for h in nasa_rows:
    key = (round(h.lat, 4), round(h.lon, 4), h.acq_date)
    if key in lookup:
        h.confidence = lookup[key]
        updated += 1
    else:
        not_found += 1

db.commit()
db.flush()
print(f"Updated: {updated}, Not in CSV: {not_found}")

# Show new distribution
from sqlalchemy import func
conf_dist = db.query(models.Hotspot.confidence, func.count(models.Hotspot.id)).filter(
    models.Hotspot.source == "nasa_firms"
).group_by(models.Hotspot.confidence).order_by(models.Hotspot.confidence).all()
print(f"Confidence distribution: {dict(conf_dist)}")

dq_dist = db.query(models.Hotspot.data_quality, func.count(models.Hotspot.id)).filter(
    models.Hotspot.source == "nasa_firms"
).group_by(models.Hotspot.data_quality).all()
print(f"Data quality distribution: {dict(dq_dist)}")

db.close()