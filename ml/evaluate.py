"""
Standalone evaluation (Phase 9) + rule-engine vs. XGBoost comparison
(Phase 10). Loads the already-trained model from ml/models/ and re-runs
it against a freshly-built held-out set — does NOT retrain.

Also runs the deterministic rule engine (classifier.rule_based_classify)
against the SAME held-out rows, so the comparison is apples-to-apples.

IMPORTANT LIMITATION, stated plainly: Hotspot rows do not persist
`behavior_label` (it's computed transiently at pipeline-time from
facility_fingerprint, not stored). This script approximates it from the
stored `persistence_score` + `is_anomaly` columns using the same 0.6
threshold facility_fingerprint.py itself uses. This is a reasonable
proxy, not a re-derivation of the exact original value — documented here
so the comparison's limits are clear, not hidden.

Run with:  python ml/evaluate.py   (after ml/train.py has produced a model)
"""
import sys, os, json, pickle
sys.path.append(os.path.join(os.path.dirname(__file__), "..", "backend"))
sys.path.append(os.path.dirname(__file__))

from sklearn.metrics import classification_report, balanced_accuracy_score

from dataset_builder import build_dataset, dataset_stats
from train import facility_aware_split, MIN_VERIFIED_FOR_TRAINING
from app.services.feature_schema import vector_from_row
from app.services.classifier import rule_based_classify

MODEL_PATH = os.path.join(os.path.dirname(__file__), "models", "classifier.pkl")


def approximate_behavior_label(row) -> str:
    persistence = row.get("persistence_score") or 0.0
    if persistence == 0.0:
        return "INSUFFICIENT_HISTORY"
    if persistence >= 0.6:
        return "PERSISTENT_UNEXPECTED" if row.get("is_anomaly") else "PERSISTENT_EXPECTED"
    return "IRREGULAR"


def rule_engine_predict(row) -> str:
    features = {
        "distance_to_facility_km": row.get("distance_to_facility_km"),
        "land_cover": row.get("land_cover", "unknown"),
        "month": row.get("month"),
        "behavior_label": approximate_behavior_label(row),
        "baseline_status": row.get("baseline_status", "INSUFFICIENT_HISTORY"),
        "confidence": row.get("confidence", 0),
    }
    result = rule_based_classify(features)
    # Map the rule engine's own vocabulary onto the human-verification vocabulary
    # for a fair comparison (see label_builder.py for why these differ).
    # NOTE: the rule engine has no way to distinguish "confirmed normal
    # industrial heat" from a generic "industrial" reading — both of its
    # industrial_* categories map to INDUSTRIAL here. This is a real,
    # documented limitation of the comparison, not an oversight: the rule
    # engine was never designed to predict the 5-class human taxonomy.
    mapping = {
        "industrial_normal": "INDUSTRIAL", "industrial_alert": "INDUSTRIAL", "industrial_new": "INDUSTRIAL",
        "wildfire": "WILDFIRE", "agricultural_burning": "AGRICULTURAL", "unknown": "UNKNOWN",
    }
    return mapping.get(result["category"], "UNKNOWN")


def evaluate():
    stats = dataset_stats()
    if stats["verified_observations"] < MIN_VERIFIED_FOR_TRAINING:
        print("Insufficient validated observations for reliable performance estimation. "
              f"Have {stats['verified_observations']}, need {MIN_VERIFIED_FOR_TRAINING}.")
        return None

    if not os.path.exists(MODEL_PATH):
        print("No trained model found at ml/models/classifier.pkl — run ml/train.py first.")
        return None

    df = build_dataset()
    _, test_df = facility_aware_split(df)   # same seed as train.py -> same held-out rows

    with open(MODEL_PATH, "rb") as f:
        bundle = pickle.load(f)
    model, encoder = bundle["model"], bundle["label_encoder"]

    X_test = [vector_from_row(row) for _, row in test_df.iterrows()]
    y_test_raw = test_df["label"]
    y_test = encoder.transform(y_test_raw)
    ml_preds = model.predict(X_test)

    ml_report = classification_report(y_test, ml_preds, target_names=encoder.classes_, zero_division=0, output_dict=True)
    ml_balanced_acc = balanced_accuracy_score(y_test, ml_preds)

    rule_preds_str = [rule_engine_predict(row) for _, row in test_df.iterrows()]
    known_labels = list(encoder.classes_)
    rule_preds_encoded = [known_labels.index(p) if p in known_labels else -1 for p in rule_preds_str]
    valid_mask = [p != -1 for p in rule_preds_encoded]
    if any(valid_mask):
        rule_report = classification_report(
            [y for y, v in zip(y_test, valid_mask) if v],
            [p for p, v in zip(rule_preds_encoded, valid_mask) if v],
            labels=list(range(len(known_labels))), target_names=known_labels, zero_division=0, output_dict=True,
        )
        rule_balanced_acc = balanced_accuracy_score(
            [y for y, v in zip(y_test, valid_mask) if v],
            [p for p, v in zip(rule_preds_encoded, valid_mask) if v],
        )
    else:
        rule_report, rule_balanced_acc = None, None

    comparison = {
        "test_set_size": len(test_df),
        "xgboost": {
            "balanced_accuracy": ml_balanced_acc,
            "macro_f1": ml_report["macro avg"]["f1-score"],
            "weighted_f1": ml_report["weighted avg"]["f1-score"],
        },
        "rule_engine": {
            "balanced_accuracy": rule_balanced_acc,
            "macro_f1": rule_report["macro avg"]["f1-score"] if rule_report else None,
            "weighted_f1": rule_report["weighted avg"]["f1-score"] if rule_report else None,
        } if rule_report else {"note": "rule engine predicted no labels in the model's known class set"},
        "xgboost_improves_over_rules": (
            ml_report["macro avg"]["f1-score"] > rule_report["macro avg"]["f1-score"]
            if rule_report else None
        ),
        "note": "behavior_label used by the rule engine here is APPROXIMATED from stored "
                "persistence_score/is_anomaly, not the exact original pipeline-time value — see module docstring.",
    }

    out_path = os.path.join(os.path.dirname(__file__), "reports")
    os.makedirs(out_path, exist_ok=True)
    with open(os.path.join(out_path, "model_performance.json"), "w") as f:
        json.dump({"ml_report": ml_report, "rule_report": rule_report, "comparison": comparison}, f, indent=2, default=str)

    print(json.dumps(comparison, indent=2, default=str))
    print(f"\nSaved full report to {out_path}/model_performance.json")
    return comparison


if __name__ == "__main__":
    evaluate()
