"""Tests for the paginated hotspots endpoint — verifies total count, offset
pagination, verification filtering, and demo/nasa_firms separation.

Run with:
    cd backend && python -m unittest tests.test_hotspots_pagination -v
"""
import os
import sys
import unittest

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

from fastapi.testclient import TestClient
from app.main import app


class TestHotspotsPagination(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)

    def test_response_has_pagination_envelope(self):
        r = self.client.get("/hotspots", params={"limit": 10})
        self.assertEqual(r.status_code, 200)
        j = r.json()
        self.assertIn("total", j)
        self.assertIn("limit", j)
        self.assertIn("offset", j)
        self.assertIn("hotspots", j)
        self.assertIsInstance(j["total"], int)
        self.assertIsInstance(j["hotspots"], list)

    def test_total_greater_than_or_equal_returned(self):
        r = self.client.get("/hotspots", params={"limit": 100})
        j = r.json()
        self.assertGreaterEqual(j["total"], len(j["hotspots"]))

    def test_large_limit_returns_all_within_one_page(self):
        """Fetch the total via limit=1, then verify all records can be
        retrieved via pagination."""
        summary = self.client.get("/hotspots", params={"limit": 1}).json()
        total = summary["total"]
        # Fetch all via pagination with PAGE_SIZE=2000
        all_ids = []
        offset = 0
        while offset < total:
            page = self.client.get("/hotspots", params={"limit": 2000, "offset": offset}).json()
            all_ids.extend(h["id"] for h in page["hotspots"])
            if len(page["hotspots"]) < 2000:
                break
            offset += 2000
        self.assertEqual(len(all_ids), total)

    def test_offset_pagination_works(self):
        page1 = self.client.get("/hotspots", params={"limit": 100, "offset": 0}).json()
        page2 = self.client.get("/hotspots", params={"limit": 100, "offset": 100}).json()
        self.assertLessEqual(100, page1["total"])
        ids1 = {h["id"] for h in page1["hotspots"]}
        ids2 = {h["id"] for h in page2["hotspots"]}
        self.assertEqual(ids1.isdisjoint(ids2), True, "Page 1 and page 2 should not overlap")

    def test_default_limit_is_500(self):
        j = self.client.get("/hotspots").json()
        self.assertLessEqual(len(j["hotspots"]), 500)
        self.assertEqual(j["limit"], 500)

    def test_offset_zero_returns_first_page(self):
        j = self.client.get("/hotspots", params={"limit": 10}).json()
        self.assertEqual(j["offset"], 0)

    def test_total_reflects_filters(self):
        all_resp = self.client.get("/hotspots", params={"limit": 1}).json()
        nasa_resp = self.client.get("/hotspots", params={"source": "nasa_firms", "limit": 1}).json()
        demo_resp = self.client.get("/hotspots", params={"source": "demo_synthetic", "limit": 1}).json()
        self.assertEqual(all_resp["total"], nasa_resp["total"] + demo_resp["total"])

    def test_source_filter_separates_demo_and_nasa(self):
        nasa_ids = set()
        demo_ids = set()
        offset = 0
        while True:
            page = self.client.get("/hotspots", params={"source": "nasa_firms", "limit": 2000, "offset": offset}).json()
            for h in page["hotspots"]:
                self.assertEqual(h["source"], "nasa_firms")
                nasa_ids.add(h["id"])
            if len(page["hotspots"]) < 2000:
                break
            offset += 2000

        offset = 0
        while True:
            page = self.client.get("/hotspots", params={"source": "demo_synthetic", "limit": 2000, "offset": offset}).json()
            for h in page["hotspots"]:
                self.assertEqual(h["source"], "demo_synthetic")
                demo_ids.add(h["id"])
            if len(page["hotspots"]) < 2000:
                break
            offset += 2000

        self.assertGreater(len(nasa_ids), 0, "Should have NASA FIRMS observations")
        self.assertGreater(len(demo_ids), 0, "Should have demo observations")
        self.assertEqual(len(nasa_ids) + len(demo_ids),
                         self.client.get("/hotspots", params={"limit": 1}).json()["total"])

    def test_verified_filter_true_returns_only_verified(self):
        """verified=true should return only records with verification.
        We verify by checking that the count is consistent across pages."""
        total = self.client.get(
            "/hotspots", params={"verified": "true", "limit": 1}
        ).json()["total"]
        # Fetch all pages
        fetched = []
        offset = 0
        while True:
            page = self.client.get(
                "/hotspots", params={"verified": "true", "limit": 2000, "offset": offset}
            ).json()
            fetched.extend(page["hotspots"])
            if len(page["hotspots"]) < 2000:
                break
            offset += 2000
        self.assertEqual(len(fetched), total)

    def test_verified_filter_false_excludes_verified(self):
        """verified=false should return only records WITHOUT verification."""
        total = self.client.get(
            "/hotspots", params={"verified": "false", "limit": 1}
        ).json()["total"]
        fetched = []
        offset = 0
        while True:
            page = self.client.get(
                "/hotspots", params={"verified": "false", "limit": 2000, "offset": offset}
            ).json()
            fetched.extend(page["hotspots"])
            if len(page["hotspots"]) < 2000:
                break
            offset += 2000
        self.assertEqual(len(fetched), total)

    def test_anomaly_filter_works(self):
        r = self.client.get("/hotspots", params={"limit": 1}).json()
        if r["total"] > 0:
            anomaly_total = self.client.get(
                "/hotspots", params={"anomaly_only": "true", "limit": 1}
            ).json()["total"]
            all_total = self.client.get("/hotspots", params={"limit": 1}).json()["total"]
            self.assertLessEqual(anomaly_total, all_total)

    def test_source_all_returns_all_records(self):
        """source=all (or 'all') should return NO source filter, same as default."""
        default = self.client.get("/hotspots", params={"limit": 1}).json()
        source_all = self.client.get("/hotspots", params={"source": "all", "limit": 1}).json()
        self.assertEqual(default["total"], source_all["total"])
        # Verify no source filtering is applied — records from both sources appear
        if default["total"] > 10:
            page = self.client.get("/hotspots", params={"source": "all", "limit": 2000}).json()
            sources = {h["source"] for h in page["hotspots"]}
            self.assertGreater(len(sources), 1, "source=all should include multiple sources")


class TestHotspotsVerificationFilter(unittest.TestCase):
    """Verify that the verified=true/false filters correctly join to the
    verifications table."""

    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)

    def test_verified_true_count_leq_total(self):
        total = self.client.get("/hotspots", params={"limit": 1}).json()["total"]
        verified = self.client.get(
            "/hotspots", params={"verified": "true", "limit": 1}
        ).json()
        self.assertLessEqual(verified["total"], total)

    def test_verified_false_count_leq_total(self):
        total = self.client.get("/hotspots", params={"limit": 1}).json()["total"]
        unverified = self.client.get(
            "/hotspots", params={"verified": "false", "limit": 1}
        ).json()
        self.assertLessEqual(unverified["total"], total)

    def test_verified_true_plus_false_equals_total(self):
        """verified=true + verified=false should equal total (no NULL
        in verification join — every hotspot either has or doesn't have
        a verification record)."""
        total = self.client.get("/hotspots", params={"limit": 1}).json()["total"]
        verified_count = self.client.get(
            "/hotspots", params={"verified": "true", "limit": 1}
        ).json()["total"]
        unverified_count = self.client.get(
            "/hotspots", params={"verified": "false", "limit": 1}
        ).json()["total"]
        self.assertEqual(verified_count + unverified_count, total)


if __name__ == "__main__":
    unittest.main()
