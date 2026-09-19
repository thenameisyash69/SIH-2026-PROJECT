"""
Canonical facility-association constants for KAVACH.

A single shared radius governs every place where the product reasons about
whether a thermal observation is "facility-associated":

  1. facility matching / association  (facility_matcher.match_facility)
  2. evidence_engine                  (NEAR_FACILITY / FAR_FROM_FACILITY)
  3. analyst candidate filtering      (hotspots.py listing reasons)
  4. API response fields              (distance_to_facility_km is always raw)
  5. UI evidence interpretation

FACILITY_ASSOCIATION_RADIUS_KM is the ONE operational association radius.
It is deliberately NOT a causation threshold: proximity is context, never
proof that a facility caused an event. Wording everywhere stays
"facility-associated context", never "facility caused".

The raw numeric distance in km is always preserved in
`distance_to_facility_km` so the UI can show the exact value regardless of
which side of the radius it falls on.
"""

# The single canonical operational association radius, in kilometres.
# A hotspot with distance_to_facility_km <= this value is facility-associated.
FACILITY_ASSOCIATION_RADIUS_KM = 5.0

# Backwards-compatible alias used by facility_matcher's public default
# argument. New code should import FACILITY_ASSOCIATION_RADIUS_KM directly.
DEFAULT_MAX_MATCH_KM = FACILITY_ASSOCIATION_RADIUS_KM