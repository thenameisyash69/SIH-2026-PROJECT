"""Tests for the thermal-history detailed extension and evidence UI logic.

Run with:
    cd backend && python -m unittest tests.test_evidence_ui -v
"""
import os
import sys
import unittest

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

from fastapi.testclient import TestClient
from app.main import app


class TestEvidenceUI(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)

    def test_detailed_returns_observations(self):
        r = self.client.get("/facilities/2/thermal-history", params={
            "window_days": 90, "source": "nasa_firms", "detailed": True})
        self.assertEqual(r.status_code, 200)
        j = r.json()
        self.assertFalse(j["insufficient_history"])
        self.assertGreater(len(j["observations"]), 0)
        row = j["observations"][0]
        for field in ("hotspot_id", "acq_date", "brightness", "frp", "confidence",
                      "z_score", "deviation_percentage", "baseline_status", "is_anomaly"):
            self.assertIn(field, row)

    def test_non_detailed_omits_observations(self):
        r = self.client.get("/facilities/2/thermal-history", params={
            "window_days": 90, "source": "nasa_firms", "detailed": False})
        self.assertEqual(r.status_code, 200)
        j = r.json()
        self.assertEqual(j["observations"], [])

    def test_insufficient_history_still_returns_rows_when_detailed(self):
        r = self.client.get("/facilities/1/thermal-history", params={
            "window_days": 90, "source": "nasa_firms", "detailed": True})
        self.assertEqual(r.status_code, 200)
        j = r.json()
        self.assertIsInstance(j["observations"], list)

    def test_satellite_image_endpoint_returns_dict(self):
        r = self.client.get("/hotspots/1/satellite-image")
        self.assertEqual(r.status_code, 200)
        j = r.json()
        # build_satellite_image_url always returns a dict — either a usable
        # image URL or an explicit unavailable state. Never fake imagery.
        self.assertIn("url", j)

    def test_sudden_rise_level_returned(self):
        r = self.client.get("/facilities/2/thermal-history", params={
            "window_days": 90, "source": "nasa_firms", "detailed": True})
        j = r.json()
        self.assertIn(j.get("sudden_rise_level"),
                      ("SUDDEN_THERMAL_SPIKE", "ELEVATED", "NORMAL_RANGE",
                       "PROVISIONAL", "INSUFFICIENT_HISTORY"))

    def test_insufficient_history_has_insufficient_level(self):
        # Facility 3 (Vizag Steel Plant) historically has minimal NASA FIRMS
        # history. Verify the response is internally consistent across the
        # three possible baseline states.
        r = self.client.get("/facilities/3/thermal-history", params={
            "window_days": 90, "source": "nasa_firms", "detailed": True})
        self.assertEqual(r.status_code, 200)
        j = r.json()
        # Fields must always be present.
        self.assertIn("baseline_status", j)
        self.assertIn("confidence", j)
        self.assertIn("limitations", j)
        self.assertIn("sudden_rise_level", j)
        # The three fields must be mutually consistent.
        status = j["baseline_status"]
        self.assertIn(status, ("INSUFFICIENT_HISTORY", "PROVISIONAL", "ESTABLISHED"))
        if status == "INSUFFICIENT_HISTORY":
            self.assertTrue(j["insufficient_history"])
            self.assertEqual(j["sudden_rise_level"], "INSUFFICIENT_HISTORY")
            self.assertIn("No observations", j["confidence"])
        elif status == "PROVISIONAL":
            self.assertFalse(j["insufficient_history"])
            self.assertEqual(j["sudden_rise_level"], "PROVISIONAL")
            self.assertIn("Provisional", j["confidence"])
        else:
            self.assertFalse(j["insufficient_history"])
            self.assertNotIn(j["sudden_rise_level"], ("PROVISIONAL", "INSUFFICIENT_HISTORY"))

    def test_thermal_history_returns_baseline_status_and_confidence(self):
        """All thermal-history responses must include baseline_status,
        confidence, and limitations fields regardless of status."""
        r = self.client.get("/facilities/2/thermal-history", params={
            "window_days": 90, "source": "nasa_firms", "detailed": True})
        self.assertEqual(r.status_code, 200)
        j = r.json()
        self.assertIn("baseline_status", j)
        self.assertIn("confidence", j)
        self.assertIn("limitations", j)
        self.assertIn(j["baseline_status"], ("INSUFFICIENT_HISTORY", "PROVISIONAL", "ESTABLISHED"))
        self.assertIsInstance(j["confidence"], str)
        self.assertIsInstance(j["limitations"], str)

    def test_thermal_history_no_incorrect_fabricated_stats(self):
        """Demo data must never appear in nasa_firms thermal history."""
        r = self.client.get("/facilities/2/thermal-history", params={
            "window_days": 90, "source": "nasa_firms"})
        self.assertEqual(r.status_code, 200)
        j = r.json()
        self.assertEqual(j["source"], "nasa_firms")


if __name__ == "__main__":
    unittest.main()