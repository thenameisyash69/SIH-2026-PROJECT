"""Debug: find rows that DO match the CSV lookup."""
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

print(f"Lookup entries: {len(lookup)}")

# Check DB rows
conn = sqlite3.connect(DB_PATH)
c = conn.cursor()
c.execute('SELECT id, lat, lon, acq_date FROM hotspots WHERE source="nasa_firms" ORDER BY id')
rows = c.fetchall()

# Find matching rows
matches = []
for hid, lat, lon, acq in rows:
    if hasattr(acq, 'strftime'):
        db_key = acq.strftime("%Y-%m-%d %H:%M:%S")
    elif isinstance(acq, str):
        db_key = acq.split('.')[0] if '.' in acq else acq
    else:
        db_key = str(acq)
    
    key = (round(float(lat), 4), round(float(lon), 4), db_key)
    if key in lookup:
        matches.append((hid, key, lookup[key]))

print(f"Total matches: {len(matches)}")

# Show first 5 matches
print("\nFirst 5 matches:")
for hid, key, conf in matches[:5]:
    print(f"  id={hid}, key={key}, conf={conf}")

# Show last 5 matches
print("\nLast 5 matches:")
for hid, key, conf in matches[-5:]:
    print(f"  id={hid}, key={key}, conf={conf}")

conn.close()