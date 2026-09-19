"""Debug: check table schema and test bulk update."""
import sqlite3, os

THIS_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(THIS_DIR, "sih.db")

conn = sqlite3.connect(DB_PATH)
c = conn.cursor()

# Check schema
c.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='hotspots'")
print("Table schema:")
print(c.fetchone()[0])

# Check for triggers
c.execute("SELECT sql FROM sqlite_master WHERE type='trigger'")
print("\nTriggers:")
for row in c.fetchall():
    print(f"  {row[0]}")

# Check current state
c.execute('SELECT confidence, COUNT(*) FROM hotspots WHERE source="nasa_firms" GROUP BY confidence ORDER BY confidence')
print("\nCurrent distribution:")
for row in c.fetchall():
    print(f"  {row[0]}: {row[1]}")

# Try a bulk update with a simple WHERE
c.execute("UPDATE hotspots SET confidence = 30.0 WHERE source='nasa_firms' AND confidence = 77.0")
conn.commit()
print(f"\nBulk update rows affected: {c.rowcount}")

c.execute('SELECT confidence, COUNT(*) FROM hotspots WHERE source="nasa_firms" GROUP BY confidence ORDER BY confidence')
print("After bulk update:")
for row in c.fetchall():
    print(f"  {row[0]}: {row[1]}")

conn.close()