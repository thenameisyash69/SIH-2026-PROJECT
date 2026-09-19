"""
Source classification. Combines rule logic (always available) with an
optional trained ML model, and can explicitly return UNKNOWN rather than
forcing a label when evidence is weak, history is thin, the model's own
score is too low, or the loaded model's feature schema doesn't match what
this codebase currently computes (never guess).

IMPORTANT: the ML model's output is a "model score", not a calibrated
probability, until real validation says otherwise.

MODEL LOADING (Phase 7 — automatic latest-valid, no manual copy step):
Scans ml/models/ for versioned artifacts (classifier_xgb_v*.pkl + matching
.json metadata), tries the highest version number first, validates its
feature schema signature, and uses the first one that's actually
compatible. Falls back to the single legacy path
(backend/app/services/classifier.pkl) for backward compatibility if no
versioned artifacts exist. If nothing valid is found anywhere, uses the
rule engine — this fallback always remains functional.
"""
import os
import re
import json
import pickle
from app.services.feature_schema import vector_from_features, schema_signature
from app.services.facility_constants import FACILITY_ASSOCIATION_RADIUS_KM

AGRI_BURN_MONTHS = {10, 11}

MODEL_SCORE_ABSTENTION_THRESHOLD = 0.45

_LEGACY_MODEL_PATH = os.path.join(os.path.dirname(__file__), "classifier.pkl")
_VERSIONED_MODELS_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "..", "ml", "models")
_VERSION_PATTERN = re.compile(r"classifier_xgb_v(\d+)\.pkl$")

_model_bundle = None
_model_load_attempted = False


def _discover_versioned_models() -> list:
    """Returns [(version_int, pkl_path), ...] sorted highest version first."""
    if not os.path.isdir(_VERSIONED_MODELS_DIR):
        return []
    found = []
    for fname in os.listdir(_VERSIONED_MODELS_DIR):
        m = _VERSION_PATTERN.search(fname)
        if m:
            found.append((int(m.group(1)), os.path.join(_VERSIONED_MODELS_DIR, fname)))
    return sorted(found, key=lambda x: x[0], reverse=True)


def _try_load(pkl_path: str):
    """Returns the bundle if valid (schema matches), else None (never raises)."""
    if not os.path.exists(pkl_path):
        return None
    try:
        with open(pkl_path, "rb") as f:
            bundle = pickle.load(f)
    except Exception as e:
        print(f"[classifier] Could not load {pkl_path}: {e} — skipping (corrupted artifact).")
        return None

    saved_signature = bundle.get("feature_schema_signature")
    if saved_signature != schema_signature():
        print(f"[classifier] {pkl_path}: feature schema ({saved_signature}) does not match "
              f"the current codebase's schema ({schema_signature()}) — SKIPPING, not loading. "
              f"Re-run ml/train.py to produce a compatible artifact.")
        return None
    return bundle


def _load_model():
    global _model_bundle, _model_load_attempted
    if _model_load_attempted:
        return _model_bundle
    _model_load_attempted = True

    versioned = _discover_versioned_models()
    for version, path in versioned:
        bundle = _try_load(path)
        if bundle is not None:
            _model_bundle = bundle
            print(f"[classifier] ACTIVE: XGBoost (versioned artifact v{version:03d} from {path}).")
            return _model_bundle

    # Backward-compat fallback: the single legacy path from before versioning existed.
    bundle = _try_load(_LEGACY_MODEL_PATH)
    if bundle is not None:
        _model_bundle = bundle
        print(f"[classifier] ACTIVE: XGBoost (legacy unversioned artifact, version "
              f"{bundle.get('model_version', 'unknown')}).")
        return _model_bundle

    print("[classifier] ACTIVE: RULE ENGINE FALLBACK — no valid trained model found "
          f"(checked {len(versioned)} versioned artifact(s) in {_VERSIONED_MODELS_DIR} "
          f"and the legacy path {_LEGACY_MODEL_PATH}). Run ml/train.py once enough "
          f"verified real data exists.")
    return None


def active_engine() -> str:
    """Phase 7: the application must be able to state plainly which engine
    is actually active. Never inferred from file existence alone — this
    calls the real loader (with caching), so it reflects schema validation too."""
    return "XGBoost ACTIVE" if _load_model() is not None else "RULE ENGINE FALLBACK"


def rule_based_classify(features: dict) -> dict:
    dist = features.get("distance_to_facility_km")
    land_cover = features.get("land_cover")
    month = features.get("month")
    behavior = features.get("behavior_label")
    baseline_status = features.get("baseline_status")

    near_facility = dist is not None and dist <= FACILITY_ASSOCIATION_RADIUS_KM

    if near_facility and behavior in ("PERSISTENT_EXPECTED",) and baseline_status != "ABNORMAL":
        return {"category": "industrial_normal", "confidence": 0.8}

    if near_facility and baseline_status == "ABNORMAL":
        return {"category": "industrial_alert", "confidence": 0.75}

    if near_facility and behavior == "INSUFFICIENT_HISTORY":
        return {"category": "industrial_new", "confidence": 0.5}

    if land_cover == "forest" and not near_facility:
        return {"category": "wildfire", "confidence": 0.65}

    if land_cover == "agricultural" and month in AGRI_BURN_MONTHS and not near_facility:
        return {"category": "agricultural_burning", "confidence": 0.6}

    if features.get("confidence", 0) < 40 or (not near_facility and land_cover == "unknown"):
        return {"category": "unknown", "confidence": 0.3}

    return {"category": "unknown", "confidence": 0.35}


def ml_classify(features: dict) -> dict | None:
    bundle = _load_model()
    if bundle is None:
        return None
    model, encoder = bundle["model"], bundle["label_encoder"]
    X = [vector_from_features(features)]
    pred_idx = model.predict(X)[0]
    category = encoder.inverse_transform([pred_idx])[0]
    model_score = float(max(model.predict_proba(X)[0]))

    if model_score < MODEL_SCORE_ABSTENTION_THRESHOLD:
        # Phase 12: do not force a confident classification when the model
        # itself isn't confident — abstain rather than guess.
        return {"category": "unknown", "confidence": model_score, "abstained": True}

    return {"category": category, "confidence": model_score, "abstained": False,
            "model_version": bundle.get("model_version")}


def classify(features: dict) -> dict:
    """
    Single entry point. Returns category, classification_method,
    classification_confidence (explicitly a model score if from ML),
    and model_version when applicable. Falls back to rules if no model
    (or if the model's feature schema doesn't match), and both paths can
    return "unknown".
    """
    ml_result = ml_classify(features)
    if ml_result is not None:
        return {
            "category": ml_result["category"],
            "classification_method": "ml_model",
            "classification_confidence": round(ml_result["confidence"], 2),
            "model_version": ml_result.get("model_version"),
        }
    rule_result = rule_based_classify(features)
    return {
        "category": rule_result["category"],
        "classification_method": "rules",
        "classification_confidence": round(rule_result["confidence"], 2),
        "model_version": None,
    }
