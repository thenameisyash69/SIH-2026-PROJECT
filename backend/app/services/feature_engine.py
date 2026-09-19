"""
Centralizes every feature used anywhere in the classification/anomaly/
risk pipeline, so a prediction is always reproducible from stored
inputs (spec §14) — no feature gets computed ad-hoc in one place and
differently somewhere else.
"""
from datetime import datetime


def build_features(observation: dict, facility, distance_km: float | None,
                    baseline_eval: dict, fingerprint: dict | None) -> dict:
    """
    observation: {brightness, confidence, frp, acq_date, land_cover}
    facility: models.Facility or None
    baseline_eval: output of baseline_engine.evaluate_against_baseline()
    fingerprint: output of facility_fingerprint.build_fingerprint(), or None
    """
    acq_date = observation.get("acq_date") or datetime.utcnow()
    month = acq_date.month if isinstance(acq_date, datetime) else datetime.utcnow().month

    return {
        "brightness": observation.get("brightness", 0.0),
        "confidence": observation.get("confidence", 0.0),
        "frp": observation.get("frp"),
        "distance_to_facility_km": distance_km,
        "facility_type": facility.type if facility else None,
        "facility_criticality": facility.criticality if facility else None,
        "land_cover": observation.get("land_cover", "unknown"),
        "month": month,
        "z_score": baseline_eval.get("z_score", 0.0),
        "deviation_percentage": baseline_eval.get("deviation_percentage", 0.0),
        "baseline_status": baseline_eval.get("baseline_status", "INSUFFICIENT_HISTORY"),
        "observation_count": fingerprint.get("observation_count", 0) if fingerprint else 0,
        "persistence_score": fingerprint.get("persistence_score", 0.0) if fingerprint else 0.0,
        "recent_7d_count": fingerprint.get("recent_7d_count", 0) if fingerprint else 0,
        "recent_30d_count": fingerprint.get("recent_30d_count", 0) if fingerprint else 0,
        "recent_60d_count": fingerprint.get("recent_60d_count", 0) if fingerprint else 0,
        "behavior_label": fingerprint.get("behavior_label", "INSUFFICIENT_HISTORY") if fingerprint else "INSUFFICIENT_HISTORY",
    }


def ml_feature_vector(features: dict) -> list:
    """
    DEPRECATED as of feature_schema.py (see docs/ML_TRAINING_PIPELINE.md
    Phase 5 audit — this function and ml/train.py's FEATURE_COLUMNS were
    two independently-maintained lists, a confirmed real duplication risk).
    Kept only so any external code still importing this doesn't hard-crash.
    Delegates to the single canonical schema.
    """
    from app.services.feature_schema import vector_from_features
    return vector_from_features(features)
