"""Offline, database-only wildfire candidate detector tests.

Run with:
    cd backend && python -m unittest tests.test_wildfire_candidates -v
"""
import os
import sys
import unittest
from datetime import datetime, timedelta
from types import SimpleNamespace

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

from app.services.wildfire_engine import (
    build_clusters,
    evaluate_wildfire_candidate,
    grid_bin,
    NOT_A_CANDIDATE,
    TIER_A_STRONG,
    TIER_B_PLAUSIBLE,
)


def _hs(hid, lat, lon, frp, confidence, acq_date, brightness=320.0):
    return SimpleNamespace(
        id=hid,
        lat=lat,
        lon=lon,
        brightness=brightness,
        confidence=confidence,
        frp=frp,
        acq_date=acq_date,
        facility_id=None,
    )


class TestGridBin(unittest.TestCase):
    def test_deterministic(self):
        lat, lon = grid_bin(8.72, 77.63)
        self.assertAlmostEqual(lat, 8.70, places=2)
        self.assertAlmostEqual(lon, 77.60, places=2)

    def test_negative_coords(self):
        lat, lon = grid_bin(-1.23, -4.56)
        self.assertAlmostEqual(lat, -1.25, places=2)
        self.assertAlmostEqual(lon, -4.60, places=2)


class TestCandidateGate(unittest.TestCase):
    def test_single_high_frp_observation_is_not_candidate(self):
        cluster = {
            "cluster_id": "wf_1",
            "observation_count": 1,
            "unique_dates": 1,
            "cluster_duration_days": 0,
            "max_frp": 50.0,
            "median_frp": 50.0,
            "mean_confidence": 90.0,
            "high_confidence_count": 1,
        }
        result = evaluate_wildfire_candidate(cluster)
        self.assertEqual(result["candidate_tier"], NOT_A_CANDIDATE)
        self.assertEqual(result["wildfire_candidate_score"], 0.0)

    def test_repeated_single_date_only_is_not_candidate(self):
        cluster = {
            "cluster_id": "wf_2",
            "observation_count": 4,
            "unique_dates": 1,
            "cluster_duration_days": 0,
            "max_frp": 15.0,
            "median_frp": 15.0,
            "mean_confidence": 80.0,
            "high_confidence_count": 4,
        }
        result = evaluate_wildfire_candidate(cluster)
        self.assertEqual(result["candidate_tier"], NOT_A_CANDIDATE)

    def test_three_observations_two_dates_frp10_conf60_is_candidate(self):
        cluster = {
            "cluster_id": "wf_3",
            "observation_count": 3,
            "unique_dates": 2,
            "cluster_duration_days": 2,
            "max_frp": 12.0,
            "median_frp": 12.0,
            "mean_confidence": 65.0,
            "high_confidence_count": 2,
        }
        result = evaluate_wildfire_candidate(cluster)
        self.assertIn(result["candidate_tier"], (TIER_A_STRONG, TIER_B_PLAUSIBLE))
        self.assertGreater(result["wildfire_candidate_score"], 0.0)
        self.assertIn("NON_FACILITY_LOCATION", result["supporting_evidence"])

    def test_five_observations_three_dates_frp20_is_tier_a(self):
        cluster = {
            "cluster_id": "wf_4",
            "observation_count": 5,
            "unique_dates": 3,
            "cluster_duration_days": 4,
            "max_frp": 25.0,
            "median_frp": 22.0,
            "mean_confidence": 70.0,
            "high_confidence_count": 5,
        }
        result = evaluate_wildfire_candidate(cluster)
        self.assertEqual(result["candidate_tier"], TIER_A_STRONG)
        self.assertIn("HIGH_FRP", result["supporting_evidence"])

    def test_low_frp_blocks_candidate(self):
        cluster = {
            "cluster_id": "wf_5",
            "observation_count": 3,
            "unique_dates": 2,
            "cluster_duration_days": 2,
            "max_frp": 5.0,
            "median_frp": 5.0,
            "mean_confidence": 80.0,
            "high_confidence_count": 3,
        }
        result = evaluate_wildfire_candidate(cluster)
        self.assertEqual(result["candidate_tier"], NOT_A_CANDIDATE)
        self.assertIn("LOW_FRP", result["contradicting_evidence"])

    def test_low_confidence_blocks_candidate(self):
        cluster = {
            "cluster_id": "wf_6",
            "observation_count": 3,
            "unique_dates": 2,
            "cluster_duration_days": 2,
            "max_frp": 15.0,
            "median_frp": 15.0,
            "mean_confidence": 40.0,
            "high_confidence_count": 0,
        }
        result = evaluate_wildfire_candidate(cluster)
        self.assertEqual(result["candidate_tier"], NOT_A_CANDIDATE)
        self.assertIn("LOW_SOURCE_CONFIDENCE", result["contradicting_evidence"])

    def test_two_tier_a_candidates_with_different_temporal_concentration_differ(self):
        # Short, dense burst vs long, sparse spread — same obs/dates counts.
        dense = {
            "cluster_id": "wf_a",
            "observation_count": 6,
            "unique_dates": 4,
            "cluster_duration_days": 4,
            "max_frp": 25.0,
            "median_frp": 20.0,
            "mean_confidence": 70.0,
            "high_confidence_count": 6,
        }
        sparse = {
            "cluster_id": "wf_b",
            "observation_count": 6,
            "unique_dates": 4,
            "cluster_duration_days": 40,
            "max_frp": 25.0,
            "median_frp": 20.0,
            "mean_confidence": 70.0,
            "high_confidence_count": 6,
        }
        r_dense = evaluate_wildfire_candidate(dense)
        r_sparse = evaluate_wildfire_candidate(sparse)
        self.assertEqual(r_dense["candidate_tier"], TIER_A_STRONG)
        self.assertEqual(r_sparse["candidate_tier"], TIER_A_STRONG)
        self.assertGreater(r_dense["wildfire_candidate_score"], r_sparse["wildfire_candidate_score"])
        self.assertGreater(r_dense["temporal_concentration"], r_sparse["temporal_concentration"])

    def test_short_burst_ranks_higher_than_spread(self):
        # Same obs/dates/FRP/confidence, only duration differs.
        short = {
            "cluster_id": "wf_s",
            "observation_count": 8,
            "unique_dates": 5,
            "cluster_duration_days": 5,
            "max_frp": 22.0,
            "median_frp": 18.0,
            "mean_confidence": 75.0,
            "high_confidence_count": 8,
        }
        long = {
            "cluster_id": "wf_l",
            "observation_count": 8,
            "unique_dates": 5,
            "cluster_duration_days": 50,
            "max_frp": 22.0,
            "median_frp": 18.0,
            "mean_confidence": 75.0,
            "high_confidence_count": 8,
        }
        r_short = evaluate_wildfire_candidate(short)
        r_long = evaluate_wildfire_candidate(long)
        self.assertGreater(r_short["wildfire_candidate_score"], r_long["wildfire_candidate_score"])

    def test_single_extreme_frp_spike_does_not_max_the_score(self):
        # One extreme spike with a low median should NOT reach 100.
        cluster = {
            "cluster_id": "wf_spike",
            "observation_count": 5,
            "unique_dates": 3,
            "cluster_duration_days": 3,
            "max_frp": 200.0,
            "median_frp": 5.0,
            "mean_confidence": 65.0,
            "high_confidence_count": 4,
        }
        result = evaluate_wildfire_candidate(cluster)
        self.assertEqual(result["candidate_tier"], TIER_A_STRONG)
        self.assertLess(result["wildfire_candidate_score"], 100.0)
        # FRP sub-score must be dominated by the low median, not the spike.
        self.assertLess(result["frp_intensity_score"], 0.5)

    def test_score_is_continuous_not_collapsed(self):
        # Several valid TIER_A clusters with materially different signals
        # must not all collapse to the same score.
        clusters = [
            {"cluster_id": "c1", "observation_count": 12, "unique_dates": 4,
             "cluster_duration_days": 69, "max_frp": 21.87, "median_frp": 2.31,
             "mean_confidence": 60.0, "high_confidence_count": 12},
            {"cluster_id": "c2", "observation_count": 5, "unique_dates": 3,
             "cluster_duration_days": 40, "max_frp": 21.3, "median_frp": 16.1,
             "mean_confidence": 60.0, "high_confidence_count": 5},
            {"cluster_id": "c3", "observation_count": 7, "unique_dates": 4,
             "cluster_duration_days": 4, "max_frp": 28.19, "median_frp": 4.13,
             "mean_confidence": 64.3, "high_confidence_count": 7},
        ]
        scores = [evaluate_wildfire_candidate(c)["wildfire_candidate_score"] for c in clusters]
        self.assertEqual(len(set(scores)), len(scores), "scores must be distinct")
        for s in scores:
            self.assertGreaterEqual(s, 0.0)
            self.assertLessEqual(s, 100.0)

    def test_not_candidate_score_is_zero(self):
        cluster = {
            "cluster_id": "wf_nc",
            "observation_count": 2,
            "unique_dates": 1,
            "cluster_duration_days": 0,
            "max_frp": 100.0,
            "median_frp": 100.0,
            "mean_confidence": 99.0,
            "high_confidence_count": 2,
        }
        result = evaluate_wildfire_candidate(cluster)
        self.assertEqual(result["candidate_tier"], NOT_A_CANDIDATE)
        self.assertEqual(result["wildfire_candidate_score"], 0.0)


class TestBuildClusters(unittest.TestCase):
    def test_groups_by_grid_cell(self):
        base = datetime(2026, 1, 1)
        hotspots = [
            _hs(1, 8.72, 77.63, 10, 70, base),
            _hs(2, 8.73, 77.64, 12, 75, base + timedelta(days=1)),
            _hs(3, 8.74, 77.62, 14, 80, base + timedelta(days=2)),
        ]
        clusters = build_clusters(hotspots)
        self.assertEqual(len(clusters), 1)
        info = list(clusters.values())[0]
        self.assertEqual(info["observation_count"], 3)
        self.assertEqual(info["unique_dates"], 3)
        self.assertEqual(info["max_frp"], 14.0)

    def test_separate_cells(self):
        base = datetime(2026, 1, 1)
        hotspots = [
            _hs(1, 8.72, 77.63, 10, 70, base),
            _hs(2, 9.50, 78.50, 12, 75, base),
        ]
        clusters = build_clusters(hotspots)
        self.assertEqual(len(clusters), 2)


class TestEndpoint(unittest.TestCase):
    """Database-backed endpoint tests via TestClient."""

    @classmethod
    def setUpClass(cls):
        from fastapi.testclient import TestClient
        from app.main import app
        cls.client = TestClient(app)

    def test_endpoint_is_offline_and_fast(self):
        import time
        t0 = time.time()
        r = self.client.get("/hotspots/wildfire/candidates", params={"limit": 5})
        elapsed = time.time() - t0
        self.assertEqual(r.status_code, 200)
        self.assertLess(elapsed, 10.0, "endpoint must not hang on network calls")
        j = r.json()
        self.assertGreaterEqual(j["total_examined"], 0)
        for cand in j["candidates"]:
            self.assertTrue(cand["review_required"])
            self.assertNotIn("probability", str(cand).lower())

    def test_classification_unchanged(self):
        from app.database import SessionLocal
        from app.models import Hotspot
        db = SessionLocal()
        before = db.query(Hotspot).filter(Hotspot.source == "nasa_firms").count()
        self.client.get("/hotspots/wildfire/candidates", params={"limit": 5})
        after = db.query(Hotspot).filter(Hotspot.source == "nasa_firms").count()
        db.close()
        self.assertEqual(before, after)


if __name__ == "__main__":
    unittest.main()