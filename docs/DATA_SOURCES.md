# Data Sources

| Source | What it provides | Key required | Status endpoint |
|---|---|---|---|
| NASA FIRMS | Raw VIIRS/MODIS thermal anomaly detections | Yes (free, instant) | `GET /data-sources/status` |
| NASA GIBS Worldview Snapshot | Real satellite imagery for any lat/lon/date | No | same |
| OpenStreetMap Overpass API | Land-use tagging (industrial/forest/agricultural/urban) | No | same |
| Anthropic Claude API | Natural-language phrasing of chatbot answers | No (optional) | same |

`GET /data-sources/status` reports the REAL, checked state of each source —
it never reports "ok" for FIRMS unless real `nasa_firms`-sourced rows actually
exist in the database, and never reports "ok" for the ML model unless a
trained `classifier.pkl` file is actually present on disk.

## Live ingestion architecture (this pass)

`app/services/firms_ingestion.py` is now the single service both the
background scheduler (`main.py`'s `_firms_sync_loop`) and the manual
`POST /data-sources/firms/sync` endpoint call — see `docs/LIVE_DATA_SETUP.md`
for full setup instructions and `docs/ARCHITECTURE.md` for the data flow
diagram. Every sync attempt (success or failure) is recorded in the
`IngestionRun` table, which is what `/data-sources/status` reads from —
status is never inferred from "does real data currently exist," only from
"did a real sync attempt actually succeed, and how recently."
