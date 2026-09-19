# ML Validation — Methodology & Real Results

## What "honest evaluation" means in this codebase

`ml/evaluate.py` computes, on a facility-aware held-out test set:
accuracy, macro precision/recall/F1, weighted F1, per-class precision/
recall/F1, support, confusion matrix, and balanced accuracy — then runs
the SAME test rows through the deterministic rule engine
(`classifier.rule_based_classify`, via an approximated `behavior_label` —
see `ml/evaluate.py`'s module docstring for the exact limitation of that
approximation) for a rule-vs-ML comparison. Neither script has ever
produced a real number in this project's history, because 0 verified real
labels exist — this is stated plainly, not glossed over.

## Real results as of this pass

**None exist.** `python ml/evaluate.py` requires a trained model at
`ml/models/classifier_xgb_v*.pkl`, which does not exist, and would refuse
to run meaningfully even if it did, because `ml/dataset_builder.py`
returns an empty dataset (0 verified real labels).

## Phase 10 — live inference proof (this WAS actually executed)

Evaluation metrics require a trained model; **live inference through the
full pipeline does not**, and was genuinely run in this pass against real
NASA FIRMS data:

```
Source:             nasa_firms
Satellite:          VIIRS_Suomi_NPP
Acquisition:        2026-09-06T20:27:00
Facility:           None matched
Distance:           None km
Brightness:         339.28
Confidence:         60.0
FRP:                9.48
Land cover:         unknown
Engine:             RULE ENGINE FALLBACK
Model version:      N/A (rule engine)
Prediction:         unknown
Model score:        0.3
Baseline status:    INSUFFICIENT_HISTORY
Anomaly:            no
Risk:               WATCH (score 0.0)
```

Full output: `data-pipeline/metadata/live_inference_proof_output.txt`,
produced by `backend/tests/run_live_inference_proof.py`. Note the honest
`Engine: RULE ENGINE FALLBACK` line — this run does NOT claim an XGBoost
prediction, because none exists. `land_cover: unknown` and
`Facility: None matched` are also both real, not simplified for the demo —
this sandbox can't reach the Overpass API, and this particular real
detection genuinely wasn't near any of the 12 curated facilities.

## Baseline vs. XGBoost comparison

Not run — requires a trained model, which doesn't exist. When it can be
run, `ml/evaluate.py` will report both models' macro F1 side-by-side and
state plainly whether XGBoost actually improves on the rule engine —
including printing that fact if XGBoost does NOT improve, per this
project's explicit no-hiding-bad-results rule.

## Calibration status

Not implemented. `classifier.py`'s output is always called a **"model
score,"** never "probability" or "confidence," anywhere in the API
responses or frontend — grep-verifiable.
