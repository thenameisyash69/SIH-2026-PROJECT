from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import List
from datetime import timedelta
from app.database import get_db
from app import models, schemas
from app.services.facility_fingerprint import build_fingerprint
from app.services.baseline_engine import compute_baseline, MIN_OBSERVATIONS_FOR_BASELINE

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
    included. If fewer than MIN_OBSERVATIONS_FOR_BASELINE observations
    exist in the window, insufficient_history=True is returned and no
    misleading statistics are computed.

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
        return schemas.ThermalHistoryOut(
            facility_id=facility.id,
            facility_name=facility.name,
            source=source,
            window_days=window_days,
            observation_count=0,
            insufficient_history=True,
            sudden_rise_level="INSUFFICIENT_HISTORY",
        )

    latest = max(h.acq_date for h in valid)
    cutoff = latest - timedelta(days=window_days - 1)
    in_window = [h for h in valid if h.acq_date >= cutoff]

    observation_count = len(in_window)
    unique_days = len({h.acq_date.date() for h in in_window})

    if (observation_count < MIN_OBSERVATIONS_FOR_BASELINE
            or unique_days < MIN_OBSERVATIONS_FOR_BASELINE):
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
        return schemas.ThermalHistoryOut(
            facility_id=facility.id,
            facility_name=facility.name,
            source=source,
            window_days=window_days,
            date_start=min(h.acq_date for h in in_window).isoformat() if in_window else None,
            date_end=latest.isoformat(),
            observation_count=observation_count,
            insufficient_history=True,
            observations=observations,
            sudden_rise_level="INSUFFICIENT_HISTORY",
        )

    brightness_values = [h.brightness for h in in_window]
    baseline = compute_baseline(brightness_values, unique_days=unique_days)

    # 5 K histogram bins
    lo = int(min(brightness_values) // 5) * 5
    hi = int(max(brightness_values) // 5) * 5 + 5
    bins = {}
    for b in brightness_values:
        bucket = int(b // 5) * 5
        bins[bucket] = bins.get(bucket, 0) + 1

    histogram = [
        schemas.ThermalHistoryBin(bin_start=float(k), bin_end=float(k + 5), count=v)
        for k, v in sorted(bins.items())
    ]

    latest_obs = in_window[-1]

    # Deterministic display-triage level for the LATEST observation.
    # This is NOT a fire detector — it is a label for unusual thermal
    # activity so the analyst can spot it quickly. Derived ONLY from the
    # stored z_score and the baseline_engine thresholds (Z_ABNORMAL=2.5,
    # Z_ELEVATED=1.5).
    z = latest_obs.z_score
    if z is None:
        sudden_rise_level = "NORMAL_RANGE"
    elif z >= 2.5:
        sudden_rise_level = "SUDDEN_THERMAL_SPIKE"
    elif z >= 1.5:
        sudden_rise_level = "ELEVATED"
    else:
        sudden_rise_level = "NORMAL_RANGE"

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

    return schemas.ThermalHistoryOut(
        facility_id=facility.id,
        facility_name=facility.name,
        source=source,
        window_days=window_days,
        date_start=min(h.acq_date for h in in_window).isoformat(),
        date_end=latest.isoformat(),
        observation_count=len(in_window),
        mean=round(baseline.mean, 2) if baseline.mean is not None else None,
        median=round(baseline.median, 2) if baseline.median is not None else None,
        std=round(baseline.std, 2) if baseline.std is not None else None,
        p95=round(baseline.p95, 2) if baseline.p95 is not None else None,
        current_brightness=latest_obs.brightness,
        insufficient_history=False,
        histogram=histogram,
        observations=observations,
        sudden_rise_level=sudden_rise_level,
    )
