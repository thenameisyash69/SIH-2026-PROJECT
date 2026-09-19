"""Audit highest-risk NASA observation - read-only."""
import sqlite3, os

THIS_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(THIS_DIR, "sih.db")

conn = sqlite3.connect(DB_PATH)
c = conn.cursor()

# List all tables and their columns
c.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
tables = [r[0] for r in c.fetchall()]
print(f"Tables: {tables}")

for t in tables:
    c.execute(f"PRAGMA table_info({t})")
    cols = [r[1] for r in c.fetchall()]
    print(f"  {t}: {cols}")

# Find highest-risk NASA observation
c.execute('''
    SELECT id, lat, lon, brightness, frp, confidence, data_quality,
           baseline_status, z_score, deviation_percentage, persistence_score,
           risk_score, risk_level, category, classification_method,
           classification_confidence, reason, reason_codes, acq_date, source,
           facility_id, distance_to_facility_km, state
    FROM hotspots 
    WHERE source = "nasa_firms"
    ORDER BY risk_score DESC, id ASC
    LIMIT 1
''')
row = c.fetchone()

cols = ['id', 'lat', 'lon', 'brightness', 'frp', 'confidence', 'data_quality',
        'baseline_status', 'z_score', 'deviation_percentage', 'persistence_score',
        'risk_score', 'risk_level', 'category', 'classification_method',
        'classification_confidence', 'reason', 'reason_codes', 'acq_date', 'source',
        'facility_id', 'distance_to_facility_km', 'state']

print("\n" + "=" * 60)
print("HIGHEST-RISK NASA FIRMS OBSERVATION")
print("=" * 60)
for col, val in zip(cols, row):
    print(f"  {col}: {val}")

# Get facility info if associated
if row[20]:  # facility_id
    c.execute('SELECT id, name, state, lat, lon FROM facilities WHERE id = ?', (row[20],))
    fac = c.fetchone()
    if fac:
        print(f"\n  facility_id: {fac[0]}")
        print(f"  facility_name: {fac[1]}")
        print(f"  facility_state: {fac[2]}")
        print(f"  facility_lat: {fac[3]}")
        print(f"  facility_lon: {fac[4]}")

# Get alerts for this observation
c.execute('SELECT * FROM alerts WHERE hotspot_id = ?', (row[0],))
alert_rows = c.fetchall()
if alert_rows:
    alert_cols = [r[1] for r in c.execute("PRAGMA table_info(alerts)")]
    print(f"\n  Alerts ({len(alert_rows)}):")
    for ar in alert_rows:
        for ac, av in zip(alert_cols, ar):
            print(f"    {ac}: {av}")

# Get ingestion run info
c.execute('SELECT * FROM ingestion_runs ORDER BY id DESC LIMIT 1')
ing_rows = c.fetchall()
if ing_rows:
    ing_cols = [r[1] for r in c.execute("PRAGMA table_info(ingestion_runs)")]
    print(f"\n  Latest ingestion run:")
    for ir in ing_rows[:1]:
        for ic, iv in zip(ing_cols, ir):
            print(f"    {ic}: {iv}")

# Get verifications for this observation
c.execute('SELECT * FROM verifications WHERE hotspot_id = ?', (row[0],))
ver_rows = c.fetchall()
if ver_rows:
    ver_cols = [r[1] for r in c.execute("PRAGMA table_info(verifications)")]
    print(f"\n  Verifications ({len(ver_rows)}):")
    for vr in ver_rows:
        for vc, vv in zip(ver_cols, vr):
            print(f"    {vc}: {vv}")

conn.close()