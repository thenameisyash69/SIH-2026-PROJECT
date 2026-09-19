"""Debug: check CSV confidence column values."""
import csv, os
from collections import Counter

THIS_DIR = os.path.dirname(os.path.abspath(__file__))
BACKEND_DIR = os.path.dirname(THIS_DIR)
ARCHIVE_CSV = os.path.join(BACKEND_DIR, "data", "firms_archive", "firms_90day_india.csv")

with open(ARCHIVE_CSV, newline="") as f:
    reader = csv.DictReader(f)
    print(f"Columns: {reader.fieldnames}")
    
    conf_values = Counter()
    sample_rows = []
    for i, row in enumerate(reader):
        conf = row.get("confidence", "MISSING")
        conf_values[conf] += 1
        if i < 5:
            sample_rows.append(row)

print(f"\nConfidence value distribution (first 20):")
for val, cnt in conf_values.most_common(20):
    print(f"  '{val}': {cnt}")

print(f"\nTotal unique confidence values: {len(conf_values)}")
print(f"\nSample rows:")
for row in sample_rows:
    print(f"  {row}")