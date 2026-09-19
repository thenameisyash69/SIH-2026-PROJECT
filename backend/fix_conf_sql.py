"""Update stored NASA confidence values from raw archive CSV."""
import sys, os, csv
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from sqlalchemy import create_engine, text
from app.config import settings
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

engine = create_engine(settings.database_url)

# Build lookup with string-normalized keys
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
            # Normalize to string for matching
            key = (lat, lon, acq_date.strftime("%Y-%m-%d %H:%M:%S"))
            lookup[key] = conf
        except (KeyError, ValueError):
            continue

print(f"  Lookup entries: {len(lookup)}")

# Update using raw SQL with string matching
with engine.begin() as conn:
    result = conn.execute(text("SELECT id, lat, lon, acq_date FROM hotspots WHERE source = 'nasa_firms'"))
    rows = result.fetchall()
    print(f"  NASA rows to update: {len(rows)}")

    updated = 0
    not_found = 0
    for row in rows:
        hid, lat, lon, acq_date_str = row
        # Normalize DB acq_date to match CSV format
        if isinstance(acq_date_str, str):
            # Strip microseconds if present
            db_key = acq_date_str.split('.')[0] if '.' in acq_date_str else acq_date_str
        else:
            db_key = acq_date_str.strftime("%Y-%m-%d %H:%M:%S") if hasattr(acq_date_str, 'strftime') else str(acq_date_str)

        key = (round(float(lat), 4), round(float(lon), 4), db_key)
        if key in lookup:
            new_conf = lookup[key]
            conn.execute(
                text("UPDATE hotspots SET confidence = :conf WHERE id = :id"),
                {"conf": new_conf, "id": hid}
            )
            updated += 1
        else:
            not_found += 1

    print(f"  Updated: {updated}, Not found: {not_found}")

# Verify
with engine.connect() as conn:
    result = conn.execute(text("""
        SELECT confidence, COUNT(*) FROM hotspots 
        WHERE source = 'nasa_firms' 
        GROUP BY confidence ORDER BY confidence
    """))
    print("\nConfidence distribution:")
    for row in result:
        print(f"  confidence={row[0]}: {row[1]} rows")

    result = conn.execute(text("""
        SELECT data_quality, COUNT(*) FROM hotspots 
        WHERE source = 'nasa_firms' 
        GROUP BY data_quality
    """))
    print("\nData quality distribution:")
    for row in result:
        print(f"  data_quality={row[0]}: {row[1]} rows")