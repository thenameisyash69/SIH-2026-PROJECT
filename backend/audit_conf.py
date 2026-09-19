"""Audit NASA confidence distribution - read-only."""
import sqlite3, os

THIS_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(THIS_DIR, "sih.db")

conn = sqlite3.connect(DB_PATH)
c = conn.cursor()

# 1. Raw/normalized confidence counts
print("=" * 60)
print("1. RAW/NORMALIZED CONFIDENCE COUNTS")
print("=" * 60)
c.execute('''
    SELECT confidence, COUNT(*) 
    FROM hotspots 
    WHERE source = "nasa_firms" 
    GROUP BY confidence 
    ORDER BY confidence
''')
total = 0
for row in c.fetchall():
    total += row[1]
    print(f"  confidence={row[0]}: {row[1]} rows")

print(f"  TOTAL: {total} rows")

# 2. Per-confidence breakdown
print("\n" + "=" * 60)
print("2. PER-CONFIDENCE BREAKDOWN")
print("=" * 60)
for conf in [30.0, 60.0, 90.0]:
    c.execute('''
        SELECT COUNT(*) FROM hotspots 
        WHERE source = "nasa_firms" AND confidence = ?
    ''', (conf,))
    cnt = c.fetchone()[0]
    pct = (cnt / total) * 100 if total else 0
    
    # data_quality distribution
    c.execute('''
        SELECT data_quality, COUNT(*) FROM hotspots 
        WHERE source = "nasa_firms" AND confidence = ?
        GROUP BY data_quality ORDER BY data_quality
    ''', (conf,))
    dq_dist = {row[0]: row[1] for row in c.fetchall()}
    
    # avg and max risk_score
    c.execute('''
        SELECT AVG(risk_score), MAX(risk_score) FROM hotspots 
        WHERE source = "nasa_firms" AND confidence = ?
    ''', (conf,))
    avg_risk, max_risk = c.fetchone()
    
    print(f"\n  confidence={conf} ({cnt} rows, {pct:.1f}%)")
    print(f"    data_quality: {dq_dist}")
    print(f"    avg risk_score: {avg_risk:.4f}")
    print(f"    max risk_score: {max_risk}")

# 3. 10 highest-risk NASA observations
print("\n" + "=" * 60)
print("3. 10 HIGHEST-RISK NASA OBSERVATIONS")
print("=" * 60)
c.execute('''
    SELECT id, brightness, frp, confidence, data_quality, 
           baseline_status, risk_score, risk_level, is_anomaly
    FROM hotspots 
    WHERE source = "nasa_firms"
    ORDER BY risk_score DESC, id ASC
    LIMIT 10
''')
cols = ['id', 'brightness', 'frp', 'confidence', 'data_quality', 
        'baseline_status', 'risk_score', 'risk_level', 'is_anomaly']
for row in c.fetchall():
    print(f"\n  id={row[0]}")
    print(f"    brightness={row[1]}, frp={row[2]}, confidence={row[3]}")
    print(f"    data_quality={row[4]}, baseline_status={row[5]}")
    print(f"    risk_score={row[6]}, risk_level={row[7]}, is_anomaly={row[8]}")

conn.close()