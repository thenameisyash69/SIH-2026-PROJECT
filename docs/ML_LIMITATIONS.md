# ML Limitations — stated plainly

## Current state (checked, not assumed)

- **0 real observations exist in any persistent database right now.** Real
  NASA data (79 valid rows after quality checks) was fetched and run through
  the real pipeline via a sandbox test harness in this pass, but that data
  lives in an in-memory test store, not `backend/sih.db` — the user's real
  environment (confirmed `FIRMS_MAP_KEY` working) is where real persistent
  ingestion must happen. Loading it there uses
  `backend/scripts/load_real_firms_snapshot.py` or
  `data-pipeline/ingest_firms.py` / `scripts/bootstrap_firms_history.py`.
- **0 human-verified labels exist anywhere.** No model can be trained until
  a person clicks through `POST /hotspots/{id}/verify` at least
  `MIN_VERIFIED_FOR_TRAINING = 30` times on real observations.
- **0 of the 79 real, valid detections pulled in this pass matched any of
  the 12 curated demo facilities** within the 5km match radius — a real,
  load-bearing finding: the facility registry's small size means most real
  detections currently accrue no facility-specific baseline value at all.
  This is the single most important thing to fix before real training data
  will be meaningful (see `docs/ML_TRAINING_PIPELINE.md`).

## Structural limitations

- **No temporal split** — only facility-aware, not facility+time
  (see `docs/ML_SPLIT_METHODOLOGY.md` for why this wasn't attempted yet).
- **Rule-vs-ML comparison's `behavior_label` is approximated**, not exactly
  reconstructed, because it isn't persisted on `Hotspot` rows (see
  `ml/evaluate.py`'s module docstring).
- **Small facility registry (12) fundamentally caps dataset richness** —
  even with abundant real FIRMS detections, most will have no facility
  context until the registry grows (schema already supports
  `source: "osm_derived"` for this, ingestion job not built).
- **`MODEL_SCORE_ABSTENTION_THRESHOLD = 0.45`** in `classifier.py` is a
  conservative, documented, but uncalibrated cutoff — not derived from any
  validation curve, because there isn't yet a validation set to derive it from.

## What "trained" will and won't mean, honestly, even once it happens

Per this project's own stated rule: a model is only "successfully trained"
when REAL DATA → VALIDATED LABELS → TRAINING → HELD-OUT EVALUATION → MODEL
ARTIFACT → LIVE INFERENCE has actually been demonstrated end-to-end. Given
the current real-verified-label count is 0, **no model has met this bar**,
and `/model-performance` will honestly report `NO_TRAINED_MODEL` until it does.
