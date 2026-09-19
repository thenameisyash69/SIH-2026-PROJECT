"""Tests for the NORMAL_INDUSTRIAL_HEAT ground-truth labeling queue.

Run with:
    cd backend && python -m unittest tests.test_normal_industrial_heat -v
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


class TestNormalIndustrialHeatQueue(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)

    def test_endpoint_is_read_only(self):
        db = SessionLocal()
        before = db.query(Hotspot).count()
        self.client.get("/hotspots/normal-industrial-heat/candidates", params={"limit": 5})
        after = db.query(Hotspot).count()
        db.close()
        self.assertEqual(before, after)

    def test_verified_records_excluded(self):
        db = SessionLocal()
        verified_ids = {v.hotspot_id for v in db.query(Verification).all()}
        r = self.client.get("/hotspots/normal-industrial-heat/candidates", params={"limit": 70})
        returned_ids = {c["id"] for c in r.json()["candidates"]}
        db.close()
        self.assertEqual(verified_ids & returned_ids, set(), "verified records must be excluded")

    def test_only_normal_no_anomaly(self):
        db = SessionLocal()
        r = self.client.get("/hotspots/normal-industrial-heat/candidates", params={"limit": 70})
        for c in r.json()["candidates"]:
            h = db.query(Hotspot).filter(Hotspot.id == c["id"]).one()
            self.assertEqual(h.baseline_status, "NORMAL")
            self.assertFalse(h.is_anomaly)
        db.close()

    def test_no_candidate_beyond_radius(self):
        db = SessionLocal()
        r = self.client.get("/hotspots/normal-industrial-heat/candidates", params={"limit": 70})
        for c in r.json()["candidates"]:
            self.assertIsNotNone(c["facility_distance"])
            self.assertLessEqual(c["facility_distance"], FACILITY_ASSOCIATION_RADIUS_KM)
        db.close()

    def test_deterministic_ordering(self):
        r1 = self.client.get("/hotspots/normal-industrial-heat/candidates", params={"limit": 70})
        r2 = self.client.get("/hotspots/normal-industrial-heat/candidates", params={"limit": 70})
        ids1 = [c["id"] for c in r1.json()["candidates"]]
        ids2 = [c["id"] for c in r2.json()["candidates"]]
        self.assertEqual(ids1, ids2)

    def test_count_does_not_modify_rows(self):
        db = SessionLocal()
        before = db.query(Hotspot).filter(Hotspot.baseline_status == "NORMAL").count()
        self.client.get("/hotspots/normal-industrial-heat/candidates", params={"limit": 70})
        after = db.query(Hotspot).filter(Hotspot.baseline_status == "NORMAL").count()
        db.close()
        self.assertEqual(before, after)

    def test_review_required_always_true(self):
        r = self.client.get("/hotspots/normal-industrial-heat/candidates", params={"limit": 70})
        for c in r.json()["candidates"]:
            self.assertTrue(c["review_required"])

    def test_no_auto_labeling(self):
        db = SessionLocal()
        r = self.client.get("/hotspots/normal-industrial-heat/candidates", params={"limit": 70})
        for c in r.json()["candidates"]:
            h = db.query(Hotspot).filter(Hotspot.id == c["id"]).one()
            self.assertIsNone(h.verification)
        db.close()


if __name__ == "__main__":
    unittest.main()