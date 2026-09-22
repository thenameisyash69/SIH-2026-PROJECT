"""
Real labeling-progress stats — implemented natively against the ORM
(rather than importing ml/dataset_builder.py's pandas/raw-SQL version,
which points at a hardcoded relative DB path meant for offline CLI use).
Both compute the same underlying counts; this is the one the running
API serves.
"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import Optional
from app.database import get_db
from app import models
from math import radians, sin, cos, sqrt, atan2

router = APIRouter(prefix="/ml", tags=["ml"])


def haversine_km(lat1, lon1, lat2, lon2) -> float:
    R = 6371.0
    dlat, dlon = radians(lat2 - lat1), radians(lon2 - lon1)
    a = sin(dlat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon / 2) ** 2
    return 2 * R * atan2(sqrt(a), sqrt(1 - a))


def facility_proximity_bin(distance_km: Optional[float]) -> str:
    if distance_km is None:
        return "no_facility"
    if distance_km <= 2.0:
        return "near"
    elif distance_km <= 5.0:
        return "moderate"
    elif distance_km <= 20.0:
        return "far"
    return "very_far"


@router.get("/labeling/stats")
def labeling_stats(
    source: str = Query("nasa_firms", description="Source to filter: nasa_firms, demo_synthetic, demo"),
    db: Session = Depends(get_db),
):
    from app.services.india_scope import is_in_india

    total_real = db.query(func.count(models.Hotspot.id)).filter(
        models.Hotspot.source == source
    ).scalar() or 0

    # KAVACH operational scope: India only for nasa_firms observations.
    # Raw observations are preserved in the database; this is a scope
    # filter for the analyst queue display counts only.
    if source == "nasa_firms":
        all_real = db.query(models.Hotspot).filter(
            models.Hotspot.source == source
        ).all()
        in_scope = [h for h in all_real if is_in_india(h.lat, h.lon)]
        total_real = len(in_scope)
        verified_query = (
            db.query(models.Verification)
            .join(models.Hotspot, models.Hotspot.id == models.Verification.hotspot_id)
            .filter(models.Hotspot.source == source)
        )
        verified_in_scope = [v for v in verified_query.all() if is_in_india(v.hotspot.lat, v.hotspot.lon)]
        total_verified = len(verified_in_scope)
        class_distribution = {}
        for v in verified_in_scope:
            class_distribution[v.decision] = class_distribution.get(v.decision, 0) + 1

        # Quality breakdown
        high_conf_verified = sum(1 for v in verified_in_scope if v.hotspot.confidence >= 80)
        facility_verified = sum(1 for v in verified_in_scope if v.hotspot.facility_id is not None)
        non_facility_verified = total_verified - facility_verified

        # Additional breakdowns for unverified nasa_firms
        unverified_query = (
            db.query(models.Hotspot)
            .outerjoin(models.Verification, models.Hotspot.id == models.Verification.hotspot_id)
            .filter(models.Hotspot.source == source, models.Verification.id.is_(None))
        )
        unverified_hotspots = [h for h in unverified_query.all() if is_in_india(h.lat, h.lon)]
        total_unverified = len(unverified_hotspots)
    else:
        verified_query = (
            db.query(models.Verification)
            .join(models.Hotspot, models.Hotspot.id == models.Verification.hotspot_id)
            .filter(models.Hotspot.source == source)
        )
        total_verified = verified_query.count()

        class_distribution = {}
        for v in verified_query.all():
            class_distribution[v.decision] = class_distribution.get(v.decision, 0) + 1

        # Quality breakdown
        high_conf_verified = verified_query.filter(
            models.Hotspot.confidence >= 80
        ).count()

        # Facility-associated breakdown
        facility_verified = verified_query.filter(
            models.Hotspot.facility_id.isnot(None)
        ).count()

        non_facility_verified = total_verified - facility_verified

        # Additional breakdowns for unverified
        unverified_query = (
            db.query(models.Hotspot)
            .outerjoin(models.Verification, models.Hotspot.id == models.Verification.hotspot_id)
            .filter(models.Hotspot.source == source, models.Verification.id.is_(None))
        )
        total_unverified = unverified_query.count()

    # Facility proximity distribution for unverified in-scope observations
    facilities = db.query(models.Facility).all()
    facility_proximity_dist = {"near": 0, "moderate": 0, "far": 0, "very_far": 0, "no_facility": 0}
    thermal_dist = {"very_low": 0, "low": 0, "medium": 0, "high": 0}
    frp_dist = {"zero": 0, "low": 0, "medium": 0, "high": 0, "unknown": 0}
    temporal_dist = {}

    for h in unverified_hotspots:
        # Facility proximity
        nearest_dist = None
        for f in facilities:
            d = haversine_km(h.lat, h.lon, f.lat, f.lon)
            if nearest_dist is None or d < nearest_dist:
                nearest_dist = d
        fac_bin = facility_proximity_bin(round(nearest_dist, 3) if nearest_dist else None)
        facility_proximity_dist[fac_bin] = facility_proximity_dist.get(fac_bin, 0) + 1

        # Thermal brightness
        if h.brightness >= 340:
            thermal_dist["high"] += 1
        elif h.brightness >= 320:
            thermal_dist["medium"] += 1
        elif h.brightness >= 300:
            thermal_dist["low"] += 1
        else:
            thermal_dist["very_low"] += 1

        # FRP
        if h.frp is None:
            frp_dist["unknown"] += 1
        elif h.frp >= 100:
            frp_dist["high"] += 1
        elif h.frp >= 20:
            frp_dist["medium"] += 1
        elif h.frp > 0:
            frp_dist["low"] += 1
        else:
            frp_dist["zero"] += 1

        # Temporal (month)
        if h.acq_date:
            month_key = h.acq_date.strftime("%Y-%m")
            temporal_dist[month_key] = temporal_dist.get(month_key, 0) + 1

    result = {
        "source": source,
        "total_observations": total_real,
        "verified_observations": total_verified,
        "unverified_observations": total_unverified,
        "class_distribution": class_distribution,
        "quality_breakdown": {
            "high_confidence_verified": high_conf_verified,
            "facility_associated_verified": facility_verified,
            "non_facility_verified": non_facility_verified,
        },
        "unverified_breakdown": {
            "by_facility_proximity": facility_proximity_dist,
            "by_thermal_brightness": thermal_dist,
            "by_frp": frp_dist,
            "by_acquisition_month": temporal_dist,
        },
    }

    MIN_FOR_TRAINING = 30
    if total_verified < MIN_FOR_TRAINING:
        result["training_readiness"] = "INSUFFICIENT"
        result["message"] = (
            f"Only {total_verified} verified real observations exist — at least "
            f"{MIN_FOR_TRAINING} are recommended before running ml/train.py for a "
            f"meaningful facility-aware split. Verify more via POST /hotspots/{{id}}/verify."
        )
    else:
        result["training_readiness"] = "READY"
        result["message"] = f"{total_verified} verified observations available — ml/train.py can be run."

    return result


@router.get("/labeling/training-eligibility")
def training_eligibility(db: Session = Depends(get_db)):
    """
    Detailed breakdown of what would be used for training.
    Mirrors ml/dataset_builder.py logic but via the API.
    """
    import sys
    import os
    # Add project root to path for ml module
    project_root = os.path.join(os.path.dirname(__file__), "..", "..", "..")
    sys.path.insert(0, project_root)
    
    from ml.label_builder import VERIFIED_LABEL_VOCABULARY, EXCLUDED_FROM_TRAINING
    from app.services.india_scope import is_in_india

    # Get all nasa_firms hotspots with their verifications — India scope only.
    verified_hotspots = db.query(models.Hotspot).join(
        models.Verification, models.Hotspot.id == models.Verification.hotspot_id
    ).filter(models.Hotspot.source == "nasa_firms").all()
    
    verified_hotspots = [h for h in verified_hotspots if is_in_india(h.lat, h.lon)]

    if not verified_hotspots:
        return {
            "eligible_for_training": 0,
            "excluded_false_positive": 0,
            "class_counts": {},
            "message": "No verified observations found within the India operational scope.",
        }
    
    eligible = 0
    excluded = 0
    class_counts = {}
    
    for h in verified_hotspots:
        decision = h.verification.decision
        if decision in EXCLUDED_FROM_TRAINING:
            excluded += 1
        else:
            eligible += 1
            canonical = VERIFIED_LABEL_VOCABULARY.get(decision, "UNKNOWN")
            class_counts[canonical] = class_counts.get(canonical, 0) + 1
    
    return {
        "eligible_for_training": eligible,
        "excluded_false_positive": excluded,
        "class_counts": class_counts,
        "training_readiness": "READY" if eligible >= 30 else "INSUFFICIENT",
        "note": "Only VERIFIED analyst labels are used for training. Rule-engine categories (WEAK) are never used as training targets. Scope: India operational area only.",
    }
