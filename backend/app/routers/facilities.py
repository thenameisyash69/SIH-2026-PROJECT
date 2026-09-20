from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import List
from datetime import timedelta
from app.database import get_db
from app import models, schemas
from app.services.facility_fingerprint import build_fingerprint
from app.services.baseline_engine import (
    compute_baseline, baseline_confidence,
    MIN_OBSERVATIONS_FOR_BASELINE,
    INSUFFICIENT_HISTORY, PROVISIONAL, ESTABLISHED,
    Z_ABNORMAL, Z_ELEVATED,
)

router = APIRouter(prefix="/facilities", tags=["facilities"])


@router.get("", response_model=List[schemas.FacilityOut])
def list_facilities(db: Session = Depends(get_db)):
    return db.query(models.Facility).all()


@router.get("/{facility_id}", response_model=schemas.FacilityOut)
def get_facility(facility_id: int, db: Session = Depends(get_db)):
    facility = db.query(models.Facility).filter(models.Facility.id == facility_id).first()
    if not facility:
        return {"error": "not found"}
    return facility


@router.get("/{facility_id}/fingerprint", response_model=schemas.FacilityFingerprintOut)
def get_facility_fingerprint(facility_id: int, db: Session = Depends(get_db)):
    """The core differentiator: this facility's thermal fingerprint vs. NASA FIRMS'
    raw per-pixel detections. See docs/DIFFERENTIATION.md."""
    facility = db.query(models.Facility).filter(models.Facility.id == facility_id).first()
    if not facility:
        return {"error": "not found"}
    return build_fingerprint(db, facility)


@router.get("/{facility_id}/thermal-history", response_model=schemas.ThermalHistoryOut)
def get_thermal_history(facility_id: int, db: Session = Depends(get_db),
                         window_days: int = 90, source: str = "nasa_firms",
                         detailed: bool = Query(False,
                             description="If true, also return per-observation rows for charts.")):
    """
    READ-ONLY rolling thermal baseline + brightness histogram for a facility.

    Uses ONLY real NASA FIRMS observations (source="nasa_firms") within
    the requested rolling calendar window. Demo observations are never
    included.

    Baseline status:
      - INSUFFICIENT_HISTORY: no usable observations in the window.
      - PROVISIONAL: some real observations exist but fewer than
        MIN_OBSERVATIONS_FOR_BASELINE (8) obs or 8 unique active days —
        baseline stats are computed and returned, but are not yet stable.
      - ESTABLISHED: at least 8 observations across 8 unique active days.

    Demo data is never mixed with real FIRMS data (spec §28). Demo
    observations are always tagged source="demo_synthetic" and are
    excluded unless the caller explicitly passes source="demo_synthetic".

    Histogram bins are 5 K brightness buckets.
    """
    facility = db.query(models.Facility).filter(models.Facility.id == facility_id).first()
    if not facility:
        raise HTTPException(status_code=404, detail="Facility not found")

    rows = (
        db.query(models.Hotspot)
        .filter(
            models.Hotspot.facility_id == facility_id,
            models.Hotspot.source == source,
        )
        .order_by(models.Hotspot.acq_date.asc())
        .all()
    )

    valid = [h for h in rows if h.acq_date is not None]
    if not valid:
        status, explanation = baseline_confidence(0, 0)
        return schemas.ThermalHistoryOut(
            facility_id=facility.id,
            facility_name=facility.name,
            source=source,
            window_days=window_days,
            observation_count=0,
            unique_active_days=0,
            insufficient_history=True,
            baseline_status=status,
            confidence=explanation,
            limitations=explanation,
            sudden_rise_level="INSUFFICIENT_HISTORY",
        )

    latest = max(h.acq_date for h in valid)
    cutoff = latest - timedelta(days=window_days - 1)
    in_window = [h for h in valid if h.acq_date >= cutoff]

    observation_count = len(in_window)
    unique_days = len({h.acq_date.date() for h in in_window})

    # Always compute baseline stats from the available in-window history.
    # compute_baseline() now returns PROVISIONAL (stats computed) instead
    # of discarding them when the 8/8 threshold isn't met.
    brightness_values = [h.brightness for h in in_window]
    baseline = compute_baseline(brightness_values, unique_days=unique_days)
    baseline_status, explanation = baseline_confidence(observation_count, unique_days)

    # 5 K histogram bins
    bins = {}
    for b in brightness_values:
        bucket = int(b // 5) * 5
        bins[bucket] = bins.get(bucket, 0) + 1

    histogram = [
        schemas.ThermalHistoryBin(bin_start=float(k), bin_end=float(k + 5), count=v)
        for k, v in sorted(bins.items())
    ]

    observations = []
    if detailed:
        observations = [
            schemas.ThermalObservationRow(
                hotspot_id=h.id,
                acq_date=h.acq_date.isoformat() if h.acq_date else None,
                brightness=h.brightness,
                frp=h.frp,
                confidence=h.confidence,
                z_score=h.z_score,
                deviation_percentage=h.deviation_percentage,
                baseline_status=h.baseline_status,
                is_anomaly=bool(h.is_anomaly),
            )
            for h in in_window
        ]

    latest_obs = in_window[-1]

    # sudden_rise_level is a display triage label, not a fire detector.
    # For PROVISIONAL baselines, z-scores are not statistically reliable
    # so we surface the provisional state instead of a misleading spike flag.
    if baseline_status == PROVISIONAL:
        sudden_rise_level = "PROVISIONAL"
    elif baseline_status == INSUFFICIENT_HISTORY:
        sudden_rise_level = "INSUFFICIENT_HISTORY"
    else:
        z = latest_obs.z_score
        if z is None:
            sudden_rise_level = "NORMAL_RANGE"
        elif z >= Z_ABNORMAL:
            sudden_rise_level = "SUDDEN_THERMAL_SPIKE"
        elif z >= Z_ELEVATED:
            sudden_rise_level = "ELEVATED"
        else:
            sudden_rise_level = "NORMAL_RANGE"

    return schemas.ThermalHistoryOut(
        facility_id=facility.id,
        facility_name=facility.name,
        source=source,
        window_days=window_days,
        date_start=min(h.acq_date for h in in_window).isoformat() if in_window else None,
        date_end=latest.isoformat(),
        observation_count=observation_count,
        unique_active_days=unique_days,
        mean=round(baseline.mean, 2) if baseline.mean is not None else None,
        median=round(baseline.median, 2) if baseline.median is not None else None,
        std=round(baseline.std, 2) if baseline.std is not None else None,
        p95=round(baseline.p95, 2) if baseline.p95 is not None else None,
        current_brightness=latest_obs.brightness,
        insufficient_history=(baseline_status == INSUFFICIENT_HISTORY),
        baseline_status=baseline_status,
        confidence=explanation,
        limitations=explanation,
        histogram=histogram,
        observations=observations,
        sudden_rise_level=sudden_rise_level,
    )
