"""
Demo-only data management endpoints for KAVACH.

These endpoints allow creating or resetting synthetic demo observations for
demonstration purposes (e.g. YouTube videos, training, UI showcases).

SAFETY RULES (enforced in code):
  - ONLY records with source='demo' are created, listed, or deleted.
  - NASA FIRMS records (source='nasa_firms') are NEVER modified, deleted, or
    counted as demo.
  - Existing demo_synthetic seed data (source='demo_synthetic') is NEVER
    touched by these endpoints — it's managed separately by seed.py.
  - Verification decisions are never fabricated — demo verifications (if any)
    are explicitly synthetic and tagged as such.
  - The scenario endpoint is idempotent: calling it multiple times replaces
    the existing demo scenario data without duplicating records.
  - Each observation runs through pipeline.process_observation() — the same
    code path as real FIRMS data — so classification, baseline, and anomaly
    logic are exercised legitimately.
"""
import random
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from app.database import get_db
from app import models
from app.services.pipeline import process_observation
from app.services.facility_fingerprint import build_fingerprint
import random as _random

router = APIRouter(prefix="/demo", tags=["demo"])

DEMO_SOURCE = "demo"
DEMO_FACILITIES = [
    {"name": "Jamnagar Refinery (Demo)", "type": "refinery", "state": "Gujarat",
     "lat": 22.3511, "lon": 69.8340, "criticality": "critical"},
    {"name": "Bokaro Steel Plant (Demo)", "type": "steel_plant", "state": "Jharkhand",
     "lat": 23.6693, "lon": 86.1511, "criticality": "high"},
    {"name": "Talcher Power Station (Demo)", "type": "power_plant", "state": "Odisha",
     "lat": 20.9500, "lon": 85.2333, "criticality": "critical"},
]

# Deterministic seed for reproducible demo data
_RANDOM_SEED = 42


def _reset_demo_data(db: Session) -> int:
    """Delete ALL demo records only — never touches nasa_firms or demo_synthetic.

    Returns the number of hotspots deleted.
    Also cleans up orphaned verifications and alerts for deleted demo hotspots.
    """
    # Count before delete for reporting
    count = db.query(models.Hotspot).filter(models.Hotspot.source == DEMO_SOURCE).count()

    # Delete verifications for demo hotspots first (FK constraint)
    demo_ids_select = (
        select(models.Hotspot.id)
        .where(models.Hotspot.source == DEMO_SOURCE)
    )
    db.query(models.Verification).filter(
        models.Verification.hotspot_id.in_(demo_ids_select)
    ).delete(synchronize_session=False)

    # Delete alerts for demo hotspots
    db.query(models.Alert).filter(
        models.Alert.hotspot_id.in_(demo_ids_select)
    ).delete(synchronize_session=False)

    # Delete demo hotspots
    db.query(models.Hotspot).filter(models.Hotspot.source == DEMO_SOURCE).delete(
        synchronize_session=False
    )

    # Delete demo facilities (tagged source='demo' in facility source column)
    db.query(models.Facility).filter(models.Facility.source == DEMO_SOURCE).delete(
        synchronize_session=False
    )

    return count


def _create_demo_scenario(db: Session, days: int = 30) -> dict:
    """Create a reproducible demo scenario with enough history for baseline charts.

    Creates 3 demo facilities with 30+ days of observations each, including:
    - Normal baseline readings (8+ unique days for ESTABLISHED baseline)
    - Spike anomalies for some facilities (to demonstrate anomaly detection)
    - A mix of industrial and natural-event observations

    All observations run through process_observation() — same pipeline as real FIRMS.
    """
    _random.seed(_RANDOM_SEED)
    random.seed(_RANDOM_SEED)

    now = datetime.utcnow()
    total_created = 0

    # Create demo facilities
    for f in DEMO_FACILITIES:
        # Check if facility already exists
        existing = db.query(models.Facility).filter(
            models.Facility.name == f["name"],
            models.Facility.source == DEMO_SOURCE
        ).first()
        if not existing:
            facility = models.Facility(**f, source=DEMO_SOURCE)
            db.add(facility)
            db.flush()
        else:
            facility = existing

        # Generate observations: baseline + anomalies
        baseline = random.uniform(305, 320)
        is_anomaly_story = random.random() < 0.5
        spike_start = random.randint(3, 10)
        spike_duration = random.randint(2, 5)

        for day_offset in range(days, -1, -1):
            acq_date = now - timedelta(days=day_offset)
            # Add a few hours variation per day for unique timestamps
            hour = random.randint(0, 20)
            acq_date = acq_date.replace(hour=hour, minute=random.randint(0, 59))

            brightness = baseline + random.uniform(-3, 3)

            # Insert anomaly spike on some days
            if is_anomaly_story and spike_start <= day_offset <= (spike_start + spike_duration):
                brightness = baseline + random.uniform(40, 70)

            confidence = random.uniform(60, 95)
            frp = random.uniform(5, 80) if brightness > 330 else random.uniform(0, 15)

            process_observation(db, {
                "lat": facility.lat + random.uniform(-0.005, 0.005),
                "lon": facility.lon + random.uniform(-0.005, 0.005),
                "brightness": brightness,
                "confidence": confidence,
                "frp": frp,
                "acq_date": acq_date,
                "land_cover": "industrial",
                "source": DEMO_SOURCE,
            }, commit=False)
            total_created += 1

    # Add some natural event observations (non-industrial)
    natural_events = [
        {"lat": 30.3165, "lon": 78.0322, "state": "Uttarakhand", "land_cover": "forest"},
        {"lat": 11.4102, "lon": 76.6950, "state": "Kerala", "land_cover": "forest"},
    ]
    for event in natural_events:
        for _ in range(random.randint(3, 5)):
            day_offset = random.randint(0, days)
            acq_date = now - timedelta(days=day_offset)
            acq_date = acq_date.replace(hour=random.randint(0, 20), minute=random.randint(0, 59))

            process_observation(db, {
                "lat": event["lat"] + random.uniform(-0.05, 0.05),
                "lon": event["lon"] + random.uniform(-0.05, 0.05),
                "brightness": random.uniform(300, 345),
                "confidence": random.uniform(50, 80),
                "frp": random.uniform(0, 30),
                "acq_date": acq_date,
                "land_cover": event["land_cover"],
                "state": event["state"],
                "source": DEMO_SOURCE,
            }, commit=False)
            total_created += 1

    db.commit()
    return {"facilities": len(DEMO_FACILITIES), "observations": total_created}


@router.get("/status")
def get_demo_status(db: Session = Depends(get_db)):
    """Returns the current count of demo (source='demo') records only.
    Never reports on nasa_firms or demo_synthetic data."""
    demo_count = db.query(models.Hotspot).filter(
        models.Hotspot.source == DEMO_SOURCE
    ).count()
    demo_facilities = db.query(models.Facility).filter(
        models.Facility.source == DEMO_SOURCE
    ).count()

    # Date range of demo data
    date_result = db.query(
        func.min(models.Hotspot.acq_date),
        func.max(models.Hotspot.acq_date)
    ).filter(models.Hotspot.source == DEMO_SOURCE).first()

    latest = db.query(models.Hotspot).filter(
        models.Hotspot.source == DEMO_SOURCE
    ).order_by(models.Hotspot.acq_date.desc()).first()

    return {
        "source": DEMO_SOURCE,
        "observations": demo_count,
        "facilities": demo_facilities,
        "date_range": {
            "start": date_result[0].isoformat() if date_result and date_result[0] else None,
            "end": date_result[1].isoformat() if date_result and date_result[1] else None,
        },
        "latest_acq_date": latest.acq_date.isoformat() if latest and latest.acq_date else None,
    }


@router.post("/scenario")
def create_demo_scenario(
    days: int = 30,
    db: Session = Depends(get_db)
):
    """
    Create a reproducible demo scenario with enough historical depth for
    baseline charts and trend analysis.

    This endpoint is IDEMPOTENT: it first resets any existing source='demo'
    records (NOT nasa_firms, NOT demo_synthetic), then creates fresh demo
    data. Calling it multiple times will not create duplicates.

    Parameters:
      - days: number of days of history to generate (default 30, minimum 10)

    All observations are clearly tagged source='demo' and run through the
    real classification pipeline (process_observation) — but the baseline
    engine treats them identically to live data. Baseline status is NOT
    faked; it's computed from real observation history.
    """
    if days < 10:
        raise HTTPException(
            status_code=400,
            detail="days must be >= 10 for a meaningful baseline demonstration"
        )

    # Reset existing demo data (ONLY source='demo', never other sources)
    deleted = _reset_demo_data(db)

    # Create fresh demo scenario
    result = _create_demo_scenario(db, days=days)

    return {
        "status": "success",
        "source": DEMO_SOURCE,
        "previous_demo_records_deleted": deleted,
        "new_facilities": result["facilities"],
        "new_observations": result["observations"],
        "days_of_history": days,
        "note": f"Demo scenario created with {days} days of history. "
                f"All {result['observations']} observations are tagged source='demo'. "
                f"Live NASA FIRMS data (source='nasa_firms') was NOT modified."
    }


@router.delete("/data")
def reset_demo_data(
    confirm: str = None,
    db: Session = Depends(get_db)
):
    """
    Delete ALL demo records (source='demo' ONLY).
    Never touches nasa_firms or demo_synthetic records.

    Requires confirm='DELETE_DEMO_DATA' for safety.
    """
    if confirm != "DELETE_DEMO_DATA":
        raise HTTPException(
            status_code=400,
            detail="Missing confirmation. Pass confirm=DELETE_DEMO_DATA to proceed."
        )

    deleted = _reset_demo_data(db)
    db.commit()

    return {
        "status": "success",
        "source": DEMO_SOURCE,
        "records_deleted": deleted,
        "note": f"Deleted {deleted} demo records (source='demo'). "
                f"Live NASA FIRMS data and existing demo_synthetic seed data were NOT affected."
    }
