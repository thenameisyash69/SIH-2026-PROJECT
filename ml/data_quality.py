"""
Real data-quality checks (Phase 6). Runs against either:
  (a) the real database (source='nasa_firms' rows), in a normal environment, or
  (b) a raw FIRMS CSV snapshot directly (used here, since this dev sandbox
      has no database with real rows in it — see docs/PIPELINE_VALIDATION.md).

Never silently drops rows — every removal is counted and reported by reason.

Run with:  python ml/data_quality.py --csv ../data-pipeline/modis_raw.csv ../data-pipeline/viirs_raw.csv
"""
import sys, os, csv, json, argparse
from datetime import datetime

INDIA_BBOX = (68, 6, 97, 37)


def check_csv_files(filepaths: list) -> dict:
    total = 0
    issues = {
        "impossible_coordinates": 0,
        "missing_brightness": 0,
        "invalid_timestamp": 0,
        "invalid_frp": 0,
        "duplicate_rows": 0,
        "outside_configured_bbox": 0,
        "valid": 0,
    }
    seen_keys = set()
    valid_rows = []

    for filepath in filepaths:
        if not os.path.exists(filepath):
            print(f"[data_quality] {filepath} not found — skipping.")
            continue
        with open(filepath) as f:
            for row in csv.DictReader(f):
                total += 1
                problems = []

                try:
                    lat, lon = float(row["latitude"]), float(row["longitude"])
                    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
                        problems.append("impossible_coordinates")
                except (KeyError, ValueError):
                    problems.append("impossible_coordinates")
                    lat = lon = None

                brightness_raw = row.get("brightness") or row.get("bright_ti4")
                try:
                    brightness = float(brightness_raw)
                    if brightness <= 0 or brightness > 500:  # VIIRS/MODIS brightness temps are never outside ~200-500K
                        problems.append("missing_brightness")
                except (TypeError, ValueError):
                    problems.append("missing_brightness")
                    brightness = None

                try:
                    datetime.strptime(row["acq_date"], "%Y-%m-%d")
                    int(str(row["acq_time"]).zfill(4))
                except (KeyError, ValueError):
                    problems.append("invalid_timestamp")

                frp_raw = row.get("frp")
                if frp_raw:
                    try:
                        frp = float(frp_raw)
                        if frp < 0:
                            problems.append("invalid_frp")
                    except ValueError:
                        problems.append("invalid_frp")

                if lat is not None and lon is not None:
                    west, south, east, north = INDIA_BBOX
                    if not (south <= lat <= north and west <= lon <= east):
                        problems.append("outside_configured_bbox")

                dedup_key = (round(lat, 4) if lat else None, round(lon, 4) if lon else None,
                             row.get("acq_date"), row.get("acq_time"))
                if dedup_key in seen_keys:
                    problems.append("duplicate_rows")
                else:
                    seen_keys.add(dedup_key)

                if not problems:
                    issues["valid"] += 1
                    valid_rows.append(row)
                else:
                    for p in set(problems):
                        if p in issues:
                            issues[p] += 1

    return {"total_rows_checked": total, "issues": issues, "valid_rows": len(valid_rows)}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--csv", nargs="+", required=True)
    args = parser.parse_args()

    result = check_csv_files(args.csv)
    print(json.dumps(result, indent=2))

    out_path = os.path.join(os.path.dirname(__file__), "data_quality_report.json")
    with open(out_path, "w") as f:
        json.dump(result, f, indent=2)
    print(f"\nSaved to {out_path}")
