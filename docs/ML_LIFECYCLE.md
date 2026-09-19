# ML Lifecycle — Real Training, Honestly

*This document is the entry point for the full ML lifecycle work in this
pass. It answers Phase 1's 7 required audit questions, then links to the
rest of the pipeline docs.*

## Phase 1 audit answers

1. **Which features already exist?** `feature_engine.build_features()`
   computes a rich dict; the ML-facing subset is centralized in
   `app/services/feature_schema.py` (`FEATURE_SCHEMA`, 6 named features:
   brightness, confidence, month, has_facility, z_score, persistence_score) —
   fixed in a prior pass from two independently-maintained lists into one.
2. **Which features does classifier.py expect?** Exactly the schema above,
   accessed via `feature_schema.vector_from_features()` — never a raw
   positional list anymore.
3. **Which model type is already implemented?** XGBoost
   (`XGBClassifier`, `ml/train.py`), multiclass, with a facility-aware
   train/test split. No competing model type exists — this pass extends
   the existing one, does not replace it.
4. **Where is classifier.pkl expected?**
   `backend/app/services/classifier.pkl` (single file). This pass adds
   VERSIONED artifacts alongside it (`ml/models/classifier_xgb_v001.pkl` +
   `.json` metadata) with automatic "latest valid version" loading — see
   Phase 7 section below. The single deployed file at the path
   `classifier.py` reads is still authoritative for what the running app
   actually uses; the versioned archive is the historical record.
5. **How are predictions represented?** `classifier.classify()` returns
   `category`, `classification_method` ("rules"/"ml_model"),
   `classification_confidence` (a **model score**, never called
   "probability"), `model_version`. Stored on `Hotspot` with matching
   column names.
6. **How does the pipeline invoke classification?** Single call site:
   `pipeline.process_observation()` → `classifier.classify(features)`.
   Verified via grep — no second classification path exists anywhere.
7. **How do real FIRMS observations enter the pipeline?**
   `firms_ingestion.sync_once()` (live, scheduled + manual) and
   `scripts/bootstrap_firms_history.py` (historical backfill) both call
   `pipeline.process_observation()` — same single orchestrator, source
   always tagged `nasa_firms`.

## What this pass adds (see linked docs for full detail)

- `docs/TRAINING_DATASET.md` — Phase 2/4, real dataset + report
- `docs/MODEL_CARD.md` — Phase 7, versioned artifact + metadata contract
- `docs/ML_VALIDATION.md` — Phase 6/10, evaluation methodology + live inference proof
- `docs/POST_ML_STATUS.md` — the required final 10-point report

## The one constraint that shapes everything else in this pass

This development sandbox has no network access for the Python backend
itself (confirmed repeatedly across this project's build history — blocked
`pip`/`apt`, 403). Real NASA data used in this pass was fetched via a
separate tool with genuine internet access (real, current, not fabricated —
99 rows, 79 valid after quality checks, see `docs/TRAINING_DATASET.md`),
but true deep historical archive access requires either an Earthdata Login
(not available here) or the live Area API with a real `FIRMS_MAP_KEY` run
from an environment with real internet access (the user's, not this
sandbox's). `xgboost`/`scikit-learn` are also not installable here. This
means: **this pass cannot execute a real supervised training run.** Every
section below states plainly what was and wasn't actually executed.
