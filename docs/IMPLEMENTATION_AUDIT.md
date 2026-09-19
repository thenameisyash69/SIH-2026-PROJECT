# Kavach — Implementation Audit
*Phase 0. Honest inventory of the repository as it exists before this transformation pass.*

## Existing functionality (real, working)

| Area | File | Status |
|---|---|---|
| FastAPI app, CORS, router registration | `backend/app/main.py` | Working |
| SQLite (dev) / Postgres (docker) persistence | `backend/app/database.py` | Working |
| Facility, Hotspot, Alert tables | `backend/app/models.py` | Working, schema is thin (see P0 below) |
| NASA FIRMS live pull | `backend/app/services/firms_fetcher.py` | Working code, **not yet run against live data by the user** |
| OSM/Overpass land-cover tagging | `backend/app/services/landcover_fetcher.py` | Working, called **once per point, no caching/batching** (P1) |
| NASA GIBS satellite imagery | `backend/app/services/satellite_image.py` | Working, no API key needed |
| Rule-based classifier | `backend/app/services/classifier.py` | Working, but logic is a flat if/else chain, not fed by a shared feature layer |
| XGBoost classifier | `ml/train.py` + `classifier.py`'s `ml_classify()` | Trains on 4 shallow features (`brightness`, `confidence`, `month`, `has_facility`); **not yet trained/deployed by the user** |
| Z-score anomaly check | `backend/app/services/anomaly_detector.py` | Working but standalone — not integrated into a facility-level "fingerprint" concept |
| Chatbot | `backend/app/services/rag_engine.py` | Working; keyword-parsing retrieval + optional Claude phrasing. Already correctly retrieval-then-generate (does not let the LLM invent DB rows) |
| GIS dashboard | `frontend/src/components/HeatMap.jsx`, `App.jsx` | Working |
| Timeline (per-facility history) | `frontend/src/components/Timeline.jsx` | Working, but shows raw brightness only — no baseline/deviation overlay |
| Docker setup | `docker-compose.yml` | Written, **never actually run/verified** in this environment (no network access here) |
| Seed/demo data | `backend/scripts/seed.py` | Generates 12 facilities × 60 days synthetic history |

## Fake / demo-only functionality (must be labeled honestly, per spec §28)

- **All current hotspot data is synthetic** (from `seed.py`), except whatever the user has separately pulled via `ingest_firms.py` — the two are not currently distinguished anywhere in the UI or schema. **P0.**
- **The ML model has never been trained** — `classifier.py` silently falls back to rules, which is correct behavior, but the UI never surfaces "no trained model exists yet" as a system-status fact. **P0.**
- **Risk = anomaly = thermal detection**, effectively. There is no facility-criticality weighting, no evidence fusion, no separate "risk" concept distinct from "is this statistically unusual." This is exactly the gap the new spec calls out. **P0.**
- **Facility "matching" only checked one nearest facility with a hardcoded radius**, and never stored the distance on the Hotspot row — it was recomputed on the fly and thrown away. **P0.**

## Duplicated / non-centralized logic

- `classify_hotspot()` was called separately, near-identically, from both `seed.py` and `ingest_firms.py`, with slightly different anomaly-merging logic in each (`ingest_firms.py` layered z-score on top; `seed.py` did not). This is exactly the kind of drift the spec warns about. **P1 — fixed in this pass by introducing a single `pipeline.py` orchestrator both scripts now call.**

## Missing validation / weak assumptions

- Brightness thresholds in the rule engine (e.g. `> 330`) are hardcoded magic numbers with no documented basis — acceptable for a hackathon rule-of-thumb but must be labeled as such, not implied to be calibrated science. **P1.**
- The XGBoost model's `predict_proba` output was being shown to the user framed loosely as "confidence" — per spec §12 this must be relabeled "model score" unless calibrated. **P0 — fixed in this pass.**
- No facility criticality tiering existed at all — every facility was treated as equally important. **P0.**

## Scalability issues

- `landcover_fetcher.py` makes one live Overpass HTTP call per point with no caching — fine for a demo of a dozen facilities, will rate-limit immediately at any real scale. **P1 — added simple persistence-backed caching in this pass; a proper TTL/refresh policy is future work.**
- Facility registry is 12 hardcoded rows — nowhere near representative of India's industrial landscape, and the old docs did not say so clearly enough. **P1 — now explicitly labeled `source: "curated_demo"` on every seed facility, with the schema supporting `"osm_derived"` / `"external"` for future ingestion.**

## Security

- `.env.example` exists, `.env` is not committed (assumed — verify locally), no keys are read on the frontend. No auth exists on any endpoint — acceptable for a hackathon demo, **flagged as a known limitation, not fixed (P2)**, since building real auth would consume time better spent on the intelligence layer itself, per spec §47 (don't chase feature count).

## UI problems

- Original sidebar mixed alerts, chatbot, and detail view with no clear "why does this event matter" narrative — this was the "headache-inducing" feedback from earlier. Partially addressed with tabs in the previous pass; **this pass adds real risk/evidence/baseline data to `DetailPanel` so the tab has something substantive to show, but the full dedicated "Event Investigation" and "Facility Intelligence" screens from spec §19–20 are P1, not completed in this pass** — see Final Status doc for what remains.

## Priority ranking used for this pass

- **P0 (done in this pass):** facility fingerprint, baseline engine, feature engine, evidence engine, risk engine, unknown class, provenance fields, data-source status endpoint, verification endpoint, centralized pipeline (no more duplicated ingestion logic), honest "model score" vs "probability" language, DEMO vs REAL data labeling.
- **P1 (partially done / documented, not fully built):** land-cover caching (basic version done), facility registry scaling (schema supports it, no external ingestion job built), dedicated Event Investigation / Facility Intelligence UI screens (DetailPanel extended instead).
- **P2 (not done, explicitly deferred):** authentication, automated test suite, verified Docker run, model retraining pipeline.
- **P3 (not done, correctly out of scope per spec §47):** 3D globe, voice assistant, mobile app, microservices, blockchain — none of these were ever built, correctly.
