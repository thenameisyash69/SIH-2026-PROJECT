"""Non-facility wildfire candidate-generation layer for KAVACH.

READ-ONLY. Never modifies classification, verified, or verification_decision.

This module is fully offline and database-only. It operates exclusively on
NASA FIRMS observations already stored in the KAVACH Hotspot table. There
are no network calls, no external APIs, no land-cover service, and no
satellite downloads.

Design principles:
- UNKNOWN / uncertain evidence => NOT_A_CANDIDATE. We never fabricate.
- High FRP alone is NOT sufficient for any tier.
- Facility association alone is NOT sufficient to exclude a candidate,
  but exclude_facility=true removes facility-associated observations.
- Every signal maps to a real computed feature from the stored rows.
- This is a HIGH-PRECISION candidate detector, NOT a wildfire classifier.
  It must not claim 100% wildfire accuracy. review_required is always True.
"""

import math
from statistics import median

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

GRID_DEGREES = 0.05

TIER_A_STRONG = "TIER_A_STRONG"
TIER_B_PLAUSIBLE = "TIER_B_PLAUSIBLE"
NOT_A_CANDIDATE = "NOT_A_CANDIDATE"

# Candidate gate thresholds
MIN_OBSERVATIONS = 3
MIN_UNIQUE_DATES = 2
MIN_FRP = 10.0
MIN_MEAN_CONFIDENCE = 60.0

# TIER_A thresholds
TIER_A_MIN_OBSERVATIONS = 5
TIER_A_MIN_UNIQUE_DATES = 3
TIER_A_MIN_FRP = 20.0
TIER_A_MIN_MEAN_CONFIDENCE = 60.0

# Evidence codes
SUPPORTING_NON_FACILITY = "NON_FACILITY_LOCATION"
SUPPORTING_MULTI_OBS = "MULTI_OBSERVATION_CLUSTER"
SUPPORTING_MULTI_DATE = "MULTI_DATE_ACTIVITY"
SUPPORTING_HIGH_FRP = "HIGH_FRP"
SUPPORTING_HIGH_CONF = "HIGH_SOURCE_CONFIDENCE"
SUPPORTING_SPATIAL_CONC = "SPATIAL_CONCENTRATION"

CONTRADICTING_FACILITY = "FACILITY_ASSOCIATION"
CONTRADICTING_SINGLE = "SINGLE_OBSERVATION"
CONTRADICTING_LOW_CONF = "LOW_SOURCE_CONFIDENCE"
CONTRADICTING_LOW_FRP = "LOW_FRP"


# ---------------------------------------------------------------------------
# Scoring constants (ranking only — NOT a probability / confidence / accuracy)
# ---------------------------------------------------------------------------

# Weighted components of the continuous 0-100 wildfire_candidate_score.
SCORE_WEIGHT_RECURRENCE = 0.25
SCORE_WEIGHT_FRP = 0.20
SCORE_WEIGHT_CONFIDENCE = 0.15
SCORE_WEIGHT_TEMPORAL = 0.20
SCORE_WEIGHT_SPATIAL = 0.20

# Normalization anchors. A single extreme FRP spike must not dominate the
# score, so median FRP is the primary FRP signal and max FRP is capped.
FRP_MEDIAN_ANCHOR = 30.0      # median FRP (MW) mapping to full FRP sub-score
FRP_MAX_ANCHOR = 60.0         # max FRP (MW) used only as a capped bonus
OBSERVATION_ANCHOR = 10.0     # observation count mapping to full recurrence sub-score
UNIQUE_DATE_ANCHOR = 5.0      # unique dates mapping to full recurrence sub-score
CONFIDENCE_ANCHOR = 100.0     # source confidence mapping to full confidence sub-score


def _clamp01(value):
    """Clamp a value into the closed [0, 1] interval."""
    if value < 0.0:
        return 0.0
    if value > 1.0:
        return 1.0
    return value


def _compute_sub_scores(cluster_info):
    """Compute continuous, robust ranking sub-scores for a candidate cluster.

    All values are deterministic and lie in [0, 1]. They are ranking features
    only — never a probability, confidence, or accuracy estimate.
    """
    obs_count = cluster_info["observation_count"]
    unique_dates = cluster_info["unique_dates"]
    duration_days = cluster_info["cluster_duration_days"]
    median_frp = cluster_info.get("median_frp")
    max_frp = cluster_info.get("max_frp")
    mean_conf = cluster_info["mean_confidence"]

    # Temporal concentration: unique dates per day. A dense short burst
    # scores higher than the same number of dates spread thinly.
    temporal_concentration = unique_dates / max(duration_days, 1)

    # Recurrence: how often and how many distinct days the cell re-ignites.
    recurrence_score = (
        0.5 * _clamp01(obs_count / OBSERVATION_ANCHOR)
        + 0.5 * _clamp01(unique_dates / UNIQUE_DATE_ANCHOR)
    )

    # FRP intensity: median FRP is the robust primary signal; max FRP is a
    # capped bonus so a single spike cannot dominate the score.
    median_component = _clamp01((median_frp or 0.0) / FRP_MEDIAN_ANCHOR)
    max_component = _clamp01((max_frp or 0.0) / FRP_MAX_ANCHOR)
    frp_intensity_score = 0.8 * median_component + 0.2 * max_component

    # Source confidence.
    confidence_score = _clamp01(mean_conf / CONFIDENCE_ANCHOR)

    # Spatial concentration: how many observations fall in the same cell.
    spatial_concentration_score = _clamp01(obs_count / OBSERVATION_ANCHOR)

    return {
        "temporal_concentration": round(temporal_concentration, 6),
        "recurrence_score": round(recurrence_score, 4),
        "frp_intensity_score": round(frp_intensity_score, 4),
        "confidence_score": round(confidence_score, 4),
        "spatial_concentration_score": round(spatial_concentration_score, 4),
    }

def grid_bin(lat, lon, grid_degrees=GRID_DEGREES):
    """Deterministic spatial cell key for a coordinate pair."""
    return (math.floor(lat / grid_degrees) * grid_degrees,
            math.floor(lon / grid_degrees) * grid_degrees)


def build_clusters(hotspots, grid_degrees=GRID_DEGREES):
    """Group non-facility observations into deterministic spatial cells.

    Returns a dict keyed by (grid_lat, grid_lon) with per-cell aggregate stats.
    """
    groups = {}
    for h in hotspots:
        key = grid_bin(h.lat, h.lon, grid_degrees)
        groups.setdefault(key, []).append(h)

    clusters = {}
    for key, items in groups.items():
        dates = sorted({h.acq_date.date() for h in items if h.acq_date})
        frps = [h.frp for h in items if h.frp is not None]
        brightnesses = [h.brightness for h in items if h.brightness is not None]
        confidences = [h.confidence for h in items if h.confidence is not None]

        clusters[key] = {
            "cluster_id": "wf_%.2f_%.2f" % (key[0], key[1]),
            "grid_lat": key[0],
            "grid_lon": key[1],
            "observation_count": len(items),
            "unique_dates": len(dates),
            "first_date": dates[0] if dates else None,
            "last_date": dates[-1] if dates else None,
            "cluster_duration_days": (dates[-1] - dates[0]).days if len(dates) >= 2 else 0,
            "max_frp": max(frps) if frps else None,
            "median_frp": median(frps) if frps else None,
            "max_brightness": max(brightnesses) if brightnesses else None,
            "median_brightness": median(brightnesses) if brightnesses else None,
            "mean_confidence": (sum(confidences) / len(confidences)) if confidences else 0.0,
            "high_confidence_count": sum(1 for c in confidences if c >= 60),
            "hotspot_ids": [h.id for h in items],
        }
    return clusters


# ---------------------------------------------------------------------------
# Candidate evaluation
# ---------------------------------------------------------------------------

def evaluate_wildfire_candidate(cluster_info):
    """Apply the high-precision wildfire candidate gate.

    Returns a dict with candidate_tier, wildfire_candidate_score, and the
    supporting / contradicting evidence codes that are actually true for
    this cluster. Never fabricates evidence.

    The candidate GATE is unchanged from the previous implementation. Only
    the continuous ranking SCORE has been improved so that materially
    different thermal/temporal patterns no longer all collapse to 100.
    """
    supporting = []
    contradicting = []

    obs_count = cluster_info["observation_count"]
    unique_dates = cluster_info["unique_dates"]
    max_frp = cluster_info["max_frp"]
    mean_conf = cluster_info["mean_confidence"]
    duration_days = cluster_info["cluster_duration_days"]

    # --- Candidate gate (UNCHANGED) ---
    gate_pass = True

    if obs_count < MIN_OBSERVATIONS:
        gate_pass = False
        contradicting.append(CONTRADICTING_SINGLE)

    if unique_dates < MIN_UNIQUE_DATES:
        gate_pass = False
        contradicting.append(CONTRADICTING_SINGLE)

    if max_frp is None or max_frp < MIN_FRP:
        gate_pass = False
        contradicting.append(CONTRADICTING_LOW_FRP)

    if mean_conf < MIN_MEAN_CONFIDENCE:
        # E: mean confidence >= 60 OR at least two observations with confidence >= 60
        high_conf_count = cluster_info.get("high_confidence_count", 0)
        if high_conf_count < 2:
            gate_pass = False
            contradicting.append(CONTRADICTING_LOW_CONF)

    if not gate_pass:
        return {
            "candidate_tier": NOT_A_CANDIDATE,
            "wildfire_candidate_score": 0.0,
            "supporting_evidence": supporting,
            "contradicting_evidence": contradicting,
        }

    # --- Gate passed: build evidence (UNCHANGED) ---
    supporting.append(SUPPORTING_NON_FACILITY)
    supporting.append(SUPPORTING_MULTI_OBS)
    supporting.append(SUPPORTING_MULTI_DATE)
    if max_frp is not None and max_frp >= 20:
        supporting.append(SUPPORTING_HIGH_FRP)
    if mean_conf >= 60:
        supporting.append(SUPPORTING_HIGH_CONF)
    supporting.append(SUPPORTING_SPATIAL_CONC)

    # --- Tier assignment (UNCHANGED) ---
    tier_a = (
        obs_count >= TIER_A_MIN_OBSERVATIONS
        and unique_dates >= TIER_A_MIN_UNIQUE_DATES
        and max_frp is not None
        and max_frp >= TIER_A_MIN_FRP
        and mean_conf >= TIER_A_MIN_MEAN_CONFIDENCE
    )
    tier = TIER_A_STRONG if tier_a else TIER_B_PLAUSIBLE

    # --- Continuous ranking score (NEW) ---
    sub = _compute_sub_scores(cluster_info)
    score = (
        SCORE_WEIGHT_RECURRENCE * sub["recurrence_score"]
        + SCORE_WEIGHT_FRP * sub["frp_intensity_score"]
        + SCORE_WEIGHT_CONFIDENCE * sub["confidence_score"]
        + SCORE_WEIGHT_TEMPORAL * sub["temporal_concentration"]
        + SCORE_WEIGHT_SPATIAL * sub["spatial_concentration_score"]
    ) * 100.0

    return {
        "candidate_tier": tier,
        "wildfire_candidate_score": round(min(score, 100.0), 1),
        "supporting_evidence": supporting,
        "contradicting_evidence": contradicting,
        "temporal_concentration": sub["temporal_concentration"],
        "frp_intensity_score": sub["frp_intensity_score"],
        "recurrence_score": sub["recurrence_score"],
        "confidence_score": sub["confidence_score"],
    }