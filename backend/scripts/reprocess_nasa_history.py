"""
Reprocesses historical NASA FIRMS observations through the existing
intelligence pipeline. Bulk-inserted archive rows were stored with
deferred enrichment (baseline_status=INSUFFICIENT_HISTORY,
reason_codes=DEFERRED_HISTORICAL, risk_score=0.0). This script re-evaluates
each existing NASA row using the SAME service functions the live pipeline
calls — no duplicated scoring logic.

Only source="nasa_firms" rows are touched. Raw fields (lat, lon, brightness,
frp, acq_date, satellite, source) are NEVER modified. Demo data is never
touched.

Idempotent: running twice produces the same result. Batch-commits keep
SQLite unlocked.

Run with:
    python -m scripts.reprocess_nasa_history
    python -m scripts.reprocess_nasa_history --dry-run
"""
import sys
import os
from datetime import datetime

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BACKEND_DIR)

from sqlalchemy.orm import Session
from app.database import SessionLocal, init_db
from app import models
from app.services.facility_matcher import match_facility
from app.services.facility_fingerprint import (
    get_baseline_for_new_reading,
    build_fingerprint,
)
from app.services.baseline_engine import evaluate_against_baseline
from app.services.feature_engine import build_features
from app.services import classifier
from app.services.evidence_engine import build_evidence
from app.services.anomaly_engine import assess_anomaly
from app.services.risk_engine import assess_risk

BATCH_SIZE = 200


def _determine_data_quality(observation: dict) -> str:
    confidence = observation.get("confidence")
    if confidence is None:
        return "unknown"
    if confidence >= 70:
        return "good"
    if confidence >= 40:
        return "degraded"
    return "poor"


def reprocess_nasa_history(dry_run: bool = False) -> dict:
    init_db()
    db = SessionLocal()

    try:
        nasa_rows = (
            db.query(models.Hotspot)
            .filter(models.Hotspot.source == "nasa_firms")
            .order_by(models.Hotspot.id)
            .all()
        )
        total = len(nasa_rows)
        print(f"[reprocess_nasa] Found {total} NASA FIRMS observations to evaluate.")

        stats = {
            "scanned": 0,
            "enriched": 0,
            "skipped": 0,
            "facility_associated": 0,
            "baseline_status_counts": {},
            "anomaly_status_counts": {},
            "risk_level_counts": {},
            "still_insufficient": 0,
            "still_deferred": 0,
        }

        batch = []

        for h in nasa_rows:
            stats["scanned"] += 1

            # Build observation dict from existing row (raw fields preserved)
            observation = {
                "lat": h.lat,
                "lon": h.lon,
                "brightness": h.brightness,
                "confidence": h.confidence,
                "frp": h.frp,
                "acq_date": h.acq_date,
                "satellite": h.satellite,
                "source": h.source,
                "land_cover": h.land_cover or "unknown",
            }

            # --- Facility association (existing 5 km rule) ---
            facility, distance_km = match_facility(db, h.lat, h.lon)

            # --- 90-day rolling baseline (NASA-only) ---
            baseline = get_baseline_for_new_reading(
                db,
                facility.id if facility else None,
                baseline_window_days=90,
                source="nasa_firms",
            )
            baseline_eval = evaluate_against_baseline(h.brightness, baseline)

            # --- Source-aware persistence ---
            fingerprint = build_fingerprint(db, facility, source="nasa_firms") if facility else None

            # --- Features ---
            features = build_features(observation, facility, distance_km, baseline_eval, fingerprint)
            data_quality = _determine_data_quality(observation)

            # --- Classification, evidence, anomaly, risk (existing logic) ---
            classification = classifier.classify(features)
            evidence = build_evidence(features, data_quality)
            anomaly = assess_anomaly(features, evidence)
            risk = assess_risk(anomaly, features, facility, data_quality)

            is_anomaly = anomaly["anomaly_status"] in ("ELEVATED", "ABNORMAL")
            reason_parts = evidence["supporting_evidence"][:2] or ["No strong supporting evidence identified."]
            reason = " ".join(reason_parts)

            # --- Update existing row's computed fields (raw fields untouched) ---
            h.land_cover = features["land_cover"]
            h.facility_id = facility.id if facility else None
            h.distance_to_facility_km = distance_km
            h.state = facility.state if facility else "unknown"
            h.category = classification["category"]
            h.classification_method = classification["classification_method"]
            h.classification_confidence = classification["classification_confidence"]
            h.model_version = classification.get("model_version")
            h.baseline_status = baseline_eval["baseline_status"]
            h.z_score = baseline_eval["z_score"]
            h.deviation_percentage = baseline_eval["deviation_percentage"]
            h.persistence_score = fingerprint["persistence_score"] if fingerprint else 0.0
            h.is_anomaly = is_anomaly
            h.reason = reason
            h.reason_codes = ",".join(evidence["reason_codes"])
            h.risk_score = risk["risk_score"]
            h.risk_level = risk["risk_level"]
            h.data_quality = data_quality

            if facility:
                stats["facility_associated"] += 1

            stats["baseline_status_counts"][h.baseline_status] = (
                stats["baseline_status_counts"].get(h.baseline_status, 0) + 1
            )
            stats["anomaly_status_counts"][anomaly["anomaly_status"]] = (
                stats["anomaly_status_counts"].get(anomaly["anomaly_status"], 0) + 1
            )
            stats["risk_level_counts"][h.risk_level] = (
                stats["risk_level_counts"].get(h.risk_level, 0) + 1
            )

            if h.baseline_status == "INSUFFICIENT_HISTORY":
                stats["still_insufficient"] += 1
            if "DEFERRED_HISTORICAL" in (h.reason_codes or ""):
                stats["still_deferred"] += 1

            stats["enriched"] += 1
            batch.append(h)

            if len(batch) >= BATCH_SIZE:
                if not dry_run:
                    db.bulk_save_objects(batch)
                    db.commit()
                batch.clear()

        if batch:
            if not dry_run:
                db.bulk_save_objects(batch)
                db.commit()
            batch.clear()

        if dry_run:
            db.rollback()
            print("[reprocess_nasa] DRY RUN — no changes written.")

        print(f"\n[reprocess_nasa] Complete:")
        print(f"  NASA rows scanned:      {stats['scanned']}")
        print(f"  Rows enriched:          {stats['enriched']}")
        print(f"  Rows skipped:           {stats['skipped']}")
        print(f"  Facility-associated:     {stats['facility_associated']}")
        print(f"  Baseline status:         {stats['baseline_status_counts']}")
        print(f"  Anomaly status:          {stats['anomaly_status_counts']}")
        print(f"  Risk levels:             {stats['risk_level_counts']}")
        print(f"  Still INSUFFICIENT:      {stats['still_insufficient']}")
        print(f"  Still DEFERRED:          {stats['still_deferred']}")

        return stats
    finally:
        db.close()


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Reprocess NASA FIRMS observations through existing pipeline.")
    parser.add_argument("--dry-run", action="store_true", help="Count only, do not write")
    args = parser.parse_args()

    reprocess_nasa_history(dry_run=args.dry_run)