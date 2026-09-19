# ML Evaluation Approach

## The circularity problem this fixes

An earlier version of `ml/train.py` trained on the `Hotspot.category`
column — which is the pipeline's own rule-engine output. A model trained
this way can only ever learn to imitate the rule engine; it has no way to
learn anything the rules don't already encode, and "high accuracy" would
mean nothing more than "successfully reproduced deterministic if/else
logic." This is a well-known failure mode in ML systems built on top of
rule-based bootstrapping, and it was present in this codebase until this
pass.

## The fix: train on human-verified ground truth only

`ml/dataset_builder.py` now builds the training set from
`Hotspot ⋈ Verification` (inner join) — only rows a human analyst has
actually confirmed via `POST /hotspots/{id}/verify`, and only where
`source = "nasa_firms"`. `demo_synthetic` rows are never used as
supervised training labels, even though they're perfectly fine for
demoing the *interface* and for facility-baseline bootstrapping in the
demo environment (which needs brightness history, not labels).

## Minimum data bar

`MIN_VERIFIED_FOR_TRAINING = 30` in both `ml/train.py` and
`GET /ml/labeling/stats`. Below this, both refuse to produce metrics and
instead print/return the exact sentence:

> "Insufficient validated observations for reliable supervised model
> evaluation."

This is enforced in code, not just written in a doc — `train()` returns
early without touching `XGBClassifier` at all if the check fails.

## Validation methodology

Facility-aware split (`facility_aware_split()` in `ml/train.py`): rows are
grouped by `facility_id` before splitting, so no facility's observations
appear in both train and test. A naive random row-level split would let
the model partially memorize a facility's specific baseline rather than
learn generalizable features — this was flagged and fixed in an earlier
pass (see `docs/PIPELINE_VALIDATION.md`) and remains in place here.

## What "model score" means (and doesn't)

`classifier.ml_classify()` reports `predict_proba()`'s output as a "model
score." This is explicitly **not** a calibrated probability — no Platt
scaling or isotonic calibration has been applied, and with a small number
of distinct facilities, there isn't yet enough data to calibrate one
meaningfully. `/model-performance` and every UI surface referring to this
number use the phrase "model score," never "confidence" or "probability."

## Current status in this environment

No model has been trained in this development sandbox: `xgboost` and
`scikit-learn` are not installable here (no network access — see
`docs/PIPELINE_VALIDATION.md`), and even if they were, this environment
has zero human-verified real observations (0 real FIRMS data has been
ingested here either). `GET /model-performance` and `GET /ml/labeling/stats`
both correctly report this honestly rather than showing placeholder numbers.

**To get real metrics:** follow `docs/LIVE_DATA_SETUP.md` steps 1-7 in an
environment with normal internet access.
