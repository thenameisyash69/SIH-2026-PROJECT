"""Debug: test raw sqlite3 update persistence."""
import sqlite3, os

THIS_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(THIS_DIR, "sih.db")

print(f"DB_PATH: {DB_PATH}")
print(f"Exists: {os.path.exists(DB_PATH)}")
print(f"Size: {os.path.getsize(DB_PATH)}")

# Check journal mode
conn = sqlite3.connect(DB_PATH)
c = conn.cursor()
c.execute("PRAGMA journal_mode")
print(f"Journal mode: {c.fetchone()[0]}")

# Check current state
c.execute('SELECT confidence, COUNT(*) FROM hotspots WHERE source="nasa_firms" GROUP BY confidence ORDER BY confidence')
print("Before update:")
for row in c.fetchall():
    print(f"  {row[0]}: {row[1]}")

# Try updating 3 rows
c.execute('SELECT id FROM hotspots WHERE source="nasa_firms" LIMIT 3')
ids = [r[0] for r in c.fetchall()]
print(f"\nUpdating IDs: {ids}")

for hid in ids:
    c.execute("UPDATE hotspots SET confidence = 55.0 WHERE id = ?", (hid,))
    print(f"  Updated id={hid}, rows_affected={c.rowcount}")

conn.commit()

# Verify in same connection
c.execute('SELECT id, confidence FROM hotspots WHERE id IN (?,?,?)', ids)
print(f"After update (same conn): {c.fetchall()}")

conn.close()

# Verify with fresh connection
conn2 = sqlite3.connect(DB_PATH)
c2 = conn2.cursor()
c2.execute('SELECT id, confidence FROM hotspots WHERE id IN (?,?,?)', ids)
print(f"After update (fresh conn): {c2.fetchall()}")
conn2.close()