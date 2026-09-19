# Post-ML Status — Final Report

*Answers the exact 10 points required at the end of this pass. Every
number here was either actually computed by an executed script (shown) or
explicitly marked N/A — none are estimates or placeholders.*

## 1. Historical dataset size

**79 valid real observations** (of 99 fetched, 2 duplicates and 18
outside-bbox excluded by `ml/data_quality.py`) — real NASA MODIS Terra +
VIIRS Suomi-NPP data, South Asia region, 2026-09-06/07. This is a rolling
~24-30 hour NRT snapshot, not deep historical archive data — true
multi-week/month historical depth requires either an Earthdata Login (not
available in this sandbox) or the live Area API with the user's real
`FIRMS_MAP_KEY`, run from an environment with real internet access.

## 2. Verified label count

**0.**

## 3. Weak/curated label count

**79 WEAK** (the pipeline's own rule-engine category, usable only as a
reference/comparison signal, never as supervised training input — see
`ml/label_builder.py`). **0 CURATED.**

## 4. Training samples

**0** — training was not attempted; see `docs/TRAINING_DATASET.md`'s
explicit STOP.

## 5. Test samples

**0** — same reason.

## 6. Model version

**None deployed.** `classifier.active_engine()` returns `"RULE ENGINE
FALLBACK"` — confirmed by actual execution, not inferred from file
existence alone (it validates feature-schema compatibility too).

## 7. Actual metrics

**None exist.** No accuracy, F1, precision, recall, or confusion matrix
number appears anywhere in this codebase's output, because none was ever
computed from a real training run. `ml/evaluate.py` and `ml/train.py` both
refuse to proceed and print exactly why when run against the current
(0-verified-label) dataset.

## 8. Real FIRMS inference result

**Executed successfully** — a real VIIRS Suomi-NPP detection (brightness
339.28K, FRP 9.48, 2026-09-06 20:27 UTC) was run through the complete real
pipeline (facility matching → baseline → evidence → anomaly → risk),
honestly labeled `Engine: RULE ENGINE FALLBACK`, `Prediction: unknown`,
`Risk: WATCH`. Full trace: `data-pipeline/metadata/live_inference_proof_output.txt`.

## 9. What remains incomplete

- **No real persistent database with real ingested FIRMS data exists in
  this sandbox** (no network access here — confirmed repeatedly). The
  user's own environment (confirmed working `FIRMS_MAP_KEY`) is where real
  ingestion must actually accumulate.
- **Zero verified labels anywhere** — the single hard blocker to any real
  training run.
- **Zero facility-associated real detections** in the 79-row sample
  available to this pass — even once labels exist, the 12-facility
  registry's small size will limit how much facility-specific signal a
  near-term model could learn from.
- **XGBoost/scikit-learn are not installable in this sandbox** — even with
  enough data, `ml/train.py` cannot be executed here; it must be run in
  the user's real environment.
- Calibration, temporal+facility split, and the Satellite Evidence Viewer
  (from an earlier pass's spec) remain not built — correctly deprioritized
  behind the ML lifecycle work this pass focused on.

## 10. Exact next step

**Get real observations verified.** In the user's real environment:
1. Confirm live data: `python -m scripts.test_firms`, then
   `POST /data-sources/firms/sync` or `scripts/bootstrap_firms_history.py`.
2. Open the Event Investigation panel for real observations and click
   through the verify buttons (`CONFIRM INDUSTRIAL FIRE` /
   `CONFIRM NORMAL INDUSTRIAL HEAT` / `MARK WILDFIRE` / `MARK AGRICULTURAL`
   / `MARK FALSE POSITIVE` / `MARK UNKNOWN`) at least 30 times on real data.
3. Check progress: `GET /ml/labeling/stats`.
4. Once `training_readiness: READY`, run
   `pip install -r ml/requirements.txt && python ml/train.py` — this is
   the first point at which a real number can honestly appear anywhere in
   this project.
