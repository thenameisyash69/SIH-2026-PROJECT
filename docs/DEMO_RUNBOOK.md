# Demo Runbook

## Setup (do this BEFORE demo day, not live)

```bash
cd backend
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
rm -f sih.db                      # start clean
python -m scripts.seed            # 12 facilities, 60 days, run through the real pipeline
uvicorn app.main:app --reload

# separate terminal
cd data-pipeline && python ingest_firms.py   # pulls real NASA data alongside the demo set

# separate terminal, once you have enough combined data
cd ml && python train.py
cp models/classifier.pkl ../backend/app/services/classifier.pkl
# restart backend
```

## The four scenarios to walk a judge through (spec §29)

1. **Normal industrial source** — click a facility marked `industrial_normal`.
   Show: baseline status NORMAL, behavior label PERSISTENT_EXPECTED, risk LOW.
   Say: *"This refinery has been this hot for 60 days straight — Kavach knows
   that's normal for this specific site."*

2. **Abnormal industrial event** — click a facility marked `industrial_alert`.
   Show: baseline status ABNORMAL, z-score, deviation %, evidence list, risk
   HIGH/CRITICAL, then click "Generate assessment."
   Say: *"Same kind of facility, but THIS reading is a real statistical
   outlier against its own history — that's what gets flagged, not just
   'it's hot.'"*

3. **Wildfire** — click the Kerala/Uttarakhand forest hotspot.
   Say: *"No nearby facility, forest land-cover — classified as wildfire,
   not industrial."*

4. **Agricultural burning** — click the Punjab/Haryana hotspot.
   Say: *"Farmland, correct season — classified as agricultural burning."*

## If asked "is this real data?"

Point at the REAL vs DEMO split in the impact stats row and the
`🛰 REAL — NASA FIRMS` / `◆ DEMO — synthetic data` flag on the detail panel.
Answer honestly: *"The classification and risk engine are real and run on
both; the facility registry and most current hotspots are a curated demo set,
and we're actively ingesting live FIRMS data alongside it."*

## If the internet drops mid-demo

The frontend automatically falls back to `demoData.js` — the map and detail
panel keep working, badged "showing demo data — backend offline." Mention
this is intentional, not a bug.

## Before demo day — live data checklist (this pass)

1. Follow `docs/LIVE_DATA_SETUP.md` fully: get a `FIRMS_MAP_KEY`, run
   `scripts/bootstrap_firms_history.py --days 30`, verify at least 30 real
   observations via the Event Investigation panel's verify buttons, run
   `ml/train.py`, deploy the model.
2. Confirm `GET /data-sources/status` shows `LIVE — NASA FIRMS`, not
   `OFFLINE`, before you walk on stage.
3. If step 2 fails on the day (venue wifi, NASA API hiccup): the app does
   NOT break — it falls back to demo data automatically and says so
   ("showing demo data — backend offline" / "DEMO MODE"). Rehearse
   acknowledging this calmly rather than being caught off guard: *"Looks
   like we've lost the live feed — here's the same system running against
   our demo dataset, same intelligence pipeline underneath."*
4. Use the REAL NASA / DEMO / ALL filter buttons in the Command Center to
   show judges you can distinguish the two live, on demand, in the UI
   itself — this is a stronger trust signal than just claiming it in words.
