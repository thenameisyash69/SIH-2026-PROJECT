"""
python -m scripts.build_training_dataset

Builds the real dataset report (Phase 4) — total/unique/facility-associated
observations, class distribution, label quality breakdown, missing-feature
counts, duplicates, date range, geographic coverage, satellite distribution.

Writes:
  data-pipeline/metadata/dataset_report.json  (machine-readable)
  docs/TRAINING_DATASET.md is the human-readable counterpart, written
  separately since it also needs the "STOP — insufficient data" narrative
  Phase 4 requires when training can't proceed.

This reads the REAL database (source='nasa_firms' rows) — run it in an
environment where real FIRMS data has actually been ingested. If run
against an empty/demo-only database, it correctly reports zeros rather
than fabricating anything.
"""
import sys, os, json
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.append(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "..", "ml"))

from datetime import datetime
from app.database import SessionLocal, init_db
from app import models
from sqlalchemy import func

OUT_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
                         "data-pipeline", "metadata", "dataset_report.json")


def build_report():
    init_db()
    db = SessionLocal()

    real_q = db.query(models.Hotspot).filter(models.Hotspot.source == "nasa_firms")
    total = real_q.count()

    facility_associated = real_q.filter(models.Hotspot.facility_id.isnot(None)).count()

    verified_q = db.query(models.Verification).join(
        models.Hotspot, models.Hotspot.id == models.Verification.hotspot_id
    ).filter(models.Hotspot.source == "nasa_firms")
    verified_count = verified_q.count()

    class_distribution = {}
    label_quality_counts = {"VERIFIED": 0, "CURATED": 0, "WEAK": 0}
    excluded_count = 0
    for v in verified_q.all():
        if v.decision == "false_positive":
            excluded_count += 1
            continue
        class_distribution[v.decision] = class_distribution.get(v.decision, 0) + 1
        label_quality_counts["VERIFIED"] += 1

    unverified_count = total - verified_count

    missing_brightness = real_q.filter(models.Hotspot.brightness.is_(None)).count()
    missing_frp = real_q.filter(models.Hotspot.frp.is_(None)).count()

    earliest = db.query(func.min(models.Hotspot.acq_date)).filter(models.Hotspot.source == "nasa_firms").scalar()
    latest = db.query(func.max(models.Hotspot.acq_date)).filter(models.Hotspot.source == "nasa_firms").scalar()

    states = [r[0] for r in db.query(models.Hotspot.state).filter(
        models.Hotspot.source == "nasa_firms").distinct().all() if r[0]]

    satellites = {}
    for r in real_q.all():
        satellites[r.satellite] = satellites.get(r.satellite, 0) + 1

    report = {
        "generated_at": datetime.utcnow().isoformat(),
        "total_observations": total,
        "unique_observations": total,  # pipeline's own duplicate detection means every stored row is already unique
        "facility_associated_observations": facility_associated,
        "class_distribution_verified": class_distribution,
        "label_quality_counts": label_quality_counts,
        "verified_labels": verified_count - excluded_count,
        "curated_labels": 0,   # no curated-label workflow produces data in this codebase yet
        "weak_labels_available_for_reference": total,  # every real row has a pipeline-assigned category usable as a WEAK reference label
        "excluded_false_positive_count": excluded_count,
        "unverified_observations": unverified_count,
        "missing_feature_counts": {"brightness": missing_brightness, "frp": missing_frp},
        "date_range": {"earliest": earliest.isoformat() if earliest else None,
                        "latest": latest.isoformat() if latest else None},
        "geographic_coverage_states": states,
        "satellite_distribution": satellites,
    }

    os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
    with open(OUT_PATH, "w") as f:
        json.dump(report, f, indent=2, default=str)

    print(json.dumps(report, indent=2, default=str))
    print(f"\nSaved to {OUT_PATH}")

    if report["verified_labels"] < 30:
        print(f"\nInsufficient validated observations for reliable ML training. "
              f"Have {report['verified_labels']} verified labels (excluding false positives), "
              f"need at least 30. STOPPING before training — see docs/TRAINING_DATASET.md.")
    return report


if __name__ == "__main__":
    build_report()
