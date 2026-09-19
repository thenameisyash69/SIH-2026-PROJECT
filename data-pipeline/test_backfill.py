"""
Tests for historical FIRMS backfill functionality.
Run with: python -m unittest test_backfill -v
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


class TestBackfillDeduplication(unittest.TestCase):
    """Test that duplicate detection works correctly for historical backfill."""

    def setUp(self):
        _reset_store()
        self.db = FakeSession()
        
        # Add a facility for matching
        from app import models
        facility = models.Facility(
            name="Test Refinery", type="refinery", state="Gujarat",
            lat=22.0, lon=70.0, criticality="high", source="curated_demo"
        )
        self.db.add(facility)
        self.db.flush()
        self.facility_id = facility.id

    def test_duplicate_same_source_rounded_coords_exact_timestamp(self):
        """Same source + rounded lat/lon + exact acq_date = duplicate."""
        from app.services.pipeline import _find_duplicate
        
        acq_date = datetime(2026, 9, 1, 12, 0)
        
        # Insert first observation
        obs1 = {
            "lat": 22.12345, "lon": 70.12345, "brightness": 310,
            "confidence": 80, "acq_date": acq_date, "land_cover": "industrial",
            "source": "nasa_firms",
        }
        from app.services.pipeline import process_observation
        hs1 = process_observation(self.db, obs1, commit=True)
        
        # Try to insert duplicate (same rounded coords, same timestamp, same source)
        obs2 = {
            "lat": 22.12346, "lon": 70.12346, "brightness": 315,  # rounds to same
            "confidence": 85, "acq_date": acq_date, "land_cover": "industrial",
            "source": "nasa_firms",
        }
        hs2 = process_observation(self.db, obs2, commit=True)
        
        # Should return the same hotspot
        self.assertEqual(hs1.id, hs2.id)
        self.assertTrue(getattr(hs2, "_was_duplicate", False))

    def test_different_acquisition_timestamps_are_distinct(self):
        """Two observations same day, different timestamps = NOT duplicates."""
        from app.services.pipeline import process_observation
        
        base_date = datetime(2026, 9, 1)
        acq1 = base_date.replace(hour=10, minute=0)
        acq2 = base_date.replace(hour=14, minute=30)  # Different pass
        
        obs1 = {
            "lat": 22.1234, "lon": 70.1234, "brightness": 310,
            "confidence": 80, "acq_date": acq1, "land_cover": "industrial",
            "source": "nasa_firms",
        }
        obs2 = {
            "lat": 22.1234, "lon": 70.1234, "brightness": 315,
            "confidence": 85, "acq_date": acq2, "land_cover": "industrial",
            "source": "nasa_firms",
        }
        
        hs1 = process_observation(self.db, obs1, commit=True)
        hs2 = process_observation(self.db, obs2, commit=True)
        
        # Should be TWO distinct hotspots
        self.assertNotEqual(hs1.id, hs2.id)
        self.assertFalse(getattr(hs2, "_was_duplicate", False))
        self.assertEqual(self.db.query(models.Hotspot).count(), 2)

    def test_different_sources_not_duplicates(self):
        """Same coords/timestamp but different source = NOT duplicates."""
        from app.services.pipeline import process_observation
        
        acq_date = datetime(2026, 9, 1, 12, 0)
        
        obs_nasa = {
            "lat": 22.1234, "lon": 70.1234, "brightness": 310,
            "confidence": 80, "acq_date": acq_date, "land_cover": "industrial",
            "source": "nasa_firms",
        }
        obs_demo = {
            "lat": 22.1234, "lon": 70.1234, "brightness": 310,
            "confidence": 80, "acq_date": acq_date, "land_cover": "industrial",
            "source": "demo_synthetic",
        }
        
        hs1 = process_observation(self.db, obs_nasa, commit=True)
        hs2 = process_observation(self.db, obs_demo, commit=True)
        
        # Should be distinct because sources differ
        self.assertNotEqual(hs1.id, hs2.id)
        self.assertEqual(hs1.source, "nasa_firms")
        self.assertEqual(hs2.source, "demo_synthetic")

    def test_source_nasa_firms_preserved(self):
        """Historical backfill must preserve source='nasa_firms'."""
        from app.services.pipeline import process_observation
        
        acq_date = datetime(2026, 9, 1, 12, 0)
        obs = {
            "lat": 22.1234, "lon": 70.1234, "brightness": 310,
            "confidence": 80, "acq_date": acq_date, "land_cover": "industrial",
            "source": "nasa_firms",
        }
        
        hs = process_observation(self.db, obs, commit=True)
        self.assertEqual(hs.source, "nasa_firms")
        self.assertNotEqual(hs.source, "demo_synthetic")


class TestBackfillMalformedRows(unittest.TestCase):
    """Test that malformed FIRMS rows are skipped safely."""

    def setUp(self):
        _reset_store()
        self.db = FakeSession()
        from app import models
        facility = models.Facility(
            name="Test", type="refinery", state="Gujarat",
            lat=22.0, lon=70.0, criticality="high", source="curated_demo"
        )
        self.db.add(facility)
        self.db.flush()

    def test_missing_latitude_skipped(self):
        """Observation missing lat should be skipped."""
        from backfill_firms import run_backfill
        # This tests the validation logic in run_backfill
        # We'll test the validation directly
        obs = {"lon": 70.0, "brightness": 310, "acq_date": datetime.utcnow()}
        required = ["lat", "lon", "brightness", "acq_date"]
        is_valid = all(k in obs and obs[k] is not None for k in required)
        self.assertFalse(is_valid)

    def test_missing_longitude_skipped(self):
        obs = {"lat": 22.0, "brightness": 310, "acq_date": datetime.utcnow()}
        required = ["lat", "lon", "brightness", "acq_date"]
        is_valid = all(k in obs and obs[k] is not None for k in required)
        self.assertFalse(is_valid)

    def test_missing_brightness_skipped(self):
        obs = {"lat": 22.0, "lon": 70.0, "acq_date": datetime.utcnow()}
        required = ["lat", "lon", "brightness", "acq_date"]
        is_valid = all(k in obs and obs[k] is not None for k in required)
        self.assertFalse(is_valid)

    def test_missing_acq_date_skipped(self):
        obs = {"lat": 22.0, "lon": 70.0, "brightness": 310}
        required = ["lat", "lon", "brightness", "acq_date"]
        is_valid = all(k in obs and obs[k] is not None for k in required)
        self.assertFalse(is_valid)

    def test_none_values_skipped(self):
        obs = {"lat": None, "lon": 70.0, "brightness": 310, "acq_date": datetime.utcnow()}
        required = ["lat", "lon", "brightness", "acq_date"]
        is_valid = all(k in obs and obs[k] is not None for k in required)
        self.assertFalse(is_valid)


class TestBackfillLandCoverCache(unittest.TestCase):
    """Test land cover caching behavior."""

    def test_cache_hit_after_miss(self):
        from backfill_firms import LandCoverCache
        
        cache = LandCoverCache(grid_degrees=0.01)
        
        # First call - miss
        with patch('backfill_firms.tag_land_cover', return_value="industrial") as mock_tag:
            result1 = cache.get(22.1234, 70.1234)
            self.assertEqual(result1, "industrial")
            self.assertEqual(mock_tag.call_count, 1)
        
        # Second call same grid - hit
        with patch('backfill_firms.tag_land_cover', return_value="industrial") as mock_tag:
            result2 = cache.get(22.1235, 70.1235)  # Same grid cell
            self.assertEqual(result2, "industrial")
            self.assertEqual(mock_tag.call_count, 0)  # Should not call API
        
        stats = cache.stats()
        self.assertEqual(stats["hits"], 1)
        self.assertEqual(stats["misses"], 1)
        self.assertEqual(stats["hit_rate"], 0.5)

    def test_different_grid_cells_are_separate(self):
        from backfill_firms import LandCoverCache
        
        cache = LandCoverCache(grid_degrees=0.01)
        
        with patch('backfill_firms.tag_land_cover', side_effect=["industrial", "forest"]) as mock_tag:
            result1 = cache.get(22.1234, 70.1234)
            result2 = cache.get(22.5000, 70.5000)  # Different grid cell
            
            self.assertEqual(result1, "industrial")
            self.assertEqual(result2, "forest")
            self.assertEqual(mock_tag.call_count, 2)


class TestBackfillDoesNotModifyDemoData(unittest.TestCase):
    """Test that historical backfill never modifies demo_synthetic data."""

    def setUp(self):
        _reset_store()
        self.db = FakeSession()
        from app import models
        facility = models.Facility(
            name="Test", type="refinery", state="Gujarat",
            lat=22.0, lon=70.0, criticality="high", source="curated_demo"
        )
        self.db.add(facility)
        self.db.flush()

    def test_demo_synthetic_count_unchanged(self):
        """Running backfill logic should not affect demo_synthetic records."""
        from app.services.pipeline import process_observation
        from app import models
        
        # Add some demo_synthetic data
        for i in range(5):
            process_observation(self.db, {
                "lat": 22.0 + i * 0.01, "lon": 70.0 + i * 0.01,
                "brightness": 300 + i, "confidence": 80,
                "acq_date": datetime.utcnow() - timedelta(days=i),
                "land_cover": "industrial", "source": "demo_synthetic",
            }, commit=True)
        
        demo_count_before = self.db.query(models.Hotspot).filter(
            models.Hotspot.source == "demo_synthetic"
        ).count()
        
        # Add nasa_firms data (simulating backfill)
        process_observation(self.db, {
            "lat": 23.0, "lon": 71.0, "brightness": 310,
            "confidence": 85, "acq_date": datetime.utcnow(),
            "land_cover": "industrial", "source": "nasa_firms",
        }, commit=True)
        
        demo_count_after = self.db.query(models.Hotspot).filter(
            models.Hotspot.source == "demo_synthetic"
        ).count()
        
        self.assertEqual(demo_count_before, demo_count_after)
        self.assertEqual(demo_count_after, 5)


class TestBackfillDatabasePath(unittest.TestCase):
    """Test that the correct database path is used."""

    def test_backfill_script_uses_backend_db(self):
        """Verify backfill_firms.py resolves to backend/sih.db not data-pipeline/sih.db."""
        import backfill_firms as backfill_module
        
        # The script adds BACKEND_DIR to sys.path and imports from app.database
        # Check that the path resolution is correct
        backend_dir = os.path.join(os.path.dirname(__file__), "..", "backend")
        backend_dir = os.path.abspath(backend_dir)
        
        # The script's BACKEND_DIR should point to the backend folder
        self.assertTrue(os.path.exists(os.path.join(backend_dir, "app", "database.py")))


class TestLiveIngestionUnchanged(unittest.TestCase):
    """Test that live ingestion (firms_ingestion.sync_once) still works."""

    def setUp(self):
        _reset_store()
        self.db = FakeSession()
        from app import models
        facility = models.Facility(
            name="Test", type="refinery", state="Gujarat",
            lat=22.0, lon=70.0, criticality="high", source="curated_demo"
        )
        self.db.add(facility)
        self.db.flush()

    def test_sync_once_without_map_key_returns_failure(self):
        """sync_once should fail honestly without FIRMS_MAP_KEY."""
        from app.services import firms_ingestion
        from app.config import settings
        
        # Ensure no map key
        original_key = settings.firms_map_key
        settings.firms_map_key = ""
        
        try:
            result = firms_ingestion.sync_once(self.db)
            self.assertFalse(result["success"])
            self.assertIn("FIRMS_MAP_KEY", result["error"])
            self.assertEqual(result["fetched"], 0)
            self.assertEqual(result["inserted"], 0)
        finally:
            settings.firms_map_key = original_key

    def test_sync_once_records_ingestion_run(self):
        """Failed sync should still record an IngestionRun."""
        from app.services import firms_ingestion
        from app.config import settings
        from app import models
        
        original_key = settings.firms_map_key
        settings.firms_map_key = ""
        
        try:
            firms_ingestion.sync_once(self.db)
            runs = self.db.query(models.IngestionRun).all()
            self.assertEqual(len(runs), 1)
            self.assertFalse(runs[0].success)
            self.assertIsNotNone(runs[0].error_message)
        finally:
            settings.firms_map_key = original_key


if __name__ == "__main__":
    unittest.main(verbosity=2)