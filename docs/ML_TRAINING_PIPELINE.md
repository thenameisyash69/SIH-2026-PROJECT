# ML Training Pipeline — Audit & Design

## Phase 0 audit findings (answering the 10 required questions)

1. **What features currently exist?** `feature_engine.build_features()` computes a
   rich dict (brightness, confidence, frp, distance_to_facility_km, facility_type,
   facility_criticality, land_cover, month, z_score, deviation_percentage,
   baseline_status, observation_count, persistence_score, recent_7/30/60d_count,
   behavior_label). But only 6 of these ever reached the model:
   `feature_engine.ml_feature_vector()` hardcoded a reduced list
   (`brightness, confidence, month, has_facility, z_score, persistence_score`),
   and `ml/train.py` had **its own separate, independently-maintained**
   `FEATURE_COLUMNS` list that had to be kept in sync by hand. **This is exactly
   the "one feature list in train.py and another in classifier.py" problem
   Phase 5 warns about — confirmed as a real, pre-existing defect, not
   hypothetical.** Fixed in this pass (see `app/services/feature_schema.py`).

2. **What labels currently exist?** Two label sources existed and were being
   conflated across different points in the project's history:
   (a) `Hotspot.category` — the pipeline's own rule-engine output, and
   (b) `Verification.decision` — real human judgment. The most recent version
   of `ml/train.py` (from the live-ingestion pass) correctly used (b), but there
   was no shared, documented label-provenance model — fixed here via
   `ml/label_builder.py`.

3. **What dataset does train.py currently use?** `ml/dataset_builder.py`
   builds from `Hotspot ⋈ Verification` where `source='nasa_firms'` — real
   observations only, verified labels only. This part was already correct
   from the prior pass.

4. **Does it currently use synthetic/demo data?** No — `source='nasa_firms'`
   is hard-filtered in the SQL query. Confirmed by reading the query directly,
   not assumed.

5. **Where does classifier.py expect classifier.pkl?**
   `backend/app/services/classifier.pkl` (same directory as `classifier.py`,
   loaded via `os.path.dirname(__file__)`). This is a slightly unusual location
   for a model artifact (mixed into source code directory) — spec suggests
   `backend/models/classifier.pkl` as cleaner. **Decision: keep the existing
   path.** Moving it would touch `classifier.py`'s loader, `data_sources.py`'s
   status check, and `model_performance.py`'s existence check, for a purely
   cosmetic gain, which risks breaking a working, tested path for no functional
   benefit — deferred per "do not rebuild working systems."

6. **What exact feature order does the classifier expect?** Previously:
   whatever order `ml_feature_vector()` happened to return, matched by
   position (not name) against `FEATURE_COLUMNS` in train.py — a fragile,
   silent-failure-prone contract (if the two lists' order ever diverged, the
   model would silently receive mislabeled inputs with zero error). **Fixed**:
   `feature_schema.py` now defines features as named, ordered entries; both
   training and inference build vectors by name lookup, not raw positional trust.

7. **What classes are currently supported?** `confirmed_industrial`,
   `confirmed_wildfire`, `confirmed_agricultural`, `confirmed_static_thermal`,
   `unknown` (human verification vocabulary) vs. the pipeline's own
   `industrial_normal/industrial_alert/industrial_new/wildfire/
   agricultural_burning/unknown` (rule-engine vocabulary) — **these are two
   different taxonomies that were never explicitly reconciled.** This pass
   documents the mapping explicitly in `label_builder.py` rather than leaving
   it implicit.

8. **How is a missing model handled?** `classifier.py`'s `_load_model()`
   returns `None` if `classifier.pkl` doesn't exist; `classify()` falls back
   to `rule_based_classify()`. This was already correct and is unchanged.

9. **How does pipeline.py call the classifier?**
   `pipeline.process_observation()` → `classifier.classify(features)` →
   tries ML, falls back to rules. Single call site, no second classification
   path exists anywhere else in the codebase (verified via grep).

10. **What changes are required to support a real trained artifact?**
    (a) centralize the feature contract (`feature_schema.py`), (b) add
    explicit low-score abstention to `UNKNOWN` (previously the model would
    always commit to its top-scoring class regardless of confidence), (c) add
    model versioning metadata so a prediction can be traced to the exact
    model/feature-schema version that produced it, (d) add feature-schema
    mismatch detection so a stale/incompatible `classifier.pkl` fails safely
    to `UNKNOWN` rather than silently misclassifying.

## Current real-data status (checked, not assumed)

As of this pass: the user has confirmed `FIRMS_MAP_KEY` is configured and
readable in their real (non-sandbox) environment. This development sandbox
still has no network access for the Python backend itself, but real, current
NASA FIRMS data (81 India-bbox observations, fetched live via a separate
tool with real internet access) was pulled and is used in this pass as a
one-time real-data snapshot — see `docs/ML_DATA_QUALITY.md` and
`backend/scripts/load_real_firms_snapshot.py`. **Zero of these 81 observations
have been human-verified yet** — verification is a manual step the user must
do via the UI. This means: real data now exists in principle, but the
training pipeline correctly and honestly cannot proceed past the dataset-
quality stage yet, because there are 0 verified labels. This is reported
plainly in the final report below, not glossed over.
