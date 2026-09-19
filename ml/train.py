"""
Trains an XGBoost classifier on REAL, ANALYST-VERIFIED observations only.

Uses app.services.feature_schema — the SINGLE canonical feature contract
also used at inference time in classifier.py. Before this schema module
existed, this file maintained its own independent FEATURE_COLUMNS list
that had to happen to match feature_engine.py's by hand — a confirmed real
defect (see docs/ML_TRAINING_PIPELINE.md Phase 0 audit, finding 6).

Trains on Verification.decision (via label_builder.py's mapping), NEVER
on Hotspot.category — training on the pipeline's own rule-engine output
would be circular (see label_builder.py's module docstring).

Uses a FACILITY-AWARE split (see docs/ML_SPLIT_METHODOLOGY.md).

Run with:  python ml/train.py   (from the project root)
"""
import sys, os
sys.path.append(os.path.join(os.path.dirname(__file__), "..", "backend"))
sys.path.append(os.path.dirname(__file__))

import pickle
import json
import random
from datetime import datetime
from sklearn.preprocessing import LabelEncoder
from xgboost import XGBClassifier
from sklearn.metrics import classification_report, confusion_matrix, balanced_accuracy_score

from dataset_builder import build_dataset, dataset_stats, build_manifest
from app.services.feature_schema import FEATURE_NAMES, FEATURE_SCHEMA_VERSION, schema_signature, vector_from_row

MIN_VERIFIED_FOR_TRAINING = 30
MODELS_DIR = os.path.join(os.path.dirname(__file__), "models")


def next_version_number() -> int:
    """
    Phase 7 — auto-incrementing version, no manual bookkeeping. Scans
    ml/models/ for existing classifier_xgb_v*.pkl files and returns the
    next integer. Starts at 1 if none exist yet.
    """
    import re
    if not os.path.isdir(MODELS_DIR):
        return 1
    versions = []
    for fname in os.listdir(MODELS_DIR):
        m = re.match(r"classifier_xgb_v(\d+)\.pkl$", fname)
        if m:
            versions.append(int(m.group(1)))
    return max(versions, default=0) + 1


def facility_aware_split(df, test_frac: float = 0.2, seed: int = 42):
    groups = list(df["facility_id"].fillna(-1).unique())
    random.seed(seed)
    random.shuffle(groups)
    n_test = max(1, int(len(groups) * test_frac))
    test_groups = set(groups[:n_test])
    test_mask = df["facility_id"].fillna(-1).isin(test_groups)
    return df[~test_mask], df[test_mask]


def train():
    stats = dataset_stats()
    print(f"Real NASA FIRMS observations: {stats['total_real_observations']}")
    print(f"Verified (usable for training): {stats['verified_observations']}")
    print(f"Class distribution: {stats['class_distribution']}")

    if stats["verified_observations"] < MIN_VERIFIED_FOR_TRAINING:
        print(f"\nInsufficient validated observations for reliable supervised model evaluation. "
              f"Need at least {MIN_VERIFIED_FOR_TRAINING} analyst-verified real observations "
              f"(have {stats['verified_observations']}). Verify more via POST /hotspots/{{id}}/verify, "
              f"or run scripts/bootstrap_firms_history.py / scripts/load_real_firms_snapshot.py "
              f"to get more real data to verify first.")
        return None

    df = build_dataset()
    if df.empty or df["label"].nunique() < 2:
        print("Dataset has fewer than 2 distinct verified classes — cannot train a classifier yet.")
        return None

    train_df, test_df = facility_aware_split(df)
    if len(test_df) < 5:
        print("Not enough facility diversity among verified observations for a clean held-out split yet.")
        return None

    for col in FEATURE_NAMES:
        if col not in df.columns:
            df[col] = 0
    X_train = [vector_from_row(row) for _, row in train_df.iterrows()]
    X_test = [vector_from_row(row) for _, row in test_df.iterrows()]
    y_train_raw, y_test_raw = train_df["label"], test_df["label"]

    encoder = LabelEncoder()
    encoder.fit(df["label"])
    y_train = encoder.transform(y_train_raw)
    y_test = encoder.transform(y_test_raw)

    model = XGBClassifier(n_estimators=150, max_depth=4, learning_rate=0.1,
                           eval_metric="mlogloss", random_state=42)
    model.fit(X_train, y_train)

    preds = model.predict(X_test)
    report = classification_report(y_test, preds, target_names=encoder.classes_, zero_division=0, output_dict=True)
    bal_acc = balanced_accuracy_score(y_test, preds)
    print(classification_report(y_test, preds, target_names=encoder.classes_, zero_division=0))
    print(f"Balanced accuracy: {bal_acc:.3f}")
    print("Confusion matrix (rows=actual, cols=predicted):")
    cm = confusion_matrix(y_test, preds)
    print(cm)

    manifest = build_manifest(df)
    dataset_hash = manifest["dataset_hash"]

    version_num = next_version_number()
    model_version = f"kavach-xgb-v{version_num:03d}"

    os.makedirs(MODELS_DIR, exist_ok=True)
    pkl_filename = f"classifier_xgb_v{version_num:03d}.pkl"
    with open(os.path.join(MODELS_DIR, pkl_filename), "wb") as f:
        pickle.dump({
            "model": model,
            "label_encoder": encoder,
            "features": FEATURE_NAMES,
            "feature_schema_signature": schema_signature(),
            "model_version": model_version,
        }, f)

    metadata = {
        "model_version": model_version,
        "trained_at": datetime.utcnow().isoformat(),
        "label_source": "human_verified",
        "data_source": "nasa_firms_only",
        "dataset_hash": dataset_hash,
        "feature_schema_version": FEATURE_SCHEMA_VERSION,
        "feature_schema_signature": schema_signature(),
        "class_mapping": {int(i): c for i, c in enumerate(encoder.classes_)},
        "dataset_size": len(df),
        "train_size": len(train_df),
        "test_size": len(test_df),
        "class_distribution": stats["class_distribution"],
        "split_method": "facility_aware",
        "split_seed": 42,
        "balanced_accuracy": bal_acc,
        "metrics": report,
        "confusion_matrix": cm.tolist(),
    }
    # Versioned metadata alongside the versioned model (Phase 7)
    with open(os.path.join(MODELS_DIR, f"classifier_xgb_v{version_num:03d}.json"), "w") as f:
        json.dump(metadata, f, indent=2, default=str)
    # Also kept as metadata.json (latest) for backward-compat with
    # /model-performance's current lookup — see docs/MODEL_CARD.md.
    with open(os.path.join(MODELS_DIR, "metadata.json"), "w") as f:
        json.dump(metadata, f, indent=2, default=str)

    print(f"\nSaved model ({model_version}) to {MODELS_DIR}/{pkl_filename}")
    print(f"classifier.py auto-discovers this on next backend restart — NO manual copy needed "
          f"(it scans {MODELS_DIR} for the highest-numbered valid classifier_xgb_v*.pkl).")
    return metadata


if __name__ == "__main__":
    train()
