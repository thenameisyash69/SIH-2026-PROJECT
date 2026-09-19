"""Update stored NASA confidence values from raw archive CSV using corrected parser."""
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
    key = str(raw).lower()
    if key in CONFIDENCE_MAP:
        return CONFIDENCE_MAP[key]
    try:
        return float(raw)
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

# Update stored confidence values
conn = sqlite3.connect(DB_PATH)
c = conn.cursor()

c.execute('SELECT id, lat, lon, acq_date FROM hotspots WHERE source="nasa_firms" ORDER BY id')
rows = c.fetchall()
print(f"  NASA rows to update: {len(rows)}")

# Build update batch
updates = []
updated = 0
not_found = 0
for i, (hid, lat, lon, acq) in enumerate(rows):
    if hasattr(acq, 'strftime'):
        db_key = acq.strftime("%Y-%m-%d %H:%M:%S")
    elif isinstance(acq, str):
        db_key = acq.split('.')[0] if '.' in acq else acq
    else:
        db_key = str(acq)

    key = (round(float(lat), 4), round(float(lon), 4), db_key)
    if key in lookup:
        updates.append((lookup[key], hid))
        updated += 1
    else:
        not_found += 1

    if (i + 1) % 5000 == 0:
        print(f"  ... {i+1}/{len(rows)} processed, {updated} updated, {not_found} not found")

print(f"\n  Total to update: {updated}, Not found: {not_found}")

# Use executemany in batches
batch_size = 5000
for i in range(0, len(updates), batch_size):
    batch = updates[i:i+batch_size]
    c.executemany("UPDATE hotspots SET confidence = ? WHERE id = ?", batch)
    print(f"  Batch {i//batch_size + 1}: {len(batch)} rows")

conn.commit()
print(f"\n  Total updated: {updated}")

# Verify in same connection
c.execute('SELECT confidence, COUNT(*) FROM hotspots WHERE source="nasa_firms" GROUP BY confidence ORDER BY confidence')
print("\nConfidence distribution after update (same conn):")
for row in c.fetchall():
    print(f"  confidence={row[0]}: {row[1]} rows")

conn.close()

# Verify with fresh connection
print("\nVerifying with fresh connection...")
conn2 = sqlite3.connect(DB_PATH)
c2 = conn2.cursor()
c2.execute('SELECT confidence, COUNT(*) FROM hotspots WHERE source="nasa_firms" GROUP BY confidence ORDER BY confidence')
print("Confidence distribution (fresh):")
for row in c2.fetchall():
    print(f"  confidence={row[0]}: {row[1]} rows")
conn2.close()