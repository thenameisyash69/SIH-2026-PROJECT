# Kavach — Industrial Fire & Thermal Anomaly Detection
### SIH 2026 · Problem Statement 162

AI-enabled geospatial system that classifies satellite-detected thermal
anomalies (industrial fires, gas flares, wildfires, agricultural burning)
and flags abnormal industrial thermal behaviour for follow-up.

## Fastest way to see it running (no API keys needed)

```bash
# 1. Backend
cd backend
python -m venv venv && source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -r requirements.txt
python -m scripts.seed          # loads demo facilities + 15 days of synthetic hotspot history
uvicorn app.main:app --reload   # http://localhost:8000/docs for the live API

# 2. Frontend (new terminal)
cd frontend
npm install
npm run dev                     # http://localhost:5173
```

The dashboard works even before you run the backend (it falls back to
`src/demoData.js`) — but seed the DB and start the API for the real thing,
including the chatbot and live alerts.

## Going further

| Step | Where |
|---|---|
| Pull real satellite hotspot data | `data-pipeline/ingest_firms.py` (needs a free [FIRMS API key](https://firms.modaps.eosdis.nasa.gov/api/)) |
| Enable LLM-phrased chatbot answers | set `ANTHROPIC_API_KEY` in `backend/.env` |
| Full stack with Postgres | `docker-compose up --build` |

## Training the real ML classifier (do this once you have data)

The system runs on a transparent rule engine out of the box (`classified_by: "rules"`
on every hotspot). To switch on the trained model:

```bash
cd ml
pip install -r requirements.txt
python train.py
# copy the output model so the backend picks it up automatically:
cp models/classifier.pkl ../backend/app/services/classifier.pkl
```

Restart the backend — new hotspots will now show `classified_by: "ml_model"`
along with the model's confidence score in the `reason` field. No other code
changes needed; `classifier.py` checks for this file automatically on startup.

## What's now implemented (beyond the original MVP)

- **Explainable classification** — every hotspot carries a plain-English `reason`
  and whether it was labeled by the rule engine or the trained model.
- **Satellite imagery** — real NASA GIBS true-color imagery for any hotspot's
  location and date, no API key required (`/hotspots/{id}/satellite-image`).
- **Thermal history / time-lapse** — a per-facility brightness chart over time,
  with anomalous readings highlighted (`/hotspots/{id}/history`, `Timeline.jsx`).
- **Quantified impact stats** — facilities monitored, estimated coverage area,
  anomaly rate, and how many detections were ML- vs rule-classified (`/stats`).
- **Trained ML classifier** — `ml/train.py` trains XGBoost on real seeded/ingested
  data; the backend automatically prefers it over rules once present.

## Architecture

```
NASA FIRMS ──┐
Bhuvan/OSM ──┼──▶ data-pipeline/ingest_firms.py ──▶ Postgres/SQLite ──▶ FastAPI ──▶ React dashboard
Facility DB ─┘                                            ▲
                                          ml/train.py ─────┘ (classifier.pkl)
```

See `/docs` in the full project blueprint for the day-by-day build plan,
future-scope ideas (CNN on raw imagery, TEE for sensitive facility data,
CCTV/drone hybrid for live visual confirmation), and presentation structure.
