# Training Dataset Report

*Real numbers from `backend/tests/run_dataset_report.py`, run against the
real NASA FIRMS snapshot data in `data-pipeline/raw/` — genuinely fetched
from NASA's public feed (MODIS Terra + VIIRS Suomi-NPP, South Asia region,
2026-09-06/07), not fabricated. Machine-readable version:
`data-pipeline/metadata/dataset_report.json`. In the user's real
environment (confirmed live `FIRMS_MAP_KEY`), the authoritative command is
`python -m scripts.build_training_dataset`, which reads the real
persistent database instead of this snapshot.*

## Dataset report

| Metric | Value |
|---|---|
| Total observations | 79 |
| Unique observations (after pipeline dedup) | 79 |
| Duplicates caught and skipped | 2 |
| Facility-associated observations | **0** |
| Verified labels | **0** |
| Curated labels | 0 |
| Weak labels available (pipeline category, reference only) | 79 |
| Missing brightness | 0 |
| Missing FRP | 0 |
| Date range | 2026-09-06 02:47 UTC → 2026-09-07 03:32 UTC |
| Satellite distribution | MODIS_Terra: 35, VIIRS_Suomi_NPP: 44 |
| Geographic coverage (states matched to a facility) | none — see below |

## STOP — training cannot proceed, and here's exactly why

Per Phase 4's explicit instruction: this dataset is **insufficient for
reliable ML training**, and training is not attempted. Two independent
reasons, either of which alone would be disqualifying:

1. **Zero verified labels.** `MIN_VERIFIED_FOR_TRAINING = 30` (in
   `ml/train.py`, `GET /ml/labeling/stats`). No human has verified any
   observation via `POST /hotspots/{id}/verify` — not in this snapshot,
   and (per `docs/ML_LIFECYCLE.md`) not anywhere in this project's real
   database either, as far as this pass can determine.

2. **Zero facility associations.** Even if labels existed, 0 of these 79
   real detections fell within 5km of any of the 12 curated demo
   facilities. This means the facility-specific features that make Kavach
   different from a plain classifier — baseline deviation, persistence,
   behavior label — would all be `INSUFFICIENT_HISTORY`/null for every
   single row in this dataset. A model trained on this data could not
   learn to use those features at all, even with enough labels.

## What's actually needed before training can happen

1. Ingest real FIRMS data in an environment with a working `FIRMS_MAP_KEY`
   (the user's, not this sandbox) over enough time that some real
   detections land near a curated facility, OR grow the facility registry
   (schema already supports `source: "osm_derived"` for this).
2. Get at least 30 of those real observations analyst-verified.
3. Only then does `python -m scripts.build_training_dataset` produce a
   report clearing the bar, and only then should `ml/train.py` be run.

## Why "0 facility-associated" is itself useful information

This isn't a wasted finding — it's the single most concrete piece of
evidence in this whole pass that the 12-facility registry is the real
bottleneck for the ML story, ranked above the ML code itself. See
`docs/POST_ML_STATUS.md` for this as the explicit "next step."
