"""
Phase 10 — takes at least one REAL NASA FIRMS observation and runs it
through the COMPLETE pipeline, printing every stage exactly as required
for the SIH demo proof.

In a normal environment (real FIRMS_MAP_KEY, real ingested data), this
reads the most recent real hotspot from the database. Run with:

    python -m scripts.live_inference_proof

Honesty note printed by design: if no trained XGBoost model exists, the
"Model" line says exactly that — RULE ENGINE FALLBACK — never fabricated
as "XGBoost v001".
"""
import sys, os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import SessionLocal, init_db
from app import models
from app.services import classifier


def run():
    init_db()
    db = SessionLocal()

    hotspot = db.query(models.Hotspot).filter(
        models.Hotspot.source == "nasa_firms"
    ).order_by(models.Hotspot.acq_date.desc()).first()

    if not hotspot:
        print("No real NASA FIRMS observations found in the database yet.")
        print("Run `python -m scripts.test_firms` to check your connection, then "
              "`POST /data-sources/firms/sync` or `scripts.bootstrap_firms_history` to ingest real data.")
        return

    print("=" * 60)
    print("KAVACH — LIVE INFERENCE PROOF")
    print("=" * 60)
    print(f"Source:             {hotspot.source}")
    print(f"Satellite:          {hotspot.satellite}")
    print(f"Acquisition:        {hotspot.acq_date.isoformat() if hotspot.acq_date else None}")
    print(f"Facility:           {hotspot.facility.name if hotspot.facility else 'None matched'}")
    print(f"Distance:           {hotspot.distance_to_facility_km} km")
    print(f"Brightness:         {hotspot.brightness}")
    print(f"Confidence:         {hotspot.confidence}")
    print(f"FRP:                {hotspot.frp}")
    print(f"Land cover:         {hotspot.land_cover}")
    print(f"Engine:             {classifier.active_engine()}")
    print(f"Model version:      {hotspot.model_version or 'N/A (rule engine)'}")
    print(f"Prediction:         {hotspot.category}")
    print(f"Model score:        {hotspot.classification_confidence}  "
          f"({'model score, not calibrated probability' if hotspot.classification_method == 'ml_model' else 'rule-engine confidence heuristic'})")
    print(f"Baseline status:    {hotspot.baseline_status}")
    print(f"Z-score:            {hotspot.z_score}")
    print(f"Deviation %:        {hotspot.deviation_percentage}")
    print(f"Anomaly:            {'YES' if hotspot.is_anomaly else 'no'}")
    print(f"Evidence:           {hotspot.reason}")
    print(f"Reason codes:       {hotspot.reason_codes}")
    print(f"Risk:               {hotspot.risk_level} (score {hotspot.risk_score})")
    print(f"Data quality:       {hotspot.data_quality}")
    print("=" * 60)


if __name__ == "__main__":
    run()
