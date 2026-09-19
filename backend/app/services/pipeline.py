"""
The single orchestration path every thermal observation goes through,
whether it comes from seed.py (demo) or ingest_firms.py (real NASA data).

This exists specifically to fix the duplicated-logic problem flagged in
docs/IMPLEMENTATION_AUDIT.md — seed.py and ingest_firms.py previously
each re-implemented slightly different versions of "classify + check
anomaly". Now both call process_observation() and cannot drift apart.

    raw observation
        │
        ▼
    facility_matcher.match_facility()
        │
        ▼
    facility_fingerprint.get_baseline_for_new_reading()
    baseline_engine.evaluate_against_baseline()
        │
        ▼
    facility_fingerprint.build_fingerprint()   (only if facility matched)
        │
        ▼
    feature_engine.build_features()
        │
        ▼
    classifier.classify()
        │
        ▼
    evidence_engine.build_evidence()
        │
        ▼
    anomaly_engine.assess_anomaly()
        │
        ▼
    risk_engine.assess_risk()
        │
        ▼
    models.Hotspot (+ models.Alert if risk warrants one)
"""
from datetime import datetime
from sqlalchemy.orm import Session
from app import models
from app.services.facility_matcher import match_facility
from app.services.facility_fingerprint import build_fingerprint, get_baseline_for_new_reading
from app.services.baseline_engine import evaluate_against_baseline
from app.services.feature_engine import build_features
from app.services import classifier
from app.services.evidence_engine import build_evidence
from app.services.anomaly_engine import assess_anomaly
from app.services.risk_engine import assess_risk


def _determine_data_quality(observation: dict) -> str:
    confidence = observation.get("confidence")
    if confidence is None:
        return "unknown"
    if confidence >= 70:
        return "good"
    if confidence >= 40:
        return "degraded"
    return "poor"


def _find_duplicate(db: Session, observation: dict):
    """
    Guards against the same observation being ingested twice — a real risk
    if data-pipeline/ingest_firms.py runs on a schedule with overlapping
    day_range windows, which it does by design (day_range=1, run e.g. hourly).

    Matches on rounded coordinates (~11m, matching VIIRS pixel-scale noise)
    + the EXACT acquisition timestamp + same source. Deliberately NOT
    same-calendar-day: a facility can have multiple genuinely distinct
    readings on the same day (different satellite passes), and an earlier
    version of this function matched on day-granularity, which incorrectly
    treated a real new reading as a duplicate of an earlier one from the
    same day — caught by tests/run_pipeline_scenarios.py Scenario B, fixed
    here. Real FIRMS detections carry a genuine acq_date+acq_time from the
    satellite, so two truly identical re-ingested rows WILL share the exact
    same timestamp; two distinct passes will not.
    """
    lat_r, lon_r = round(observation["lat"], 4), round(observation["lon"], 4)
    acq_date = observation.get("acq_date") or datetime.utcnow()
    source = observation.get("source", "demo_synthetic")

    candidates = db.query(models.Hotspot).filter(
        models.Hotspot.source == source,
    ).all()
    for c in candidates:
        if (round(c.lat, 4) == lat_r and round(c.lon, 4) == lon_r
                and c.acq_date == acq_date):
            return c
    return None


def process_observation(db: Session, observation: dict, commit: bool = True) -> models.Hotspot:
    """
    observation: {lat, lon, brightness, confidence, frp?, acq_date, land_cover,
                  satellite?, source ("demo_synthetic"|"nasa_firms")}
    """
    duplicate = _find_duplicate(db, observation)
    if duplicate is not None:
        duplicate._was_duplicate = True   # transient attribute, not a DB column — for ingestion reporting only
        return duplicate

    facility, distance_km = match_facility(db, observation["lat"], observation["lon"])

    obs_source = observation.get("source", "demo_synthetic")
    is_nasa = obs_source == "nasa_firms"

    # NASA FIRMS observations use a rolling 90-day baseline computed from
    # NASA-only history. Demo observations keep the existing unbounded
    # behavior so demo data is never filtered by a window it did not opt into.
    baseline = get_baseline_for_new_reading(
        db,
        facility.id if facility else None,
        baseline_window_days=90 if is_nasa else None,
        source="nasa_firms" if is_nasa else None,
    )
    baseline_eval = evaluate_against_baseline(observation["brightness"], baseline)

    fingerprint = build_fingerprint(db, facility, source=obs_source) if facility else None

    features = build_features(observation, facility, distance_km, baseline_eval, fingerprint)
    data_quality = _determine_data_quality(observation)

    classification = classifier.classify(features)
    evidence = build_evidence(features, data_quality)
    anomaly = assess_anomaly(features, evidence)
    risk = assess_risk(anomaly, features, facility, data_quality)

    is_anomaly = anomaly["anomaly_status"] in ("ELEVATED", "ABNORMAL")

    reason_parts = evidence["supporting_evidence"][:2] or ["No strong supporting evidence identified."]
    reason = " ".join(reason_parts)

    hotspot = models.Hotspot(
        lat=observation["lat"], lon=observation["lon"],
        brightness=observation["brightness"], confidence=observation.get("confidence", 0.0),
        frp=observation.get("frp"), acq_date=observation.get("acq_date", datetime.utcnow()),
        satellite=observation.get("satellite", "VIIRS_SNPP"),
        source=observation.get("source", "demo_synthetic"),
        land_cover=features["land_cover"],
        facility_id=facility.id if facility else None,
        distance_to_facility_km=distance_km,
        state=facility.state if facility else observation.get("state", "unknown"),
        category=classification["category"],
        classification_method=classification["classification_method"],
        classification_confidence=classification["classification_confidence"],
        model_version=classification.get("model_version"),
        baseline_status=baseline_eval["baseline_status"],
        z_score=baseline_eval["z_score"],
        deviation_percentage=baseline_eval["deviation_percentage"],
        persistence_score=fingerprint["persistence_score"] if fingerprint else 0.0,
        is_anomaly=is_anomaly,
        reason=reason,
        reason_codes=",".join(evidence["reason_codes"]),
        risk_score=risk["risk_score"],
        risk_level=risk["risk_level"],
        data_quality=data_quality,
    )
    db.add(hotspot)
    db.flush()

    if risk["risk_level"] in ("HIGH", "CRITICAL"):
        db.add(models.Alert(
            hotspot_id=hotspot.id,
            severity="high" if risk["risk_level"] == "CRITICAL" else "medium",
            message=f"{facility.name if facility else 'Unregistered location'}: {reason} "
                    f"(risk: {risk['risk_level']}, score {risk['risk_score']})",
        ))

    if commit:
        db.commit()
    hotspot._was_duplicate = False
    return hotspot
