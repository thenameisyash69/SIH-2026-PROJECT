"""Debug: check why lookup keys don't match DB rows."""
import sys, os, csv
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from sqlalchemy import create_engine, text
from app.config import settings
from datetime import datetime

ARCHIVE_CSV = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data", "firms_archive", "firms_90day_india.csv",
)

engine = create_engine(settings.database_url)

# Check first few CSV rows
print("=== CSV Sample ===")
with open(ARCHIVE_CSV, newline="") as f:
    reader = csv.DictReader(f)
    for i, row in enumerate(reader):
        if i >= 3:
            break
        lat = round(float(row["latitude"]), 4)
        lon = round(float(row["longitude"]), 4)
        acq_date = datetime.strptime(row["acq_date"], "%Y-%m-%d")
        if row.get("acq_time"):
            t = str(row["acq_time"]).zfill(4)
            acq_date = acq_date.replace(hour=int(t[:2]), minute=int(t[2:]))
        print(f"  CSV: lat={lat}, lon={lon}, acq_date={acq_date}, type={type(acq_date)}")

# Check first few DB rows
print("\n=== DB Sample ===")
with engine.connect() as conn:
    result = conn.execute(text("SELECT id, lat, lon, acq_date, confidence FROM hotspots WHERE source = 'nasa_firms' LIMIT 5"))
    for row in result:
        print(f"  DB: id={row[0]}, lat={round(float(row[1]),4)}, lon={round(float(row[2]),4)}, acq_date={row[3]}, type={type(row[3])}")

# Try matching
print("\n=== Match Test ===")
with open(ARCHIVE_CSV, newline="") as f:
    reader = csv.DictReader(f)
    row = next(reader)
    lat = round(float(row["latitude"]), 4)
    lon = round(float(row["longitude"]), 4)
    acq_date = datetime.strptime(row["acq_date"], "%Y-%m-%d")
    if row.get("acq_time"):
        t = str(row["acq_time"]).zfill(4)
        acq_date = acq_date.replace(hour=int(t[:2]), minute=int(t[2:]))

print(f"Looking for: ({lat}, {lon}, {acq_date})")

with engine.connect() as conn:
    result = conn.execute(text(
        "SELECT id, lat, lon, acq_date FROM hotspots WHERE source = 'nasa_firms' AND lat = :lat AND lon = :lon"
    ), {"lat": lat, "lon": lon})
    db_rows = result.fetchall()
    print(f"Found {len(db_rows)} DB rows with matching lat/lon")
    for db_row in db_rows:
        print(f"  DB: id={db_row[0]}, acq_date={db_row[3]}, type={type(db_row[3])}")
        # Compare
        db_acq = db_row[3]
        if hasattr(db_acq, 'replace'):
            db_acq_cmp = db_acq
        else:
            db_acq_cmp = db_acq
        print(f"  Match: {db_acq_cmp == acq_date}")
        if hasattr(db_acq_cmp, 'year'):
            print(f"  DB year={db_acq_cmp.year}, month={db_acq_cmp.month}, day={db_acq_cmp.day}, hour={db_acq_cmp.hour}, minute={db_acq_cmp.minute}")
            print(f"  CSV year={acq_date.year}, month={acq_date.month}, day={acq_date.day}, hour={acq_date.hour}, minute={acq_date.minute}")