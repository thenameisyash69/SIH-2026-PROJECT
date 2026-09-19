"""Tests for the canonical facility-association radius.

Run with:
    cd backend && python -m unittest tests.test_facility_distance -v
"""
import os
import sys
import unittest

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

from app.services.facility_constants import FACILITY_ASSOCIATION_RADIUS_KM
from app.services.facility_matcher import DEFAULT_MAX_MATCH_KM
from app.services.evidence_engine import build_evidence
from app.services.classifier import rule_based_classify


class TestCanonicalRadius(unittest.TestCase):
    def test_radius_is_canonical_value(self):
        self.assertEqual(FACILITY_ASSOCIATION_RADIUS_KM, 5.0)

    def test_matcher_default_uses_canonical(self):
        self.assertEqual(DEFAULT_MAX_MATCH_KM, FACILITY_ASSOCIATION_RADIUS_KM)


class TestEvidenceWithinRadius(unittest.TestCase):
    def test_within_radius_is_associated_no_far_code(self):
        result = build_evidence({"distance_to_facility_km": 4.96}, "good")
        self.assertIn("NEAR_FACILITY", result["reason_codes"])
        self.assertNotIn("FAR_FROM_FACILITY", result["reason_codes"])

    def test_exact_boundary_is_associated(self):
        result = build_evidence({"distance_to_facility_km": 5.0}, "good")
        self.assertIn("NEAR_FACILITY", result["reason_codes"])
        self.assertNotIn("FAR_FROM_FACILITY", result["reason_codes"])

    def test_just_beyond_radius_is_far(self):
        result = build_evidence({"distance_to_facility_km": 5.01}, "good")
        self.assertNotIn("NEAR_FACILITY", result["reason_codes"])
        self.assertIn("FAR_FROM_FACILITY", result["reason_codes"])

    def test_far_distance_is_far(self):
        result = build_evidence({"distance_to_facility_km": 12.3}, "good")
        self.assertIn("FAR_FROM_FACILITY", result["reason_codes"])
        self.assertNotIn("NEAR_FACILITY", result["reason_codes"])

    def test_no_distance_is_silent(self):
        result = build_evidence({"distance_to_facility_km": None}, "good")
        self.assertNotIn("NEAR_FACILITY", result["reason_codes"])
        self.assertNotIn("FAR_FROM_FACILITY", result["reason_codes"])


class TestClassifierConsistency(unittest.TestCase):
    def test_within_radius_is_near(self):
        self.assertTrue(rule_based_classify(
            {"distance_to_facility_km": 4.96, "behavior_label": "PERSISTENT_EXPECTED",
             "baseline_status": "NORMAL"})["category"] in ("industrial_normal", "industrial_alert"))

    def test_beyond_radius_is_not_near(self):
        cat = rule_based_classify(
            {"distance_to_facility_km": 6.0, "behavior_label": "PERSISTENT_EXPECTED",
             "baseline_status": "NORMAL", "land_cover": "unknown"})
        self.assertNotIn("industrial", cat["category"])


if __name__ == "__main__":
    unittest.main()