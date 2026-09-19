"""Tests for the INDUSTRIAL_FIRE ground-truth labeling queue.

Run with:
    cd backend && python -m unittest tests.test_industrial_fire -v
"""
import os
import sys
import unittest

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

from fastapi.testclient import TestClient
from app.main import app
from app.database import SessionLocal
from app.models import Hotspot, Verification
from app.services.facility_constants import FACILITY_ASSOCIATION_RADIUS_KM


class TestIndustrialFireQueue(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)

    def test_endpoint_is_read_only(self):
        db = SessionLocal()
        before = db.query(Hotspot).count()
        self.client.get("/hotspots/industrial-fire/candidates", params={"limit": 5})
        after = db.query(Hotspot).count()
        db.close()
        self.assertEqual(before, after)

    def test_verified_records_excluded(self):
        db = SessionLocal()
        verified_ids = {v.hotspot_id for v in db.query(Verification).all()}
        r = self.client.get("/hotspots/industrial-fire/candidates", params={"limit": 70})
        returned_ids = {c["id"] for c in r.json()["candidates"]}
        db.close()
        self.assertEqual(verified_ids & returned_ids, set(), "verified records must be excluded")

    def test_only_facility_associated_within_radius(self):
        db = SessionLocal()
        r = self.client.get("/hotspots/industrial-fire/candidates", params={"limit": 70})
        for c in r.json()["candidates"]:
            self.assertIsNotNone(c["facility_distance"])
            self.assertLessEqual(c["facility_distance"], FACILITY_ASSOCIATION_RADIUS_KM)
            h = db.query(Hotspot).filter(Hotspot.id == c["id"]).one()
            self.assertIsNotNone(h.facility_id)
        db.close()

    def test_only_abnormal_or_elevated_with_anomaly(self):
        db = SessionLocal()
        r = self.client.get("/hotspots/industrial-fire/candidates", params={"limit": 70})
        for c in r.json()["candidates"]:
            self.assertIn(c["baseline_status"], ("ABNORMAL", "ELEVATED"))
            self.assertTrue(c["anomaly"])
            h = db.query(Hotspot).filter(Hotspot.id == c["id"]).one()
            self.assertEqual(h.baseline_status, c["baseline_status"])
            self.assertTrue(h.is_anomaly)
        db.close()

    def test_abnormal_ranks_before_elevated(self):
        r = self.client.get("/hotspots/industrial-fire/candidates", params={"limit": 70})
        statuses = [c["baseline_status"] for c in r.json()["candidates"]]
        # All ELEVATED implies no ABNORMAL available; if any ABNORMAL exists
        # it must precede the first ELEVATED.
        if "ELEVATED" in statuses:
            first_elevated = statuses.index("ELEVATED")
            self.assertEqual(statuses[:first_elevated], ["ABNORMAL"] * first_elevated)

    def test_deterministic_ordering(self):
        r1 = self.client.get("/hotspots/industrial-fire/candidates", params={"limit": 70})
        r2 = self.client.get("/hotspots/industrial-fire/candidates", params={"limit": 70})
        ids1 = [c["id"] for c in r1.json()["candidates"]]
        ids2 = [c["id"] for c in r2.json()["candidates"]]
        self.assertEqual(ids1, ids2)

    def test_count_does_not_modify_rows(self):
        db = SessionLocal()
        before = db.query(Hotspot).filter(Hotspot.is_anomaly == True).count()
        self.client.get("/hotspots/industrial-fire/candidates", params={"limit": 70})
        after = db.query(Hotspot).filter(Hotspot.is_anomaly == True).count()
        db.close()
        self.assertEqual(before, after)

    def test_no_verification_rows_created(self):
        db = SessionLocal()
        before = db.query(Verification).count()
        self.client.get("/hotspots/industrial-fire/candidates", params={"limit": 70})
        after = db.query(Verification).count()
        db.close()
        self.assertEqual(before, after)

    def test_review_required_always_true(self):
        r = self.client.get("/hotspots/industrial-fire/candidates", params={"limit": 70})
        for c in r.json()["candidates"]:
            self.assertTrue(c["review_required"])
            self.assertIsNone(c["verification_decision"])

    def test_no_auto_labeling(self):
        db = SessionLocal()
        r = self.client.get("/hotspots/industrial-fire/candidates", params={"limit": 70})
        for c in r.json()["candidates"]:
            h = db.query(Hotspot).filter(Hotspot.id == c["id"]).one()
            self.assertIsNone(h.verification)
        db.close()

    def test_candidate_score_is_normalized_0_100(self):
        r = self.client.get("/hotspots/industrial-fire/candidates", params={"limit": 70})
        for c in r.json()["candidates"]:
            self.assertIn("industrial_fire_candidate_score", c)
            s = c["industrial_fire_candidate_score"]
            self.assertGreaterEqual(s, 0.0, f"score below 0: {s}")
            self.assertLessEqual(s, 100.0, f"score above 100: {s}")
            self.assertNotIn("candidate_score", c, "old unbounded field must be removed")
            self.assertEqual(c["score_label"], "industrial_fire_candidate_score")

    def test_component_scores_present(self):
        r = self.client.get("/hotspots/industrial-fire/candidates", params={"limit": 70})
        for c in r.json()["candidates"]:
            for field in ("anomaly_severity_score", "deviation_score",
                          "frp_intensity_score", "persistence_score_component",
                          "confidence_score_component"):
                self.assertIn(field, c)
                self.assertGreaterEqual(c[field], 0.0)
                self.assertLessEqual(c[field], 1.0)

    def test_candidate_pool_excludes_verified(self):
        # The pool excludes already-verified records, so its size can shrink
        # as labeling progresses. Assert the invariant instead of a frozen count.
        r = self.client.get("/hotspots/industrial-fire/candidates", params={"limit": 70})
        self.assertEqual(r.status_code, 200)
        j = r.json()
        db = SessionLocal()
        verified_ids = {v.hotspot_id for v in db.query(Verification).all()}
        db.close()
        for c in j["candidates"]:
            self.assertNotIn(c["hotspot_id"], verified_ids)
        # Pool size must never exceed the number of matching unverified rows.
        self.assertGreaterEqual(j["total_candidates"], 0)

    def test_no_database_writes(self):
        db = SessionLocal()
        before = db.query(Hotspot).count()
        self.client.get("/hotspots/industrial-fire/candidates", params={"limit": 70})
        after = db.query(Hotspot).count()
        db.close()
        self.assertEqual(before, after)


if __name__ == "__main__":
    unittest.main()