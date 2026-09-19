"""Reset test confidence values back to 0.0."""
import sqlite3, os

THIS_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(THIS_DIR, "sih.db")

conn = sqlite3.connect(DB_PATH)
c = conn.cursor()

# Reset test values
c.execute("UPDATE hotspots SET confidence = 0.0 WHERE confidence != 0.0")
conn.commit()
print(f"Rows reset: {c.rowcount}")

# Verify
c.execute('SELECT confidence, COUNT(*) FROM hotspots WHERE source="nasa_firms" GROUP BY confidence ORDER BY confidence')
for row in c.fetchall():
    print(f"  confidence={row[0]}: {row[1]} rows")

conn.close()