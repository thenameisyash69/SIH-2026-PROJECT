"""Debug: test executemany with 13385 rows."""
import sqlite3, os

THIS_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(THIS_DIR, "sih.db")

print(f"DB_PATH: {DB_PATH}")
print(f"DB exists: {os.path.exists(DB_PATH)}")
print(f"DB size: {os.path.getsize(DB_PATH)}")

conn = sqlite3.connect(DB_PATH)
c = conn.cursor()

# Get 13385 NASA row IDs
c.execute('SELECT id FROM hotspots WHERE source="nasa_firms" ORDER BY id LIMIT 13385')
ids = [r[0] for r in c.fetchall()]
print(f"Got {len(ids)} IDs")

# Build updates
updates = [(30.0, hid) for hid in ids]
print(f"Built {len(updates)} updates")

# executemany in batches of 5000
for i in range(0, len(updates), 5000):
    batch = updates[i:i+5000]
    c.executemany("UPDATE hotspots SET confidence = ? WHERE id = ?", batch)
    print(f"  Batch {i//5000 + 1}: {len(batch)} rows, total_affected={c.rowcount}")

conn.commit()

# Verify
c.execute('SELECT COUNT(*) FROM hotspots WHERE source="nasa_firms" AND confidence = 30.0')
print(f"\nAfter update (same conn): {c.fetchone()[0]}")

conn.close()

# Fresh connection
conn2 = sqlite3.connect(DB_PATH)
c2 = conn2.cursor()
c2.execute('SELECT COUNT(*) FROM hotspots WHERE source="nasa_firms" AND confidence = 30.0')
print(f"After update (fresh conn): {c2.fetchone()[0]}")
conn2.close()