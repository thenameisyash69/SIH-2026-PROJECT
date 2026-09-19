"""
Replaces the old standalone anomaly_detector.py with a version that
reasons using baseline + persistence + evidence, not brightness alone.
Returns an explainable anomaly_score/status, never a bare z-score.
"""


def assess_anomaly(features: dict, evidence: dict) -> dict:
    baseline_status = features.get("baseline_status", "INSUFFICIENT_HISTORY")
    behavior_label = features.get("behavior_label", "INSUFFICIENT_HISTORY")

    if baseline_status == "INSUFFICIENT_HISTORY":
        return {"anomaly_score": 0.0, "anomaly_status": "UNKNOWN",
                "reason_codes": evidence["reason_codes"] + ["INSUFFICIENT_HISTORY"]}

    # A persistent-and-expected facility should NOT be flagged just because
    # it's hot — this is the exact naive mistake the spec warns against.
    if behavior_label == "PERSISTENT_EXPECTED" and baseline_status != "ABNORMAL":
        return {"anomaly_score": 5.0, "anomaly_status": "NORMAL", "reason_codes": evidence["reason_codes"]}

    score_map = {"NORMAL": 10.0, "ELEVATED": 45.0, "ABNORMAL": 80.0}
    score = score_map.get(baseline_status, 10.0)

    # Evidence can push the score up or down within its band
    score = max(0.0, min(100.0, score + evidence["evidence_score"] * 4))

    status = "ABNORMAL" if score >= 70 else "ELEVATED" if score >= 35 else "NORMAL"

    return {"anomaly_score": round(score, 1), "anomaly_status": status, "reason_codes": evidence["reason_codes"]}
