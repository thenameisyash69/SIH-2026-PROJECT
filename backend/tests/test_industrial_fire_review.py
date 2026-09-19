"""Tests for the INDUSTRIAL_FIRE batch-review workflow.

Run with:
    cd backend && python -m unittest tests.test_industrial_fire_review -v
"""
import os
import sys
import unittest

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

from fastapi.testclient import TestClient
from app.main import app
from app.database import SessionLocal
from app.models import Verification


class TestIndustrialFireReview(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)

    def test_candidates_sorted_descending(self):
        r = self.client.get("/hotspots/industrial-fire/candidates", params={"limit": 37})
        self.assertEqual(r.status_code, 200)
        j = r.json()
        scores = [c["industrial_fire_candidate_score"] for c in j["candidates"]]
        self.assertTrue(all(scores[i] >= scores[i + 1] for i in range(len(scores) - 1)))

    def test_candidates_have_required_fields(self):
        r = self.client.get("/hotspots/industrial-fire/candidates", params={"limit": 37})
        required = {
            "hotspot_id", "facility_name", "facility_distance", "brightness", "frp",
            "source_confidence", "baseline_status", "z_score", "deviation_percentage",
            "persistence_score", "anomaly", "risk_level", "industrial_fire_candidate_score",
            "acq_date", "reason_codes", "review_required",
        }
        for c in r.json()["candidates"]:
            self.assertTrue(required.issubset(c.keys()), f"missing {required - c.keys()}")

    def test_progress_endpoint(self):
        r = self.client.get("/hotspots/industrial-fire/review/progress")
        self.assertEqual(r.status_code, 200)
        p = r.json()
        for key in ("confirmed_industrial_fire", "confirmed_normal_industrial_heat",
                    "wildfire", "agricultural", "false_positive", "unknown"):
            self.assertIn(key, p["verified"])
        self.assertIn("remaining_candidates", p)

    def test_note_required_for_confirmed_industrial_fire(self):
        db = SessionLocal()
        hid = db.query(Verification).first()
        db.close()
        target = hid.hotspot_id if hid else 11477
        r = self.client.post(f"/hotspots/{target}/verify", json={
            "decision": "confirmed_industrial_fire", "note": "", "analyst_name": "t",
        })
        self.assertEqual(r.status_code, 400)
        self.assertIn("note", r.json()["detail"].lower())

    def test_verify_then_reverify_does_not_duplicate(self):
        db = SessionLocal()
        target = 11477
        before = db.query(Verification).filter(Verification.hotspot_id == target).count()
        db.close()
        self.client.post(f"/hotspots/{target}/verify", json={
            "decision": "confirmed_industrial_fire",
            "note": "batch review test",
            "analyst_name": "t",
        })
        self.client.post(f"/hotspots/{target}/verify", json={
            "decision": "unknown",
            "note": "re-reviewed",
            "analyst_name": "t",
        })
        db = SessionLocal()
        rows = db.query(Verification).filter(Verification.hotspot_id == target).all()
        db.close()
        self.assertEqual(len(rows), max(before, 1))
        self.assertEqual(rows[0].decision, "unknown")
        # Clean up the test artifact.
        db = SessionLocal()
        for row in db.query(Verification).filter(Verification.hotspot_id == target).all():
            db.delete(row)
        db.commit()
        db.close()

    def test_read_only_no_auto_labeling(self):
        db = SessionLocal()
        before = db.query(Verification).count()
        self.client.get("/hotspots/industrial-fire/candidates", params={"limit": 37})
        after = db.query(Verification).count()
        db.close()
        self.assertEqual(before, after)


if __name__ == "__main__":
    unittest.main()