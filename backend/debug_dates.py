"""Debug: check CSV date range and DB date range."""
import sqlite3, csv, os
from datetime import datetime

THIS_DIR = os.path.dirname(os.path.abspath(__file__))
BACKEND_DIR = os.path.dirname(THIS_DIR)
DB_PATH = os.path.join(THIS_DIR, "sih.db")
ARCHIVE_CSV = os.path.join(BACKEND_DIR, "data", "firms_archive", "firms_90day_india.csv")

# Check CSV date range
csv_dates = set()
with open(ARCHIVE_CSV, newline="") as f:
    reader = csv.DictReader(f)
    for row in reader:
        csv_dates.add(row["acq_date"])

print(f"CSV dates: {len(csv_dates)} unique dates")
print(f"  Min: {min(csv_dates)}")
print(f"  Max: {max(csv_dates)}")

# Check DB date range
conn = sqlite3.connect(DB_PATH)
c = conn.cursor()
c.execute('SELECT MIN(acq_date), MAX(acq_date) FROM hotspots WHERE source="nasa_firms"')
db_min, db_max = c.fetchone()
print(f"\nDB NASA dates: Min={db_min}, Max={db_max}")

# Check if 2026-09-05 is in CSV
print(f"\n2026-09-05 in CSV: {'2026-09-05' in csv_dates}")

# Check DB rows with dates that ARE in CSV
c.execute('SELECT id, lat, lon, acq_date FROM hotspots WHERE source="nasa_firms" ORDER BY id')
rows = c.fetchall()

matches = 0
for hid, lat, lon, acq in rows:
    if hasattr(acq, 'strftime'):
        db_date = acq.strftime("%Y-%m-%d")
    elif isinstance(acq, str):
        db_date = acq.split(' ')[0]
    else:
        db_date = str(acq).split(' ')[0]
    
    if db_date in csv_dates:
        matches += 1
        if matches <= 3:
            print(f"  Match: id={hid}, date={db_date}, lat={lat}, lon={lon}")

print(f"\nTotal DB rows with date in CSV: {matches}")

conn.close()