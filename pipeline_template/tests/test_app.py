"""Offline tests for the Flask app, the extraction step (fake Gemini) and the orchestrator (fake store)."""

import os
import unittest
from types import SimpleNamespace
from unittest import mock

os.environ.setdefault("SECRET_KEY", "test-secret")

import app as app_module  # noqa: E402
from pipeline import extract, orchestrator  # noqa: E402

FAKE_DASHBOARD = {
    "year": 2026, "app_title": "T",
    "kpis": {"documents": 1, "sources": 1, "themes": 1, "high_band": 1, "blind_spots": 0},
    "scores": [], "comparison": [], "status_counts": {}, "documents": [],
}


class WebTests(unittest.TestCase):
    def setUp(self):
        self.client = app_module.create_app().test_client()

    def test_health(self):
        r = self.client.get("/health")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["status"], "ok")

    def test_dashboard_page_and_api(self):
        with mock.patch("pipeline.dashboard.available_years", return_value=[2026, 2025]), \
             mock.patch("pipeline.dashboard.fetch_dashboard", return_value=FAKE_DASHBOARD):
            page = self.client.get("/")
            self.assertEqual(page.status_code, 200)
            self.assertIn(b"api/dashboard", page.data)
            self.assertIn(b"app.css", page.data)
            api = self.client.get("/api/dashboard?year=2026")
            self.assertEqual(api.get_json()["kpis"]["documents"], 1)

    def test_upload_page_renders_csrf_form(self):
        r = self.client.get("/upload")
        self.assertEqual(r.status_code, 200)
        self.assertIn(b'name="csrf_token"', r.data)

    def test_upload_post_without_csrf_is_rejected(self):
        self.assertEqual(self.client.post("/upload", data={"source": "x"}).status_code, 400)

    def test_event_endpoint(self):
        # machine endpoint: no CSRF token needed
        r = self.client.post("/event", json={"bucket": "b", "name": "2026/_locks/x"})
        self.assertEqual(r.get_json()["status"], "ignored")
        self.assertEqual(self.client.post("/event", data="not json").status_code, 400)
        self.assertEqual(self.client.post("/event", json={"nothing": 1}).status_code, 400)
        with mock.patch("pipeline.web.run_event", side_effect=RuntimeError("boom")):
            self.assertEqual(self.client.post("/event", json={"bucket": "b", "name": "a.pdf"}).status_code, 500)

    def test_production_requires_secret_key(self):
        with mock.patch.dict(os.environ, {"APP_ENV": "production", "SECRET_KEY": ""}):
            with self.assertRaises(RuntimeError):
                app_module.create_app()


class ExtractTests(unittest.TestCase):
    def test_extract_document_validates_model_output(self):
        answer = ('{"title": "T", "findings": [{"theme_hint": "Cost pressure", "direction": "negative", '
                  '"severity": "high", "evidence_text": "costs are rising", "confidence": 0.8}]}')
        fake_client = SimpleNamespace(models=SimpleNamespace(generate_content=lambda **kw: SimpleNamespace(text=answer)))
        with mock.patch.object(extract, "genai_client", return_value=fake_client):
            result = extract.extract_document(b"%PDF-1.4", source="Acme", year=2026)
        self.assertEqual(result.findings[0].theme_hint, "Cost pressure")

    def test_empty_model_answer_is_an_error(self):
        fake_client = SimpleNamespace(models=SimpleNamespace(generate_content=lambda **kw: SimpleNamespace(text="")))
        with mock.patch.object(extract, "genai_client", return_value=fake_client):
            with self.assertRaises(ValueError):
                extract.extract_document(b"x", source="s", year=2026)


class OrchestratorTests(unittest.TestCase):
    def test_process_document_writes_rows_and_is_idempotent(self):
        extraction = SimpleNamespace(
            title="T", summary="S", document_date="2026-03-01",
            findings=[SimpleNamespace(theme_hint=" Cost ", direction="negative", severity="high",
                                      evidence_text="q", page_ref=1, confidence=0.9),
                      SimpleNamespace(theme_hint=" ", direction="neutral", severity="low",
                                      evidence_text="blank label", page_ref=None, confidence=0.9)],
        )
        meta = SimpleNamespace(year=2026, source="Acme", filename="n.pdf")
        loaded, deleted = {}, []
        with mock.patch.object(orchestrator, "read_object", return_value=(extraction, meta)), \
             mock.patch.object(orchestrator.store, "log_status"), \
             mock.patch.object(orchestrator.store, "delete_where", side_effect=lambda t, w, **p: deleted.append(t)), \
             mock.patch.object(orchestrator.store, "load_rows", side_effect=lambda t, rows: loaded.__setitem__(t, rows)):
            out = orchestrator.process_document("b", "2026/Acme/n.pdf")
        self.assertEqual(out["findings"], 2)
        self.assertEqual(len(deleted), 2)  # old document + findings removed first
        findings_rows = loaded[orchestrator.config.T_FINDINGS]
        self.assertEqual([r["raw_label"] for r in findings_rows], ["Cost"])  # blank labels dropped

    def test_handle_event_runs_refresh_for_the_document_year(self):
        with mock.patch.object(orchestrator, "process_document", return_value={"year": 2025}), \
             mock.patch.object(orchestrator, "run_after_steps", return_value={"ok": 1}) as after, \
             mock.patch.object(orchestrator.config, "AUTO_REFRESH", True):
            out = orchestrator.handle_event({"bucket": "b", "name": "2025/A/x.pdf"})
        after.assert_called_once_with(2025)
        self.assertEqual(out["status"], "ok")


if __name__ == "__main__":
    unittest.main()
