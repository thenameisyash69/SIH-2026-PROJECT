"""
Risk is deliberately NOT equal to anomaly score (spec §17). A CRITICAL
facility with an ABNORMAL reading matters far more than a low-criticality
facility with the same statistical deviation. This produces an
"operational prioritization score" — explicitly not a casualty predictor.
"""

CRITICALITY_WEIGHT = {"low": 0.6, "medium": 0.8, "high": 1.0, "critical": 1.25}

DATA_QUALITY_PENALTY = {"good": 1.0, "degraded": 0.85, "poor": 0.6, "unknown": 0.75}


def assess_risk(anomaly: dict, features: dict, facility, data_quality: str) -> dict:
    base = anomaly["anomaly_score"]
    criticality = (facility.criticality if facility else "low")
    weight = CRITICALITY_WEIGHT.get(criticality, 0.6)
    quality_factor = DATA_QUALITY_PENALTY.get(data_quality, 0.75)

    confidence_factor = min(1.0, (features.get("confidence") or 50) / 100)

    risk_score = base * weight * quality_factor * (0.5 + 0.5 * confidence_factor)
    risk_score = round(max(0.0, min(100.0, risk_score)), 1)

    if anomaly["anomaly_status"] == "UNKNOWN":
        level = "WATCH"
    elif risk_score >= 75:
        level = "CRITICAL"
    elif risk_score >= 50:
        level = "HIGH"
    elif risk_score >= 25:
        level = "WATCH"
    else:
        level = "LOW"

    reasons = [f"Anomaly status {anomaly['anomaly_status']} (score {base})",
               f"Facility criticality: {criticality}",
               f"Data quality: {data_quality}"]

    return {"risk_score": risk_score, "risk_level": level, "risk_reasons": reasons}
