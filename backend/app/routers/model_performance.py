"""
Reports REAL model evaluation metrics from ml/train.py's saved metadata.
Never fabricates a number — if training hasn't been run, or hasn't been
run since data changed, says so explicitly.
"""
import os
import json
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func
from app.database import get_db
from app import models
from app.services import classifier

router = APIRouter(prefix="/model-performance", tags=["model-performance"])

METADATA_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "..", "ml", "models", "metadata.json")

MIN_VALIDATED_FOR_RELIABLE_ESTIMATE = 30


@router.get("")
def get_model_performance(db: Session = Depends(get_db)):
    engine_status = classifier.active_engine()   # "XGBoost ACTIVE" or "RULE ENGINE FALLBACK" — Phase 7
    model_deployed = engine_status == "XGBoost ACTIVE"
    metadata = None
    if os.path.exists(METADATA_PATH):
        try:
            with open(METADATA_PATH) as f:
                metadata = json.load(f)
        except (json.JSONDecodeError, OSError):
            metadata = None

    verified_count = db.query(func.count(models.Verification.id)).join(
        models.Hotspot, models.Hotspot.id == models.Verification.hotspot_id
    ).filter(models.Hotspot.source == "nasa_firms").scalar() or 0

    real_count = db.query(func.count(models.Hotspot.id)).filter(models.Hotspot.source == "nasa_firms").scalar() or 0

    result = {
        "engine_status": engine_status,
        "model_deployed": model_deployed,
        "model_type": "XGBoost (gradient-boosted trees)" if model_deployed else None,
        "rule_engine_always_available": True,
        "real_observations_total": real_count,
        "verified_labels_count": verified_count,
        "training_metadata_found": metadata is not None,
    }

    if metadata is None:
        result["status"] = "NO_TRAINED_MODEL"
        result["message"] = ("No model has been trained yet in this environment. The system is running "
                              "entirely on the transparent rule engine (app/services/classifier.py "
                              "rule_based_classify). Run `python ml/train.py` after collecting at least "
                              f"{MIN_VALIDATED_FOR_RELIABLE_ESTIMATE} analyst-verified real observations.")
        return result

    result.update({
        "model_version": metadata.get("model_version"),
        "trained_at": metadata.get("trained_at"),
        "label_source": metadata.get("label_source"),
        "data_source": metadata.get("data_source"),
        "dataset_hash": metadata.get("dataset_hash"),
        "feature_schema_version": metadata.get("feature_schema_version"),
        "feature_schema_signature": metadata.get("feature_schema_signature"),
        "class_mapping": metadata.get("class_mapping"),
        "dataset_size": metadata.get("dataset_size"),
        "train_size": metadata.get("train_size"),
        "test_size": metadata.get("test_size"),
        "class_distribution": metadata.get("class_distribution"),
        "split_method": metadata.get("split_method"),
        "balanced_accuracy": metadata.get("balanced_accuracy"),
        "confusion_matrix": metadata.get("confusion_matrix"),
    })

    if metadata.get("test_size", 0) < 5:
        result["status"] = "INSUFFICIENT_DATA"
        result["message"] = ("Insufficient validated observations for reliable performance estimation. "
                              f"Test set has only {metadata.get('test_size', 0)} facility-held-out rows.")
    else:
        result["status"] = "METRICS_AVAILABLE"
        result["message"] = ("Metrics come from a facility-aware train/test split — no facility's data "
                              "appears in both train and test.")
        result["metrics"] = metadata.get("metrics")

    # Phase 18: never let a small real dataset be mistaken for production-validated AI.
    if metadata.get("dataset_size", 0) < 100:
        result["maturity_label"] = "Research prototype — limited validated training data"
    else:
        result["maturity_label"] = None

    if verified_count < MIN_VALIDATED_FOR_RELIABLE_ESTIMATE:
        result["human_verification_note"] = (
            f"Only {verified_count} analyst-verified real observations exist so far (via "
            f"POST /hotspots/{{id}}/verify)."
        )

    return result
