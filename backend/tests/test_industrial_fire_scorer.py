"""Tests for the INDUSTRIAL_FIRE analyst ranking score.

Run with:
    cd backend && python -m unittest tests.test_industrial_fire_scorer -v
"""
import os
import sys
import unittest
from types import SimpleNamespace

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

from app.services.industrial_fire_scorer import compute_industrial_fire_candidate_score


def _hs(z_score=0.0, deviation_percentage=0.0, frp=0.0, persistence_score=0.0,
        confidence=0.0, data_quality="good"):
    return SimpleNamespace(
        z_score=z_score,
        deviation_percentage=deviation_percentage,
        frp=frp,
        persistence_score=persistence_score,
        confidence=confidence,
        data_quality=data_quality,
    )


class TestScoreRange(unittest.TestCase):
    def test_zero_signal_scores_zero(self):
        result = compute_industrial_fire_candidate_score(_hs())
        self.assertEqual(result["industrial_fire_candidate_score"], 0.0)

    def test_score_within_0_100(self):
        for z in (0.0, 1.0, 2.5, 5.0, 10.0):
            for frp in (0.0, 10.0, 30.0, 60.0, 200.0):
                for conf in (0.0, 50.0, 80.0, 100.0):
                    s = compute_industrial_fire_candidate_score(
                        _hs(z_score=z, frp=frp, confidence=conf))["industrial_fire_candidate_score"]
                    self.assertGreaterEqual(s, 0.0, f"score below 0: {s}")
                    self.assertLessEqual(s, 100.0, f"score above 100: {s}")

    def test_extreme_inputs_capped_at_100(self):
        result = compute_industrial_fire_candidate_score(
            _hs(z_score=999.0, deviation_percentage=9999.0, frp=99999.0,
                 persistence_score=99.0, confidence=999.0, data_quality="good"))
        self.assertLessEqual(result["industrial_fire_candidate_score"], 100.0)


class TestDeterministic(unittest.TestCase):
    def test_same_inputs_same_score(self):
        a = compute_industrial_fire_candidate_score(_hs(z_score=2.0, frp=10.0, confidence=70.0))
        b = compute_industrial_fire_candidate_score(_hs(z_score=2.0, frp=10.0, confidence=70.0))
        self.assertEqual(a["industrial_fire_candidate_score"], b["industrial_fire_candidate_score"])

    def test_component_scores_deterministic(self):
        r = compute_industrial_fire_candidate_score(_hs(z_score=2.0, frp=10.0, confidence=70.0))
        self.assertEqual(r["anomaly_severity_score"], round(2.0 / 3.0, 4))
        self.assertEqual(r["frp_intensity_score"], round(10.0 / 60.0, 4))


class TestExtremeFrp(unittest.TestCase):
    def test_extreme_frp_does_not_max_the_score(self):
        # Same everything except FRP: one extreme spike vs a weak observation.
        spike = compute_industrial_fire_candidate_score(
            _hs(z_score=1.0, deviation_percentage=5.0, frp=500.0,
                 persistence_score=0.3, confidence=70.0, data_quality="good"))
        weak = compute_industrial_fire_candidate_score(
            _hs(z_score=1.0, deviation_percentage=5.0, frp=5.0,
                 persistence_score=0.3, confidence=70.0, data_quality="good"))
        # FRP is capped at 60, so the spike caps at 1.0 and the weak at 5/60.
        self.assertEqual(spike["frp_intensity_score"], 1.0)
        self.assertAlmostEqual(weak["frp_intensity_score"], 5.0 / 60.0, places=4)
        # The FRP weight is 0.20, so the spike can add at most 20 points
        # above the weak observation — a single extreme FRP cannot dominate.
        gap = spike["industrial_fire_candidate_score"] - weak["industrial_fire_candidate_score"]
        self.assertLessEqual(gap, 20.0 + 1e-6)
        # And the final score must not hit the ceiling from FRP alone.
        self.assertLess(spike["industrial_fire_candidate_score"], 100.0)

    def test_frp_capped_component(self):
        r = compute_industrial_fire_candidate_score(_hs(frp=99999.0))
        self.assertEqual(r["frp_intensity_score"], 1.0)
        # FRP weight is 0.20, so even maxed FRP cannot push the score to 100.
        self.assertLess(r["industrial_fire_candidate_score"], 20.01)


class TestAnomalyRanking(unittest.TestCase):
    def test_stronger_anomaly_ranks_higher(self):
        strong = compute_industrial_fire_candidate_score(
            _hs(z_score=2.5, deviation_percentage=15.0, frp=10.0,
                 persistence_score=0.3, confidence=70.0, data_quality="good"))
        weak = compute_industrial_fire_candidate_score(
            _hs(z_score=0.5, deviation_percentage=3.0, frp=10.0,
                 persistence_score=0.3, confidence=70.0, data_quality="good"))
        self.assertGreater(strong["industrial_fire_candidate_score"],
                           weak["industrial_fire_candidate_score"])
        self.assertGreater(strong["anomaly_severity_score"], weak["anomaly_severity_score"])

    def test_comparable_other_factors_stronger_anomaly_wins(self):
        a = compute_industrial_fire_candidate_score(
            _hs(z_score=2.0, deviation_percentage=10.0, frp=10.0,
                 persistence_score=0.3, confidence=70.0, data_quality="good"))
        b = compute_industrial_fire_candidate_score(
            _hs(z_score=1.0, deviation_percentage=10.0, frp=10.0,
                 persistence_score=0.3, confidence=70.0, data_quality="good"))
        self.assertGreater(a["industrial_fire_candidate_score"],
                           b["industrial_fire_candidate_score"])


class TestNotProbability(unittest.TestCase):
    def test_label_and_meaning(self):
        r = compute_industrial_fire_candidate_score(_hs(z_score=1.0, frp=10.0))
        self.assertEqual(r["score_label"], "industrial_fire_candidate_score")
        self.assertIn("NOT a probability", r["score_meaning"])
        self.assertIn("NOT", r["score_meaning"].upper())


if __name__ == "__main__":
    unittest.main()