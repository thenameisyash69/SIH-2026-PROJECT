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
                      ("SUDDEN_THERMAL_SPIKE", "ELEVATED", "NORMAL_RANGE", "INSUFFICIENT_HISTORY"))

    def test_insufficient_history_has_insufficient_level(self):
        # Facility 3 (Vizag Steel Plant) has insufficient NASA FIRMS history.
        r = self.client.get("/facilities/3/thermal-history", params={
            "window_days": 90, "source": "nasa_firms", "detailed": True})
        self.assertEqual(r.status_code, 200)
        j = r.json()
        self.assertTrue(j["insufficient_history"])
        self.assertEqual(j["sudden_rise_level"], "INSUFFICIENT_HISTORY")


if __name__ == "__main__":
    unittest.main()