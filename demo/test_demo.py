"""Checks that the demo seeds, scores and serves the dashboard. Run: python -m unittest discover -s demo"""

import os
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
os.environ.setdefault("SECRET_KEY", "test-secret")

from run_demo import create_demo_app  # noqa: E402


class DemoTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = create_demo_app()
        cls.client = cls.app.test_client()

    def test_dashboard_page_and_api(self):
        self.assertEqual(self.client.get("/").status_code, 200)
        data = self.client.get("/api/dashboard?year=2026").get_json()
        self.assertEqual(data["kpis"]["sources"], 6)
        self.assertGreaterEqual(data["kpis"]["themes"], 6)
        scores = [s["score"] for s in data["scores"]]
        self.assertEqual(scores, sorted(scores, reverse=True))

    def test_all_comparison_statuses_appear(self):
        data = self.client.get("/api/dashboard?year=2026").get_json()
        statuses = {c["status"] for c in data["comparison"]}
        self.assertIn("not_in_external", statuses)          # Supply Chain Disruption: a blind spot
        self.assertTrue(statuses & {"aligned", "external_higher", "external_lower"})

    def test_both_years_are_available(self):
        self.assertEqual(self.client.get("/api/dashboard?year=2025").get_json()["year"], 2025)
        self.assertIn(b"2025", self.client.get("/").data)

    def test_low_confidence_findings_do_not_score(self):
        signals = self.app.demo_store.tables["tpl_signals"]
        self.assertTrue(any(not s["counted"] for s in signals))
        self.assertTrue(any(s["counted"] for s in signals))

    def test_upload_is_disabled(self):
        self.assertEqual(self.client.get("/upload").status_code, 403)


if __name__ == "__main__":
    unittest.main()
