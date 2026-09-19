"""
THE single canonical feature contract for Kavach's ML classifier.

Before this file existed, `feature_engine.ml_feature_vector()` and
`ml/train.py`'s `FEATURE_COLUMNS` were two independently-maintained lists
that had to happen to agree in name AND order for the model to work
correctly — a silent-failure risk (confirmed real, not hypothetical, in
docs/ML_TRAINING_PIPELINE.md's audit). Every other place in the codebase
that builds a feature vector for the model — training, inference, dataset
building — must import FEATURE_SCHEMA from here and nowhere else.

Adding a feature: add one FeatureSpec entry below. Both train.py and
classifier.py automatically pick it up via `vector_from_features()` /
`vector_from_row()` — no second list to update.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class FeatureSpec:
    name: str                  # must match a key in feature_engine.build_features()'s output
    description: str
    missing_value: float = 0.0  # used if the feature is absent/None — never silently fabricated as something else


FEATURE_SCHEMA_VERSION = "v1"

FEATURE_SCHEMA = [
    FeatureSpec("brightness", "Raw thermal brightness/brightness-temperature reading."),
    FeatureSpec("confidence", "Source-reported detection confidence (0-100)."),
    FeatureSpec("month", "Calendar month of acquisition (1-12) — captures seasonal patterns e.g. stubble burning."),
    FeatureSpec("has_facility", "1 if a known facility was matched within range, else 0."),
    FeatureSpec("z_score", "Deviation from this facility's own historical baseline, in std-devs (clamped +-10)."),
    FeatureSpec("persistence_score", "How consistently this facility/location has shown thermal activity historically."),
]

FEATURE_NAMES = [f.name for f in FEATURE_SCHEMA]


def vector_from_features(features: dict) -> list:
    """
    Used at INFERENCE time — features dict comes from feature_engine.build_features().
    `has_facility` is derived here since build_features() stores `facility_type`
    (a string or None), not a boolean — this derivation lives in exactly one
    place now, not duplicated between train/inference.
    """
    row = dict(features)
    row["has_facility"] = 1 if features.get("facility_type") else 0
    return [_safe(row.get(spec.name), spec.missing_value) for spec in FEATURE_SCHEMA]


def vector_from_row(row: dict) -> list:
    """
    Used at TRAINING time — row comes from a pandas DataFrame row (dict-like)
    built by ml/dataset_builder.py, which already computes `has_facility`
    directly (1/0) rather than a facility_type string.
    """
    return [_safe(row.get(spec.name), spec.missing_value) for spec in FEATURE_SCHEMA]


def _safe(value, default):
    if value is None:
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def schema_signature() -> str:
    """A short string identifying this exact schema — stored in model metadata
    so a saved model can be checked against the schema that's currently live
    (Phase 19: feature-schema mismatch must fail safe to UNKNOWN, not guess)."""
    return f"{FEATURE_SCHEMA_VERSION}:{','.join(FEATURE_NAMES)}"
