# Kavach Architecture

```
NASA FIRMS ──┐
OSM/Overpass ┼──▶ THERMAL EVENT INGESTION (data-pipeline/ingest_firms.py, scripts/seed.py)
Facility DB ─┘                    │
                                   ▼
                    app.services.pipeline.process_observation()
                     (the ONE path both real and demo data go through)
                                   │
        ┌──────────────┬──────────┼───────────┬───────────────┐
        ▼              ▼          ▼            ▼               ▼
 facility_matcher  baseline_   feature_    classifier      evidence_
   .py               engine.py   engine.py    .py             engine.py
        │              │          │            │               │
        └──────────────┴──────────┴─────┬──────┴───────────────┘
                                         ▼
                              anomaly_engine.py
                                         │
                                         ▼
                               risk_engine.py
                                         │
                                         ▼
                          models.Hotspot (+ Alert if HIGH/CRITICAL)
                                         │
                    ┌────────────────────┼────────────────────┐
                    ▼                    ▼                    ▼
              FastAPI routers      React dashboard      Chatbot (rag_engine.py
           (hotspots/facilities/                         — retrieves DB rows,
            alerts/stats/                                 optionally has Claude
            data-sources)                                 phrase them; never
                                                            invents facts)
```

## Why a single pipeline module

Before this pass, `seed.py` and `ingest_firms.py` each called the classifier
and anomaly logic slightly differently, and would have silently drifted apart
over time (documented as a P1 finding in `IMPLEMENTATION_AUDIT.md`). Now both
call `pipeline.process_observation()` — one code path, one behavior, whether
the data is real or synthetic.

## Design boundaries

- **React** — presentation only. No business logic beyond simple UI state.
- **FastAPI routers** — thin HTTP layer: parse request, call a service, return schema.
- **Services** (`app/services/`) — all actual intelligence lives here, one
  concern per file, each independently testable.
- **ML** (`ml/`) — training and evaluation only; the trained artifact is a
  plain pickle file the backend loads read-only.
- **Database** — persistence only; raw source observation fields are never
  overwritten by derived values (see `models.py` comments).

## Live ingestion path (this pass)

```
FIRMS_MAP_KEY configured?
        │
    ┌───┴───┐
   YES       NO → sync_once() returns success=False immediately,
    │              records an honest IngestionRun row, no fabrication
    ▼
firms_fetcher.fetch_firms_hotspots()  — one HTTP request per configured
    │                                    sensor (VIIRS_NOAA21_NRT +
    │                                    VIIRS_NOAA20_NRT by default),
    │                                    never one request per point
    ▼
firms_ingestion.sync_once()
    │  for each raw observation:
    │    - tag_land_cover()
    │    - pipeline.process_observation()  ← same orchestrator as seed.py
    │                                        and bootstrap_firms_history.py
    ▼
IngestionRun row recorded (fetched/inserted/duplicate counts, success/error)
    │
    ▼
GET /data-sources/status  ← reads IngestionRun, reports LIVE/STALE/OFFLINE
POST /data-sources/firms/sync  ← triggers the above on demand
main.py's _firms_sync_loop()   ← triggers the above automatically every
                                   FIRMS_SYNC_INTERVAL_MINUTES
```

`data-pipeline/ingest_firms.py` and `backend/scripts/bootstrap_firms_history.py`
are thin CLI wrappers around the same `firms_ingestion` module — no
ingestion logic is duplicated across the manual script, the historical
bootstrap, the HTTP endpoint, and the background loop.
