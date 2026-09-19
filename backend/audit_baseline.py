"""Audit baseline sufficiency for NASA FIRMS observations - read-only."""
import sqlite3, os
from collections import defaultdict

THIS_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(THIS_DIR, "sih.db")

conn = sqlite3.connect(DB_PATH)
c = conn.cursor()

# 1. Count of observations per facility (NASA only)
print("=" * 60)
print("1. NASA OBSERVATIONS PER FACILITY")
print("=" * 60)
c.execute('''
    SELECT h.facility_id, f.name, COUNT(*) as cnt
    FROM hotspots h
    JOIN facilities f ON h.facility_id = f.id
    WHERE h.source = "nasa_firms"
    GROUP BY h.facility_id
    ORDER BY cnt DESC
''')
facility_obs_counts = {}
for row in c.fetchall():
    facility_obs_counts[row[0]] = row[2]
    print(f"  facility_id={row[0]}, name={row[1]}, obs_count={row[2]}")

# 2. Unique active days per facility (NASA only)
print("\n" + "=" * 60)
print("2. UNIQUE ACTIVE DAYS PER FACILITY")
print("=" * 60)
c.execute('''
    SELECT h.facility_id, f.name, h.acq_date
    FROM hotspots h
    JOIN facilities f ON h.facility_id = f.id
    WHERE h.source = "nasa_firms"
    ORDER BY h.facility_id, h.acq_date
''')
facility_days = defaultdict(set)
for fid, fname, acq in c.fetchall():
    if hasattr(acq, 'strftime'):
        d = acq.strftime("%Y-%m-%d")
    elif isinstance(acq, str):
        d = acq.split(' ')[0]
    else:
        d = str(acq).split(' ')[0]
    facility_days[fid].add(d)

for fid in sorted(facility_days):
    c.execute('SELECT name FROM facilities WHERE id = ?', (fid,))
    fname = c.fetchone()[0]
    days = len(facility_days[fid])
    obs_count = facility_obs_counts.get(fid, 0)
    print(f"  facility_id={fid}, name={fname}, unique_days={days}, obs_count={obs_count}")

# 3. baseline_status distribution per facility
print("\n" + "=" * 60)
print("3. BASELINE_STATUS DISTRIBUTION PER FACILITY")
print("=" * 60)
c.execute('''
    SELECT h.facility_id, f.name, h.baseline_status, COUNT(*) as cnt
    FROM hotspots h
    JOIN facilities f ON h.facility_id = f.id
    WHERE h.source = "nasa_firms"
    GROUP BY h.facility_id, h.baseline_status
    ORDER BY h.facility_id, h.baseline_status
''')
facility_status = defaultdict(dict)
for fid, fname, status, cnt in c.fetchall():
    facility_status[fid][status] = cnt

for fid in sorted(facility_status):
    c.execute('SELECT name FROM facilities WHERE id = ?', (fid,))
    fname = c.fetchone()[0]
    print(f"  facility_id={fid}, name={fname}: {facility_status[fid]}")

# 4. ABNORMAL or ELEVATED observations
print("\n" + "=" * 60)
print("4. ABNORMAL/ELEVATED NASA OBSERVATIONS")
print("=" * 60)
c.execute('''
    SELECT h.id, h.facility_id, f.name, h.baseline_status, h.z_score, 
           h.deviation_percentage, h.acq_date
    FROM hotspots h
    JOIN facilities f ON h.facility_id = f.id
    WHERE h.source = "nasa_firms" 
      AND h.baseline_status IN ("ABNORMAL", "ELEVATED")
    ORDER BY h.risk_score DESC
''')
abnormal_rows = c.fetchall()
print(f"  Total ABNORMAL/ELEVATED: {len(abnormal_rows)}")
for hid, fid, fname, status, z, dev, acq in abnormal_rows:
    obs_count = facility_obs_counts.get(fid, 0)
    days = len(facility_days.get(fid, set()))
    print(f"  id={hid}, facility={fname}, obs_count={obs_count}, unique_days={days}, "
          f"z={z}, dev={dev}%, status={status}")

# 5. Check for ABNORMAL/ELEVATED with < 8 unique active days
print("\n" + "=" * 60)
print("5. ABNORMAL/ELEVATED WITH < 8 UNIQUE ACTIVE DAYS")
print("=" * 60)
flagged = []
for hid, fid, fname, status, z, dev, acq in abnormal_rows:
    days = len(facility_days.get(fid, set()))
    if days < 8:
        flagged.append((hid, fname, days, status, z, dev))

if flagged:
    print(f"  FLAGGED: {len(flagged)} observations with < 8 unique active days:")
    for hid, fname, days, status, z, dev in flagged:
        print(f"    id={hid}, facility={fname}, unique_days={days}, status={status}, z={z}, dev={dev}%")
else:
    print("  None found. All ABNORMAL/ELEVATED observations have >= 8 unique active days.")

# Also check: which facilities have >= 8 obs but < 8 unique days
print("\n" + "=" * 60)
print("6. FACILITIES WITH >= 8 OBS BUT < 8 UNIQUE DAYS")
print("=" * 60)
for fid in sorted(facility_days):
    days = len(facility_days[fid])
    obs_count = facility_obs_counts.get(fid, 0)
    if obs_count >= 8 and days < 8:
        c.execute('SELECT name FROM facilities WHERE id = ?', (fid,))
        fname = c.fetchone()[0]
        print(f"  facility_id={fid}, name={fname}, obs_count={obs_count}, unique_days={days}")

conn.close()