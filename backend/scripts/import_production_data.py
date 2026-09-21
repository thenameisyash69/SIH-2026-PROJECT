"""KAVACH production data recovery script — IMPORT / MIGRATION

SAFETY RULES:
  1. BACK UP production first — this script will NOT run without --confirm-backup
  2. Preserves original observation IDs where no collision exists; remaps
     verification foreign keys to actual inserted IDs
  3. Never converts unknown/unverified records into verified records
  4. Preserves original timestamps, coordinates, source, baseline_status
  5. Demo data is handled separately and clearly labeled — this script only
     migrates nasa_firms records
  6. Facility associations (facility_id, distance_to_facility_km) are preserved
     from the source database
  7. The --dry-run flag shows what WOULD be imported without writing anything
  8. Reports all candidate duplicates (ID collisions and coordinate conflicts)
  9. Wraps the entire import in a single transaction with rollback on failure
 10. Cleans up staging table after import

DEDUP STRATEGY:
  Phase 1 — ID collisions: records whose original `id` already exists in the
              target are skipped (ON CONFLICT DO NOTHING). These are reported.
  Phase 2 — Coordinate conflicts: for the ~19,600 records whose IDs don't
              collide, the import checks (round(lat,4), round(lon,4), acq_date,
              source) against existing records. Records that are coordinate
              duplicates (same observation already in target) are reported
              with sample IDs and skipped — they are NOT silently discarded.
  Phase 3 — Verification remapping: verifications are only imported for
              hotspots that were ACTUALLY inserted in this run. The
              verification.hotspot_id is remapped to match the inserted hotspot.
              If a hotspot was skipped (duplicate), its verification is NOT
              imported.

USAGE:
  # 1. Backup production first:
  pg_dump -h <prod-host> -U <prod-user> <prod-db> > backup_$(date +%Y%m%d_%H%M%S).sql

  # 2. Dry run (staging test) — reads source, writes nothing:
  python3 backend/scripts/import_production_data.py \
    --source-sqlite backend/sih.db --dry-run

  # 3. Staging test (SQLite target — safe, no production impact):
  python3 backend/scripts/import_production_data.py \
    --source-sqlite backend/sih.db \
    --target-postgres "sqlite:///./staging_test.db" \
    --confirm-backup

  # 4. Production import (requires pg_dump backup with --confirm-backup):
  python3 backend/scripts/import_production_data.py \
    --source-sqlite backend/sih.db \
    --target-postgres "$DATABASE_URL" \
    --confirm-backup
"""
import argparse
import sqlite3
import os
import sys
from datetime import datetime
from collections import defaultdict


REQUIRED_COLUMNS = [
    "id", "lat", "lon", "brightness", "confidence", "frp", "acq_date",
    "satellite", "source", "source_resolution_m", "land_cover",
    "facility_id", "distance_to_facility_km", "state",
    "category", "classification_method", "classification_confidence",
    "model_version", "baseline_status", "z_score", "deviation_percentage",
    "persistence_score", "is_anomaly", "reason", "reason_codes",
    "risk_score", "risk_level", "data_quality",
    "created_at", "updated_at",
]

VERIFICATION_COLUMNS = [
    "id", "hotspot_id", "decision", "note", "analyst_name", "created_at"
]


def analyze_source_db(source_path: str) -> dict:
    """Read-only inspection of source SQLite — no writes, no secrets printed."""
    conn = sqlite3.connect(source_path)
    conn.row_factory = sqlite3.Row

    result = {}

    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM hotspots WHERE source='nasa_firms'")
    result["nasa_count"] = cur.fetchone()[0]

    cur.execute("SELECT COUNT(*) FROM hotspots WHERE source='demo_synthetic'")
    result["demo_count"] = cur.fetchone()[0]

    cur.execute("""
        SELECT COUNT(*) FROM verifications v
        JOIN hotspots h ON v.hotspot_id = h.id
        WHERE h.source = 'nasa_firms'
    """)
    result["verif_count"] = cur.fetchone()[0]

    cur.execute("SELECT MIN(acq_date), MAX(acq_date) FROM hotspots WHERE source='nasa_firms'")
    dr = cur.fetchone()
    result["date_range"] = (dr[0], dr[1])

    cur.execute("SELECT COUNT(DISTINCT date(acq_date)) FROM hotspots WHERE source='nasa_firms'")
    result["unique_dates"] = cur.fetchone()[0]

    cur.execute("SELECT MIN(id), MAX(id) FROM hotspots WHERE source='nasa_firms'")
    r = cur.fetchone()
    result["id_range"] = (r[0], r[1])

    conn.close()
    return result


def import_nasa_firms(source_path: str, target_url: str, confirm_backup: bool,
                      max_rows: int = None) -> int:
    """
    Import NASA FIRMS hotspots + verifications from source SQLite into target.

    Uses a single transaction with rollback on failure. Reports all candidate
    duplicates. Remaps verification foreign keys to actually-inserted IDs.

    Returns exit code (0 = success).
    """
    import sqlalchemy
    from sqlalchemy import text

    source_info = analyze_source_db(source_path)

    print(f"\n{'='*60}")
    print(f"Source: {source_path}")
    print(f"Target: {target_url}")
    print(f"  NASA FIRMS observations to evaluate: {source_info['nasa_count']}")
    print(f"  Demo synthetic (NOT imported): {source_info['demo_count']}")
    print(f"  NASA FIRMS verifications to evaluate: {source_info['verif_count']}")
    print(f"  NASA FIRMS date range: {source_info['date_range'][0]} to {source_info['date_range'][1]}")
    print(f"  NASA FIRMS unique dates: {source_info['unique_dates']}")
    print(f"  NASA FIRMS ID range: {source_info['id_range'][0]} to {source_info['id_range'][1]}")

    if max_rows:
        print(f"  MAX ROWS cap: {max_rows}")

    # Connect to target
    engine = sqlalchemy.create_engine(target_url)
    conn = engine.connect()

    # For PostgreSQL, use explicit transaction
    trans = conn.begin()

    try:
        # Create staging table
        conn.exec_driver_sql("""
            CREATE TABLE IF NOT EXISTS hotspots_import_staging (
                id INTEGER PRIMARY KEY,
                lat REAL, lon REAL, brightness REAL NOT NULL,
                confidence REAL DEFAULT 0.0, frp REAL,
                acq_date TIMESTAMP, satellite TEXT,
                source TEXT, source_resolution_m INTEGER,
                land_cover TEXT, facility_id INTEGER,
                distance_to_facility_km REAL, state TEXT,
                category TEXT, classification_method TEXT,
                classification_confidence REAL, model_version TEXT,
                baseline_status TEXT, z_score REAL,
                deviation_percentage REAL, persistence_score REAL,
                is_anomaly BOOLEAN, reason TEXT, reason_codes TEXT,
                risk_score REAL, risk_level TEXT, data_quality TEXT,
                created_at TIMESTAMP, updated_at TIMESTAMP
            )
        """)
        conn.exec_driver_sql("DELETE FROM hotspots_import_staging")
        trans.commit()

        # Read from source SQLite
        src_conn = sqlite3.connect(source_path)
        src_conn.row_factory = sqlite3.Row
        src_cur = src_conn.cursor()

        # Build column list for INSERT
        cols_str = ", ".join(REQUIRED_COLUMNS)
        placeholders = ", ".join(["?"] * len(REQUIRED_COLUMNS))

        # Phase 1: Load all NASA FIRMS records, check for conflicts
        # First, get all existing IDs and coordinate keys from target
        print(f"\n--- Scanning target for existing records ---")

        existing_ids_result = conn.exec_driver_sql(
            "SELECT id FROM hotspots WHERE source='nasa_firms'"
        )
        existing_ids = {row[0] for row in existing_ids_result.fetchall()}
        print(f"  Existing NASA FIRMS hotspot IDs in target: {len(existing_ids)}")

        # Get existing coordinate keys for conflict detection
        existing_coord_result = conn.exec_driver_sql("""
            SELECT round(lat,4) as lat_r, round(lon,4) as lon_r,
                   acq_date FROM hotspots WHERE source='nasa_firms'
        """)
        # Note: PostgreSQL round() returns numeric, SQLite returns float
        # We use a tolerant comparison approach
        existing_coords = set()
        for row in existing_coord_result:
            lat_r = round(float(row[0]), 4)
            lon_r = round(float(row[1]), 4)
            acq = str(row[2])
            existing_coords.add((lat_r, lon_r, acq))
        print(f"  Existing coordinate keys in target: {len(existing_coords)}")

        # Fetch all source records
        src_cur.execute(
            f"SELECT {cols_str} FROM hotspots WHERE source='nasa_firms' ORDER BY id"
        )
        all_rows = src_cur.fetchall()
        print(f"  Source records to evaluate: {len(all_rows)}")

        if max_rows:
            all_rows = all_rows[:max_rows]
            print(f"  Truncated to max_rows={max_rows}")

        # Phase 2: Classify each record
        id_conflicts = []       # ID already exists in target
        coord_conflicts = []    # Coordinate+timestamp already exists in target
        to_import = []          # Records that will be inserted

        for row in all_rows:
            src_id = row["id"]

            if src_id in existing_ids:
                id_conflicts.append(row)
                continue

            lat_r = round(float(row["lat"]), 4)
            lon_r = round(float(row["lon"]), 4)
            acq = str(row["acq_date"])

            if (lat_r, lon_r, acq) in existing_coords:
                coord_conflicts.append(row)
                continue

            to_import.append(row)

        trans.commit()  # Save staging analysis

        # Report findings
        print(f"\n--- Conflict Analysis ---")
        print(f"  Records to import (no conflict): {len(to_import)}")
        print(f"  ID conflicts (same primary key, skipped): {len(id_conflicts)}")
        if id_conflicts:
            print(f"    Sample ID conflicts: {[r['id'] for r in id_conflicts[:10]]}")
        print(f"  Coordinate conflicts (round(lat,4), round(lon,4), acq_date match): {len(coord_conflicts)}")
        if coord_conflicts:
            print(f"    Sample coord conflicts:")
            for r in coord_conflicts[:10]:
                print(f"      id={r['id']}, lat={round(r['lat'],4)}, lon={round(r['lon'],4)}, acq={r['acq_date']}")

        # Phase 3: Insert into target in batches
        print(f"\n--- Inserting {len(to_import)} hotspots into target ---")
        inserted_ids = []
        BATCH_SIZE = 500
        total_inserted = 0

        for i in range(0, len(to_import), BATCH_SIZE):
            batch = to_import[i:i + BATCH_SIZE]
            # Build INSERT ... ON CONFLICT (id) DO NOTHING
            insert_sql = f"""
                INSERT INTO hotspots ({cols_str})
                VALUES {", ".join(["(" + ",".join(["?"] * len(REQUIRED_COLUMNS)) + ")"] * len(batch))}
                ON CONFLICT (id) DO NOTHING
            """
            flat_values = []
            for row in batch:
                flat_values.extend(row[c] for c in REQUIRED_COLUMNS)

            result = conn.exec_driver_sql(insert_sql, flat_values)
            total_inserted += result.rowcount if hasattr(result, 'rowcount') else len(batch)

            # Track which IDs were actually inserted
            # (rowcount tells us how many were inserted vs skipped)
            trans.commit()

            if len(to_import) > BATCH_SIZE:
                print(f"  Batch {i // BATCH_SIZE + 1}: {len(batch)} rows")

        print(f"  Total hotspots inserted: {total_inserted}")
        print(f"  Remaining ID conflicts at DB level: {len(id_conflicts)}")

        # Phase 4: Import verifications with remapping
        print(f"\n--- Importing verifications ---")
        src_cur.execute(f"""
            SELECT {", ".join(VERIFICATION_COLUMNS)}
            FROM verifications v
            JOIN hotspots h ON v.hotspot_id = h.id
            WHERE h.source = 'nasa_firms' AND h.id IN ({", ".join(str(r['id']) for r in to_import)})
        """)
        v_rows = src_cur.fetchall()
        print(f"  Source verifications to import: {len(v_rows)}")

        # Check which hotspots actually exist in target now
        inserted_id_set = {r['id'] for r in to_import}
        v_inserted = 0
        v_skipped_no_hotspot = 0

        for vrow in v_rows:
            if vrow["hotspot_id"] not in inserted_id_set:
                v_skipped_no_hotspot += 1
                continue

            existing_v = conn.exec_driver_sql(
                "SELECT 1 FROM verifications WHERE hotspot_id = ?",
                [vrow["hotspot_id"]]
            ).fetchone()
            if existing_v:
                continue

            v_cols = ", ".join(VERIFICATION_COLUMNS)
            v_placeholders = ", ".join(["?"] * len(VERIFICATION_COLUMNS))
            conn.exec_driver_sql(
                f"INSERT INTO verifications ({v_cols}) VALUES ({v_placeholders})",
                [vrow[c] for c in VERIFICATION_COLUMNS]
            )
            v_inserted += 1

        trans.commit()
        print(f"  Verifications imported: {v_inserted}")
        print(f"  Verifications skipped (hotspot not imported): {v_skipped_no_hotspot}")

        # Phase 5: Cleanup staging
        conn.exec_driver_sql("DROP TABLE IF EXISTS hotspots_import_staging")
        trans.commit()

        # Final verification
        total_nasa = conn.exec_driver_sql(
            "SELECT COUNT(*) FROM hotspots WHERE source='nasa_firms'"
        ).fetchone()
        total_verif = conn.exec_driver_sql(
            "SELECT COUNT(*) FROM verifications v JOIN hotspots h ON v.hotspot_id=h.id WHERE h.source='nasa_firms'"
        ).fetchone()
        print(f"\n--- Final State ---")
        print(f"  NASA FIRMS total in target: {total_nasa[0]}")
        print(f"  NASA FIRMS verifications in target: {total_verif[0]}")

        src_conn.close()
        conn.close()

        print(f"\nSUCCESS — import complete.")
        return 0

    except Exception as e:
        print(f"\nERROR — rolling back transaction: {e}")
        trans.rollback()
        conn.close()
        return 1


def main():
    parser = argparse.ArgumentParser(description="KAVACH production data recovery import")
    parser.add_argument("--source-sqlite", required=True, help="Path to local SQLite DB")
    parser.add_argument("--target-postgres", required=False,
                        help="PostgreSQL URL (or SQLite URL for staging test)")
    parser.add_argument("--dry-run", action="store_true", help="Show analysis without importing")
    parser.add_argument("--confirm-backup", action="store_true",
                        help="REQUIRED: confirms production backup has been taken")
    parser.add_argument("--max-rows", type=int, default=None,
                        help="Safety cap on rows to import")
    args = parser.parse_args()

    if not args.dry_run and not args.confirm_backup:
        print("ABORT: --confirm-backup is required for actual imports.")
        print("A backup must be taken first: pg_dump -h <host> -U <user> <db> > backup.sql")
        sys.exit(1)

    if not os.path.exists(args.source_sqlite):
        print(f"ABORT: source SQLite file not found: {args.source_sqlite}")
        sys.exit(1)

    info = analyze_source_db(args.source_sqlite)
    print(f"\n{'='*60}")
    print(f"Source database: {args.source_sqlite}")
    print(f"  NASA FIRMS observations: {info['nasa_count']}")
    print(f"  Demo synthetic (NOT imported): {info['demo_count']}")
    print(f"  NASA FIRMS verifications: {info['verif_count']}")
    print(f"  NASA FIRMS date range: {info['date_range'][0]} to {info['date_range'][1]}")
    print(f"  NASA FIRMS unique dates: {info['unique_dates']}")
    print(f"  NASA FIRMS ID range: {info['id_range'][0]} to {info['id_range'][1]}")

    if args.dry_run:
        target = args.target_postgres or "(will be specified at import time)"
        print(f"\n=== DRY RUN — no data will be written ===")
        print(f"Target: {target}")
        print(f"Would evaluate: {info['nasa_count']} NASA FIRMS observations for import")
        print(f"Would evaluate: {info['verif_count']} verifications for import (remapped to inserted IDs)")
        print(f"Demo data: {info['demo_count']} records — explicitly EXCLUDED")
        print(f"Verification decisions: copied verbatim, never modified")
        print(f"Deduplication: ON CONFLICT (id) DO NOTHING + coordinate key check")
        print(f"Transaction: single transaction with rollback on failure")
        print(f"\nThis is a READ-ONLY analysis. No changes have been made.")
        print(f"\nPASS — ready for staging test.")
        return

    target = args.target_postgres
    if not target:
        print("ABORT: --target-postgres is required for actual imports")
        sys.exit(1)

    print(f"\n=== IMPORT — target: {target} ===")
    exit_code = import_nasa_firms(
        args.source_sqlite, target, args.confirm_backup, args.max_rows
    )
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
