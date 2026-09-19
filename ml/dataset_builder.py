"""
Builds the supervised training dataset — REAL observations only, VERIFIED
labels only (see label_builder.py for why the pipeline's own category is
never used as a training target — training on it would be circular).

Per spec: outputs to ml/data/ (this project's actual ML directory — see
docs/ML_TRAINING_PIPELINE.md's Phase 0 audit note on why this deviates
from a suggested backend/ml/data/ path: the existing, working, documented
structure keeps ml/ as a top-level sibling of backend/, and moving it would
break every doc/script that already references `cd ml && python train.py`
for no functional benefit).

Outputs:
  ml/data/kavach_training_dataset.csv   (parquet unavailable — pyarrow not
                                          installed in this environment;
                                          CSV per spec's own fallback rule)
  ml/data/dataset_manifest.json

Run standalone to see dataset stats without training:
    python ml/dataset_builder.py
"""
import sys, os, json, hashlib
sys.path.append(os.path.join(os.path.dirname(__file__), "..", "backend"))

import pandas as pd
from datetime import datetime
from sqlalchemy import create_engine

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "backend", "sih.db")
OUT_DIR = os.path.join(os.path.dirname(__file__), "data")

REQUIRED_FIELDS = ["lat", "lon", "brightness", "acq_date"]


def build_dataset() -> pd.DataFrame:
    """
    Returns a DataFrame of REAL, ANALYST-VERIFIED observations only, with
    the label column set to the human decision (mapped through
    label_builder.VERIFIED_LABEL_VOCABULARY), not the pipeline's own
    category. Rows verified as "false_positive" are explicitly EXCLUDED
    (not mapped to UNKNOWN — see label_builder.py's module docstring for
    why those are a different concept). Empty DataFrame (not an exception)
    if nothing qualifies yet.
    """
    from label_builder import VERIFIED_LABEL_VOCABULARY, EXCLUDED_FROM_TRAINING

    engine = create_engine(f"sqlite:///{DB_PATH}")

    hotspots = pd.read_sql("SELECT * FROM hotspots WHERE source = 'nasa_firms'", engine)
    if hotspots.empty:
        return hotspots

    verifications = pd.read_sql("SELECT * FROM verifications", engine)
    if verifications.empty:
        return pd.DataFrame()

    verifications = verifications[~verifications["decision"].isin(EXCLUDED_FROM_TRAINING)]
    if verifications.empty:
        return pd.DataFrame()

    merged = hotspots.merge(
        verifications[["hotspot_id", "decision"]],
        left_on="id", right_on="hotspot_id", how="inner",
    )

    for field in REQUIRED_FIELDS:
        merged = merged[merged[field].notnull()]
    merged = merged[(merged["lat"].between(-90, 90)) & (merged["lon"].between(-180, 180))]

    merged["month"] = pd.to_datetime(merged["acq_date"]).dt.month
    merged["has_facility"] = merged["facility_id"].notnull().astype(int)
    merged["label"] = merged["decision"].map(VERIFIED_LABEL_VOCABULARY).fillna("UNKNOWN")
    merged["label_source"] = "analyst_verified"
    merged["label_quality"] = "VERIFIED"

    return merged


def _dataset_hash(df: pd.DataFrame) -> str:
    """A stable hash of the dataset's actual content, so a trained model's
    metadata can record exactly which data version produced it."""
    if df.empty:
        return "empty"
    content = pd.util.hash_pandas_object(df.sort_values("id") if "id" in df.columns else df, index=False)
    return hashlib.sha256(content.values.tobytes()).hexdigest()[:16]


def build_manifest(df: pd.DataFrame) -> dict:
    engine = create_engine(f"sqlite:///{DB_PATH}")
    total_real = pd.read_sql("SELECT COUNT(*) as n FROM hotspots WHERE source='nasa_firms'", engine)["n"][0]
    total_demo = pd.read_sql("SELECT COUNT(*) as n FROM hotspots WHERE source='demo_synthetic'", engine)["n"][0]
    total_verified_all = pd.read_sql("SELECT COUNT(*) as n FROM verifications", engine)["n"][0]

    manifest = {
        "generated_at": datetime.utcnow().isoformat(),
        "dataset_hash": _dataset_hash(df),
        "total_rows_in_dataset": len(df),
        "real_rows_in_db": int(total_real),
        "demo_rows_in_db": int(total_demo),
        "verified_rows_in_db_total": int(total_verified_all),
        "verified_rows_used_in_dataset": len(df),   # after real+verified+validity filtering
        "class_counts": df["label"].value_counts().to_dict() if not df.empty else {},
        "date_range": {
            "earliest": df["acq_date"].min() if not df.empty else None,
            "latest": df["acq_date"].max() if not df.empty else None,
        },
        "num_facilities_represented": int(df["facility_id"].nunique()) if not df.empty else 0,
        "num_states_represented": int(df["state"].nunique()) if not df.empty and "state" in df.columns else 0,
        "label_source_counts": df["label_source"].value_counts().to_dict() if not df.empty else {},
        "missing_value_counts": df[REQUIRED_FIELDS].isnull().sum().to_dict() if not df.empty else {
            f: 0 for f in REQUIRED_FIELDS
        },
    }
    return manifest


def dataset_stats() -> dict:
    """Used by GET /ml/labeling/stats — real counts, no fabrication."""
    engine = create_engine(f"sqlite:///{DB_PATH}")
    try:
        total_real = pd.read_sql("SELECT COUNT(*) as n FROM hotspots WHERE source='nasa_firms'", engine)["n"][0]
        total_verified = pd.read_sql(
            "SELECT COUNT(*) as n FROM hotspots h JOIN verifications v ON h.id = v.hotspot_id "
            "WHERE h.source='nasa_firms'", engine
        )["n"][0]
        class_dist_df = pd.read_sql(
            "SELECT v.decision, COUNT(*) as n FROM hotspots h JOIN verifications v ON h.id = v.hotspot_id "
            "WHERE h.source='nasa_firms' GROUP BY v.decision", engine
        )
        class_distribution = dict(zip(class_dist_df["decision"], class_dist_df["n"]))
    except Exception:
        total_real, total_verified, class_distribution = 0, 0, {}

    return {
        "total_real_observations": int(total_real),
        "verified_observations": int(total_verified),
        "unverified_observations": int(total_real - total_verified),
        "class_distribution": class_distribution,
    }


def save_dataset_and_manifest():
    os.makedirs(OUT_DIR, exist_ok=True)
    df = build_dataset()
    manifest = build_manifest(df)

    csv_path = os.path.join(OUT_DIR, "kavach_training_dataset.csv")
    manifest_path = os.path.join(OUT_DIR, "dataset_manifest.json")

    df.to_csv(csv_path, index=False)
    with open(manifest_path, "w") as f:
        json.dump(manifest, f, indent=2, default=str)

    print(f"Saved {len(df)} rows to {csv_path}")
    print(f"Saved manifest to {manifest_path}")
    return df, manifest


if __name__ == "__main__":
    stats = dataset_stats()
    print(f"Real NASA FIRMS observations: {stats['total_real_observations']}")
    print(f"Verified (usable for training): {stats['verified_observations']}")
    print(f"Unverified: {stats['unverified_observations']}")
    print(f"Class distribution among verified: {stats['class_distribution']}")
    if stats["verified_observations"] < 30:
        print("\nInsufficient validated observations for reliable supervised model evaluation. "
              "Verify more real observations via POST /hotspots/{id}/verify before training.")
    else:
        save_dataset_and_manifest()
