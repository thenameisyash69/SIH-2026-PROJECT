"""Debug: check key matching in fix_stored_conf.py."""
import sqlite3, csv, os
from datetime import datetime

THIS_DIR = os.path.dirname(os.path.abspath(__file__))
BACKEND_DIR = os.path.dirname(THIS_DIR)
DB_PATH = os.path.join(THIS_DIR, "sih.db")
ARCHIVE_CSV = os.path.join(BACKEND_DIR, "data", "firms_archive", "firms_90day_india.csv")

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

# Build lookup from CSV
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

# Sample some lookup keys
print("\nSample lookup keys:")
for i, k in enumerate(list(lookup.keys())[:5]):
    print(f"  {k}")

# Check DB rows
conn = sqlite3.connect(DB_PATH)
c = conn.cursor()
c.execute('SELECT id, lat, lon, acq_date FROM hotspots WHERE source="nasa_firms" ORDER BY id LIMIT 10')
rows = c.fetchall()
print("\nSample DB rows:")
for hid, lat, lon, acq in rows:
    if hasattr(acq, 'strftime'):
        db_key = acq.strftime("%Y-%m-%d %H:%M:%S")
    elif isinstance(acq, str):
        db_key = acq.split('.')[0] if '.' in acq else acq
    else:
        db_key = str(acq)
    
    key = (round(float(lat), 4), round(float(lon), 4), db_key)
    print(f"  id={hid}, lat={lat}, lon={lon}, acq={acq}, db_key={db_key}, lookup_key={key}, found={key in lookup}")

conn.close()