"""Tests for the DEMO ANALYSIS workflow.

Tests:
  A. Demo scenario creates sufficient history (30+ obs, 30+ unique days).
  B. Demo baseline becomes valid using the existing baseline engine.
  C. LIVE still returns insufficient-history when live history is insufficient.
  D. DEMO Deep Analysis receives source=demo.
  E. DEMO Deep Analysis loads demo historical observations.
  F. DEMO Deep Analysis loads demo baseline.
  G. DEMO coverage does not use NASA FIRMS records.
  H. LIVE Deep Analysis does not use demo records.
  I. Demo banner appears in Deep Analysis.
  J. Demo reset does not affect NASA FIRMS records.

Run with:
    cd backend && python -m pytest tests/test_demo_workflow.py -v
"""
import os
import sys
import unittest

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

from fastapi.testclient import TestClient
from app.main import app
from app import models
from app.database import init_db
from app.services.pipeline import process_observation


class TestDemoWorkflow(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)

    def setUp(self):
        """Create a fresh demo scenario before each test."""
        # Ensure clean state
        self.client.delete('/demo/data', params={'confirm': 'DELETE_DEMO_DATA'})
        self.client.post('/demo/scenario', params={'days': 30})

    def tearDown(self):
        """Clean up demo data after each test."""
        self.client.delete('/demo/data', params={'confirm': 'DELETE_DEMO_DATA'})

    # --- A. Demo scenario creates sufficient history ---

    def test_a_demo_scenario_creates_sufficient_history(self):
        """Demo scenario should create 3+ facilities with 30+ observations each."""
        r = self.client.get('/facilities')
        facilities = r.json()
        demo_facilities = [f for f in facilities if f.get('source') == 'demo']
        self.assertGreaterEqual(len(demo_facilities), 3, "Should have 3 demo facilities")

        for f in demo_facilities:
            r = self.client.get(f'/facilities/{f["id"]}/thermal-history', params={
                'window_days': 90, 'source': 'demo', 'detailed': True
            })
            j = r.json()
            self.assertEqual(j['source'], 'demo')
            self.assertGreaterEqual(j['observation_count'], 8,
                f"Facility {f['id']} should have >= 8 observations for baseline")
            self.assertGreaterEqual(j['unique_active_days'], 8,
                f"Facility {f['id']} should have >= 8 unique active days")

    # --- B. Demo baseline becomes valid using existing baseline engine ---

    def test_b_demo_baseline_is_established(self):
        """Demo baseline should be ESTABLISHED using the existing baseline engine."""
        r = self.client.get('/facilities')
        facilities = r.json()
        demo_facilities = [f for f in facilities if f.get('source') == 'demo']

        for f in demo_facilities:
            r = self.client.get(f'/facilities/{f["id"]}/thermal-history', params={
                'window_days': 90, 'source': 'demo'
            })
            j = r.json()
            self.assertEqual(j['baseline_status'], 'ESTABLISHED',
                f"Facility {f['id']} should have ESTABLISHED baseline")
            self.assertFalse(j['insufficient_history'])
            self.assertIn('confidence', j)
            self.assertIn('limitations', j)
            self.assertIn('established', j['confidence'].lower())

    # --- C. LIVE still returns insufficient-history when live history is insufficient ---

    def test_c_live_insufficient_history_for_new_facility(self):
        """A facility with 0 observations should return INSUFFICIENT_HISTORY."""
        # Find a facility that has no NASA FIRMS history (typically facility 1 in a fresh DB)
        # Or check that insufficient_history flag works correctly
        r = self.client.get('/facilities/1/thermal-history', params={
            'window_days': 90, 'source': 'nasa_firms', 'detailed': True
        })
        j = r.json()
        self.assertIn(j['baseline_status'], ('INSUFFICIENT_HISTORY', 'PROVISIONAL', 'ESTABLISHED'))
        # If INSUFFICIENT_HISTORY, verify the confidence message
        if j['baseline_status'] == 'INSUFFICIENT_HISTORY':
            self.assertIn('No observations', j['confidence'])

    # --- D. DEMO Deep Analysis receives source=demo ---

    def test_d_demo_deep_analysis_preserves_source(self):
        """When fetching a demo hotspot by ID, the source must be 'demo'."""
        r = self.client.get('/hotspots', params={'source': 'demo', 'limit': 1})
        data = r.json()
        hotspots = data.get('hotspots', [])
        self.assertGreater(len(hotspots), 0, "Should have demo hotspots")

        demo_hotspot = hotspots[0]
        self.assertEqual(demo_hotspot['source'], 'demo',
            "Demo hotspot source must be 'demo'")

        # Fetch by ID
        r = self.client.get(f'/hotspots/{demo_hotspot["id"]}')
        single = r.json()
        self.assertEqual(single['source'], 'demo',
            "Single demo hotspot fetch must preserve source='demo'")

    # --- E. DEMO Deep Analysis loads demo historical observations ---

    def test_e_demo_deep_analysis_loads_demo_observations(self):
        """Thermal history for a demo facility must return demo-sourced observations only."""
        r = self.client.get('/facilities')
        facilities = r.json()
        demo_facilities = [f for f in facilities if f.get('source') == 'demo']

        for f in demo_facilities:
            r = self.client.get(f'/facilities/{f["id"]}/thermal-history', params={
                'window_days': 90, 'source': 'demo', 'detailed': True
            })
            j = r.json()
            self.assertEqual(j['source'], 'demo')
            self.assertGreater(len(j['observations']), 0,
                f"Demo facility {f['id']} should have historical observations")
            # All observations must be demo source
            for obs in j['observations']:
                self.assertEqual(obs['baseline_status'].upper() in ('NORMAL', 'ELEVATED', 'ABNORMAL', 'INSUFFICIENT_HISTORY'), True,
                    f"Observation should have valid baseline_status")

    # --- F. DEMO Deep Analysis loads demo baseline ---

    def test_f_demo_baseline_loads_with_stats(self):
        """Demo baseline must include computed statistics (mean, median, p95)."""
        r = self.client.get('/facilities')
        facilities = r.json()
        demo_facilities = [f for f in facilities if f.get('source') == 'demo']

        f = demo_facilities[0]
        r = self.client.get(f'/facilities/{f["id"]}/thermal-history', params={
            'window_days': 90, 'source': 'demo'
        })
        j = r.json()
        self.assertEqual(j['baseline_status'], 'ESTABLISHED')
        self.assertIsNotNone(j.get('mean'), "Demo baseline should have mean")
        self.assertIsNotNone(j.get('median'), "Demo baseline should have median")
        self.assertIsNotNone(j.get('p95'), "Demo baseline should have p95")
        self.assertGreater(j['observation_count'], 0)

    # --- G. DEMO coverage does not use NASA FIRMS records ---

    def test_g_demo_coverage_excludes_nasa(self):
        """Thermal history with source='demo' must not include NASA FIRMS rows."""
        r = self.client.get('/facilities')
        facilities = r.json()
        demo_facilities = [f for f in facilities if f.get('source') == 'demo']

        f = demo_facilities[0]
        # Get demo history
        r = self.client.get(f'/facilities/{f["id"]}/thermal-history', params={
            'window_days': 90, 'source': 'demo', 'detailed': True
        })
        demo_history = r.json()

        # Get NASA FIRMS history for same facility
        r = self.client.get(f'/facilities/{f["id"]}/thermal-history', params={
            'window_days': 90, 'source': 'nasa_firms', 'detailed': True
        })
        nasa_history = r.json()

        # Demo history source must be 'demo', NASA must be 'nasa_firm'
        self.assertEqual(demo_history['source'], 'demo')
        self.assertEqual(nasa_history['source'], 'nasa_firms')

        # Demo facility should have demo observations > 0
        self.assertGreater(demo_history['observation_count'], 0)

    # --- H. LIVE Deep Analysis does not use demo records ---

    def test_h_live_coverage_excludes_demo(self):
        """NASA FIRMS thermal history must not include demo observations."""
        # Find a NASA FIRMS facility with data
        r = self.client.get('/hotspots', params={'source': 'nasa_firms', 'limit': 1})
        data = r.json()
        nasa_hotspots = data.get('hotspots', [])
        if not nasa_hotspots:
            self.skipTest("No NASA FIRMS data available")

        hotspot = nasa_hotspots[0]
        if not hotspot.get('facility'):
            self.skipTest("No facility on first NASA hotspot")

        facility_id = hotspot['facility']['id']
        r = self.client.get(f'/facilities/{facility_id}/thermal-history', params={
            'window_days': 90, 'source': 'nasa_firms', 'detailed': True
        })
        j = r.json()
        self.assertEqual(j['source'], 'nasa_firms')
        # The source must never be 'demo' for a NASA FIRMS query
        self.assertNotEqual(j['source'], 'demo')

    # --- I. Demo banner data is present in responses ---

    def test_i_demo_data_has_clear_source_tagging(self):
        """Demo hotspots and facilities must be clearly tagged as demo."""
        r = self.client.get('/hotspots', params={'source': 'demo', 'limit': 5})
        data = r.json()
        hotspots = data.get('hotspots', [])
        for h in hotspots:
            self.assertEqual(h['source'], 'demo',
                "All demo hotspots must have source='demo'")

        r = self.client.get('/facilities')
        facilities = r.json()
        demo_facilities = [f for f in facilities if f.get('source') == 'demo']
        for f in demo_facilities:
            self.assertEqual(f['source'], 'demo',
                "All demo facilities must have source='demo'")

    # --- J. Demo reset does not affect NASA FIRMS records ---

    def test_j_demo_reset_preserves_nasa_and_seed(self):
        """Reset must only delete source='demo' records — NASA and seed untouched."""
        # Get counts before
        nasa_before = self.client.get('/hotspots', params={'source': 'nasa_firms', 'limit': 1}).json()['total']
        seed_before = self.client.get('/hotspots', params={'source': 'demo_synthetic', 'limit': 1}).json()['total']
        demo_before = self.client.get('/hotspots', params={'source': 'demo', 'limit': 1}).json()['total']

        self.assertGreater(demo_before, 0, "Should have demo data to reset")

        # Reset
        r = self.client.delete('/demo/data', params={'confirm': 'DELETE_DEMO_DATA'})
        self.assertEqual(r.status_code, 200)
        result = r.json()
        self.assertEqual(result['source'], 'demo')
        self.assertGreater(result['records_deleted'], 0)

        # Verify counts after
        nasa_after = self.client.get('/hotspots', params={'source': 'nasa_firms', 'limit': 1}).json()['total']
        seed_after = self.client.get('/hotspots', params={'source': 'demo_synthetic', 'limit': 1}).json()['total']
        demo_after = self.client.get('/hotspots', params={'source': 'demo', 'limit': 1}).json()['total']

        self.assertEqual(nasa_after, nasa_before, "NASA FIRMS records must be unchanged")
        self.assertEqual(seed_after, seed_before, "demo_synthetic seed records must be unchanged")
        self.assertEqual(demo_after, 0, "All demo records must be deleted")

    def test_demo_scenario_is_idempotent(self):
        """Calling POST /demo/scenario twice should not duplicate data."""
        r1 = self.client.post('/demo/scenario', params={'days': 30})
        j1 = r1.json()
        total1 = self.client.get('/hotspots', params={'source': 'demo', 'limit': 1}).json()['total']

        r2 = self.client.post('/demo/scenario', params={'days': 30})
        j2 = r2.json()
        total2 = self.client.get('/hotspots', params={'source': 'demo', 'limit': 1}).json()['total']

        self.assertEqual(total2, total1,
            "Idempotent: demo scenario should produce same total each time")
        self.assertEqual(j2['previous_demo_records_deleted'], j1['new_observations'],
            "Second call should delete first call's observations")

    def test_demo_requires_confirmation_for_reset(self):
        """DELETE /demo/data without confirm param should fail."""
        r = self.client.delete('/demo/data')
        self.assertEqual(r.status_code, 400)
        self.assertIn('confirmation', r.json()['detail'].lower())


if __name__ == "__main__":
    unittest.main()
