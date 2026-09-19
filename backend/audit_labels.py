"""Audit verification records and label distribution - read-only."""
import sqlite3, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

THIS_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(THIS_DIR, "sih.db")

conn = sqlite3.connect(DB_PATH)
c = conn.cursor()

# 1. Total NASA observations
c.execute('SELECT COUNT(*) FROM hotspots WHERE source = "nasa_firms"')
total_nasa = c.fetchone()[0]
print(f"1. Total NASA observations: {total_nasa}")

# 2. Observations with analyst verification
c.execute('''
    SELECT COUNT(DISTINCT v.hotspot_id) 
    FROM verifications v 
    JOIN hotspots h ON v.hotspot_id = h.id 
    WHERE h.source = "nasa_firms"
''')
verified_nasa = c.fetchone()[0]
print(f"2. NASA observations with verification: {verified_nasa}")

# 3. Count by decision
c.execute('''
    SELECT v.decision, COUNT(*) 
    FROM verifications v 
    JOIN hotspots h ON v.hotspot_id = h.id 
    WHERE h.source = "nasa_firms"
    GROUP BY v.decision
    ORDER BY COUNT(*) DESC
''')
print(f"\n3. Verification decisions (NASA only):")
for row in c.fetchall():
    print(f"   {row[0]}: {row[1]}")

# 4. All verifications (including demo)
c.execute('SELECT v.decision, COUNT(*) FROM verifications v GROUP BY v.decision ORDER BY COUNT(*) DESC')
print(f"\n   All verifications (all sources):")
for row in c.fetchall():
    print(f"   {row[0]}: {row[1]}")

# 5. Check verification table structure
c.execute("PRAGMA table_info(verifications)")
print(f"\n   verifications columns: {[r[1] for r in c.fetchall()]}")

# 6. Sample verifications
c.execute('SELECT * FROM verifications LIMIT 5')
cols = [d[0] for d in c.description]
print(f"\n   Sample verifications:")
for row in c.fetchall():
    print(f"   {dict(zip(cols, row))}")

# 7. Check for weak/curated labels
c.execute("SELECT COUNT(*) FROM verifications WHERE decision = 'false_positive'")
fp = c.fetchone()[0]
print(f"\n   false_positive count: {fp}")

# 8. Check if any non-NASA verifications exist
c.execute('''
    SELECT h.source, COUNT(*) 
    FROM verifications v 
    JOIN hotspots h ON v.hotspot_id = h.id 
    GROUP BY h.source
''')
print(f"\n   Verifications by source:")
for row in c.fetchall():
    print(f"   {row[0]}: {row[1]}")

# 9. Check current model artifacts
import glob
models_dir = os.path.join(THIS_DIR, "..", "ml", "models")
models_dir = os.path.abspath(models_dir)
print(f"\n   Models dir: {models_dir}")
print(f"   Exists: {os.path.isdir(models_dir)}")
if os.path.isdir(models_dir):
    for f in sorted(os.listdir(models_dir)):
        print(f"   {f}")

conn.close()