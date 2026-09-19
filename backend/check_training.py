"""Verify training pipeline eligibility - read-only."""
import sys, os

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, PROJECT_ROOT)
sys.path.insert(0, os.path.join(PROJECT_ROOT, "backend"))
sys.path.insert(0, os.path.join(PROJECT_ROOT, "ml"))

# Check dataset builder
from ml.dataset_builder import build_dataset, dataset_stats, build_manifest

stats = dataset_stats()
print("=== Dataset Stats ===")
print(f"Total real NASA observations: {stats['total_real_observations']}")
print(f"Verified (usable for training): {stats['verified_observations']}")
print(f"Unverified: {stats['unverified_observations']}")
print(f"Class distribution: {stats['class_distribution']}")

# Try building dataset
df = build_dataset()
print(f"\n=== Dataset ===")
print(f"Rows: {len(df)}")
if not df.empty:
    print(f"Columns: {list(df.columns)}")
    print(f"Label distribution: {df['label'].value_counts().to_dict()}")
    print(f"Facilities: {df['facility_id'].nunique()}")
    print(f"Date range: {df['acq_date'].min()} to {df['acq_date'].max()}")
else:
    print("Dataset is EMPTY — no verified labels available for training.")

# Check MIN_VERIFIED_FOR_TRAINING
from ml.train import MIN_VERIFIED_FOR_TRAINING
print(f"\nMIN_VERIFIED_FOR_TRAINING: {MIN_VERIFIED_FOR_TRAINING}")
print(f"Training eligible: {stats['verified_observations'] >= MIN_VERIFIED_FOR_TRAINING}")

# Check model artifacts
models_dir = os.path.join(PROJECT_ROOT, "ml", "models")
print(f"\nModels dir: {models_dir}")
print(f"Exists: {os.path.isdir(models_dir)}")
if os.path.isdir(models_dir):
    for f in sorted(os.listdir(models_dir)):
        print(f"  {f}")
else:
    print("  No models directory — no trained artifacts exist.")

# Check feature schema
from app.services.feature_schema import FEATURE_NAMES, FEATURE_SCHEMA_VERSION, schema_signature
print(f"\nFeature schema version: {FEATURE_SCHEMA_VERSION}")
print(f"Feature names: {FEATURE_NAMES}")
print(f"Schema signature: {schema_signature()}")

# Check label builder
from ml.label_builder import VERIFIED_LABEL_VOCABULARY, EXCLUDED_FROM_TRAINING
print(f"\nVerified label vocabulary: {VERIFIED_LABEL_VOCABULARY}")
print(f"Excluded from training: {EXCLUDED_FROM_TRAINING}")