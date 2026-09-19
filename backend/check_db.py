import sqlite3

c = sqlite3.connect("sih.db")

facilities = c.execute(
    "SELECT COUNT(*) FROM facilities"
).fetchone()[0]

demo = c.execute(
    "SELECT COUNT(*) FROM hotspots WHERE source='demo_synthetic'"
).fetchone()[0]

nasa = c.execute(
    "SELECT COUNT(*) FROM hotspots WHERE source='nasa_firms'"
).fetchone()[0]

total = c.execute(
    "SELECT COUNT(*) FROM hotspots"
).fetchone()[0]

print("FACILITIES:", facilities)
print("DEMO:", demo)
print("NASA:", nasa)
print("TOTAL:", total)

c.close()