"""Check if data_quality is being recalculated somewhere."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.database import engine
from sqlalchemy import text

# Check raw data
with engine.connect() as conn:
    result = conn.execute(text("SELECT id, confidence, data_quality FROM hotspots WHERE source = 'nasa_firms' LIMIT 5"))
    for row in result:
        print(f"  id={row[0]}, confidence={row[1]}, data_quality={row[2]}")

    # Check total
    result = conn.execute(text("SELECT COUNT(*) FROM hotspots WHERE source = 'nasa_firms'"))
    print(f"  Total NASA rows: {result.fetchone()[0]}")

    # Check if confidence column exists
    result = conn.execute(text("PRAGMA table_info(hotspots)"))
    print("\n  Hotspot columns:")
    for row in result:
        print(f"    {row[1]} ({row[2]})")

# Check if there's a trigger or view
with engine.connect() as conn:
    result = conn.execute(text("SELECT name FROM sqlite_master WHERE type='trigger'"))
    print("\n  Triggers:")
    for row in result:
        print(f"    {row[0]}")

    result = conn.execute(text("SELECT name FROM sqlite_master WHERE type='view'"))
    print("\n  Views:")
    for row in result:
        print(f"    {row[0]}")