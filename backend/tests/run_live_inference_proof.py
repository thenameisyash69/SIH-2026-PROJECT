"""
Actually executes scripts.live_inference_proof's logic against one of the
REAL NASA FIRMS observations loaded from data-pipeline/raw/ in this pass,
via the sandbox-only fake DB (see tests/_sandbox_stub/README.md).

This IS Phase 10's proof, using genuinely real satellite data — the only
thing not real about this run is that the persistence layer is a test
stub instead of SQLite (because this sandbox cannot install SQLAlchemy).
"""
import sys, os, csv
from datetime import datetime

STUB_PATH = os.path.join(os.path.dirname(__file__), "_sandbox_stub")
sys.path.insert(0, STUB_PATH)
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.services.pipeline import process_observation
from app.services.landcover_fetcher import tag_land_cover
from app.services import classifier
from tests._sandbox_stub.sqlalchemy.orm import FakeSession, _reset_store

INDIA_BBOX = (68, 6, 97, 37)
SNAPSHOT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "data-pipeline", "raw")


def in_bbox(lat, lon):
    west, south, east, north = INDIA_BBOX
    return south <= lat <= north and west <= lon <= east


def parse_acq_datetime(date_str, time_str):
    dt = datetime.strptime(date_str, "%Y-%m-%d")
    time_str = str(time_str).zfill(4)
    return dt.replace(hour=int(time_str[:2]), minute=int(time_str[2:]))


def main():
    _reset_store()
    db = FakeSession()

    # Load the highest-FRP real VIIRS observation (strongest real signal) for the proof
    filepath = os.path.join(SNAPSHOT_DIR, "viirs_raw.csv")
    best_row, best_frp = None, -1
    with open(filepath) as f:
        for row in csv.DictReader(f):
            lat, lon = float(row["latitude"]), float(row["longitude"])
            if not in_bbox(lat, lon):
                continue
            frp = float(row.get("frp", 0) or 0)
            if frp > best_frp:
                best_frp, best_row = frp, row

    lat, lon = float(best_row["latitude"]), float(best_row["longitude"])
    brightness = float(best_row["bright_ti4"])
    acq_date = parse_acq_datetime(best_row["acq_date"], best_row["acq_time"])
    land_cover = tag_land_cover(lat, lon)

    hotspot = process_observation(db, {
        "lat": lat, "lon": lon, "brightness": brightness,
        "confidence": {"low": 30.0, "nominal": 60.0, "high": 90.0}.get(best_row["confidence"].lower(), 50.0),
        "frp": float(best_row["frp"]), "acq_date": acq_date, "land_cover": land_cover,
        "satellite": "VIIRS_Suomi_NPP", "source": "nasa_firms",
    })

    print("=" * 60)
    print("KAVACH — LIVE INFERENCE PROOF (real NASA data via sandbox test harness)")
    print("=" * 60)
    print(f"Source:             {hotspot.source}")
    print(f"Satellite:          {hotspot.satellite}  "
          f"(NOTE: this sandbox's real data comes from NASA's no-key static regional feed, "
          f"MODIS Terra / VIIRS Suomi-NPP — NOT the VIIRS_NOAA21_NRT/NOAA20_NRT the user's real "
          f"MAP_KEY-based environment uses. Same pipeline, different real NASA source.)")
    print(f"Acquisition:        {hotspot.acq_date.isoformat()}")
    print(f"Facility:           {hotspot.facility.name if hotspot.facility else 'None matched'}")
    print(f"Distance:           {hotspot.distance_to_facility_km} km")
    print(f"Brightness:         {hotspot.brightness}")
    print(f"Confidence:         {hotspot.confidence}")
    print(f"FRP:                {hotspot.frp}")
    print(f"Land cover:         {hotspot.land_cover}")
    print(f"Engine:             {classifier.active_engine()}")
    print(f"Model version:      {hotspot.model_version or 'N/A (rule engine)'}")
    print(f"Prediction:         {hotspot.category}")
    print(f"Model score:        {hotspot.classification_confidence}")
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
    main()
