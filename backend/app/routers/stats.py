"""
Quantified numbers for the pitch/demo — with real vs. demo data kept
strictly separate (spec §28) so no claim ever blends synthetic with real.
"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func
from app.database import get_db
from app import models

router = APIRouter(prefix="/stats", tags=["stats"])


def _block_for_source(db: Session, source_filter: str | None):
    q = db.query(models.Hotspot)
    if source_filter:
        q = q.filter(models.Hotspot.source == source_filter)
    total = q.count()
    anomalies = q.filter(models.Hotspot.is_anomaly.is_(True)).count()
    high_risk = q.filter(models.Hotspot.risk_level.in_(["HIGH", "CRITICAL"])).count()
    unknown = q.filter(models.Hotspot.category == "unknown").count()
    return {
        "total_hotspots": total,
        "anomalies_flagged": anomalies,
        "high_or_critical_risk": high_risk,
        "unknown_classifications": unknown,
        "anomaly_rate_pct": round((anomalies / total) * 100, 1) if total else 0,
    }


@router.get("")
def get_stats(db: Session = Depends(get_db)):
    total_facilities = db.query(func.count(models.Facility.id)).scalar() or 0
    states_covered = db.query(func.count(func.distinct(models.Hotspot.state))).scalar() or 0
    ml_classified = db.query(func.count(models.Hotspot.id)).filter(
        models.Hotspot.classification_method == "ml_model").scalar() or 0

    earliest = db.query(func.min(models.Hotspot.acq_date)).scalar()
    latest = db.query(func.max(models.Hotspot.acq_date)).scalar()
    days_of_data = (latest - earliest).days + 1 if earliest and latest else 0

    monitored_area_sq_km = total_facilities * (2 * 2.0) ** 2  # illustrative, not a survey figure

    return {
        "facilities_monitored": total_facilities,
        "states_covered": states_covered,
        "days_of_data": days_of_data,
        "estimated_monitored_area_sq_km": round(monitored_area_sq_km, 1),
        "hotspots_classified_by_ml": ml_classified,
        # Real and demo numbers are reported SEPARATELY, never combined into one headline claim.
        "real_data": _block_for_source(db, "nasa_firms"),
        "demo_data": _block_for_source(db, "demo_synthetic"),
    }
