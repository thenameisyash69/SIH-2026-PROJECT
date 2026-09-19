# Model Card — Kavach XGBoost Classifier

*Standard ML model-card format, filled in honestly. Fields marked "N/A —
not trained" are exactly that; nothing here is a placeholder standing in
for a real number.*

## Model status

**No model has been trained in this project's history yet.** This card
describes the *contract* the model will conform to once training actually
happens — not a trained artifact. `classifier.active_engine()` currently
returns `"RULE ENGINE FALLBACK"` — verified by actual execution (see
`data-pipeline/metadata/live_inference_proof_output.txt`).

| Field | Value |
|---|---|
| Model type | XGBoost (`XGBClassifier`, gradient-boosted trees), multiclass |
| Current version | N/A — not trained |
| Training timestamp | N/A |
| Dataset version (hash) | N/A |
| Feature schema version | v1 (`app/services/feature_schema.py`, `FEATURE_SCHEMA_VERSION`) |
| Classes | INDUSTRIAL, WILDFIRE, AGRICULTURAL, NORMAL_INDUSTRIAL_HEAT, UNKNOWN (subject to which classes have ≥1 verified example when training actually runs) |
| Feature names | brightness, confidence, month, has_facility, z_score, persistence_score |
| Training samples | N/A — 0 verified real labels exist |
| Validation/test samples | N/A |
| Macro F1 / precision / recall | N/A — not evaluated |
| Confusion matrix | N/A |

## Artifact location & versioning (Phase 7)

- Versioned artifacts: `ml/models/classifier_xgb_v001.pkl`, `v002`, etc. —
  auto-incrementing, no manual renaming needed (`ml/train.py`'s
  `next_version_number()`).
- Matching metadata: `ml/models/classifier_xgb_v001.json` (per-version) and
  `ml/models/metadata.json` (always the latest, for `/model-performance`'s
  quick lookup).
- **Loading is fully automatic** — `classifier.py` scans `ml/models/` on
  first use, tries the highest version number first, validates its
  feature-schema signature against the currently-running code, and uses
  the first compatible one. No manual `cp` step required, and a
  schema-incompatible artifact is skipped (not force-loaded) with a clear
  log line explaining why.
- Legacy fallback: `backend/app/services/classifier.pkl` (single
  unversioned file) is still checked if no versioned artifacts exist, for
  backward compatibility with earlier passes of this project.

## Intended use

Classifying a real NASA FIRMS thermal detection as INDUSTRIAL / WILDFIRE /
AGRICULTURAL / NORMAL_INDUSTRIAL_HEAT / UNKNOWN, as one input to Kavach's
anomaly/risk assessment — never as a standalone "this is definitely a fire
of type X" claim. The model's output is a **model score**, never called a
"probability" or "confidence" without calibration (none has been
implemented — see `docs/ML_VALIDATION.md`).

## Training data (once it exists)

REAL (`source=nasa_firms`) observations ONLY. `demo_synthetic` rows are
never used as supervised training input. Labels come from
`Verification.decision` (human analyst judgment via
`POST /hotspots/{id}/verify`), never from the pipeline's own rule-engine
`category` output — training on the latter would be circular (the model
could only ever learn to imitate the rules). `false_positive`
verifications are excluded from training entirely (see
`ml/label_builder.py`), not mapped to UNKNOWN.

## Known limitations (will remain true even once trained, given current data)

- Small facility registry (12 curated facilities) — most real detections
  currently have no facility association at all (0 of 79 in this pass's
  real snapshot), meaning facility-specific features will be null/
  `INSUFFICIENT_HISTORY` for a large fraction of any near-term training set.
- Abstention threshold (`MODEL_SCORE_ABSTENTION_THRESHOLD = 0.45` in
  `classifier.py`) is a conservative, documented guess, not derived from a
  validation curve.
- Facility-aware split only, not facility+temporal (see
  `docs/ML_SPLIT_METHODOLOGY.md`).
