"""Update stored NASA confidence values using SQLAlchemy Core with explicit connection."""
import sys, os, csv
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from sqlalchemy import create_engine, MetaData, Table, Integer, Float, String, DateTime, select, update
from app.config import settings
from datetime import datetime

db_path = settings.database_url.replace("sqlite:///", "")
if not os.path.isabs(db_path):
    db_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), db_path)

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

# Use SQLAlchemy Core with raw connection
engine = create_engine(settings.database_url)
metadata = MetaData()
hotspots = Table("hotspots", metadata, autoload_with=engine)

with engine.begin() as conn:
    # Get all NASA rows
    result = conn.execute(select(hotspots.c.id, hotspots.c.lat, hotspots.c.lon, hotspots.c.acq_date).where(
        hotspots.c.source == "nasa_firms"
    ).order_by(hotspots.c.id))
    rows = result.fetchall()
    print(f"  NASA rows to update: {len(rows)}")

    updated = 0
    for i, row in enumerate(rows):
        hid, lat, lon, acq = row
        if hasattr(acq, 'strftime'):
            db_key = acq.strftime("%Y-%m-%d %H:%M:%S")
        elif isinstance(acq, str):
            db_key = acq.split('.')[0] if '.' in acq else acq
        else:
            db_key = str(acq)

        key = (round(float(lat), 4), round(float(lon), 4), db_key)
        if key in lookup:
            new_conf = lookup[key]
            conn.execute(update(hotspots).where(hotspots.c.id == hid).values(confidence=new_conf))
            updated += 1

        if (i + 1) % 5000 == 0:
            print(f"  ... {i+1}/{len(rows)} processed, {updated} updated")

    print(f"\n  Total updated: {updated}")

# Verify with fresh connection
print("\nVerifying...")
with engine.connect() as conn:
    result = conn.execute(select(hotspots.c.confidence, hotspots.c.id).where(
        hotspots.c.source == "nasa_firms"
    ).limit(5))
    print("Sample rows:")
    for row in result:
        print(f"  id={row[1]}, confidence={row[0]}")

    result = conn.execute(select(hotspots.c.confidence, func.count()).where(
        hotspots.c.source == "nasa_firms"
    ).group_by(hotspots.c.confidence).order_by(hotspots.c.confidence))
    from sqlalchemy import func
    result = conn.execute(select(hotspots.c.confidence, func.count(hotspots.c.id)).where(
        hotspots.c.source == "nasa_firms"
    ).group_by(hotspots.c.confidence).order_by(hotspots.c.confidence))
    print("\nConfidence distribution:")
    for row in result:
        print(f"  confidence={row[0]}: {row[1]} rows")