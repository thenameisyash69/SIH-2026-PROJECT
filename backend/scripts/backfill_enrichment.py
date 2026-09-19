"""
Backfills facility association + baseline + thermal fingerprint fields for
existing NASA FIRMS observations that were inserted by
data-pipeline/backfill_firms.py with deferred enrichment
(facility_id=None, baseline_status=INSUFFICIENT_HISTORY, z_score=0.0,
persistence_score=0.0, etc.).

WHY THIS EXISTS: backfill_firms.py deliberately defers per-observation
enrichment (no per-observation API calls during bulk historical backfill).
This script is the second pass that runs AFTER the bulk load, doing exactly
what the live pipeline does for each observation:

    Phase 1:
        1. match_facility()          → facility_id, distance_to_facility_km, state
        2. get_baseline_for_new_reading() + evaluate_against_baseline()
                                     → baseline_status, z_score, deviation_percentage

    Phase 2:
        3. build_fingerprint()       → persistence_score (the ONLY canonical
                                       source; pipeline.py:142 reads it from here)

It does NOT re-run classification, anomaly, risk, or evidence engines —
those remain deferred for backfilled observations (reason_codes stays
"DEFERRED_HISTORICAL") because the analyst queue already displays them
honestly as "Not yet assessed".

SAFETY:
- ONLY touches source="nasa_firms" rows.
- NEVER modifies demo_synthetic rows.
- Idempotent: safe to re-run; already-enriched rows are skipped by Phase 1,
  and Phase 2 re-stamps the same persistence_score each time.
- Preserves the DEFERRED_HISTORICAL reason_codes on every row it touches.
- Does NOT fabricate persistence when insufficient observations exist.

Run with:
    python -m scripts.backfill_enrichment            # dry-run preview
    python -m scripts.backfill_enrichment --commit   # actually update
"""
import sys
import os
import argparse

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import SessionLocal, init_db
from app import models
from app.services.facility_matcher import match_facility
from app.services.facility_fingerprint import get_baseline_for_new_reading, build_fingerprint
from app.services.baseline_engine import evaluate_against_baseline


def run(dry_run: bool = True) -> dict:
    init_db()
    db = SessionLocal()

    try:
        # ---- Phase 1: facility association + baseline (skipped if already done) ----
        targets = (
            db.query(models.Hotspot)
            .filter(
                models.Hotspot.source == "nasa_firms",
                models.Hotspot.facility_id.is_(None),
            )
            .order_by(models.Hotspot.id)
            .all()
        )

        matched_count = 0
        unmatched_count = 0
        updated_count = 0

        if targets:
            facilities = db.query(models.Facility).all()
            print(f"[backfill_enrichment] Phase 1: Found {len(targets)} NASA observations to enrich, "
                  f"{len(facilities)} facilities available.")

            # Batch updates to avoid SQLite lock contention on large tables.
            BATCH = 200
            batch = []

            def _flush_batch():
                nonlocal batch
                if not batch:
                    return
                for h in batch:
                    db.add(h)
                if not dry_run:
                    db.commit()
                batch.clear()

            for i, h in enumerate(targets):
                facility, distance_km = match_facility(db, h.lat, h.lon)

                if facility is None:
                    baseline = get_baseline_for_new_reading(db, None)
                    baseline_eval = evaluate_against_baseline(h.brightness, baseline)
                    h.baseline_status = baseline_eval["baseline_status"]
                    h.z_score = baseline_eval["z_score"]
                    h.deviation_percentage = baseline_eval["deviation_percentage"]
                    h.state = h.state or "unknown"
                    unmatched_count += 1
                    updated_count += 1
                else:
                    matched_count += 1
                    baseline = get_baseline_for_new_reading(db, facility.id, exclude_hotspot_id=h.id)
                    baseline_eval = evaluate_against_baseline(h.brightness, baseline)

                    h.facility_id = facility.id
                    h.distance_to_facility_km = distance_km
                    h.state = facility.state
                    h.baseline_status = baseline_eval["baseline_status"]
                    h.z_score = baseline_eval["z_score"]
                    h.deviation_percentage = baseline_eval["deviation_percentage"]
                    updated_count += 1

                batch.append(h)
                if len(batch) >= BATCH:
                    _flush_batch()
                    if not dry_run:
                        print(f"[backfill_enrichment] ... {i + 1}/{len(targets)} processed")

            _flush_batch()

            print(f"[backfill_enrichment] Phase 1: Matched {matched_count} to a facility, "
                  f"{unmatched_count} unassociated. Updated {updated_count} rows"
                  + (" (dry run, rolled back)" if dry_run else ""))

            if dry_run:
                db.rollback()
                print("[backfill_enrichment] DRY RUN — no changes written. Pass --commit to apply.")
                return {
                    "total": len(targets), "matched": matched_count,
                    "unmatched": unmatched_count, "updated": updated_count,
                    "fingerprinted": 0, "committed": False,
                }
        else:
            print("[backfill_enrichment] Phase 1: No NASA observations needing enrichment (already done).")

        # ---- Phase 2: thermal fingerprint / persistence_score ----
        # build_fingerprint() is the single canonical source of
        # persistence_score — it is the ONLY place that computes it, and the
        # live pipeline (pipeline.py:142) reads it from there. Backfilled
        # rows never went through process_observation(), so their
        # persistence_score stayed at the model default of 0.0. This phase
        # computes the fingerprint once per facility and stamps the same
        # value onto every NASA observation associated with that facility,
        # matching exactly what the live pipeline would have produced.
        print("[backfill_enrichment] Phase 2: computing facility thermal fingerprints...")

        fingerprinted_count = 0
        persistence_values = []
        skipped_insufficient = 0

        facilities_with_nasa = (
            db.query(models.Facility.id)
            .join(models.Hotspot, models.Hotspot.facility_id == models.Facility.id)
            .filter(models.Hotspot.source == "nasa_firms")
            .distinct()
            .all()
        )
        facility_ids_with_nasa = [fid[0] for fid in facilities_with_nasa]

        for fid in facility_ids_with_nasa:
            fac = db.query(models.Facility).filter(models.Facility.id == fid).first()
            fp = build_fingerprint(db, fac, source="nasa_firms")
            persistence = fp["persistence_score"]

            if persistence is None or persistence <= 0:
                skipped_insufficient += 1
                print(f"[backfill_enrichment]   {fp['facility_name']}: "
                      f"persistence={persistence} (insufficient history — left as 0.0)")
                continue

            rows = (
                db.query(models.Hotspot)
                .filter(
                    models.Hotspot.facility_id == fid,
                    models.Hotspot.source == "nasa_firms",
                )
                .all()
            )
            for h in rows:
                h.persistence_score = persistence
                fingerprinted_count += 1
                persistence_values.append(persistence)

            if not dry_run:
                db.commit()
            print(f"[backfill_enrichment]   {fp['facility_name']}: "
                  f"persistence={persistence} applied to {len(rows)} NASA row(s)")

        print(f"[backfill_enrichment] Phase 2 complete: {fingerprinted_count} NASA rows "
              f"received persistence_score across {len(facility_ids_with_nasa)} "
              f"facility/facilities ({skipped_insufficient} skipped due to insufficient history).")

        if dry_run:
            db.rollback()
            print("[backfill_enrichment] DRY RUN — no changes written. Pass --commit to apply.")

        return {
            "total": len(targets), "matched": matched_count,
            "unmatched": unmatched_count, "updated": updated_count,
            "fingerprinted": fingerprinted_count,
            "persistence_min": min(persistence_values) if persistence_values else None,
            "persistence_max": max(persistence_values) if persistence_values else None,
            "skipped_insufficient": skipped_insufficient,
            "committed": not dry_run,
        }
    finally:
        db.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Backfill facility association + baseline for existing NASA FIRMS observations."
    )
    parser.add_argument("--commit", action="store_true",
                        help="Actually write changes (default is dry-run).")
    args = parser.parse_args()

    result = run(dry_run=not args.commit)
    print(f"\nResult: {result}")