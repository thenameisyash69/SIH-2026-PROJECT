"""
Analyst ranking score for INDUSTRIAL_FIRE candidate review.

READ-ONLY. This module computes ONLY a candidate-ranking score. It never
modifies risk_score, anomaly_score, classification, verification, or any
existing formula. It is deterministic, bounded to [0, 100], and is explicitly
NOT a probability, confidence, or accuracy estimate.

Every component is a transparent, normalized sub-score in [0, 1]. The final
industrial_fire_candidate_score is a weighted sum of those components, scaled
to 0-100 and clamped.

A single extreme FRP observation must not dominate the score: FRP is capped
before contributing, so one spike cannot push a weak candidate to the top.

Component weights:
  1. anomaly_severity_score   (z-score)              0.30
  2. deviation_score          (deviation_percentage) 0.20
  3. frp_intensity_score      (capped FRP)           0.20
  4. persistence_score        (persistence/rec)      0.15
  5. confidence_score         (FIRMS conf + quality) 0.15
"""

import math


# Component weights (must sum to 1.0).
W_ANOMALY_SEVERITY = 0.30
W_DEVIATION = 0.20
W_FRP = 0.20
W_PERSISTENCE = 0.15
W_CONFIDENCE = 0.15

# Anchors / caps. A single extreme value cannot dominate its component.
Z_SCORE_ANCHOR = 3.0          # z-score mapping to full severity sub-score
DEVIATION_ANCHOR = 50.0       # deviation % mapping to full deviation sub-score
FRP_CAP = 60.0                # max FRP (MW) contributing to the FRP sub-score
PERSISTENCE_ANCHOR = 1.0      # persistence score mapping to full sub-score
CONFIDENCE_ANCHOR = 100.0     # FIRMS confidence mapping to full sub-score


def _clamp01(value):
    if value < 0.0:
        return 0.0
    if value > 1.0:
        return 1.0
    return value


def _normalize(value, anchor):
    """Linear normalization against an anchor, clamped to [0, 1]."""
    if value is None:
        return 0.0
    return _clamp01(float(value) / anchor)


def compute_industrial_fire_candidate_score(hotspot):
    """Compute a deterministic 0-100 ranking score for one candidate.

    hotspot: a Hotspot ORM row (or any object exposing the stored fields).
    Returns a dict with the final score, the component sub-scores, the
    component weights, and a human-readable label.
    """
    z = getattr(hotspot, "z_score", None)
    dev = getattr(hotspot, "deviation_percentage", None)
    frp = getattr(hotspot, "frp", None)
    persistence = getattr(hotspot, "persistence_score", None)
    confidence = getattr(hotspot, "confidence", None)
    data_quality = getattr(hotspot, "data_quality", None) or "unknown"

    # 1. Anomaly severity: stronger z-score => higher severity.
    anomaly_severity_score = _normalize(z, Z_SCORE_ANCHOR)

    # 2. Deviation percentage.
    deviation_score = _normalize(dev, DEVIATION_ANCHOR)

    # 3. FRP intensity: capped so a single extreme spike cannot dominate.
    frp_intensity_score = _normalize(frp, FRP_CAP)

    # 4. Persistence / recurrence.
    persistence_sub = _normalize(persistence, PERSISTENCE_ANCHOR)

    # 5. FIRMS confidence + data quality. Better quality lowers the penalty.
    quality_order = {"good": 0.0, "medium": 0.25, "degraded": 0.5, "poor": 0.75, "unknown": 1.0}
    quality_penalty = quality_order.get(data_quality.lower() if isinstance(data_quality, str) else "unknown", 1.0)
    confidence_sub = _normalize(confidence, CONFIDENCE_ANCHOR) * (1.0 - quality_penalty)

    score = (
        W_ANOMALY_SEVERITY * anomaly_severity_score
        + W_DEVIATION * deviation_score
        + W_FRP * frp_intensity_score
        + W_PERSISTENCE * persistence_sub
        + W_CONFIDENCE * confidence_sub
    ) * 100.0

    return {
        "industrial_fire_candidate_score": round(min(score, 100.0), 1),
        "anomaly_severity_score": round(anomaly_severity_score, 4),
        "deviation_score": round(deviation_score, 4),
        "frp_intensity_score": round(frp_intensity_score, 4),
        "persistence_score": round(persistence_sub, 4),
        "confidence_score": round(confidence_sub, 4),
        "component_weights": {
            "anomaly_severity": W_ANOMALY_SEVERITY,
            "deviation": W_DEVIATION,
            "frp": W_FRP,
            "persistence": W_PERSISTENCE,
            "confidence": W_CONFIDENCE,
        },
        "score_label": "industrial_fire_candidate_score",
        "score_meaning": (
            "Deterministic 0-100 candidate RANKING score for analyst review. "
            "NOT a probability, confidence, or accuracy estimate. Higher = "
            "stronger candidate signal for review. A candidate is NOT "
            "automatically an INDUSTRIAL_FIRE."
        ),
    }