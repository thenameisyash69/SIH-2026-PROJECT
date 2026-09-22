from fastapi import APIRouter, Depends, Query, HTTPException, Response
from starlette.responses import JSONResponse
from sqlalchemy.orm import Session
from sqlalchemy import func, or_, and_
from typing import Optional, List
from datetime import datetime, timedelta
import os
from app.database import get_db
from app import models, schemas
from app.services.satellite_image import build_satellite_image_url
from app.services.india_scope import is_in_india, _INDIA_BOUNDS, _SRI_LANKA_BOUNDS, _BANGLADESH_BOUNDS, _MYANMAR_BOUNDS
from math import radians, sin, cos, sqrt, atan2, floor

from app.services.facility_constants import FACILITY_ASSOCIATION_RADIUS_KM
from app.services.industrial_fire_scorer import compute_industrial_fire_candidate_score

router = APIRouter(prefix="/hotspots", tags=["hotspots"])


def haversine_km(lat1, lon1, lat2, lon2) -> float:
    R = 6371.0
    dlat, dlon = radians(lat2 - lat1), radians(lon2 - lon1)
    a = sin(dlat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon / 2) ** 2
    return 2 * R * atan2(sqrt(a), sqrt(1 - a))


def spatial_bin(lat: float, lon: float, grid_degrees: float = 0.25) -> tuple:
    """Round coordinates to a grid for geographic diversity sampling."""
    lat_bin = round(floor(lat / grid_degrees) * grid_degrees, 2)
    lon_bin = round(floor(lon / grid_degrees) * grid_degrees, 2)
    return (lat_bin, lon_bin)


def temporal_bin(acq_date: datetime, days_per_bin: int = 7) -> str:
    """Bucket acquisition dates into weekly bins for temporal diversity."""
    if not acq_date:
        return "unknown"
    # Round to start of week (Monday)
    days_since_monday = acq_date.weekday()
    week_start = acq_date - timedelta(days=days_since_monday)
    return week_start.strftime("%Y-%W")


def thermal_bin(brightness: float) -> str:
    """Bucket brightness into low/medium/high for thermal diversity."""
    if brightness >= 340:
        return "high"
    elif brightness >= 320:
        return "medium"
    elif brightness >= 300:
        return "low"
    return "very_low"


def frp_bin(frp: Optional[float]) -> str:
    """Bucket FRP into low/medium/high for thermal diversity."""
    if frp is None:
        return "unknown"
    if frp >= 100:
        return "high"
    elif frp >= 20:
        return "medium"
    elif frp > 0:
        return "low"
    return "zero"


def facility_proximity_bin(distance_km: Optional[float]) -> str:
    """Bucket facility distance for facility diversity."""
    if distance_km is None:
        return "no_facility"
    if distance_km <= 2.0:
        return "near"
    elif distance_km <= 5.0:
        return "moderate"
    elif distance_km <= 20.0:
        return "far"
    return "very_far"


@router.get("/labeling/candidates")
def get_labeling_candidates(
    source: Optional[str] = Query(None, description="Filter by source: nasa_firms, demo_synthetic, demo, or 'all' for no filter"),
    verified: Optional[bool] = Query(None, description="Filter by verification status"),
    facility_associated: Optional[bool] = Query(None, description="Filter: true = near facility (<=5km), false = away from facility"),
    facility_id: Optional[bool] = Query(None, description="Filter by facility_id presence: true = IS NOT NULL, false = IS NULL"),
    baseline_status: Optional[str] = Query(None, description="Filter by baseline_status: NORMAL / ELEVATED / ABNORMAL / INSUFFICIENT_HISTORY"),
    anomaly: Optional[bool] = Query(None, description="Filter by is_anomaly: true / false / null(unknown)"),
    risk_level: Optional[str] = Query(None, description="Filter by risk_level: LOW / WATCH / HIGH / CRITICAL"),
    classification: Optional[str] = Query(None, description="Filter by category: unknown / industrial_normal / industrial_alert / industrial_new / wildfire / agricultural_burning"),
    history_status: Optional[str] = Query(None, description="Filter by baseline sufficiency: SUFFICIENT / INSUFFICIENT (maps to baseline_status)"),
    min_frp: Optional[float] = Query(None, description="Minimum FRP value"),
    start_date: Optional[str] = Query(None, description="Start date (ISO format, e.g. 2026-01-01)"),
    end_date: Optional[str] = Query(None, description="End date (ISO format, e.g. 2026-12-31)"),
    limit: int = Query(200, le=1000, description="Maximum candidates to return"),
    diversity: bool = Query(True, description="Enable diversity sampling (geographic, temporal, thermal, facility)"),
    label_diversity: bool = Query(True, description="Prioritize label-class diversity: facility anomalies, normal facility, high-FRP unmatched, low-FRP, different facilities/dates/severity/classifications"),
    db: Session = Depends(get_db),
):
    """
    Returns candidate hotspots for analyst labeling, prioritized for diverse training data.
    
    Prioritization (highest first):
    1. Unverified nasa_firms observations
    2. High FRP observations
    3. Observations near facilities (for industrial class diversity)
    4. Observations away from facilities (for wildfire/agricultural class diversity)
    5. Geographic, temporal, thermal, and facility diversity
    """
    from datetime import timedelta
    
    # Base query: source filter
    # source='all' → no source filter (return all sources including demo)
    # source=<specific> → filter to that source
    # source=None → default to nasa_firms (backward compatible)
    if source == "all":
        query = db.query(models.Hotspot)
    elif source:
        query = db.query(models.Hotspot).filter(models.Hotspot.source == source)
    else:
        query = db.query(models.Hotspot).filter(models.Hotspot.source == "nasa_firms")
    
    # Verification status filter
    if verified is not None:
        if verified:
            # Has verification record
            query = query.join(models.Verification, models.Hotspot.id == models.Verification.hotspot_id)
        else:
            # No verification record
            query = query.outerjoin(models.Verification, models.Hotspot.id == models.Verification.hotspot_id)
            query = query.filter(models.Verification.id.is_(None))
    
    # Date range filter
    if start_date:
        try:
            start_dt = datetime.fromisoformat(start_date.replace('Z', '+00:00'))
            query = query.filter(models.Hotspot.acq_date >= start_dt)
        except ValueError:
            pass
    if end_date:
        try:
            end_dt = datetime.fromisoformat(end_date.replace('Z', '+00:00'))
            query = query.filter(models.Hotspot.acq_date <= end_dt)
        except ValueError:
            pass
    
    # Minimum FRP filter
    if min_frp is not None:
        query = query.filter(models.Hotspot.frp.isnot(None), models.Hotspot.frp >= min_frp)

    # facility_id presence filter (true = IS NOT NULL, false = IS NULL)
    if facility_id is not None:
        if facility_id:
            query = query.filter(models.Hotspot.facility_id.isnot(None))
        else:
            query = query.filter(models.Hotspot.facility_id.is_(None))

    # baseline_status filter
    if baseline_status:
        query = query.filter(models.Hotspot.baseline_status == baseline_status)

    # anomaly filter (true / false / null=unknown)
    if anomaly is not None:
        if anomaly:
            query = query.filter(models.Hotspot.is_anomaly.is_(True))
        else:
            query = query.filter(models.Hotspot.is_anomaly.is_(False))

    # risk_level filter
    if risk_level:
        query = query.filter(models.Hotspot.risk_level == risk_level)

    # classification filter (maps to category column)
    if classification:
        query = query.filter(models.Hotspot.category == classification)

    # history_status filter (SUFFICIENT = baseline_status != INSUFFICIENT_HISTORY,
    # INSUFFICIENT = baseline_status == INSUFFICIENT_HISTORY)
    if history_status:
        if history_status.upper() == 'SUFFICIENT':
            query = query.filter(models.Hotspot.baseline_status != 'INSUFFICIENT_HISTORY')
        elif history_status.upper() == 'INSUFFICIENT':
            query = query.filter(models.Hotspot.baseline_status == 'INSUFFICIENT_HISTORY')

    # Get all matching hotspots for facility distance calculation
    candidates = query.all()

    # Get facilities for distance calculation
    facilities = db.query(models.Facility).all()

    # Calculate distance to nearest facility for each candidate
    enriched = []
    for h in candidates:
        # KAVACH operational scope: India only.
        # Raw NASA FIRMS observations are preserved in the database;
        # this is a scope filter for the analyst queue only.
        if h.source == "nasa_firms" and not is_in_india(h.lat, h.lon):
            continue

        nearest_dist = None
        nearest_facility = None
        for f in facilities:
            d = haversine_km(h.lat, h.lon, f.lat, f.lon)
            if nearest_dist is None or d < nearest_dist:
                nearest_dist = d
                nearest_facility = f
        
        # Apply facility_associated filter
        if facility_associated is not None:
            is_near = nearest_dist is not None and nearest_dist <= 5.0
            if facility_associated and not is_near:
                continue
            if not facility_associated and is_near:
                continue
        
        # Compute diversity bins
        spat_bin = spatial_bin(h.lat, h.lon)
        temp_bin = temporal_bin(h.acq_date) if h.acq_date else "unknown"
        therm_bin = thermal_bin(h.brightness)
        frp_bin_val = frp_bin(h.frp)
        fac_bin = facility_proximity_bin(round(nearest_dist, 3) if nearest_dist else None)
        
        enriched.append({
    "hotspot": h,
    "nearest_facility": nearest_facility if nearest_dist is not None and nearest_dist <= 5.0 else None,
    "distance_to_nearest_facility_km": round(nearest_dist, 3) if nearest_dist is not None else None,
    "spatial_bin": spat_bin,
    "temporal_bin": temp_bin,
    "thermal_bin": therm_bin,
    "frp_bin": frp_bin_val,
    "facility_bin": fac_bin,
})

    # Prioritization scoring
    def priority_score(item):
        h = item["hotspot"]
        score = 0

        # Unverified gets highest priority
        if not h.verification:
            score += 1000

        # High FRP
        if h.frp and h.frp > 100:
            score += 200
        elif h.frp and h.frp > 50:
            score += 100
        elif h.frp and h.frp > 10:
            score += 50
        elif h.frp and h.frp > 5:
            score += 25

        # High brightness
        if h.brightness >= 340:
            score += 150
        elif h.brightness >= 320:
            score += 100
        elif h.brightness >= 300:
            score += 50

        # Facility proximity (both near and far are valuable for different classes)
        dist = item["distance_to_nearest_facility_km"]
        if dist is not None:
            if dist <= 2.0:
                score += 100  # Near facility - good for industrial labels
            elif dist >= 10.0:
                score += 100  # Far from facility - good for wildfire/agricultural

        # Recent observations get slight boost
        if h.acq_date:
            days_old = (datetime.utcnow() - h.acq_date).days
            if days_old <= 30:
                score += 50
            elif days_old <= 90:
                score += 25

        # --- Label diversity: prioritize candidates that would produce
        #     different training classes, not just the highest-risk ones.
        if label_diversity:
            # Facility-associated anomalies are the scarcest, most valuable class
            if dist is not None and dist <= 5.0 and h.baseline_status == "ABNORMAL":
                score += 200
            # Normal facility observations (NORMAL baseline, near facility)
            if dist is not None and dist <= 5.0 and h.baseline_status == "NORMAL":
                score += 120
            # Facility-associated ELEVATED
            if dist is not None and dist <= 5.0 and h.baseline_status == "ELEVATED":
                score += 150
            # High-FRP unmatched observations (potential wildfire/agricultural)
            if (dist is None or dist > 5.0) and h.frp and h.frp >= 10:
                score += 100
            # Low-FRP unmatched observations (also valuable for contrast)
            if (dist is None or dist > 5.0) and h.frp is not None and h.frp < 5:
                score += 60
            # INSUFFICIENT_HISTORY near facility (industrial_new candidate)
            if dist is not None and dist <= 5.0 and h.baseline_status == "INSUFFICIENT_HISTORY":
                score += 80

        return score

    # Sort by priority score first
    enriched.sort(key=priority_score, reverse=True)

    if diversity and len(enriched) > limit:
        # Diversity sampling: pick candidates to maximize coverage across bins
        selected = []
        seen_spatial = set()
        seen_temporal = set()
        seen_thermal = set()
        seen_frp = set()
        seen_facility = set()
        seen_baseline = set()
        seen_category = set()

        # First pass: ensure unverified are included (highest priority)
        seen_facility_ids = set()
        for item in enriched:
            h = item["hotspot"]
            if not h.verification and len(selected) < limit:
                selected.append(item)
                seen_spatial.add(item["spatial_bin"])
                seen_temporal.add(item["temporal_bin"])
                seen_thermal.add(item["thermal_bin"])
                seen_frp.add(item["frp_bin"])
                seen_facility.add(item["facility_bin"])
                seen_baseline.add(h.baseline_status)
                seen_category.add(h.category)
                if item["nearest_facility"]:
                    seen_facility_ids.add(item["nearest_facility"].id)

        # Second pass: fill remaining slots with diversity priority
        for item in enriched:
            if len(selected) >= limit:
                break
            if item in selected:
                continue

            # Calculate diversity bonus
            diversity_score = 0
            if item["spatial_bin"] not in seen_spatial:
                diversity_score += 50
            if item["temporal_bin"] not in seen_temporal:
                diversity_score += 30
            if item["thermal_bin"] not in seen_thermal:
                diversity_score += 30
            if item["frp_bin"] not in seen_frp:
                diversity_score += 20
            if item["facility_bin"] not in seen_facility:
                diversity_score += 40

            # Label-class diversity bonuses
            h = item["hotspot"]
            if h.baseline_status not in seen_baseline:
                diversity_score += 35
            if h.category not in seen_category:
                diversity_score += 25
            # Facility identity diversity
            if item["nearest_facility"] and item["nearest_facility"].id not in seen_facility_ids:
                diversity_score += 30

            # Add to priority score for final ranking
            item["diversity_bonus"] = diversity_score
            item["base_score"] = priority_score(item)
            item["final_score"] = item["base_score"] + diversity_score

        # Sort remaining by final score
        remaining = [item for item in enriched if item not in selected]
        remaining.sort(key=lambda x: x.get("final_score", x.get("base_score", 0)), reverse=True)

        # Fill remaining slots
        for item in remaining:
            if len(selected) >= limit:
                break
            selected.append(item)
            seen_spatial.add(item["spatial_bin"])
            seen_temporal.add(item["temporal_bin"])
            seen_thermal.add(item["thermal_bin"])
            seen_frp.add(item["frp_bin"])
            seen_facility.add(item["facility_bin"])
            seen_baseline.add(item["hotspot"].baseline_status)
            seen_category.add(item["hotspot"].category)

        enriched = selected[:limit]
    else:
        enriched = enriched[:limit]
    
    # Build response with candidate_reasons
    results = []
    for item in enriched:
        h = item["hotspot"]
        facility_info = None
        dist = item["distance_to_nearest_facility_km"]
        facility_associated = dist is not None and dist <= FACILITY_ASSOCIATION_RADIUS_KM
        if facility_associated and item["nearest_facility"]:
            facility_info = {
                "id": item["nearest_facility"].id,
                "name": item["nearest_facility"].name,
                "type": item["nearest_facility"].type,
                "state": item["nearest_facility"].state,
                "criticality": item["nearest_facility"].criticality,
            }
        
        # Build candidate reasons
        reasons = []
        if not h.verification:
            reasons.append("UNVERIFIED")
        if h.frp and h.frp > 100:
            reasons.append("HIGH_FRP")
        elif h.frp and h.frp > 50:
            reasons.append("MEDIUM_FRP")
        if h.brightness >= 340:
            reasons.append("HIGH_BRIGHTNESS")
        elif h.brightness >= 320:
            reasons.append("MEDIUM_BRIGHTNESS")
        dist = item["distance_to_nearest_facility_km"]
        if dist is not None and dist <= FACILITY_ASSOCIATION_RADIUS_KM:
            reasons.append("FACILITY_PROXIMITY")
        elif dist is not None:
            reasons.append("FAR_FROM_FACILITY")
        
        # Diversity reasons (only if diversity sampling was used)
        if diversity:
            if "diversity_bonus" in item and item["diversity_bonus"] > 0:
                selected_spatial = {r.get("spatial_bin") for r in selected if "spatial_bin" in r}
                selected_temporal = {r.get("temporal_bin") for r in selected if "temporal_bin" in r}
                selected_thermal = {r.get("thermal_bin") for r in selected if "thermal_bin" in r}
                selected_facility = {r.get("facility_bin") for r in selected if "facility_bin" in r}
                
                if item["spatial_bin"] not in selected_spatial:
                    reasons.append("GEOGRAPHIC_DIVERSITY")
                if item["temporal_bin"] not in selected_temporal:
                    reasons.append("TEMPORAL_DIVERSITY")
                if item["thermal_bin"] not in selected_thermal:
                    reasons.append("THERMAL_DIVERSITY")
                if item["facility_bin"] not in selected_facility:
                    reasons.append("FACILITY_DIVERSITY")
        
        results.append({
            "id": h.id,
            "lat": h.lat,
            "lon": h.lon,
            "brightness": h.brightness,
            "confidence": h.confidence,
            "frp": h.frp,
            "acq_date": h.acq_date.isoformat() if h.acq_date else None,
            "satellite": h.satellite,
            "source": h.source,
            "source_resolution_m": h.source_resolution_m,
            "land_cover": h.land_cover,
            "facility": facility_info,
            "distance_to_facility_km": item["distance_to_nearest_facility_km"],
            "verified": h.verification is not None,
            "verification_decision": h.verification.decision if h.verification else None,
            "verification_note": h.verification.note if h.verification else None,
            "category": h.category,
            "classification_method": h.classification_method,
            "classification_confidence": h.classification_confidence,
            "baseline_status": h.baseline_status,
            "z_score": h.z_score,
            "deviation_percentage": h.deviation_percentage,
            "persistence_score": h.persistence_score,
            "is_anomaly": h.is_anomaly,
            "reason": h.reason,
            "reason_codes": h.reason_codes,
            "risk_score": h.risk_score,
            "risk_level": h.risk_level,
            "data_quality": h.data_quality,
            "created_at": h.created_at.isoformat() if h.created_at else None,
            "updated_at": h.updated_at.isoformat() if h.updated_at else None,
            "candidate_reasons": reasons,
        })
    
    return {
        "candidates": results,
        "total_matched": len(enriched),
        "returned": len(results),
    }


@router.get("", response_model=schemas.PaginatedHotspots)
def list_hotspots(
    state: Optional[str] = None,
    category: Optional[str] = None,
    risk_level: Optional[str] = None,
    source: Optional[str] = None,   # "nasa_firms", "demo_synthetic", "demo", or "all"
    facility_id: Optional[int] = None,
    anomaly_only: bool = False,
    verified: Optional[bool] = Query(None, description="Filter by verification status: true=verified, false=unverified, null=both"),
    limit: int = Query(500, le=2000, description="Page size — use a large value (e.g. 10000) or page with offset"),
    offset: int = Query(0, ge=0, description="Pagination offset for sequential page fetching"),
    india_scope: bool = Query(False, description="If true and source is nasa_firms, return only India-scoped observations"),
    db: Session = Depends(get_db),
):
    """Returns hotspots as a paginated envelope with total count.

    Use `limit` and `offset` to page through results. For fetching all
    records, the frontend should iterate pages until returned count < limit.
    The `total` field tells you how many records match the current filters.
    """
    query = db.query(models.Hotspot)
    if state:
        query = query.filter(models.Hotspot.state == state)
    if category:
        query = query.filter(models.Hotspot.category == category)
    if risk_level:
        query = query.filter(models.Hotspot.risk_level == risk_level)
    if source and source != "all":
        query = query.filter(models.Hotspot.source == source)
    if facility_id is not None:
        query = query.filter(models.Hotspot.facility_id == facility_id)
    if anomaly_only:
        query = query.filter(models.Hotspot.is_anomaly.is_(True))

    # Verification-status filter (spec §22-23): join to verifications table.
    # verified=true  → has a verification record
    # verified=false → has NO verification record (unverified)
    # verified=null  → no filter (default — return both)
    if verified is not None:
        if verified:
            query = query.join(models.Verification, models.Hotspot.id == models.Verification.hotspot_id)
        else:
            query = query.outerjoin(models.Verification, models.Hotspot.id == models.Verification.hotspot_id)
            query = query.filter(models.Verification.id.is_(None))

    # India scope filter pushed into SQL so pagination works correctly.
    # Uses the same bounding boxes as india_scope.is_in_india().
    if india_scope:
        b = _INDIA_BOUNDS
        query = query.filter(
            models.Hotspot.lat >= b["min_lat"],
            models.Hotspot.lat <= b["max_lat"],
            models.Hotspot.lon >= b["min_lon"],
            models.Hotspot.lon <= b["max_lon"],
        )
        for zone in (_SRI_LANKA_BOUNDS, _BANGLADESH_BOUNDS, _MYANMAR_BOUNDS):
            query = query.filter(
                ~and_(
                    models.Hotspot.lat >= zone["min_lat"],
                    models.Hotspot.lat <= zone["max_lat"],
                    models.Hotspot.lon >= zone["min_lon"],
                    models.Hotspot.lon <= zone["max_lon"],
                )
            )

    # Count total AFTER all filters but BEFORE pagination.
    total = query.order_by(None).count()

    results = query.order_by(models.Hotspot.acq_date.desc()).offset(offset).limit(limit).all()

    return schemas.PaginatedHotspots(
        total=total,
        limit=limit,
        offset=offset,
        hotspots=results,
    )


@router.get("/export")
def export_nasa_firms(
    format: str = Query("csv", description="Output format: csv or json"),
    classification: Optional[str] = Query(None, description="Filter by category: unknown / industrial_normal / industrial_alert / industrial_new / wildfire / agricultural_burning"),
    verification_decision: Optional[str] = Query(None, description="Filter by analyst verification decision, e.g. confirmed_normal_industrial_heat"),
    db: Session = Depends(get_db),
):
    """
    READ-ONLY export of REAL NASA FIRMS hotspot records for analyst selection.

    Source is hard-filtered to nasa_firms only. No database records are
    modified, created, or deleted by this endpoint. Intended to produce a
    flat list (e.g. 280 IDs) for human verification intake.
    """
    import csv
    import io
    from datetime import datetime

    query = db.query(models.Hotspot).filter(models.Hotspot.source == "nasa_firms")
    if classification:
        query = query.filter(models.Hotspot.category == classification)
    if verification_decision:
        query = query.join(models.Verification, models.Hotspot.id == models.Verification.hotspot_id)
        query = query.filter(models.Verification.decision == verification_decision)
    hotspots = query.order_by(models.Hotspot.id.asc()).all()

    facilities = db.query(models.Facility).all()

    def nearest_facility_for(h):
        nearest_dist = None
        nearest_facility = None
        for f in facilities:
            d = haversine_km(h.lat, h.lon, f.lat, f.lon)
            if nearest_dist is None or d < nearest_dist:
                nearest_dist = d
                nearest_facility = f
        return nearest_facility, nearest_dist

    def build_row(h):
        facility, dist = nearest_facility_for(h)
        verification = h.verification
        return {
            "id": h.id,
            "latitude": h.lat,
            "longitude": h.lon,
            "brightness": h.brightness,
            "frp": h.frp,
            "confidence": h.confidence,
            "acq_date": h.acq_date.isoformat() if h.acq_date else "",
            "acq_time": h.acq_date.strftime("%H:%M:%S") if h.acq_date else "",
            "satellite": h.satellite,
            "facility_id": facility.id if facility else "",
            "facility_name": facility.name if facility else "",
            "facility_distance": round(dist, 3) if dist is not None else "",
            "baseline_status": h.baseline_status,
            "z_score": h.z_score,
            "deviation_percentage": h.deviation_percentage,
            "persistence_score": h.persistence_score,
            "anomaly": "true" if h.is_anomaly else "false",
            "risk_level": h.risk_level,
            "classification": h.category,
            "verified": "true" if verification else "false",
            "verification_decision": verification.decision if verification else "",
        }

    rows = [build_row(h) for h in hotspots]
    fieldnames = [
        "id", "latitude", "longitude", "brightness", "frp", "confidence",
        "acq_date", "acq_time", "satellite", "facility_id", "facility_name",
        "facility_distance", "baseline_status", "z_score",
        "deviation_percentage", "persistence_score", "anomaly", "risk_level",
        "classification", "verified", "verification_decision",
    ]

    if format.lower() == "json":
        return {
            "source": "nasa_firms",
            "total_records": len(rows),
            "records": rows,
        }

    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=fieldnames)
    writer.writeheader()
    for row in rows:
        writer.writerow(row)

    return Response(
        content=buffer.getvalue(),
        media_type="text/csv",
        headers={
            "Content-Disposition": 'attachment; filename="nasa_firms_hotspots.csv"',
            "X-Total-Records": str(len(rows)),
        },
    )


@router.get("/{hotspot_id}", response_model=schemas.HotspotOut)
def get_hotspot(hotspot_id: int, db: Session = Depends(get_db)):
    hotspot = db.query(models.Hotspot).filter(models.Hotspot.id == hotspot_id).first()
    if not hotspot:
        return {"error": "not found"}
    return hotspot


@router.get("/{hotspot_id}/history", response_model=List[schemas.HotspotOut])
def get_hotspot_history(
    hotspot_id: int,
    db: Session = Depends(get_db),
    source: Optional[str] = Query(None, description="Filter history by source: nasa_firms, demo, demo_synthetic, or all"),
):
    """Returns the historical observations for the same facility as the given hotspot.

    By default returns ALL sources. Pass source='nasa_firms', source='demo',
    or source='demo_synthetic' to filter. source='all' also returns all sources.
    """
    hotspot = db.query(models.Hotspot).filter(models.Hotspot.id == hotspot_id).first()
    if not hotspot or not hotspot.facility_id:
        return []
    query = (
        db.query(models.Hotspot)
        .filter(models.Hotspot.facility_id == hotspot.facility_id)
    )
    if source and source != "all":
        query = query.filter(models.Hotspot.source == source)
    return query.order_by(models.Hotspot.acq_date.asc()).all()


@router.get("/{hotspot_id}/satellite-image")
def get_satellite_image(hotspot_id: int, db: Session = Depends(get_db)):
    hotspot = db.query(models.Hotspot).filter(models.Hotspot.id == hotspot_id).first()
    if not hotspot:
        return {"error": "not found"}
    acq_date = hotspot.acq_date if isinstance(hotspot.acq_date, datetime) else None
    return build_satellite_image_url(hotspot.lat, hotspot.lon, acq_date)


@router.get("/{hotspot_id}/geographic-context", response_model=schemas.GeographicContextOut)
def get_geographic_context(hotspot_id: int, db: Session = Depends(get_db)):
    """
    Nearby mapped geographic features for an observation.

    Uses the SAME Overpass / OpenStreetMap source already used by
    landcover_fetcher — no new dependency, no API key, no signup. Returns
    only features that actually exist; never invents a place or facility.

    A "nearby feature" is NOT a confirmed source of fire — the UI must
    keep that distinction explicit.
    """
    from app.services import geographic_context
    hotspot = db.query(models.Hotspot).filter(models.Hotspot.id == hotspot_id).first()
    if not hotspot:
        return {"error": "not found"}
    summary = geographic_context.summarize(hotspot.lat, hotspot.lon)
    return {
        "hotspot_id": hotspot.id,
        "lat": hotspot.lat,
        "lon": hotspot.lon,
        "radius_m": summary["radius_m"],
        "feature_count": summary["feature_count"],
        "features": summary["features"],
    }


@router.get("/{hotspot_id}/assessment")
def get_assessment(hotspot_id: int, db: Session = Depends(get_db)):
    """
    Structured incident assessment built ENTIRELY from stored data — no
    LLM is allowed to invent facts here (spec §32). This is what
    'Generate Assessment' in the UI calls.
    """
    hotspot = db.query(models.Hotspot).filter(models.Hotspot.id == hotspot_id).first()
    if not hotspot:
        return {"error": "not found"}

    facility_name = hotspot.facility.name if hotspot.facility else "Unregistered location"
    reason_codes = hotspot.reason_codes.split(",") if hotspot.reason_codes else []

    recommended_action = "MONITOR"
    if hotspot.risk_level == "CRITICAL":
        recommended_action = "VERIFY IMMEDIATELY"
    elif hotspot.risk_level == "HIGH":
        recommended_action = "VERIFY"
    elif hotspot.category == "unknown":
        recommended_action = "MANUAL REVIEW — insufficient evidence to classify"

    return {
        "event_id": f"KV-{hotspot.id:04d}",
        "facility": facility_name,
        "facility_type": hotspot.facility.type if hotspot.facility else None,
        "facility_criticality": hotspot.facility.criticality if hotspot.facility else None,
        "assessment": hotspot.category.replace("_", " ").title(),
        "risk_level": hotspot.risk_level,
        "risk_score": hotspot.risk_score,
        "classification_method": hotspot.classification_method,
        "classification_confidence": hotspot.classification_confidence,
        "baseline_status": hotspot.baseline_status,
        "deviation_percentage": hotspot.deviation_percentage,
        "reason": hotspot.reason,
        "reason_codes": reason_codes,
        "data_quality": hotspot.data_quality,
        "data_source": hotspot.source,
        "acquisition_time": hotspot.acq_date.isoformat() if hotspot.acq_date else None,
        "satellite": hotspot.satellite,
        "recommended_analyst_action": recommended_action,
        "disclaimer": "Coordinate represents the satellite-detected thermal observation location, "
                      "not a confirmed fire boundary or verified facility ownership.",
    }


@router.post("/{hotspot_id}/verify", response_model=schemas.VerificationOut)
def verify_hotspot(hotspot_id: int, payload: schemas.VerificationIn, db: Session = Depends(get_db)):
    hotspot = db.query(models.Hotspot).filter(models.Hotspot.id == hotspot_id).first()
    if not hotspot:
        raise HTTPException(status_code=404, detail="Hotspot not found")

    # A confirmed_industrial_fire decision must carry an analyst note so the
    # ground-truth label is auditable. This is a validation guard, not a
    # change to the classification or verification workflow.
    if payload.decision == "confirmed_industrial_fire" and not (payload.note or "").strip():
        raise HTTPException(
            status_code=400,
            detail="A non-empty analyst note is required for confirmed_industrial_fire.",
        )

    existing = db.query(models.Verification).filter(models.Verification.hotspot_id == hotspot_id).first()
    if existing:
        existing.decision = payload.decision
        existing.note = payload.note or ""
        existing.analyst_name = payload.analyst_name or ""
        db.commit()
        db.refresh(existing)
        return existing

    verification = models.Verification(hotspot_id=hotspot_id, decision=payload.decision,
                                        note=payload.note or "", analyst_name=payload.analyst_name or "")
    db.add(verification)
    db.commit()
    db.refresh(verification)
    return verification


@router.get("/{hotspot_id}/verification")
def get_verification(hotspot_id: int, db: Session = Depends(get_db)):
    verification = db.query(models.Verification).filter(models.Verification.hotspot_id == hotspot_id).first()
    if not verification:
        # Return a plain JSON error response instead of a bare dict so the
        # declared response_model does not raise a 500 during serialization
        # (which would also suppress the CORS headers the middleware adds).
        return JSONResponse(
            status_code=404,
            content={"error": "not verified yet", "hotspot_id": hotspot_id},
        )
    return verification


@router.get("/wildfire/candidates")
def get_wildfire_candidates(
    limit: int = Query(100, le=1000),
    tier: Optional[str] = Query(None, description="Filter by candidate tier"),
    minimum_score: float = Query(0.0),
    minimum_cluster_dates: int = Query(1),
    land_cover: Optional[str] = Query(None, description="Filter by land cover"),
    exclude_facility: bool = Query(True, description="Exclude facility-associated observations"),
    source: Optional[str] = Query(None, description="Filter by source"),
    db: Session = Depends(get_db),
):
    """READ-ONLY, OFFLINE, DATABASE-ONLY wildfire candidate generation.

    Never modifies classification, verified, or verification_decision.
    review_required is always True. This is a high-precision candidate
    detector, not a wildfire classifier. No network calls are made.
    """
    from app.services.wildfire_engine import (
    build_clusters,
    evaluate_wildfire_candidate,
    NOT_A_CANDIDATE,
    TIER_A_STRONG,
    TIER_B_PLAUSIBLE,
)

    # Load only the required FIRMS fields once, then aggregate locally.
    query = db.query(models.Hotspot).filter(
        models.Hotspot.source == (source or "nasa_firms"),
        models.Hotspot.lat.isnot(None),
        models.Hotspot.lon.isnot(None),
    )
    if exclude_facility:
        query = query.filter(models.Hotspot.facility_id.is_(None))
    hotspots = query.all()

    clusters = build_clusters(hotspots)

    results = []
    cluster_evals = {}
    for cluster_info in clusters.values():
        if cluster_info["unique_dates"] < minimum_cluster_dates:
            continue

        eval_result = evaluate_wildfire_candidate(cluster_info)
        cluster_evals[cluster_info["cluster_id"]] = eval_result
        if eval_result["candidate_tier"] == NOT_A_CANDIDATE:
            continue
        if eval_result["wildfire_candidate_score"] < minimum_score:
            continue
        if tier and eval_result["candidate_tier"] != tier:
            continue

        # Representative observation for the candidate row.
        rep = None
        for hid in cluster_info["hotspot_ids"]:
            rep = db.query(models.Hotspot).filter(models.Hotspot.id == hid).first()
            if rep is not None:
                break
        if rep is None:
            continue

        if land_cover and (rep.land_cover or "unknown").lower() != land_cover.lower():
            continue

        results.append({
            "hotspot_id": rep.id,
            "latitude": rep.lat,
            "longitude": rep.lon,
            "acq_date": rep.acq_date.isoformat() if rep.acq_date else None,
            "brightness": rep.brightness,
            "frp": rep.frp,
            "confidence": rep.confidence,
            "cluster_id": cluster_info["cluster_id"],
            "cluster_observation_count": cluster_info["observation_count"],
            "cluster_unique_dates": cluster_info["unique_dates"],
            "cluster_duration_days": cluster_info["cluster_duration_days"],
            "max_frp": cluster_info["max_frp"],
            "median_frp": cluster_info["median_frp"],
            "wildfire_candidate_score": eval_result["wildfire_candidate_score"],
            "candidate_tier": eval_result["candidate_tier"],
            "supporting_evidence": eval_result["supporting_evidence"],
            "contradicting_evidence": eval_result["contradicting_evidence"],
            "temporal_concentration": eval_result.get("temporal_concentration"),
            "frp_intensity_score": eval_result.get("frp_intensity_score"),
            "recurrence_score": eval_result.get("recurrence_score"),
            "confidence_score": eval_result.get("confidence_score"),
            "review_required": True,
        })

    results.sort(key=lambda x: x["wildfire_candidate_score"], reverse=True)

    tier_a = sum(1 for r in results if r["candidate_tier"] == TIER_A_STRONG)
    tier_b = sum(1 for r in results if r["candidate_tier"] == TIER_B_PLAUSIBLE)
    not_candidate = sum(
        1 for ev in cluster_evals.values()
        if ev["candidate_tier"] == NOT_A_CANDIDATE
    )

    return {
        "total_examined": len(hotspots),
        "total_spatial_cells": len(clusters),
        "cells_passing_candidate_gate": len(results),
        "tier_a_count": tier_a,
        "tier_b_count": tier_b,
        "not_candidate_count": not_candidate,
        "returned": len(results[:limit]),
        "candidates": results[:limit],
        "data_readiness": {
            "land_cover_available": False,
            "non_facility_baseline_available": False,
            "message": "Fully offline, database-only candidate detector. No external APIs, no land-cover "
                       "service, no satellite downloads. review_required is always True; candidates are "
                       "advisory and must be reviewed by an analyst before any action.",
        },
    }


@router.get("/normal-industrial-heat/candidates")
def get_normal_industrial_heat_candidates(
    limit: int = Query(70, le=70, description="Max candidates to return (capped at 70)"),
    source: Optional[str] = Query(None, description="Filter by source"),
    db: Session = Depends(get_db),
):
    """READ-ONLY ground-truth labeling queue for NORMAL_INDUSTRIAL_HEAT.

    This endpoint ONLY READS the database. It never writes, never labels,
    never verifies, and never modifies classification, verified, or
    verification_decision. Facility proximity is CONTEXT, not proof of
    causation — wording everywhere stays "facility-associated context".

    Candidate criteria:
      - source = nasa_firms
      - facility-associated within the canonical FACILITY_ASSOCIATION_RADIUS_KM
      - baseline_status = NORMAL
      - is_anomaly = False
      - NOT already verified
      - NOT already assigned a non-UNKNOWN verified classification

    Ranking priority:
      1. NORMAL baseline with sufficient history
      2. anomaly = NO
      3. low risk
      4. stronger persistence/history
      5. better confidence/data quality
      6. smaller facility distance
    """
    from app.services.facility_constants import FACILITY_ASSOCIATION_RADIUS_KM

    query = db.query(models.Hotspot).filter(
        models.Hotspot.source == (source or "nasa_firms"),
        models.Hotspot.baseline_status == "NORMAL",
        models.Hotspot.is_anomaly == False,
        models.Hotspot.distance_to_facility_km.isnot(None),
        models.Hotspot.distance_to_facility_km <= FACILITY_ASSOCIATION_RADIUS_KM,
    )

    # Exclude already-verified records and records with a non-UNKNOWN
    # verified classification. UNKNOWN remains UNKNOWN until analyst review.
    query = query.outerjoin(
        models.Verification,
        models.Verification.hotspot_id == models.Hotspot.id,
    ).filter(
        models.Verification.id.is_(None),
    )

    hotspots = query.all()

    # Rank deterministically. Each tuple is (priority_key, tiebreakers...).
    # Facility diversity is a final tiebreak so the ground-truth queue draws
    # from multiple facilities rather than exhausting one site first.
    facility_ids = sorted({h.facility_id for h in hotspots if h.facility_id})
    facility_rank = {fid: i for i, fid in enumerate(facility_ids)}

    def _rank_key(h):
        # 1. baseline_status NORMAL (all rows already NORMAL) + sufficient history
        #    => observation_count >= MIN_OBSERVATIONS_FOR_BASELINE is preferred.
        #    We approximate "sufficient history" via persistence_score.
        sufficient_history = 1 if (h.persistence_score or 0.0) > 0 else 0
        # 2. anomaly = NO (all rows already non-anomalous)
        # 3. low risk: lower risk_level ordinal first
        risk_order = {"LOW": 0, "WATCH": 1, "HIGH": 2, "CRITICAL": 3}
        risk_rank = risk_order.get(h.risk_level or "LOW", 0)
        # 4. stronger persistence/history: higher persistence first
        persistence = h.persistence_score or 0.0
        # 5. better confidence/data quality: higher confidence first,
        #    then better data_quality ordinal
        quality_order = {"good": 0, "medium": 1, "degraded": 2, "poor": 3, "unknown": 4}
        quality_rank = quality_order.get(h.data_quality or "unknown", 4)
        confidence = h.confidence or 0.0
        # 6. smaller facility distance first
        dist = h.distance_to_facility_km or 0.0
        # 7. facility diversity tiebreak (round-robin across facilities)
        facility_idx = facility_rank.get(h.facility_id, 999)
        return (
            -sufficient_history,   # sufficient history first
            risk_rank,             # low risk first
            -persistence,          # stronger persistence first
            quality_rank,          # better data quality first
            -confidence,           # higher confidence first
            dist,                  # smaller distance first
            facility_idx,          # facility diversity tiebreak
            h.id,                  # deterministic tiebreak
        )

    ranked = sorted(hotspots, key=_rank_key)

    # Round-robin across facilities so the ground-truth queue draws from
    # multiple sites instead of exhausting one facility's candidates first.
    # The primary ranking above still governs which candidate is picked
    # within each facility's turn.
    selected = []
    by_facility = {}
    for h in ranked:
        by_facility.setdefault(h.facility_id, []).append(h)
    active = sorted(by_facility.keys())
    while active and len(selected) < limit:
        for fid in list(active):
            if len(selected) >= limit:
                break
            if fid in by_facility and by_facility[fid]:
                selected.append(by_facility[fid].pop(0))
            if fid in by_facility and not by_facility[fid]:
                active.remove(fid)

    results = []
    for h in selected:
        facility = h.facility
        results.append({
            "id": h.id,
            "latitude": h.lat,
            "longitude": h.lon,
            "acq_date": h.acq_date.isoformat() if h.acq_date else None,
            "brightness": h.brightness,
            "frp": h.frp,
            "confidence": h.confidence,
            "facility_id": facility.id if facility else None,
            "facility_name": facility.name if facility else None,
            "facility_distance": round(h.distance_to_facility_km, 3) if h.distance_to_facility_km is not None else None,
            "baseline_status": h.baseline_status,
            "z_score": h.z_score,
            "deviation_percentage": h.deviation_percentage,
            "persistence_score": h.persistence_score,
            "anomaly": h.is_anomaly,
            "risk_level": h.risk_level,
            "classification": h.category,
            "verified": h.verification is not None,
            "verification_decision": h.verification.decision if h.verification else None,
            "reason_codes": h.reason_codes,
            "candidate_score": round(
                (1.0 if (h.persistence_score or 0.0) > 0 else 0.0) * 30.0
                + (0.0 if (h.risk_level or "LOW") == "LOW" else 10.0)
                + (h.persistence_score or 0.0) * 10.0
                + (h.confidence or 0.0) * 0.2
                + (1.0 - (h.distance_to_facility_km or 0.0) / FACILITY_ASSOCIATION_RADIUS_KM) * 5.0,
                2),
            "review_required": True,
        })

    return {
        "total_candidates": len(results),
        "returned_count": len(results),
        "selection_criteria": (
            "source=nasa_firms; facility-associated within "
            f"{FACILITY_ASSOCIATION_RADIUS_KM} km; baseline_status=NORMAL; "
            "is_anomaly=False; not already verified; no non-UNKNOWN verified "
            "classification. Ranked by: sufficient history, anomaly=NO, low "
            "risk, stronger persistence/history, better confidence/data quality, "
            "smaller facility distance. Facility proximity is CONTEXT, not "
            "proof of causation. UNKNOWN remains UNKNOWN until analyst verification."
        ),
        "candidates": results,
    }


@router.get("/industrial-fire/candidates")
def get_industrial_fire_candidates(
    limit: int = Query(70, le=70, description="Max candidates to return (capped at 70)"),
    source: Optional[str] = Query(None, description="Filter by source"),
    db: Session = Depends(get_db),
):
    """READ-ONLY ground-truth labeling queue for INDUSTRIAL_FIRE candidates.

    This endpoint ONLY READS the database. It never writes, never labels,
    never verifies, and never modifies classification, verified, or
    verification_decision. A candidate is NOT automatically an
    INDUSTRIAL_FIRE — review_required is True for every row. Facility
    proximity is CONTEXT, not proof of causation. No fabricated baseline
    statistics: every returned z_score / deviation comes from stored rows.
    """
    from app.services.facility_constants import FACILITY_ASSOCIATION_RADIUS_KM

    query = db.query(models.Hotspot).filter(
        models.Hotspot.source == (source or "nasa_firms"),
        models.Hotspot.is_anomaly == True,
        models.Hotspot.baseline_status.in_(["ABNORMAL", "ELEVATED"]),
        models.Hotspot.distance_to_facility_km.isnot(None),
        models.Hotspot.distance_to_facility_km <= FACILITY_ASSOCIATION_RADIUS_KM,
    )

    # Exclude already-verified records and records with a non-UNKNOWN
    # verified classification. UNKNOWN remains UNKNOWN until analyst review.
    query = query.outerjoin(
        models.Verification,
        models.Verification.hotspot_id == models.Hotspot.id,
    ).filter(
        models.Verification.id.is_(None),
    )

    hotspots = query.all()

    # Rank deterministically. Facility diversity is a final round-robin
    # tiebreak so the queue draws from multiple sites.
    facility_ids = sorted({h.facility_id for h in hotspots if h.facility_id})
    facility_rank = {fid: i for i, fid in enumerate(facility_ids)}

    def _rank_key(h):
        # 1. ABNORMAL baseline before ELEVATED
        baseline_rank = 0 if h.baseline_status == "ABNORMAL" else 1
        # 2. anomaly = YES (all rows already anomalous)
        # 3. stronger z_score / deviation_percentage first
        z = h.z_score or 0.0
        dev = h.deviation_percentage or 0.0
        # 4. higher FRP and brightness first
        frp = h.frp or 0.0
        bright = h.brightness or 0.0
        # 5. stronger persistence/recurrence first
        persistence = h.persistence_score or 0.0
        # 6. better confidence/data quality first
        quality_order = {"good": 0, "medium": 1, "degraded": 2, "poor": 3, "unknown": 4}
        quality_rank = quality_order.get(h.data_quality or "unknown", 4)
        confidence = h.confidence or 0.0
        # 7. smaller facility distance first
        dist = h.distance_to_facility_km or 0.0
        # 8. facility diversity tiebreak
        facility_idx = facility_rank.get(h.facility_id, 999)
        return (
            baseline_rank,        # ABNORMAL first
            -z,                   # stronger z_score first
            -dev,                 # stronger deviation first
            -frp,                 # higher FRP first
            -bright,              # higher brightness first
            -persistence,         # stronger persistence first
            quality_rank,         # better data quality first
            -confidence,          # higher confidence first
            dist,                 # smaller distance first
            facility_idx,         # facility diversity tiebreak
            h.id,                 # deterministic tiebreak
        )

    ranked = sorted(hotspots, key=_rank_key)

    # Round-robin across facilities so the ground-truth queue draws from
    # multiple sites instead of exhausting one facility's candidates first.
    selected = []
    by_facility = {}
    for h in ranked:
        by_facility.setdefault(h.facility_id, []).append(h)
    active = sorted(by_facility.keys())
    while active and len(selected) < limit:
        for fid in list(active):
            if len(selected) >= limit:
                break
            if fid in by_facility and by_facility[fid]:
                selected.append(by_facility[fid].pop(0))
            if fid in by_facility and not by_facility[fid]:
                active.remove(fid)

    results = []
    for h in selected:
        facility = h.facility
        score_result = compute_industrial_fire_candidate_score(h)
        results.append({
            "hotspot_id": h.id,
            "id": h.id,
            "latitude": h.lat,
            "longitude": h.lon,
            "acq_date": h.acq_date.isoformat() if h.acq_date else None,
            "brightness": h.brightness,
            "frp": h.frp,
            "source_confidence": h.confidence,
            "facility_id": facility.id if facility else None,
            "facility_name": facility.name if facility else None,
            "facility_distance": round(h.distance_to_facility_km, 3) if h.distance_to_facility_km is not None else None,
            "baseline_status": h.baseline_status,
            "z_score": h.z_score,
            "deviation_percentage": h.deviation_percentage,
            "persistence_score": h.persistence_score,
            "anomaly": h.is_anomaly,
            "risk_level": h.risk_level,
            "classification": h.category,
            "verified": h.verification is not None,
            "verification_decision": h.verification.decision if h.verification else None,
            "reason_codes": h.reason_codes,
            "industrial_fire_candidate_score": score_result["industrial_fire_candidate_score"],
            "anomaly_severity_score": score_result["anomaly_severity_score"],
            "deviation_score": score_result["deviation_score"],
            "frp_intensity_score": score_result["frp_intensity_score"],
            "persistence_score_component": score_result["persistence_score"],
            "confidence_score_component": score_result["confidence_score"],
            "score_label": score_result["score_label"],
            "score_meaning": score_result["score_meaning"],
            "review_required": True,
        })

    results.sort(key=lambda x: x["industrial_fire_candidate_score"], reverse=True)

    return {
        "total_candidates": len(results),
        "returned_count": len(results),
        "selection_criteria": (
            "source=nasa_firms; facility-associated within "
            f"{FACILITY_ASSOCIATION_RADIUS_KM} km; baseline_status=ABNORMAL or "
            "ELEVATED; is_anomaly=True; not already verified; no non-UNKNOWN "
            "verified classification. Ranked by: ABNORMAL baseline, anomaly=YES, "
            "stronger z_score/deviation, higher FRP and brightness, stronger "
            "persistence/recurrence, better confidence/data quality, smaller "
            "facility distance. Facility proximity is CONTEXT, not proof of "
            "causation. No fabricated baseline statistics. A candidate is NOT "
            "automatically an INDUSTRIAL_FIRE — review_required is True for "
            "every row. industrial_fire_candidate_score is a deterministic "
            "0-100 RANKING score (NOT a probability, confidence, or accuracy "
            "estimate); a single extreme FRP observation cannot dominate it. "
            "Final list is sorted by industrial_fire_candidate_score descending."
        ),
        "candidates": results,
    }


@router.get("/industrial-fire/review/progress")
def get_industrial_fire_review_progress(
    source: Optional[str] = Query(None, description="Filter by source"),
    db: Session = Depends(get_db),
):
    """READ-ONLY progress summary for the INDUSTRIAL_FIRE batch review.

    Returns current verified class counts and the number of candidates
    still awaiting review. Never writes, labels, or modifies anything.
    """
    base = db.query(models.Verification)
    counts = {
        "confirmed_industrial_fire": 0,
        "confirmed_normal_industrial_heat": 0,
        "wildfire": 0,
        "agricultural": 0,
        "false_positive": 0,
        "unknown": 0,
    }
    for decision in counts:
        counts[decision] = base.filter(models.Verification.decision == decision).count()

    remaining = db.query(models.Hotspot).filter(
        models.Hotspot.source == (source or "nasa_firms"),
        models.Hotspot.is_anomaly == True,
        models.Hotspot.baseline_status.in_(["ABNORMAL", "ELEVATED"]),
        models.Hotspot.distance_to_facility_km.isnot(None),
    ).outerjoin(
        models.Verification,
        models.Verification.hotspot_id == models.Hotspot.id,
    ).filter(models.Verification.id.is_(None)).count()

    return {
        "verified": counts,
        "remaining_candidates": remaining,
        "total_verified": sum(counts.values()),
        "note": "READ-ONLY summary. No candidate is auto-labeled. UNKNOWN remains "
                "UNKNOWN until an analyst explicitly decides.",
    }

