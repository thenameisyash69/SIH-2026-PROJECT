"""
Combines independent signals into supporting/contradicting evidence,
instead of collapsing everything into one opaque "AI says 93%" number
(spec §15). This is what the Event Investigation view shows.

Facility distance uses the single canonical association radius from
facility_constants (FACILITY_ASSOCIATION_RADIUS_KM). A hotspot within that
radius is facility-associated CONTEXT — never proof of causation — and must
NOT also be flagged FAR_FROM_FACILITY, which would be self-contradictory.
"""

from app.services.facility_constants import FACILITY_ASSOCIATION_RADIUS_KM

AGRI_BURN_MONTHS = {10, 11}


def build_evidence(features: dict, data_quality: str) -> dict:
    supporting = []
    contradicting = []
    codes = []

    dist = features.get("distance_to_facility_km")
    if dist is not None and dist <= FACILITY_ASSOCIATION_RADIUS_KM:
        supporting.append(f"Located {dist} km from a known industrial facility — "
                          f"within the {FACILITY_ASSOCIATION_RADIUS_KM} km association radius "
                          f"(facility-associated context, not proof of causation).")
        codes.append("NEAR_FACILITY")
    elif dist is not None:
        contradicting.append(f"Nearest known facility is {dist} km away — beyond the "
                             f"{FACILITY_ASSOCIATION_RADIUS_KM} km association radius.")
        codes.append("FAR_FROM_FACILITY")

    status = features.get("baseline_status")
    if status == "ABNORMAL":
        supporting.append(f"Thermal reading deviates {features.get('deviation_percentage', 0)}% from this "
                           f"facility's historical baseline (z={features.get('z_score')}).")
        codes.append("HIGH_DEVIATION")
    elif status == "ELEVATED":
        supporting.append(f"Thermal reading is moderately elevated vs. baseline "
                           f"(z={features.get('z_score')}).")
        codes.append("MODERATE_DEVIATION")
    elif status == "INSUFFICIENT_HISTORY":
        contradicting.append("Not enough historical observations yet to establish a reliable baseline.")
        codes.append("INSUFFICIENT_HISTORY")

    if features.get("confidence") is not None and features["confidence"] < 50:
        contradicting.append(f"Source confidence is low ({features['confidence']:.0f}%).")
        codes.append("LOW_SOURCE_CONFIDENCE")
    elif features.get("confidence") is not None and features["confidence"] >= 80:
        supporting.append(f"High-confidence source observation ({features['confidence']:.0f}%).")
        codes.append("HIGH_SOURCE_CONFIDENCE")

    land_cover = features.get("land_cover")
    if land_cover == "industrial":
        supporting.append("Location falls within mapped industrial land-use context.")
        codes.append("INDUSTRIAL_LAND_USE")
    elif land_cover == "forest":
        supporting.append("Location falls within forest land-cover — consistent with wildfire context.")
        codes.append("FOREST_LAND_COVER")
    elif land_cover == "agricultural" and features.get("month") in AGRI_BURN_MONTHS:
        supporting.append("Location is farmland during the known stubble-burning season.")
        codes.append("SEASONAL_AGRI_BURN")

    behavior = features.get("behavior_label")
    if behavior == "PERSISTENT_EXPECTED":
        contradicting.append("This facility's heat signature is persistent and historically stable — "
                              "consistent with routine operation, not an incident.")
        codes.append("PERSISTENT_EXPECTED")
    elif behavior == "PERSISTENT_UNEXPECTED":
        supporting.append("This facility is persistently active but current behavior diverges from its "
                           "own historical pattern.")
        codes.append("PERSISTENT_UNEXPECTED")

    if data_quality == "poor":
        contradicting.append("Overall data quality for this observation is poor — treat assessment with caution.")
        codes.append("POOR_DATA_QUALITY")

    evidence_score = len(supporting) - len(contradicting)

    return {
        "supporting_evidence": supporting,
        "contradicting_evidence": contradicting,
        "reason_codes": codes,
        "evidence_score": evidence_score,
    }
