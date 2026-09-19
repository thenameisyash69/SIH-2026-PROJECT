"""Rebuild NASA confidence values from raw CSV using direct file replacement."""
import sys, os, csv, shutil
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.database import SessionLocal, init_db, engine
from app import models
from sqlalchemy import text
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

# Use direct SQL with the engine
with engine.begin() as conn:
    # Get all NASA rows
    result = conn.execute(text("SELECT id, lat, lon, acq_date FROM hotspots WHERE source = 'nasa_firms' ORDER BY id"))
    rows = result.fetchall()
    print(f"  NASA rows to update: {len(rows)}")

    updated = 0
    for i, (hid, lat, lon, acq) in enumerate(rows):
        if hasattr(acq, 'strftime'):
            db_key = acq.strftime("%Y-%m-%d %H:%M:%S")
        elif isinstance(acq, str):
            db_key = acq.split('.')[0] if '.' in acq else acq
        else:
            db_key = str(acq)

        key = (round(float(lat), 4), round(float(lon), 4), db_key)
        if key in lookup:
            new_conf = lookup[key]
            conn.execute(
                text("UPDATE hotspots SET confidence = :conf WHERE id = :id"),
                {"conf": new_conf, "id": hid}
            )
            updated += 1

        if (i + 1) % 5000 == 0:
            print(f"  ... {i+1}/{len(rows)} processed, {updated} updated")

    print(f"\n  Total updated: {updated}")

# Verify with direct sqlite3
import sqlite3
from app.config import settings
db_path = settings.database_url.replace("sqlite:///", "")
if not os.path.isabs(db_path):
    db_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), db_path)

conn = sqlite3.connect(db_path)
cursor = conn.cursor()
cursor.execute("SELECT confidence, COUNT(*) FROM hotspots WHERE source = 'nasa_firms' GROUP BY confidence ORDER BY confidence")
print("\nConfidence distribution (sqlite3 verify):")
for row in cursor.fetchall():
    print(f"  confidence={row[0]}: {row[1]} rows")
conn.close()