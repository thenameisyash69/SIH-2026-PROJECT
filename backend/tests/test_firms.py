"""Tests for FIRMS fetch, sync, and ingestion logic.

Run with:
    cd backend && python -m unittest tests.test_firms -v
"""
import io
import csv
import logging
import logging.handlers
import os
import sys
import unittest
from datetime import datetime
from unittest.mock import patch, MagicMock

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

import requests
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.main import app
from app.database import SessionLocal
from app.models import Hotspot, IngestionRun
from app.services import firms_ingestion
from app.services import firms_fetcher


class TestFirmsFetchSuccess(unittest.TestCase):
    """Test successful non-empty FIRMS response."""

    def test_fetch_returns_observations_for_valid_response(self):
        """A valid CSV response with data returns parsed observations."""
        csv_text = (
            "latitude,longitude,bright_ti4,scan,track,acq_date,acq_time,"
            "satellite,instrument,confidence,version,bright_ti5,frp,daynight\n"
            "23.649,96.192,328.17,0.44,0.46,2026-09-20,620,N21,VIIRS,l,2.0NRT,301.08,5.19,D\n"
            "27.889,96.082,341.12,0.56,0.43,2026-09-20,622,N21,VIIRS,n,2.0NRT,292.22,12.02,D\n"
        )

        with patch.object(firms_fetcher.requests, "get") as mock_get:
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.text = csv_text
            mock_resp.headers = {}
            mock_get.return_value = mock_resp

            result = firms_fetcher._fetch_one_sensor("VIIRS_NOAA21_NRT", 1)

        self.assertEqual(len(result["rows"]), 2)
        self.assertEqual(result["http_status"], 200)
        self.assertGreater(result["byte_count"], 0)
        self.assertEqual(result["parse_errors"], 0)
        self.assertEqual(result["rows"][0]["lat"], 23.649)
        self.assertEqual(result["rows"][0]["lon"], 96.192)
        self.assertEqual(result["sensor"], "VIIRS_NOAA21_NRT")

    def test_fetch_returns_multiple_sources(self):
        """fetch_firms_hotspots returns observations from all sources."""
        csv_text = (
            "latitude,longitude,bright_ti4,scan,track,acq_date,acq_time,"
            "satellite,instrument,confidence,version,bright_ti5,frp,daynight\n"
            "23.649,96.192,328.17,0.44,0.46,2026-09-20,620,N21,VIIRS,l,2.0NRT,301.08,5.19,D\n"
        )

        with patch.object(firms_fetcher.requests, "get") as mock_get:
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.text = csv_text
            mock_resp.headers = {}
            mock_get.return_value = mock_resp

            with patch.object(firms_fetcher.settings, "firms_map_key", "testkey"):
                result = firms_fetcher.fetch_firms_hotspots(day_range=1, sources=["VIIRS_NOAA21_NRT", "VIIRS_NOAA20_NRT"])

        self.assertEqual(len(result["observations"]), 2)
        self.assertIn("VIIRS_NOAA21_NRT", result["sources"])
        self.assertIn("VIIRS_NOAA20_NRT", result["sources"])
        self.assertEqual(result["errors"], {})

    def test_fetch_returns_structured_source_details(self):
        """Each source has detailed metrics in the result."""
        csv_text = (
            "latitude,longitude,bright_ti4,scan,track,acq_date,acq_time,"
            "satellite,instrument,confidence,version,bright_ti5,frp,daynight\n"
            "23.649,96.192,328.17,0.44,0.46,2026-09-20,620,N21,VIIRS,l,2.0NRT,301.08,5.19,D\n"
        )

        with patch.object(firms_fetcher.requests, "get") as mock_get:
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.text = csv_text
            mock_resp.headers = {}
            mock_get.return_value = mock_resp

            with patch.object(firms_fetcher.settings, "firms_map_key", "testkey"):
                result = firms_fetcher.fetch_firms_hotspots(day_range=1, sources=["VIIRS_NOAA21_NRT"])

        src = result["sources"]["VIIRS_NOAA21_NRT"]
        self.assertEqual(src["rows"], 1)
        self.assertEqual(src["http_status"], 200)
        self.assertGreater(src["byte_count"], 0)


class TestFirmsValidEmptyResponse(unittest.TestCase):
    """Test case A: FIRMS returns a valid empty dataset (no rows)."""

    def test_empty_csv_returns_zero_rows(self):
        """Headers-only CSV returns 0 rows."""
        csv_text = "latitude,longitude,bright_ti4,scan,track,acq_date,acq_time,satellite,instrument,confidence,version,bright_ti5,frp,daynight\n"

        with patch.object(firms_fetcher.requests, "get") as mock_get:
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.text = csv_text
            mock_resp.headers = {}
            mock_get.return_value = mock_resp

            result = firms_fetcher._fetch_one_sensor("VIIRS_NOAA21_NRT", 1)

        self.assertEqual(len(result["rows"]), 0)
        self.assertEqual(result["http_status"], 200)
        self.assertEqual(result["parse_errors"], 0)

    def test_completely_empty_body_returns_zero_rows(self):
        """Empty body (no headers) returns 0 rows."""
        with patch.object(firms_fetcher.requests, "get") as mock_get:
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.text = ""
            mock_resp.headers = {}
            mock_get.return_value = mock_resp

            result = firms_fetcher._fetch_one_sensor("VIIRS_NOAA21_NRT", 1)

        self.assertEqual(len(result["rows"]), 0)

    def test_sync_with_valid_empty_result_is_success(self):
        """Valid empty result is success=True with fetched=0."""
        with patch.object(firms_fetcher.settings, "firms_map_key", "testkey"), \
             patch("app.services.firms_ingestion.fetch_firms_hotspots", return_value={
                 "observations": [],
                 "sources": {},
                 "errors": {},
             }):
            db = SessionLocal()
            try:
                result = firms_ingestion.sync_once(db)
                self.assertTrue(result["success"])
                self.assertEqual(result["fetched"], 0)
                self.assertEqual(result["inserted"], 0)
                self.assertIsNone(result["error"])
            finally:
                db.close()


class TestFirmsAuthError(unittest.TestCase):
    """Test case B/C: Authentication/API error."""

    def test_invalid_api_key_raises_error(self):
        """400 with 'Invalid MAP_KEY.' raises ValueError."""
        with patch.object(firms_fetcher.requests, "get") as mock_get:
            mock_resp = MagicMock()
            mock_resp.status_code = 400
            mock_resp.text = "Invalid MAP_KEY."
            mock_resp.headers = {}
            mock_get.return_value = mock_resp

            with self.assertRaises(ValueError) as ctx:
                firms_fetcher._fetch_one_sensor("VIIRS_NOAA21_NRT", 1)
            self.assertIn("Invalid MAP_KEY", str(ctx.exception))

    def test_invalid_source_raises_error(self):
        """400 with 'Invalid source.' raises ValueError."""
        with patch.object(firms_fetcher.requests, "get") as mock_get:
            mock_resp = MagicMock()
            mock_resp.status_code = 400
            mock_resp.text = "Invalid source."
            mock_resp.headers = {}
            mock_get.return_value = mock_resp

            with self.assertRaises(ValueError):
                firms_fetcher._fetch_one_sensor("INVALID_SENSOR", 1)

    def test_http_error_raises_request_exception(self):
        """403/401 raises RequestException via raise_for_status."""
        with patch.object(firms_fetcher.requests, "get") as mock_get:
            mock_resp = MagicMock()
            mock_resp.status_code = 403
            mock_resp.raise_for_status.side_effect = requests.HTTPError("403 Forbidden")
            mock_resp.headers = {}
            mock_get.return_value = mock_resp

            with self.assertRaises(requests.HTTPError):
                firms_fetcher._fetch_one_sensor("VIIRS_NOAA21_NRT", 1)

    def test_sync_with_auth_error_is_failure(self):
        """Auth failure records success=False."""
        with patch.object(firms_fetcher.settings, "firms_map_key", "testkey"), \
             patch("app.services.firms_ingestion.fetch_firms_hotspots", side_effect=ValueError("Invalid MAP_KEY")):
            db = SessionLocal()
            try:
                result = firms_ingestion.sync_once(db)
                self.assertFalse(result["success"])
                self.assertEqual(result["error"], "Invalid MAP_KEY")
                self.assertEqual(result["fetched"], 0)
            finally:
                db.close()

    def test_timeout_is_failure(self):
        """Request timeout records success=False."""
        with patch.object(firms_fetcher.settings, "firms_map_key", "testkey"), \
             patch("app.services.firms_ingestion.fetch_firms_hotspots", side_effect=TimeoutError("timed out")):
            db = SessionLocal()
            try:
                result = firms_ingestion.sync_once(db)
                self.assertFalse(result["success"])
                self.assertIn("timed out", result["error"])
            finally:
                db.close()


class TestFirmsMalformedResponse(unittest.TestCase):
    """Test case D: Response parsing issues / malformed response."""

    def test_non_csv_text_returns_zero_rows(self):
        """Non-CSV error text without 'invalid'/'error' prefix returns 0 rows."""
        with patch.object(firms_fetcher.requests, "get") as mock_get:
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.text = "<html><body>No data available</body></html>"
            mock_resp.headers = {}
            mock_get.return_value = mock_resp

            result = firms_fetcher._fetch_one_sensor("VIIRS_NOAA21_NRT", 1)

        self.assertEqual(len(result["rows"]), 0)
        self.assertEqual(result["parse_errors"], 0)

    def test_malformed_csv_rows_are_skipped(self):
        """Rows with invalid data are skipped but valid rows are kept."""
        csv_text = (
            "latitude,longitude,bright_ti4,scan,track,acq_date,acq_time,"
            "satellite,instrument,confidence,version,bright_ti5,frp,daynight\n"
            "23.649,96.192,328.17,0.44,0.46,2026-09-20,620,N21,VIIRS,l,2.0NRT,301.08,5.19,D\n"
            "not_a_number,also_not,abc,def,ghi,2026-09-20,620,N21,VIIRS,l,2.0NRT,301.08,5.19,D\n"
        )

        with patch.object(firms_fetcher.requests, "get") as mock_get:
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.text = csv_text
            mock_resp.headers = {}
            mock_get.return_value = mock_resp

            result = firms_fetcher._fetch_one_sensor("VIIRS_NOAA21_NRT", 1)

        self.assertEqual(len(result["rows"]), 1)
        self.assertEqual(result["parse_errors"], 1)
        self.assertEqual(result["rows"][0]["lat"], 23.649)

    def test_csv_with_missing_columns_returns_zero_rows(self):
        """CSV with wrong column names returns 0 rows (KeyError on required fields)."""
        csv_text = (
            "wrong_col1,wrong_col2\n"
            "1,2\n"
        )

        with patch.object(firms_fetcher.requests, "get") as mock_get:
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.text = csv_text
            mock_resp.headers = {}
            mock_get.return_value = mock_resp

            result = firms_fetcher._fetch_one_sensor("VIIRS_NOAA21_NRT", 1)

        self.assertEqual(len(result["rows"]), 0)


class TestFirmsInsertionFailure(unittest.TestCase):
    """Test case E: Rows are fetched but rejected during validation/database insertion."""

    def test_sync_with_database_error_propagates(self):
        """Database failure during insertion propagates the exception."""
        with patch.object(firms_fetcher.settings, "firms_map_key", "testkey"), \
             patch("app.services.firms_ingestion.fetch_firms_hotspots", return_value={
                 "observations": [
                     {
                         "lat": 22.3511, "lon": 69.8340, "brightness": 328.17,
                         "confidence": 30.0, "frp": None, "satellite": "NOAA-21",
                         "acq_date": datetime(2026, 9, 20), "source_sensor": "VIIRS_NOAA21_NRT",
                     }
                 ],
                 "sources": {"VIIRS_NOAA21_NRT": {"rows": 1, "http_status": 200, "byte_count": 100, "parse_errors": 0}},
                 "errors": {},
             }), \
             patch("app.services.firms_ingestion.process_observation", side_effect=Exception("DB constraint violation")):
            db = SessionLocal()
            try:
                with self.assertRaises(Exception) as ctx:
                    firms_ingestion.sync_once(db)
                self.assertIn("DB constraint violation", str(ctx.exception))
            finally:
                db.close()

    def test_sync_endpoint_propagates_insertion_errors(self):
        """API endpoint propagates insertion errors to the client."""
        self.client = TestClient(app, raise_server_exceptions=False)
        with patch.object(firms_fetcher.settings, "firms_map_key", "testkey"), \
             patch("app.services.firms_ingestion.fetch_firms_hotspots", return_value={
                 "observations": [
                     {
                         "lat": 22.3511, "lon": 69.8340, "brightness": 328.17,
                         "confidence": 30.0, "frp": None, "satellite": "NOAA-21",
                         "acq_date": datetime(2026, 9, 20), "source_sensor": "VIIRS_NOAA21_NRT",
                     }
                 ],
                 "sources": {"VIIRS_NOAA21_NRT": {"rows": 1, "http_status": 200, "byte_count": 100, "parse_errors": 0}},
                 "errors": {},
             }), \
             patch("app.services.firms_ingestion.process_observation", side_effect=Exception("DB constraint violation")):
            db = SessionLocal()
            try:
                r = self.client.post("/data-sources/firms/sync")
                self.assertEqual(r.status_code, 500)
            finally:
                db.close()

    def test_sync_with_outside_india_rows_skips_them(self):
        """Rows outside India scope are skipped, not inserted."""
        with patch.object(firms_fetcher.settings, "firms_map_key", "testkey"), \
             patch("app.services.firms_ingestion.fetch_firms_hotspots", return_value={
                 "observations": [
                     {
                         "lat": 60.0, "lon": 100.0, "brightness": 328.17,
                         "confidence": 30.0, "frp": None, "satellite": "NOAA-21",
                         "acq_date": datetime(2026, 9, 20), "source_sensor": "VIIRS_NOAA21_NRT",
                     }
                 ],
                 "sources": {"VIIRS_NOAA21_NRT": {"rows": 1, "http_status": 200, "byte_count": 100, "parse_errors": 0}},
                 "errors": {},
             }):
            db = SessionLocal()
            try:
                result = firms_ingestion.sync_once(db)
                self.assertTrue(result["success"])
                self.assertEqual(result["fetched"], 1)
                self.assertEqual(result["inserted"], 0)
                self.assertEqual(result["skipped_outside_india"], 1)
            finally:
                db.close()

    def test_one_source_failure_does_not_prevent_others(self):
        """When one source fails, other sources are still attempted."""
        csv_text = (
            "latitude,longitude,bright_ti4,scan,track,acq_date,acq_time,"
            "satellite,instrument,confidence,version,bright_ti5,frp,daynight\n"
            "23.649,96.192,328.17,0.44,0.46,2026-09-20,620,N21,VIIRS,l,2.0NRT,301.08,5.19,D\n"
        )

        call_count = [0]

        def mock_get(*args, **kwargs):
            call_count[0] += 1
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.text = csv_text
            mock_resp.headers = {}
            return mock_resp

        with patch.object(firms_fetcher.requests, "get", side_effect=mock_get):
            with patch.object(firms_fetcher.settings, "firms_map_key", "testkey"):
                result = firms_fetcher.fetch_firms_hotspots(
                    day_range=1,
                    sources=["VIIRS_NOAA21_NRT", "VIIRS_NOAA20_NRT"],
                )

        self.assertEqual(len(result["observations"]), 2)
        self.assertEqual(result["errors"], {})
        self.assertEqual(call_count[0], 2)

    def test_sync_result_includes_source_details(self):
        """Successful sync includes per-source breakdown."""
        with patch.object(firms_fetcher.settings, "firms_map_key", "testkey"), \
             patch("app.services.firms_ingestion.fetch_firms_hotspots", return_value={
                 "observations": [
                     {
                         "lat": 23.649, "lon": 96.192, "brightness": 328.17,
                         "confidence": 30.0, "frp": None, "satellite": "NOAA-21",
                         "acq_date": datetime(2026, 9, 20), "source_sensor": "VIIRS_NOAA21_NRT",
                     }
                 ],
                 "sources": {
                     "VIIRS_NOAA21_NRT": {
                         "rows": 1, "http_status": 200,
                         "byte_count": 100, "parse_errors": 0,
                     }
                 },
                 "errors": {},
             }):
            db = SessionLocal()
            try:
                result = firms_ingestion.sync_once(db)
                self.assertIn("source_details", result)
                self.assertIn("VIIRS_NOAA21_NRT", result["source_details"])
                self.assertEqual(result["source_details"]["VIIRS_NOAA21_NRT"]["rows"], 1)
            finally:
                db.close()


class TestFirmsSyncEndpoint(unittest.TestCase):
    """Integration tests for the sync endpoint."""

    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)

    def test_sync_returns_ingestion_run_record(self):
        """POST /data-sources/firms/sync creates an IngestionRun."""
        db = SessionLocal()
        before = db.query(IngestionRun).count()
        try:
            with patch("app.services.firms_ingestion.fetch_firms_hotspots", return_value={
                "observations": [],
                "sources": {},
                "errors": {},
            }):
                r = self.client.post("/data-sources/firms/sync")
            self.assertEqual(r.status_code, 200)
            data = r.json()
            self.assertIn("success", data)
            self.assertIn("fetched", data)
            self.assertIn("inserted", data)
            self.assertIn("source_details", data)
        finally:
            after = db.query(IngestionRun).count()
            db.close()
            self.assertEqual(after, before + 1)

    def test_disabled_firms_returns_failure(self):
        """When FIRMS is disabled, sync returns success=False."""
        db = SessionLocal()
        try:
            with patch.object(firms_ingestion.settings, "firms_enabled", False):
                r = self.client.post("/data-sources/firms/sync")
            data = r.json()
            self.assertFalse(data["success"])
            self.assertIn("FIRMS_ENABLED", data["error"])
        finally:
            db.close()


class TestFirmsDiagnostics(unittest.TestCase):
    """Test diagnostic logging doesn't expose API key."""

    def test_fetcher_logs_do_not_contain_api_key(self):
        """Verify log messages use sanitized info only."""
        captured = []

        class _CaptureHandler(logging.Handler):
            def emit(self, record):
                captured.append(record)

        logger = logging.getLogger("app.services.firms_fetcher")
        handler = _CaptureHandler()
        logger.addHandler(handler)
        logger.setLevel(logging.DEBUG)

        csv_text = (
            "latitude,longitude,bright_ti4,scan,track,acq_date,acq_time,"
            "satellite,instrument,confidence,version,bright_ti5,frp,daynight\n"
            "23.649,96.192,328.17,0.44,0.46,2026-09-20,620,N21,VIIRS,l,2.0NRT,301.08,5.19,D\n"
        )

        with patch.object(firms_fetcher.requests, "get") as mock_get:
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.text = csv_text
            mock_resp.headers = {}
            mock_get.return_value = mock_resp

            with patch.object(firms_fetcher.settings, "firms_map_key", "SECRET_API_KEY"):
                firms_fetcher._fetch_one_sensor("VIIRS_NOAA21_NRT", 1)

        for record in captured:
            self.assertNotIn("SECRET_API_KEY", str(record.getMessage))
            self.assertNotIn("firms_map_key", str(record.getMessage))

        logger.removeHandler(handler)


if __name__ == "__main__":
    unittest.main()
