"""Audit facility criticality for Jamnagar Refinery - read-only."""
import sqlite3, os

THIS_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(THIS_DIR, "sih.db")

conn = sqlite3.connect(DB_PATH)
c = conn.cursor()

# Check facility criticality
c.execute('SELECT id, name, type, state, criticality, source, source_id FROM facilities WHERE id = 1')
fac = c.fetchone()
print(f"Facility: {fac}")

# Check all facilities and their criticality values
c.execute('SELECT id, name, criticality FROM facilities ORDER BY criticality DESC, id')
print("\nAll facilities:")
for row in c.fetchall():
    print(f"  id={row[0]}, name={row[1]}, criticality={row[2]}")

# Check all columns in hotspots for 18275
c.execute('SELECT * FROM hotspots WHERE id = 18275')
cols = [d[0] for d in c.description]
row = c.fetchone()
print(f"\nHotspot 18275 full record:")
for col, val in zip(cols, row):
    print(f"  {col}: {val}")

conn.close()