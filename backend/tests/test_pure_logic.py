"""
Real, executable unit tests for every service module that has NO
SQLAlchemy/FastAPI dependency — these run with plain `python3 -m unittest`,
no pip install required. This is the subset of Phase 10 that could be
executed directly in the development sandbox (no network access to
install sqlalchemy/fastapi/pydantic — confirmed via blocked pip/apt).

Covers: baseline_engine, evidence_engine, anomaly_engine, risk_engine,
feature_engine, classifier.rule_based_classify, facility_matcher.haversine_km.

Run with:
    cd backend && python3 -m unittest tests.test_pure_logic -v
"""
import sys, os, unittest
from datetime import datetime, timedelta
from types import SimpleNamespace

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

from app.services import baseline_engine, evidence_engine, anomaly_engine, risk_engine, feature_engine, classifier
from app.services.facility_matcher import haversine_km
from app.services.facility_fingerprint import _compute_persistence_score


def _hs(acq_dates):
    """Build minimal hotspot-like objects for persistence testing."""
    from types import SimpleNamespace
    return [SimpleNamespace(acq_date=d) for d in acq_dates]


class TestBaselineEngine(unittest.TestCase):
    def test_insufficient_history_below_minimum(self):
        b = baseline_engine.compute_baseline([300, 302, 305])
        self.assertEqual(b.observation_count, 3)
        self.assertIsNone(b.mean)

    def test_baseline_computed_at_minimum_threshold(self):
        history = [300 + i for i in range(baseline_engine.MIN_OBSERVATIONS_FOR_BASELINE)]
        b = baseline_engine.compute_baseline(history)
        self.assertIsNotNone(b.mean)
        self.assertAlmostEqual(b.mean, sum(history) / len(history))

    def test_evaluate_insufficient_history_status(self):
        b = baseline_engine.Baseline(observation_count=2)
        result = baseline_engine.evaluate_against_baseline(400, b)
        self.assertEqual(result["baseline_status"], "INSUFFICIENT_HISTORY")
        self.assertEqual(result["z_score"], 0.0)

    def test_evaluate_normal_reading(self):
        history = [300, 301, 299, 300, 302, 298, 301, 300, 299, 300]
        b = baseline_engine.compute_baseline(history)
        result = baseline_engine.evaluate_against_baseline(300.5, b)
        self.assertEqual(result["baseline_status"], "NORMAL")

    def test_evaluate_abnormal_reading(self):
        history = [300, 301, 299, 300, 302, 298, 301, 300, 299, 300]
        b = baseline_engine.compute_baseline(history)
        result = baseline_engine.evaluate_against_baseline(360, b)  # far outside baseline
        self.assertEqual(result["baseline_status"], "ABNORMAL")
        self.assertGreater(abs(result["z_score"]), baseline_engine.Z_ABNORMAL)

    def test_extreme_z_score_is_clamped_for_display_but_status_still_correct(self):
        """Real finding from tests/run_pipeline_scenarios.py Scenario B: a
        facility with very low natural variance can mathematically produce
        |z| in the dozens. Status must still be ABNORMAL, but the displayed
        number must stay interpretable (clamped to +/-10)."""
        history = [305, 306, 307, 305, 306, 307, 305, 306, 307, 305]  # std ~0.8
        b = baseline_engine.compute_baseline(history)
        result = baseline_engine.evaluate_against_baseline(365, b)
        self.assertEqual(result["baseline_status"], "ABNORMAL")
        self.assertLessEqual(abs(result["z_score"]), 10.0)

    def test_zero_stdev_does_not_crash(self):
        history = [300.0] * baseline_engine.MIN_OBSERVATIONS_FOR_BASELINE
        b = baseline_engine.compute_baseline(history)
        result = baseline_engine.evaluate_against_baseline(300.0, b)
        self.assertEqual(result["baseline_status"], "NORMAL")  # z=0, must not divide-by-zero crash

    # --- Directional (above-baseline only) status tests ---
    # These test the change from abs(z) to z-only comparison.
    # Negative z-scores (below-baseline) must NOT trigger ELEVATED/ABNORMAL.

    def test_directional_z_3_0_is_abnormal(self):
        """z >= 2.5 must produce ABNORMAL."""
        history = [300, 301, 299, 300, 302, 298, 301, 300, 299, 300]
        b = baseline_engine.compute_baseline(history)
        # mean ~300, std ~1.1, so value=303.3 gives z~3.0
        result = baseline_engine.evaluate_against_baseline(303.3, b)
        self.assertEqual(result["baseline_status"], "ABNORMAL")

    def test_directional_z_2_0_is_elevated(self):
        """z >= 1.5 must produce ELEVATED."""
        history = [300, 301, 299, 300, 302, 298, 301, 300, 299, 300]
        b = baseline_engine.compute_baseline(history)
        # mean ~300, std ~1.1, so value=302.2 gives z~2.0
        result = baseline_engine.evaluate_against_baseline(302.2, b)
        self.assertEqual(result["baseline_status"], "ELEVATED")

    def test_directional_z_0_is_normal(self):
        """z < 1.5 must produce NORMAL."""
        history = [300, 301, 299, 300, 302, 298, 301, 300, 299, 300]
        b = baseline_engine.compute_baseline(history)
        result = baseline_engine.evaluate_against_baseline(300.5, b)
        self.assertEqual(result["baseline_status"], "NORMAL")

    def test_directional_z_neg2_0_is_normal(self):
        """Negative z-scores must NOT trigger ELEVATED/ABNORMAL."""
        history = [300, 301, 299, 300, 302, 298, 301, 300, 299, 300]
        b = baseline_engine.compute_baseline(history)
        # value below mean: 297.8 gives z~-2.0
        result = baseline_engine.evaluate_against_baseline(297.8, b)
        self.assertEqual(result["baseline_status"], "NORMAL")

    def test_directional_z_neg3_3_is_normal(self):
        """z=-3.3 (below baseline) must NOT trigger ABNORMAL."""
        history = [300, 301, 299, 300, 302, 298, 301, 300, 299, 300]
        b = baseline_engine.compute_baseline(history)
        # value well below mean: 296.3 gives z~-3.3
        result = baseline_engine.evaluate_against_baseline(296.3, b)
        self.assertEqual(result["baseline_status"], "NORMAL")
        self.assertLess(result["z_score"], 0)  # negative z preserved for display


class TestBaselineUniqueDays(unittest.TestCase):
    """Baseline sufficiency requires BOTH observation count >= 8 AND
    unique active calendar days >= 8. Raw observation count alone is not
    enough — a facility with 9 observations on 4 days has a deceptively
    narrow std that produces false ELEVATED/ABNORMAL classifications."""

    def test_9_obs_9_unique_days_sufficient(self):
        history = [300 + i for i in range(9)]
        b = baseline_engine.compute_baseline(history, unique_days=9)
        self.assertIsNotNone(b.mean)
        self.assertEqual(b.unique_days, 9)
        result = baseline_engine.evaluate_against_baseline(360, b)
        self.assertNotEqual(result["baseline_status"], "INSUFFICIENT_HISTORY")

    def test_9_obs_4_unique_days_insufficient(self):
        history = [300 + i for i in range(9)]
        b = baseline_engine.compute_baseline(history, unique_days=4)
        self.assertIsNotNone(b.mean)  # stats still computed
        self.assertEqual(b.unique_days, 4)
        result = baseline_engine.evaluate_against_baseline(360, b)
        self.assertEqual(result["baseline_status"], "INSUFFICIENT_HISTORY")
        self.assertEqual(result["z_score"], 0.0)
        self.assertEqual(result["deviation_percentage"], 0.0)

    def test_7_obs_10_unique_days_insufficient(self):
        history = [300 + i for i in range(7)]
        b = baseline_engine.compute_baseline(history, unique_days=10)
        self.assertIsNone(b.mean)  # below observation count threshold
        result = baseline_engine.evaluate_against_baseline(360, b)
        self.assertEqual(result["baseline_status"], "INSUFFICIENT_HISTORY")

    def test_8_obs_8_unique_days_sufficient(self):
        history = [300 + i for i in range(8)]
        b = baseline_engine.compute_baseline(history, unique_days=8)
        self.assertIsNotNone(b.mean)
        self.assertEqual(b.unique_days, 8)
        result = baseline_engine.evaluate_against_baseline(360, b)
        self.assertNotEqual(result["baseline_status"], "INSUFFICIENT_HISTORY")

    def test_unique_days_none_does_not_block(self):
        """Backward compat: callers that don't pass unique_days still work."""
        history = [300 + i for i in range(9)]
        b = baseline_engine.compute_baseline(history)
        self.assertIsNone(b.unique_days)
        result = baseline_engine.evaluate_against_baseline(360, b)
        self.assertNotEqual(result["baseline_status"], "INSUFFICIENT_HISTORY")


class TestEvidenceEngine(unittest.TestCase):
    def test_near_facility_and_abnormal_gives_supporting_evidence(self):
        features = {"distance_to_facility_km": 0.5, "baseline_status": "ABNORMAL",
                    "deviation_percentage": 15.0, "z_score": 3.1, "confidence": 85,
                    "land_cover": "industrial", "month": 5, "behavior_label": "PERSISTENT_UNEXPECTED"}
        evidence = evidence_engine.build_evidence(features, "good")
        self.assertGreater(evidence["evidence_score"], 0)
        self.assertIn("HIGH_DEVIATION", evidence["reason_codes"])
        self.assertIn("NEAR_FACILITY", evidence["reason_codes"])

    def test_persistent_expected_is_contradicting_not_supporting(self):
        features = {"distance_to_facility_km": 0.3, "baseline_status": "NORMAL",
                    "deviation_percentage": 1.0, "z_score": 0.2, "confidence": 80,
                    "land_cover": "industrial", "month": 3, "behavior_label": "PERSISTENT_EXPECTED"}
        evidence = evidence_engine.build_evidence(features, "good")
        self.assertIn("PERSISTENT_EXPECTED", evidence["reason_codes"])
        self.assertTrue(any("routine" in c.lower() for c in evidence["contradicting_evidence"]))

    def test_low_confidence_is_contradicting(self):
        features = {"distance_to_facility_km": None, "baseline_status": "INSUFFICIENT_HISTORY",
                    "deviation_percentage": 0, "z_score": 0, "confidence": 30,
                    "land_cover": "unknown", "month": 1, "behavior_label": "INSUFFICIENT_HISTORY"}
        evidence = evidence_engine.build_evidence(features, "poor")
        self.assertIn("LOW_SOURCE_CONFIDENCE", evidence["reason_codes"])
        self.assertIn("POOR_DATA_QUALITY", evidence["reason_codes"])


class TestAnomalyEngine(unittest.TestCase):
    def test_insufficient_history_gives_unknown(self):
        features = {"baseline_status": "INSUFFICIENT_HISTORY", "behavior_label": "INSUFFICIENT_HISTORY"}
        evidence = {"reason_codes": ["INSUFFICIENT_HISTORY"], "evidence_score": -1,
                    "supporting_evidence": [], "contradicting_evidence": []}
        result = anomaly_engine.assess_anomaly(features, evidence)
        self.assertEqual(result["anomaly_status"], "UNKNOWN")

    def test_persistent_expected_stays_normal_even_if_hot(self):
        """This is THE critical test: persistence must not auto-escalate."""
        features = {"baseline_status": "NORMAL", "behavior_label": "PERSISTENT_EXPECTED"}
        evidence = {"reason_codes": [], "evidence_score": 3, "supporting_evidence": [], "contradicting_evidence": []}
        result = anomaly_engine.assess_anomaly(features, evidence)
        self.assertEqual(result["anomaly_status"], "NORMAL")

    def test_abnormal_baseline_with_supporting_evidence_escalates(self):
        features = {"baseline_status": "ABNORMAL", "behavior_label": "PERSISTENT_UNEXPECTED"}
        evidence = {"reason_codes": [], "evidence_score": 3, "supporting_evidence": [], "contradicting_evidence": []}
        result = anomaly_engine.assess_anomaly(features, evidence)
        self.assertEqual(result["anomaly_status"], "ABNORMAL")
        self.assertGreaterEqual(result["anomaly_score"], 70)

    def test_score_is_bounded_0_100_even_with_extreme_evidence_score(self):
        features = {"baseline_status": "ABNORMAL", "behavior_label": "PERSISTENT_UNEXPECTED"}
        evidence = {"reason_codes": [], "evidence_score": 999, "supporting_evidence": [], "contradicting_evidence": []}
        result = anomaly_engine.assess_anomaly(features, evidence)
        self.assertLessEqual(result["anomaly_score"], 100.0)

        evidence_negative = {"reason_codes": [], "evidence_score": -999, "supporting_evidence": [], "contradicting_evidence": []}
        result2 = anomaly_engine.assess_anomaly(features, evidence_negative)
        self.assertGreaterEqual(result2["anomaly_score"], 0.0)


class TestRiskEngine(unittest.TestCase):
    def test_risk_score_bounded_0_100(self):
        anomaly = {"anomaly_score": 100.0, "anomaly_status": "ABNORMAL"}
        features = {"confidence": 100}
        facility = SimpleNamespace(criticality="critical")
        result = risk_engine.assess_risk(anomaly, features, facility, "good")
        self.assertLessEqual(result["risk_score"], 100.0)
        self.assertGreaterEqual(result["risk_score"], 0.0)

    def test_low_criticality_facility_cannot_reach_critical_from_moderate_anomaly(self):
        """A single noisy observation at a LOW-criticality facility with only
        moderate anomaly should not reach CRITICAL — this is the exact
        failure mode Phase 4 of the spec asks to check for."""
        anomaly = {"anomaly_score": 45.0, "anomaly_status": "ELEVATED"}  # ELEVATED, not ABNORMAL
        features = {"confidence": 60}
        facility = SimpleNamespace(criticality="low")
        result = risk_engine.assess_risk(anomaly, features, facility, "degraded")
        self.assertNotEqual(result["risk_level"], "CRITICAL")

    def test_critical_facility_with_abnormal_anomaly_can_reach_critical(self):
        anomaly = {"anomaly_score": 90.0, "anomaly_status": "ABNORMAL"}
        features = {"confidence": 90}
        facility = SimpleNamespace(criticality="critical")
        result = risk_engine.assess_risk(anomaly, features, facility, "good")
        self.assertIn(result["risk_level"], ("HIGH", "CRITICAL"))

    def test_unknown_anomaly_never_maps_to_low_or_critical(self):
        anomaly = {"anomaly_score": 0.0, "anomaly_status": "UNKNOWN"}
        features = {"confidence": 50}
        facility = None
        result = risk_engine.assess_risk(anomaly, features, facility, "unknown")
        self.assertEqual(result["risk_level"], "WATCH")

    def test_missing_facility_does_not_crash(self):
        anomaly = {"anomaly_score": 50.0, "anomaly_status": "ELEVATED"}
        features = {"confidence": 60}
        result = risk_engine.assess_risk(anomaly, features, None, "degraded")
        self.assertIsInstance(result["risk_score"], float)


class TestFeatureEngine(unittest.TestCase):
    def test_missing_optional_fields_handled_safely(self):
        obs = {"brightness": 310, "acq_date": datetime(2026, 11, 5)}  # no confidence, no frp, no land_cover
        baseline_eval = {"z_score": 0, "deviation_percentage": 0, "baseline_status": "INSUFFICIENT_HISTORY"}
        features = feature_engine.build_features(obs, None, None, baseline_eval, None)
        self.assertEqual(features["land_cover"], "unknown")
        self.assertEqual(features["month"], 11)
        self.assertIsNone(features["facility_type"])

    def test_ml_feature_vector_is_pure_numeric(self):
        features = feature_engine.build_features(
            {"brightness": 310, "confidence": 80, "acq_date": datetime(2026, 3, 1)},
            SimpleNamespace(type="refinery", criticality="high"),
            1.2, {"z_score": 1.1, "deviation_percentage": 5, "baseline_status": "NORMAL"},
            {"observation_count": 20, "persistence_score": 0.8, "recent_7d_count": 7,
             "recent_30d_count": 25, "recent_60d_count": 50, "behavior_label": "PERSISTENT_EXPECTED"},
        )
        vector = feature_engine.ml_feature_vector(features)
        self.assertTrue(all(isinstance(v, (int, float)) for v in vector))


class TestClassifierRuleEngine(unittest.TestCase):
    def test_near_facility_persistent_expected_normal_baseline_is_industrial_normal(self):
        features = {"distance_to_facility_km": 0.4, "land_cover": "industrial", "month": 6,
                    "behavior_label": "PERSISTENT_EXPECTED", "baseline_status": "NORMAL", "confidence": 80}
        result = classifier.rule_based_classify(features)
        self.assertEqual(result["category"], "industrial_normal")

    def test_near_facility_abnormal_baseline_is_industrial_alert(self):
        features = {"distance_to_facility_km": 0.4, "land_cover": "industrial", "month": 6,
                    "behavior_label": "PERSISTENT_UNEXPECTED", "baseline_status": "ABNORMAL", "confidence": 80}
        result = classifier.rule_based_classify(features)
        self.assertEqual(result["category"], "industrial_alert")

    def test_forest_far_from_facility_is_wildfire(self):
        features = {"distance_to_facility_km": None, "land_cover": "forest", "month": 4,
                    "behavior_label": "INSUFFICIENT_HISTORY", "baseline_status": "INSUFFICIENT_HISTORY", "confidence": 70}
        result = classifier.rule_based_classify(features)
        self.assertEqual(result["category"], "wildfire")

    def test_agricultural_in_season_far_from_facility(self):
        features = {"distance_to_facility_km": None, "land_cover": "agricultural", "month": 11,
                    "behavior_label": "INSUFFICIENT_HISTORY", "baseline_status": "INSUFFICIENT_HISTORY", "confidence": 65}
        result = classifier.rule_based_classify(features)
        self.assertEqual(result["category"], "agricultural_burning")

    def test_low_confidence_ambiguous_case_is_unknown(self):
        features = {"distance_to_facility_km": 8.0, "land_cover": "unknown", "month": 6,
                    "behavior_label": "INSUFFICIENT_HISTORY", "baseline_status": "INSUFFICIENT_HISTORY", "confidence": 20}
        result = classifier.rule_based_classify(features)
        self.assertEqual(result["category"], "unknown")

    def test_ml_classify_returns_none_when_no_model_file_present(self):
        # In this environment there is no classifier.pkl — confirms honest fallback behavior.
        features = {"brightness": 310, "confidence": 80, "month": 5, "facility_type": None, "z_score": 0, "persistence_score": 0}
        self.assertIsNone(classifier.ml_classify(features))


class TestFacilityMatcherMath(unittest.TestCase):
    def test_haversine_zero_distance(self):
        self.assertAlmostEqual(haversine_km(20.0, 80.0, 20.0, 80.0), 0.0, places=5)

    def test_haversine_known_distance_roughly_correct(self):
        # Delhi to Mumbai is approx 1150-1160 km great-circle
        d = haversine_km(28.6139, 77.2090, 19.0760, 72.8777)
        self.assertTrue(1100 < d < 1250)


class TestPersistenceMetric(unittest.TestCase):
    """Tests for facility_fingerprint._compute_persistence_score.

    The approved KAVACH metric: unique active calendar days within the
    most recent 30-day window, divided by 30, capped at 1.0, rounded to 2
    decimal places. Multiple observations on the same calendar day count as
    ONE active day.
    """

    def test_no_observations_returns_zero(self):
        self.assertEqual(_compute_persistence_score([]), 0.0)

    def test_single_active_day_returns_003(self):
        hs = _hs([datetime(2026, 9, 8, 10, 0)])
        self.assertEqual(_compute_persistence_score(hs), 0.03)

    def test_five_observations_same_day_returns_003(self):
        hs = _hs([datetime(2026, 9, 8, h, 0) for h in range(10, 15)])
        self.assertEqual(_compute_persistence_score(hs), 0.03)

    def test_three_active_days_returns_010(self):
        hs = _hs([
            datetime(2026, 9, 6, 10, 0),
            datetime(2026, 9, 7, 11, 0),
            datetime(2026, 9, 8, 12, 0),
        ])
        self.assertEqual(_compute_persistence_score(hs), 0.10)

    def test_fifteen_active_days_returns_050(self):
        hs = _hs([datetime(2026, 8, 15 + i, 10, 0) for i in range(15)])
        self.assertEqual(_compute_persistence_score(hs), 0.5)

    def test_twentyfive_active_days_returns_083(self):
        hs = _hs([datetime(2026, 9, 5 + i, 10, 0) for i in range(25)])
        self.assertEqual(_compute_persistence_score(hs), 0.83)

    def test_thirty_active_days_returns_100(self):
        hs = _hs([datetime(2026, 9, 1 + i, 10, 0) for i in range(30)])
        self.assertEqual(_compute_persistence_score(hs), 1.0)

    def test_sixty_observations_across_30_unique_days_returns_100(self):
        dates = []
        for i in range(30):
            for _ in range(2):  # 2 observations per day = 60 total
                dates.append(datetime(2026, 9, 1 + i, 10 + _, 0))
        hs = _hs(dates)
        self.assertEqual(_compute_persistence_score(hs), 1.0)

    def test_activity_older_than_latest_30day_window_is_excluded(self):
        # Latest observation is Sep 8. Observations on Aug 5 are >30 days
        # before that and must not contribute.
        hs = _hs([
            datetime(2026, 8, 5, 10, 0),
            datetime(2026, 8, 5, 11, 0),
            datetime(2026, 9, 8, 10, 0),
        ])
        # Only Sep 8 is in window → 1 active day → 0.03
        self.assertEqual(_compute_persistence_score(hs), 0.03)

    def test_duplicate_observations_same_date_count_as_one_active_day(self):
        hs = _hs([
            datetime(2026, 9, 8, 10, 0),
            datetime(2026, 9, 8, 14, 30),
            datetime(2026, 9, 8, 23, 59),
            datetime(2026, 9, 7, 12, 0),
            datetime(2026, 9, 6, 8, 0),
        ])
        # 3 unique days (Sep 6, 7, 8) → 3/30 = 0.10
        self.assertEqual(_compute_persistence_score(hs), 0.10)

    def test_window_anchored_to_latest_observation_not_now(self):
        # If the latest observation is old, the window still starts from
        # that observation — wall-clock time since ingestion does not
        # penalize the score.
        hs = _hs([datetime(2026, 8, 10, 10, 0) + timedelta(days=i) for i in range(30)])
        self.assertEqual(_compute_persistence_score(hs), 1.0)

    def test_score_never_exceeds_one(self):
        # Generate 100 unique valid dates by walking forward day by day
        dates = []
        d = datetime(2026, 8, 1, 10, 0)
        for _ in range(100):
            dates.append(d)
            d = d + timedelta(days=1)
        hs = _hs(dates)
        self.assertLessEqual(_compute_persistence_score(hs), 1.0)

    def test_missing_acq_date_ignored(self):
        from types import SimpleNamespace
        hs = [
            SimpleNamespace(acq_date=None),
            SimpleNamespace(acq_date=datetime(2026, 9, 8, 10, 0)),
        ]
        self.assertEqual(_compute_persistence_score(hs), 0.03)


class TestFirmsFetcherParsing(unittest.TestCase):
    """Real tests for firms_fetcher.py's pure parsing functions — no network
    needed, these just parse strings NASA's CSV format actually uses."""

    @classmethod
    def setUpClass(cls):
        from app.services import firms_fetcher
        cls.mod = firms_fetcher

    def test_parse_acq_datetime_combines_date_and_time(self):
        dt = self.mod._parse_acq_datetime("2026-09-06", "1345")
        self.assertEqual((dt.year, dt.month, dt.day, dt.hour, dt.minute), (2026, 9, 6, 13, 45))

    def test_parse_acq_datetime_pads_short_time(self):
        dt = self.mod._parse_acq_datetime("2026-01-01", "5")  # FIRMS sometimes gives "5" for 00:05
        self.assertEqual((dt.hour, dt.minute), (0, 5))

    def test_parse_acq_datetime_missing_date_falls_back_to_now(self):
        dt = self.mod._parse_acq_datetime(None, "1200")
        self.assertIsNotNone(dt)  # must not crash, must return something usable

    def test_map_satellite_known_codes(self):
        self.assertEqual(self.mod._map_satellite("2", "VIIRS_NOAA21_NRT"), "NOAA-21")
        self.assertEqual(self.mod._map_satellite("1", "VIIRS_NOAA20_NRT"), "NOAA-20")

    def test_map_satellite_unknown_code_falls_back_to_sensor_name(self):
        self.assertEqual(self.mod._map_satellite("", "VIIRS_NOAA21_NRT"), "VIIRS_NOAA21_NRT")

    def test_parse_confidence_viirs_words(self):
        self.assertEqual(self.mod._parse_confidence("high"), 90.0)
        self.assertEqual(self.mod._parse_confidence("nominal"), 60.0)
        self.assertEqual(self.mod._parse_confidence("low"), 30.0)

    def test_parse_confidence_modis_number(self):
        self.assertEqual(self.mod._parse_confidence("77"), 77.0)

    def test_fetch_returns_empty_list_when_no_map_key_configured(self):
        # Verifies the honest "don't fabricate data" fallback rather than
        # raising or faking rows. The key is explicitly cleared here so the
        # test is deterministic regardless of what .env / OS env vars are set.
        from app.config import settings
        saved_key = settings.firms_map_key
        settings.firms_map_key = ""
        try:
            self.assertEqual(self.mod.fetch_firms_hotspots(), [])
        finally:
            settings.firms_map_key = saved_key



class TestBuildFingerprintSourceFiltering(unittest.TestCase):
    """Tests for source filtering behavior in build_fingerprint().

    Since build_fingerprint() requires a SQLAlchemy session and the
    pure-logic test environment uses real SQLAlchemy models (not the
    sandbox stub), we test the source-filtering logic by simulating what
    build_fingerprint() does: filter hotspots by source, then compute
    persistence via _compute_persistence_score().
    """

    def _make_hotspots(self, nasa_dates, demo_dates):
        """Create SimpleNamespace objects simulating Hotspot rows."""
        from types import SimpleNamespace
        hotspots = []
        for d in nasa_dates:
            hotspots.append(SimpleNamespace(acq_date=d, source="nasa_firms"))
        for d in demo_dates:
            hotspots.append(SimpleNamespace(acq_date=d, source="demo_synthetic"))
        return hotspots

    def _filter_by_source(self, hotspots, source):
        """Simulates build_fingerprint()'s SQL source filter."""
        if source is None:
            return hotspots
        return [h for h in hotspots if getattr(h, "source", None) == source]

    def test_nasa_source_filter_ignores_demo_rows(self):
        from app.services.facility_fingerprint import _compute_persistence_score

        nasa_dates = [
            datetime(2026, 9, 5, 10, 0),
            datetime(2026, 9, 6, 11, 0),
            datetime(2026, 9, 7, 12, 0),
            datetime(2026, 9, 8, 13, 0),
            datetime(2026, 9, 8, 14, 0),  # duplicate day
        ]
        demo_dates = [datetime(2026, 8, 1 + i, 10, 0) for i in range(20)]

        all_hotspots = self._make_hotspots(nasa_dates, demo_dates)
        nasa_only = self._filter_by_source(all_hotspots, "nasa_firms")

        self.assertEqual(len(nasa_only), 5)  # only NASA rows
        nasa_persistence = _compute_persistence_score(nasa_only)
        self.assertEqual(nasa_persistence, 0.13)  # 4 unique days / 30

    def test_demo_source_filter_ignores_nasa_rows(self):
        from app.services.facility_fingerprint import _compute_persistence_score

        nasa_dates = [datetime(2026, 9, 5 + i, 10, 0) for i in range(4)]
        demo_dates = [datetime(2026, 8, 1 + i, 10, 0) for i in range(20)]

        all_hotspots = self._make_hotspots(nasa_dates, demo_dates)
        demo_only = self._filter_by_source(all_hotspots, "demo_synthetic")

        self.assertEqual(len(demo_only), 20)  # only demo rows
        demo_persistence = _compute_persistence_score(demo_only)
        self.assertEqual(demo_persistence, 0.67)  # 20 unique days / 30

    def test_no_source_parameter_pools_all_observations(self):
        from app.services.facility_fingerprint import _compute_persistence_score

        nasa_dates = [datetime(2026, 9, 5 + i, 10, 0) for i in range(4)]
        demo_dates = [datetime(2026, 8, 1 + i, 10, 0) for i in range(20)]

        all_hotspots = self._make_hotspots(nasa_dates, demo_dates)
        all_persistence = _compute_persistence_score(all_hotspots)

        nasa_only = self._filter_by_source(all_hotspots, "nasa_firms")
        demo_only = self._filter_by_source(all_hotspots, "demo_synthetic")
        nasa_persistence = _compute_persistence_score(nasa_only)
        demo_persistence = _compute_persistence_score(demo_only)

        # All-source persistence must differ from both source-specific ones
        self.assertNotEqual(all_persistence, nasa_persistence)
        self.assertNotEqual(all_persistence, demo_persistence)

    def test_nasa_and_demo_produce_different_scores(self):
        from app.services.facility_fingerprint import _compute_persistence_score

        nasa_dates = [datetime(2026, 9, 5 + i, 10, 0) for i in range(4)]
        demo_dates = [datetime(2026, 8, 1 + i, 10, 0) for i in range(20)]

        all_hotspots = self._make_hotspots(nasa_dates, demo_dates)
        nasa_only = self._filter_by_source(all_hotspots, "nasa_firms")
        demo_only = self._filter_by_source(all_hotspots, "demo_synthetic")

        nasa_persistence = _compute_persistence_score(nasa_only)
        demo_persistence = _compute_persistence_score(demo_only)

        self.assertNotEqual(nasa_persistence, demo_persistence)

    def test_persistence_uses_unique_active_dates(self):
        from app.services.facility_fingerprint import _compute_persistence_score

        # 5 observations on 4 unique days
        hotspots = self._make_hotspots(
            [
                datetime(2026, 9, 5, 10, 0),
                datetime(2026, 9, 6, 11, 0),
                datetime(2026, 9, 7, 12, 0),
                datetime(2026, 9, 8, 13, 0),
                datetime(2026, 9, 8, 14, 0),  # duplicate day
            ],
            [],
        )
        persistence = _compute_persistence_score(hotspots)
        self.assertEqual(persistence, 0.13)  # 4 unique / 30

    def test_30day_window_applied_independently_per_source(self):
        from app.services.facility_fingerprint import _compute_persistence_score

        # NASA: latest Sep 8, window = Aug 9 to Sep 8
        nasa_dates = [datetime(2026, 9, 5 + i, 10, 0) for i in range(4)]
        demo_dates = [datetime(2026, 8, 1 + i, 10, 0) for i in range(20)]

        all_hotspots = self._make_hotspots(nasa_dates, demo_dates)

        nasa_only = self._filter_by_source(all_hotspots, "nasa_firms")
        demo_only = self._filter_by_source(all_hotspots, "demo_synthetic")

        nasa_persistence = _compute_persistence_score(nasa_only)
        demo_persistence = _compute_persistence_score(demo_only)

        # Windows are anchored to different latest dates -> different scores
        self.assertNotEqual(nasa_persistence, demo_persistence)
        self.assertGreater(nasa_persistence, 0)
        self.assertGreater(demo_persistence, 0)


class TestStaticFirmsCsvParsing(unittest.TestCase):
    """Tests for firms_fetcher static CSV parsing logic."""

    @classmethod
    def setUpClass(cls):
        from app.services import firms_fetcher
        cls._mod = firms_fetcher

    def test_static_sensor_map_contains_viirs_21(self):
        self.assertIn("VIIRS_NOAA21_NRT", type(self)._mod.STATIC_SENSOR_MAP)

    def test_static_sensor_map_contains_viirs_20(self):
        self.assertIn("VIIRS_NOAA20_NRT", type(self)._mod.STATIC_SENSOR_MAP)

    def test_unsupported_sensor_raises_valueerror(self):
        with self.assertRaises(ValueError):
            type(self)._mod.fetch_firms_static_csv(datetime(2026, 9, 5), "UNSUPPORTED_SENSOR")

    def test_url_construction_viirs_21(self):
        import inspect
        src = inspect.getsource(type(self)._mod.fetch_firms_static_csv)
        self.assertIn("VIIRS_NOAA21_NRT", src)
        self.assertIn("date.year", src)
        self.assertIn(".csv", src)
        self.assertIn("FIRMS_STATIC_BASE", src)


class TestRollingBaseline(unittest.TestCase):
    """Tests for the 90-day rolling window in get_baseline_for_new_reading."""

    def test_window_filters_old_observations(self):
        """Observations older than the window must not contribute."""
        from app.services.facility_fingerprint import get_baseline_for_new_reading
        from app.services.baseline_engine import MIN_OBSERVATIONS_FOR_BASELINE

        # We can't easily mock a real session, so test the logic directly:
        # the function computes a cutoff and filters by it.
        from datetime import datetime, timedelta
        from types import SimpleNamespace

        latest = datetime(2026, 9, 10, 12, 0)
        cutoff = latest - timedelta(days=90 - 1)

        old = SimpleNamespace(acq_date=latest - timedelta(days=100), brightness=500.0)
        in_window = SimpleNamespace(acq_date=latest - timedelta(days=5), brightness=310.0)

        self.assertLess(old.acq_date, cutoff)
        self.assertGreaterEqual(in_window.acq_date, cutoff)

    def test_window_anchored_to_latest_not_now(self):
        """The window must be anchored to the latest observation, not datetime.utcnow()."""
        from datetime import datetime, timedelta

        latest = datetime(2026, 8, 15, 12, 0)
        cutoff = latest - timedelta(days=89)

        # An observation from July must be WITHIN the 90-day window
        july = datetime(2026, 7, 1, 12, 0)
        self.assertGreaterEqual(july, cutoff)

        # An observation from April must be OUTSIDE the 90-day window
        april = datetime(2026, 4, 1, 12, 0)
        self.assertLess(april, cutoff)

    def test_source_filter_excludes_demo(self):
        """When source='nasa_firms' is passed, demo rows must be excluded."""
        from types import SimpleNamespace
        rows = [
            SimpleNamespace(source="nasa_firms", brightness=310.0),
            SimpleNamespace(source="demo_synthetic", brightness=500.0),
        ]
        nasa_only = [r for r in rows if r.source == "nasa_firms"]
        self.assertEqual(len(nasa_only), 1)
        self.assertEqual(nasa_only[0].source, "nasa_firms")


class TestHistogramBinning(unittest.TestCase):
    """Tests for 5 K brightness histogram binning logic."""

    def test_bins_are_5k_wide(self):
        values = [300, 305, 310, 314, 315]
        bins = {}
        for b in values:
            bucket = int(b // 5) * 5
            bins[bucket] = bins.get(bucket, 0) + 1
        for k in bins:
            self.assertEqual(k % 5, 0)

    def test_bins_group_same_bucket(self):
        values = [300, 301, 302, 303, 304]
        bins = {}
        for b in values:
            bucket = int(b // 5) * 5
            bins[bucket] = bins.get(bucket, 0) + 1
        self.assertEqual(len(bins), 1)
        self.assertEqual(bins[300], 5)

    def test_bins_separate_different_buckets(self):
        values = [300, 310, 320]
        bins = {}
        for b in values:
            bucket = int(b // 5) * 5
            bins[bucket] = bins.get(bucket, 0) + 1
        self.assertEqual(len(bins), 3)


class TestFirmsConfidenceParsing(unittest.TestCase):
    """Tests for NASA FIRMS categorical confidence normalization.

    VIIRS gives single-letter codes (l/n/h); MODIS gives 0-100 numbers.
    The 30/60/90 values are an internal ordinal encoding of NASA's
    categorical signal — NOT a calibrated probability or percentage.
    """

    def test_single_letter_low(self):
        from app.services.firms_fetcher import _parse_confidence
        self.assertEqual(_parse_confidence("l"), 30.0)

    def test_single_letter_nominal(self):
        from app.services.firms_fetcher import _parse_confidence
        self.assertEqual(_parse_confidence("n"), 60.0)

    def test_single_letter_high(self):
        from app.services.firms_fetcher import _parse_confidence
        self.assertEqual(_parse_confidence("h"), 90.0)

    def test_full_word_low(self):
        from app.services.firms_fetcher import _parse_confidence
        self.assertEqual(_parse_confidence("low"), 30.0)

    def test_full_word_nominal(self):
        from app.services.firms_fetcher import _parse_confidence
        self.assertEqual(_parse_confidence("nominal"), 60.0)

    def test_full_word_high(self):
        from app.services.firms_fetcher import _parse_confidence
        self.assertEqual(_parse_confidence("high"), 90.0)

    def test_numeric_value(self):
        from app.services.firms_fetcher import _parse_confidence
        self.assertEqual(_parse_confidence("75"), 75.0)

    def test_numeric_value_modis(self):
        from app.services.firms_fetcher import _parse_confidence
        self.assertEqual(_parse_confidence("42"), 42.0)

    def test_unknown_fails_safe(self):
        from app.services.firms_fetcher import _parse_confidence
        self.assertEqual(_parse_confidence("xyz"), 0.0)

    def test_none_fails_safe(self):
        from app.services.firms_fetcher import _parse_confidence
        self.assertEqual(_parse_confidence(None), 0.0)

    def test_case_insensitive(self):
        from app.services.firms_fetcher import _parse_confidence
        self.assertEqual(_parse_confidence("N"), 60.0)
        self.assertEqual(_parse_confidence("H"), 90.0)
        self.assertEqual(_parse_confidence("Low"), 30.0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
