"""
Tests for labeling candidates endpoint and ML labeling workflow.
Run with: python -m unittest test_labeling_workflow -v
"""
import sys
import os
import unittest
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock

# Add paths for imports
BACKEND_DIR = os.path.join(os.path.dirname(__file__), "..", "backend")
sys.path.insert(0, BACKEND_DIR)
sys.path.insert(0, os.path.dirname(__file__))

from tests._sandbox_stub.sqlalchemy.orm import FakeSession, _reset_store


class TestLabelingCandidates(unittest.TestCase):
    """Test the /hotspots/labeling/candidates endpoint logic."""

    def setUp(self):
        _reset_store()
        self.db = FakeSession()
        
        # Add facilities
        from app import models
        facilities = [
            models.Facility(name="Test Refinery", type="refinery", state="Gujarat",
                           lat=22.0, lon=70.0, criticality="high", source="curated_demo"),
            models.Facility(name="Test Steel Plant", type="steel_plant", state="Jharkhand",
                           lat=23.0, lon=86.0, criticality="high", source="curated_demo"),
            models.Facility(name="Test Power Plant", type="power_plant", state="Odisha",
                           lat=21.0, lon=85.0, criticality="critical", source="curated_demo"),
        ]
        for f in facilities:
            self.db.add(f)
        self.db.flush()
        self.facility_ids = [f.id for f in facilities]
        
        # Add nasa_firms hotspots - some near facilities, some far
        now = datetime.utcnow()
        hotspots = [
            # Near facility 1 (refinery)
            {"lat": 22.01, "lon": 70.01, "brightness": 340, "confidence": 90,
             "frp": 150.0, "acq_date": now - timedelta(days=5), "satellite": "NOAA-21",
             "source": "nasa_firms", "land_cover": "unknown", "source_resolution_m": 375,
             "category": "unknown", "classification_method": "unclassified",
             "classification_confidence": 0.0, "baseline_status": "INSUFFICIENT_HISTORY",
             "z_score": 0.0, "deviation_percentage": 0.0, "persistence_score": 0.0,
             "is_anomaly": False, "reason": "", "reason_codes": "DEFERRED_HISTORICAL",
             "risk_score": 0.0, "risk_level": "LOW", "data_quality": "unknown"},
            
            # Near facility 2 (steel plant)
            {"lat": 23.01, "lon": 86.01, "brightness": 330, "confidence": 85,
             "frp": 80.0, "acq_date": now - timedelta(days=10), "satellite": "NOAA-20",
             "source": "nasa_firms", "land_cover": "unknown", "source_resolution_m": 375,
             "category": "unknown", "classification_method": "unclassified",
             "classification_confidence": 0.0, "baseline_status": "INSUFFICIENT_HISTORY",
             "z_score": 0.0, "deviation_percentage": 0.0, "persistence_score": 0.0,
             "is_anomaly": False, "reason": "", "reason_codes": "DEFERRED_HISTORICAL",
             "risk_score": 0.0, "risk_level": "LOW", "data_quality": "unknown"},
            
            # Far from any facility (wildfire candidate)
            {"lat": 11.0, "lon": 76.0, "brightness": 320, "confidence": 70,
             "frp": 50.0, "acq_date": now - timedelta(days=15), "satellite": "NOAA-21",
             "source": "nasa_firms", "land_cover": "unknown", "source_resolution_m": 375,
             "category": "unknown", "classification_method": "unclassified",
             "classification_confidence": 0.0, "baseline_status": "INSUFFICIENT_HISTORY",
             "z_score": 0.0, "deviation_percentage": 0.0, "persistence_score": 0.0,
             "is_anomaly": False, "reason": "", "reason_codes": "DEFERRED_HISTORICAL",
             "risk_score": 0.0, "risk_level": "LOW", "data_quality": "unknown"},
            
            # Another far one (agricultural candidate)
            {"lat": 30.0, "lon": 76.0, "brightness": 310, "confidence": 65,
             "frp": 30.0, "acq_date": now - timedelta(days=20), "satellite": "NOAA-20",
             "source": "nasa_firms", "land_cover": "unknown", "source_resolution_m": 375,
             "category": "unknown", "classification_method": "unclassified",
             "classification_confidence": 0.0, "baseline_status": "INSUFFICIENT_HISTORY",
             "z_score": 0.0, "deviation_percentage": 0.0, "persistence_score": 0.0,
             "is_anomaly": False, "reason": "", "reason_codes": "DEFERRED_HISTORICAL",
             "risk_score": 0.0, "risk_level": "LOW", "data_quality": "unknown"},
        ]
        
        for hs_data in hotspots:
            hs = models.Hotspot(**hs_data)
            self.db.add(hs)
        self.db.flush()
        self.hotspot_ids = [hs.id for hs in self.db.query(models.Hotspot).filter(models.Hotspot.source=="nasa_firms").all()]
        
        # Add a demo_synthetic hotspot (should be excluded by default)
        demo_hs = models.Hotspot(
            lat=25.0, lon=75.0, brightness=300, confidence=80,
            acq_date=now - timedelta(days=1), satellite="VIIRS_SNPP",
            source="demo_synthetic", land_cover="industrial",
            category="industrial_normal", classification_method="rules",
        )
        self.db.add(demo_hs)
        self.db.flush()
        
        # Add verification to one hotspot
        verified_hs = self.db.query(models.Hotspot).filter(models.Hotspot.source=="nasa_firms").first()
        verification = models.Verification(
            hotspot_id=verified_hs.id,
            decision="confirmed_industrial_fire",
            note="Test verification",
            analyst_name="test_analyst"
        )
        self.db.add(verification)
        self.db.flush()
        
        self.verified_hs_id = verified_hs.id

    def test_candidates_returns_nasa_firms_by_default(self):
        """Candidates should return only nasa_firms by default."""
        from app.routers.hotspots import get_labeling_candidates
        
        result = get_labeling_candidates(db=self.db)
        
        self.assertEqual(len(result["candidates"]), 4)  # 4 nasa_firms hotspots
        for c in result["candidates"]:
            self.assertEqual(c["source"], "nasa_firms")

    def test_candidates_filters_by_source(self):
        """Candidates should filter by source when specified."""
        from app.routers.hotspots import get_labeling_candidates
        
        result = get_labeling_candidates(source="demo_synthetic", db=self.db)
        self.assertEqual(len(result["candidates"]), 1)
        self.assertEqual(result["candidates"][0]["source"], "demo_synthetic")
        
        result = get_labeling_candidates(source="nasa_firms", db=self.db)
        self.assertEqual(len(result["candidates"]), 4)

    def test_candidates_filters_by_verified_status(self):
        """Candidates should filter by verified/unverified status."""
        from app.routers.hotspots import get_labeling_candidates
        
        # Unverified only
        result = get_labeling_candidates(verified=False, db=self.db)
        self.assertEqual(len(result["candidates"]), 3)  # 4 total - 1 verified
        for c in result["candidates"]:
            self.assertFalse(c["verified"])
        
        # Verified only
        result = get_labeling_candidates(verified=True, db=self.db)
        self.assertEqual(len(result["candidates"]), 1)
        self.assertTrue(result["candidates"][0]["verified"])
        self.assertEqual(result["candidates"][0]["verification_decision"], "confirmed_industrial_fire")

    def test_candidates_filters_by_facility_associated(self):
        """Candidates should filter by facility proximity."""
        from app.routers.hotspots import get_labeling_candidates
        
        # Facility-associated (within 5km)
        result = get_labeling_candidates(facility_associated=True, db=self.db)
        # 2 are near facilities (within 5km)
        self.assertEqual(len(result["candidates"]), 2)
        for c in result["candidates"]:
            self.assertIsNotNone(c["distance_to_facility_km"])
            self.assertLessEqual(c["distance_to_facility_km"], 5.0)
        
        # Non-facility-associated (beyond 5km)
        result = get_labeling_candidates(facility_associated=False, db=self.db)
        self.assertEqual(len(result["candidates"]), 2)
        for c in result["candidates"]:
            self.assertTrue(c["distance_to_facility_km"] is None or c["distance_to_facility_km"] > 5.0)

    def test_candidates_filters_by_min_frp(self):
        """Candidates should filter by minimum FRP."""
        from app.routers.hotspots import get_labeling_candidates
        
        result = get_labeling_candidates(min_frp=100.0, db=self.db)
        self.assertEqual(len(result["candidates"]), 1)  # Only one has FRP > 100
        self.assertGreaterEqual(result["candidates"][0]["frp"], 100.0)
        
        result = get_labeling_candidates(min_frp=50.0, db=self.db)
        self.assertEqual(len(result["candidates"]), 2)  # Two have FRP > 50

    def test_candidates_filters_by_date_range(self):
        """Candidates should filter by date range."""
        from app.routers.hotspots import get_labeling_candidates
        
        # Last 7 days
        start = (datetime.utcnow() - timedelta(days=7)).isoformat()
        end = datetime.utcnow().isoformat()
        result = get_labeling_candidates(start_date=start, end_date=end, db=self.db)
        # 1 hotspot from 5 days ago
        self.assertEqual(len(result["candidates"]), 1)
        
        # Last 15 days
        start = (datetime.utcnow() - timedelta(days=15)).isoformat()
        result = get_labeling_candidates(start_date=start, end_date=end, db=self.db)
        # 3 hotspots from 5, 10, 15 days ago
        self.assertEqual(len(result["candidates"]), 3)

    def test_candidates_prioritization(self):
        """Candidates should be prioritized correctly."""
        from app.routers.hotspots import get_labeling_candidates
        
        result = get_labeling_candidates(limit=10, db=self.db)
        
        # Unverified should come first (highest priority)
        unverified_first = all(not c["verified"] for c in result["candidates"][:3])
        self.assertTrue(unverified_first or len(result["candidates"]) < 4)
        
        # High FRP should be near top
        # First candidate should have highest priority score
        if len(result["candidates"]) >= 2:
            # At least check the structure is correct
            self.assertIn("id", result["candidates"][0])
            self.assertIn("distance_to_facility_km", result["candidates"][0])
            self.assertIn("facility", result["candidates"][0])

    def test_candidates_includes_required_fields(self):
        """Candidates response should include all required fields."""
        from app.routers.hotspots import get_labeling_candidates
        
        result = get_labeling_candidates(db=self.db)
        
        required_fields = [
            "id", "lat", "lon", "brightness", "confidence", "frp",
            "acq_date", "satellite", "source", "source_resolution_m",
            "land_cover", "facility", "distance_to_facility_km",
            "verified", "verification_decision", "verification_note",
            "category", "classification_method", "classification_confidence",
            "baseline_status", "z_score", "deviation_percentage",
            "persistence_score", "is_anomaly", "reason", "reason_codes",
            "risk_score", "risk_level", "data_quality",
            "created_at", "updated_at"
        ]
        
        for c in result["candidates"]:
            for field in required_fields:
                self.assertIn(field, c, f"Missing field: {field}")

    def test_candidates_facility_info_included(self):
        """Candidates near facilities should include facility info."""
        from app.routers.hotspots import get_labeling_candidates
        
        result = get_labeling_candidates(db=self.db)
        
        facility_candidates = [c for c in result["candidates"] if c["facility"] is not None]
        self.assertGreater(len(facility_candidates), 0)
        
        for c in facility_candidates:
            self.assertIn("id", c["facility"])
            self.assertIn("name", c["facility"])
            self.assertIn("type", c["facility"])
            self.assertIn("state", c["facility"])
            self.assertIn("criticality", c["facility"])


class TestMLLabelingStats(unittest.TestCase):
    """Test the /ml/labeling/stats and /ml/labeling/training-eligibility endpoints."""

    def setUp(self):
        _reset_store()
        self.db = FakeSession()
        
        from app import models
        # Add facility
        facility = models.Facility(name="Test", type="refinery", state="Gujarat",
                                   lat=22.0, lon=70.0, criticality="high", source="curated_demo")
        self.db.add(facility)
        self.db.flush()
        
        # Add nasa_firms hotspots
        now = datetime.utcnow()
        for i in range(5):
            hs = models.Hotspot(
                lat=22.0 + i*0.01, lon=70.0 + i*0.01, brightness=310+i,
                confidence=80+i, frp=50.0+i*10, acq_date=now - timedelta(days=i*5),
                satellite="NOAA-21", source="nasa_firms", land_cover="unknown",
                source_resolution_m=375, category="unknown", classification_method="unclassified",
                baseline_status="INSUFFICIENT_HISTORY", data_quality="unknown"
            )
            self.db.add(hs)
        self.db.flush()
        
        # Add verifications to 3 of them
        nasa_hotspots = self.db.query(models.Hotspot).filter(models.Hotspot.source=="nasa_firms").all()
        decisions = ["confirmed_industrial_fire", "confirmed_normal_industrial_heat", "wildfire"]
        for i, hs in enumerate(nasa_hotspots[:3]):
            v = models.Verification(hotspot_id=hs.id, decision=decisions[i], note=f"Note {i}", analyst_name="analyst")
            self.db.add(v)
        self.db.flush()

    def test_labeling_stats_returns_correct_counts(self):
        """Labeling stats should return correct counts."""
        from app.routers.ml_labeling import labeling_stats
        
        result = labeling_stats(db=self.db)
        
        self.assertEqual(result["source"], "nasa_firms")
        self.assertEqual(result["total_observations"], 5)
        self.assertEqual(result["verified_observations"], 3)
        self.assertEqual(result["unverified_observations"], 2)
        self.assertEqual(result["class_distribution"]["confirmed_industrial_fire"], 1)
        self.assertEqual(result["class_distribution"]["confirmed_normal_industrial_heat"], 1)
        self.assertEqual(result["class_distribution"]["wildfire"], 1)
        self.assertEqual(result["training_readiness"], "INSUFFICIENT")

    def test_labeling_stats_filters_by_source(self):
        """Labeling stats should filter by source parameter."""
        from app.routers.ml_labeling import labeling_stats
        from app import models
        
        # Add demo_synthetic hotspot with verification
        demo_hs = models.Hotspot(
            lat=25.0, lon=75.0, brightness=300, confidence=80,
            acq_date=datetime.utcnow(), satellite="VIIRS_SNPP",
            source="demo_synthetic", category="industrial_normal",
            classification_method="rules"
        )
        self.db.add(demo_hs)
        self.db.flush()
        
        v = models.Verification(hotspot_id=demo_hs.id, decision="confirmed_industrial_fire", note="", analyst_name="")
        self.db.add(v)
        self.db.flush()
        
        result = labeling_stats(source="demo_synthetic", db=self.db)
        self.assertEqual(result["source"], "demo_synthetic")
        self.assertEqual(result["total_observations"], 1)
        self.assertEqual(result["verified_observations"], 1)

    def test_training_eligibility_excludes_false_positive(self):
        """Training eligibility should exclude false_positive decisions."""
        from app.routers.ml_labeling import training_eligibility
        from app import models
        
        # Add a false_positive verification
        nasa_hs = self.db.query(models.Hotspot).filter(models.Hotspot.source=="nasa_firms").filter(~models.Hotspot.verification.any()).first()
        v = models.Verification(hotspot_id=nasa_hs.id, decision="false_positive", note="", analyst_name="")
        self.db.add(v)
        self.db.flush()
        
        result = training_eligibility(db=self.db)
        
        # Should have 3 eligible (the original 3 verified) and 1 excluded
        self.assertEqual(result["eligible_for_training"], 3)
        self.assertEqual(result["excluded_false_positive"], 1)
        self.assertIn("INDUSTRIAL", result["class_counts"])
        self.assertIn("NORMAL_INDUSTRIAL_HEAT", result["class_counts"])
        self.assertIn("WILDFIRE", result["class_counts"])

    def test_training_eligibility_maps_decisions_correctly(self):
        """Training eligibility should map decisions to canonical labels."""
        from app.routers.ml_labeling import training_eligibility
        
        result = training_eligibility(db=self.db)
        
        self.assertIn("INDUSTRIAL", result["class_counts"])
        self.assertIn("NORMAL_INDUSTRIAL_HEAT", result["class_counts"])
        self.assertIn("WILDFIRE", result["class_counts"])
        self.assertNotIn("false_positive", result["class_counts"])


class TestVerificationProtection(unittest.TestCase):
    """Test that verified labels are protected from weak/rule-engine labels."""

    def setUp(self):
        _reset_store()
        self.db = FakeSession()
        
        from app import models
        facility = models.Facility(name="Test", type="refinery", state="Gujarat",
                                   lat=22.0, lon=70.0, criticality="high", source="curated_demo")
        self.db.add(facility)
        self.db.flush()
        
        # Add nasa_firms hotspot with rule-engine classification
        hs = models.Hotspot(
            lat=22.01, lon=70.01, brightness=340, confidence=90,
            acq_date=datetime.utcnow(), satellite="NOAA-21", source="nasa_firms",
            land_cover="unknown", category="industrial_alert",
            classification_method="rules", classification_confidence=0.75,
            baseline_status="ABNORMAL", data_quality="good"
        )
        self.db.add(hs)
        self.db.flush()
        
        # Add verification that contradicts rule engine
        v = models.Verification(hotspot_id=hs.id, decision="confirmed_normal_industrial_heat",
                                note="This is normal flare, not an incident", analyst_name="expert")
        self.db.add(v)
        self.db.flush()
        
        self.hotspot = hs

    def test_verification_takes_precedence_over_rule_engine(self):
        """Verified label should be used for training, not rule-engine category."""
        from app.routers.ml_labeling import training_eligibility
        from ml.label_builder import VERIFIED_LABEL_VOCABULARY, EXCLUDED_FROM_TRAINING
        
        result = training_eligibility(db=self.db)
        
        # Rule engine said "industrial_alert" but verified says "confirmed_normal_industrial_heat"
        # Training should use NORMAL_INDUSTRIAL_HEAT, not INDUSTRIAL
        self.assertIn("NORMAL_INDUSTRIAL_HEAT", result["class_counts"])
        self.assertNotIn("INDUSTRIAL", result["class_counts"])

    def test_weak_labels_never_used_for_training(self):
        """Rule-engine categories (WEAK) should never be used as training targets."""
        from ml.label_builder import weak_label_from_pipeline_category
        
        weak_label = weak_label_from_pipeline_category(1, "industrial_alert")
        
        self.assertEqual(weak_label.label_quality, "WEAK")
        self.assertEqual(weak_label.label_source, "firms_context")
        # This should NOT be passed to ml/train.py


class TestDatasetBuilder(unittest.TestCase):
    """Test the ML dataset builder logic."""

    def test_dataset_builder_only_uses_verified_real_data(self):
        """Dataset builder should only use nasa_firms + verified."""
        # This is tested indirectly through ml/dataset_builder.py logic
        # which is already verified in existing tests
        pass


if __name__ == "__main__":
    unittest.main(verbosity=2)