"""Debug: test raw sqlite3 update persistence with batched commits."""
import sqlite3, os

THIS_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(THIS_DIR, "sih.db")

print(f"DB_PATH: {DB_PATH}")

# Check for WAL/journal files
for ext in ['.db', '.db-wal', '.db-shm', '.db-journal']:
    f = DB_PATH.replace('.db', ext)
    print(f"  {ext}: exists={os.path.exists(f)}, size={os.path.getsize(f) if os.path.exists(f) else 0}")

conn = sqlite3.connect(DB_PATH)
c = conn.cursor()

# Check journal mode
c.execute("PRAGMA journal_mode")
print(f"Journal mode: {c.fetchone()[0]}")

# Check current state
c.execute('SELECT confidence, COUNT(*) FROM hotspots WHERE source="nasa_firms" GROUP BY confidence ORDER BY confidence')
print("Before update:")
for row in c.fetchall():
    print(f"  {row[0]}: {row[1]}")

# Try updating 1000 rows with batched commits
c.execute('SELECT id FROM hotspots WHERE source="nasa_firms" LIMIT 1000')
ids = [r[0] for r in c.fetchall()]
print(f"\nUpdating {len(ids)} rows...")

for i, hid in enumerate(ids):
    c.execute("UPDATE hotspots SET confidence = 77.0 WHERE id = ?", (hid,))
    if (i + 1) % 100 == 0:
        conn.commit()

conn.commit()

# Verify in same connection
c.execute('SELECT COUNT(*) FROM hotspots WHERE source="nasa_firms" AND confidence = 77.0')
print(f"After update (same conn): {c.fetchone()[0]}")

conn.close()

# Verify with fresh connection
conn2 = sqlite3.connect(DB_PATH)
c2 = conn2.cursor()
c2.execute('SELECT COUNT(*) FROM hotspots WHERE source="nasa_firms" AND confidence = 77.0')
print(f"After update (fresh conn): {c2.fetchone()[0]}")

# Check WAL file
for ext in ['.db-wal', '.db-shm']:
    f = DB_PATH.replace('.db', ext)
    print(f"  {ext}: exists={os.path.exists(f)}, size={os.path.getsize(f) if os.path.exists(f) else 0}")

conn2.close()