# Live Data Setup — Getting Kavach Off Demo Mode

## 1. Get a FIRMS MAP_KEY (free, instant)

1. Go to https://firms.modaps.eosdis.nasa.gov/api/map_key/
2. Enter your email — a key is emailed within seconds, no approval wait.
3. Copy it.

## 2. Configure `.env`

In `backend/.env` (copy from `.env.example` if it doesn't exist yet):

```
FIRMS_ENABLED=true
FIRMS_MAP_KEY=your_real_key_here
FIRMS_AREA=68,6,97,37          # west,south,east,north — default is India
FIRMS_SOURCES=VIIRS_NOAA21_NRT,VIIRS_NOAA20_NRT
FIRMS_SYNC_INTERVAL_MINUTES=15
```

`FIRMS_MAP_KEY` is read server-side only (`app/config.py`) and is never
included in any API response — verified by grep across every router.

## 3. Historical bootstrap (do this BEFORE relying on baselines/fingerprints)

Facility baselines need real history to mean anything — a facility with
zero or one real observation will correctly show `INSUFFICIENT_HISTORY`
forever until it has some. Run:

```bash
cd backend
python -m scripts.bootstrap_firms_history --days 30
```

This chunks the request into ≤10-day windows (NASA's practical NRT limit
per request), runs every observation through the real pipeline, and tags
every row `source="nasa_firms"` — never `demo_synthetic`. Safe to re-run;
duplicate detection means overlapping day-ranges won't double-insert.

Optional flags:
```bash
python -m scripts.bootstrap_firms_history --days 10 --bbox 68,6,97,37 --sources VIIRS_NOAA21_NRT
```

## 4. Live synchronization

**Automatic:** starts on backend startup if `FIRMS_ENABLED=true` and a key
is configured — runs immediately, then every `FIRMS_SYNC_INTERVAL_MINUTES`.
Check your backend console for `[firms_sync_loop]` log lines.

**Manual:** `POST /data-sources/firms/sync`, or the "Sync FIRMS now" button
in the Command Center top bar. Returns the real result — fetched/inserted/
duplicate counts, or a real error.

## 5. Checking status honestly

`GET /data-sources/status` — the `NASA FIRMS` entry will show one of:

- **`LIVE — NASA FIRMS`** — a real sync succeeded within the last 60 minutes
- **`STALE — NASA FIRMS`** — a sync succeeded before, but not recently
- **`OFFLINE — NASA FIRMS`** — no key configured, or every attempt has failed

The system will never show `LIVE` without a real successful NASA HTTP
request on record (`IngestionRun.success == True`).

## 6. Human labeling (needed before training)

Real detection ≠ a usable training label. Verify observations via
`POST /hotspots/{id}/verify` (or the buttons in the Event Investigation
panel) — `confirmed_industrial`, `confirmed_wildfire`,
`confirmed_agricultural`, `confirmed_static_thermal`, or `unknown`.

Check progress: `GET /ml/labeling/stats` — reports real counts and whether
you have enough (30+) verified real observations to train meaningfully.

## 7. Training

```bash
cd ml
pip install -r requirements.txt
python train.py
```

Trains **only** on real (`source=nasa_firms`), **human-verified**
observations — demo/synthetic data and the pipeline's own rule-engine
labels are both explicitly excluded from supervised training (see
`ml/dataset_builder.py`'s module docstring for why training on the
pipeline's own output would be circular). If you have fewer than 30
verified observations, it will print exactly that and refuse to fabricate
metrics, rather than train on too little data and report misleading numbers.

Deploy the result:
```bash
cp models/classifier.pkl ../backend/app/services/classifier.pkl
```
Restart the backend — it auto-detects the file.

## 8. Troubleshooting

**First step for any FIRMS issue:** run `python -m scripts.test_firms` from
`backend/`. It checks configuration loading and API connectivity separately,
and will name the exact root cause (including the most common real one:
a stray OS/shell environment variable silently shadowing your `.env` file —
see `docs/LIVE_DATA_STATUS.md` for the full explanation and a reproduced
example of exactly this bug).

| Symptom | Likely cause |
|---|---|
| `FIRMS_MAP_KEY is not set` | `.env` not created/loaded, or key not pasted in |
| Sync succeeds but `fetched: 0` | No fires currently detected in your bounding box/time window — not a bug |
| `status.startswith("STALE")` | Sync succeeded before but hasn't run in >60 min — check the background loop is running, or trigger manually |
| Facility fingerprint says `INSUFFICIENT_HISTORY` | Normal for a new facility or before bootstrap — run step 3 |
| `/model-performance` says `NO_TRAINED_MODEL` | Expected until you've done steps 6-7 |

## 9. API limits & data freshness

NASA FIRMS Area API near-real-time (NRT) products are typically updated
within 3 hours of satellite overpass; VIIRS overpasses a given location
roughly twice daily. A 15-minute sync interval is far more frequent than
new data will actually appear — this is intentional (catches new data
quickly without hammering the API), not a claim that data refreshes every
15 minutes.

## 10. Real vs. demo — how it's enforced, not just documented

Every `Hotspot.source` is either `"nasa_firms"` or `"demo_synthetic"` —
set once at ingestion time by `pipeline.process_observation()`, never
changed afterward. `/stats`, `/data-sources/status`, the Command Center's
REAL/DEMO/ALL filter, and `ml/dataset_builder.py`'s training query all key
off this same column. There is exactly one source of truth for this
distinction in the entire codebase.
