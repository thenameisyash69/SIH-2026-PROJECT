"""Debug: find actual DB file being used."""
import sqlite3, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.config import settings

db_url = settings.database_url
print(f'DATABASE_URL: {db_url}')

db_path = db_url.replace('sqlite:///', '')
print(f'Relative path: {db_path}')
print(f'Absolute: {os.path.abspath(db_path)}')
print(f'Exists: {os.path.exists(db_path)}')
print(f'Size: {os.path.getsize(db_path) if os.path.exists(db_path) else 0}')

# Check for other sih.db files
import glob
for f in glob.glob('**/sih.db', recursive=True):
    print(f'  Found: {f} ({os.path.getsize(f)} bytes)')

# Try connecting and updating
conn = sqlite3.connect(db_path)
c = conn.cursor()
c.execute('SELECT COUNT(*) FROM hotspots WHERE source="nasa_firms"')
print(f'\nTotal NASA rows: {c.fetchone()[0]}')
c.execute('SELECT confidence, COUNT(*) FROM hotspots WHERE source="nasa_firms" GROUP BY confidence ORDER BY confidence')
print('Current distribution:')
for row in c.fetchall():
    print(f'  {row[0]}: {row[1]}')

# Try a direct update on one row
c.execute('UPDATE hotspots SET confidence = 99.0 WHERE id = (SELECT id FROM hotspots WHERE source="nasa_firms" LIMIT 1)')
conn.commit()
print(f'\nRows affected by test update: {c.rowcount}')

# Verify in same connection
c.execute('SELECT confidence FROM hotspots WHERE source="nasa_firms" LIMIT 1')
print(f'After update (same conn): {c.fetchone()}')
conn.close()

# Verify with fresh connection
conn2 = sqlite3.connect(db_path)
c2 = conn2.cursor()
c2.execute('SELECT confidence FROM hotspots WHERE source="nasa_firms" LIMIT 1')
print(f'After update (fresh conn): {c2.fetchone()}')
conn2.close()