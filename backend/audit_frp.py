"""Audit NASA FIRMS FRP values - read-only."""
import sqlite3, os, statistics

THIS_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(THIS_DIR, "sih.db")

conn = sqlite3.connect(DB_PATH)
c = conn.cursor()

# 1. Count with FRP available
c.execute('SELECT COUNT(*) FROM hotspots WHERE source = "nasa_firms" AND frp IS NOT NULL')
total_with_frp = c.fetchone()[0]
c.execute('SELECT COUNT(*) FROM hotspots WHERE source = "nasa_firms"')
total_nasa = c.fetchone()[0]
print(f"1. NASA observations with FRP: {total_with_frp} / {total_nasa} ({total_with_frp/total_nasa*100:.1f}%)")

# 2. Percentiles
c.execute('SELECT frp FROM hotspots WHERE source = "nasa_firms" AND frp IS NOT NULL ORDER BY frp')
frps = [r[0] for r in c.fetchall()]
n = len(frps)
frps_sorted = sorted(frps)

def pct(arr, p):
    k = (len(arr) - 1) * p / 100
    f = int(k)
    c2 = f + 1 if f + 1 < len(arr) else f
    return arr[f] + (arr[c2] - arr[f]) * (k - f)

print(f"\n2. FRP distribution:")
print(f"   min:    {frps_sorted[0]:.2f}")
print(f"   median: {pct(frps_sorted, 50):.2f}")
print(f"   mean:   {statistics.mean(frps):.2f}")
print(f"   P75:    {pct(frps_sorted, 75):.2f}")
print(f"   P90:    {pct(frps_sorted, 90):.2f}")
print(f"   P95:    {pct(frps_sorted, 95):.2f}")
print(f"   P99:    {pct(frps_sorted, 99):.2f}")
print(f"   max:    {frps_sorted[-1]:.2f}")

# 3. Distribution by facility
print(f"\n3. FRP by facility:")
c.execute('''
    SELECT h.facility_id, f.name, COUNT(*), MIN(h.frp), AVG(h.frp), MAX(h.frp)
    FROM hotspots h
    LEFT JOIN facilities f ON h.facility_id = f.id
    WHERE h.source = "nasa_firms" AND h.frp IS NOT NULL
    GROUP BY h.facility_id
    ORDER BY COUNT(*) DESC
''')
for row in c.fetchall():
    fid, fname, cnt, mn, avg, mx = row
    fname = fname or 'unmatched'
    print(f"   facility_id={fid}, name={fname}, count={cnt}, min={mn:.2f}, avg={avg:.2f}, max={mx:.2f}")

# 4. FRP bands
bands = {'<5': 0, '5-10': 0, '10-20': 0, '20-50': 0, '>=50': 0}
c.execute('SELECT frp FROM hotspots WHERE source = "nasa_firms" AND frp IS NOT NULL')
for (frp,) in c:
    if frp < 5:
        bands['<5'] += 1
    elif frp < 10:
        bands['5-10'] += 1
    elif frp < 20:
        bands['10-20'] += 1
    elif frp < 50:
        bands['20-50'] += 1
    else:
        bands['>=50'] += 1

print(f"\n4. FRP band distribution:")
for band, cnt in bands.items():
    print(f"   {band} MW: {cnt} ({cnt/total_with_frp*100:.1f}%)")

# 5. What fraction exceeds 10 MW
c.execute('SELECT COUNT(*) FROM hotspots WHERE source = "nasa_firms" AND frp IS NOT NULL AND frp >= 10')
ge10 = c.fetchone()[0]
print(f"\n5. FRP >= 10 MW: {ge10} ({ge10/total_with_frp*100:.1f}%)")
print(f"   FRP < 10 MW: {total_with_frp - ge10} ({(total_with_frp-ge10)/total_with_frp*100:.1f}%)")

conn.close()