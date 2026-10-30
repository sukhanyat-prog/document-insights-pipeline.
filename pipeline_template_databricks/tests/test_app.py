"""Offline tests for the Flask app, extraction (fake model), PDF text and the orchestrator (fake store)."""

import os
import unittest
from types import SimpleNamespace
from unittest import mock

os.environ.setdefault("SECRET_KEY", "test-secret")

import app as app_module  # noqa: E402
from pipeline import extract, orchestrator  # noqa: E402
from pipeline.jsonutil import parse_json_text  # noqa: E402
from pipeline.pdf_text import NoTextError, pdf_to_text  # noqa: E402

from helpers import make_pdf  # noqa: E402

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
            api = self.client.get("/api/dashboard?year=2026")
            self.assertEqual(api.get_json()["kpis"]["documents"], 1)

    def test_upload_page_has_csrf_forms(self):
        with mock.patch("pipeline.web.storage.location_label", return_value="/loc"):
            r = self.client.get("/upload")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data.count(b'name="csrf_token"'), 2)  # upload form + process-new form

    def test_browser_posts_need_csrf(self):
        self.assertEqual(self.client.post("/upload", data={"source": "x"}).status_code, 400)
        self.assertEqual(self.client.post("/process-new").status_code, 400)

    def test_machine_endpoints_skip_csrf(self):
        r = self.client.post("/event", json={"name": "2026/_locks/x.txt"})
        self.assertEqual(r.get_json()["status"], "ignored")
        self.assertEqual(self.client.post("/event", data="not json").status_code, 400)
        self.assertEqual(self.client.post("/event", json={"nothing": 1}).status_code, 400)
        with mock.patch("pipeline.web.run_event", side_effect=RuntimeError("boom")):
            self.assertEqual(self.client.post("/event", json={"name": "a.pdf"}).status_code, 500)
        with mock.patch("pipeline.web.parse_new_files", return_value={"parsed": 2}) as run_new:
            r = self.client.post("/run-new?year=2025")
            self.assertEqual(r.get_json(), {"parsed": 2})
            run_new.assert_called_once_with(2025)

    def test_upload_stores_a_sanitised_name(self):
        from io import BytesIO

        client = app_module.create_app().test_client()
        with mock.patch("pipeline.web.storage.write_object", return_value="/loc/x") as write, \
             mock.patch("flask_wtf.csrf.validate_csrf", return_value=None):
            r = client.post(
                "/upload",
                data={"source": "Big Co", "year": "2025", "csrf_token": "t",
                      "file": (BytesIO(b"%PDF-1.4"), "../my note.pdf")},
                content_type="multipart/form-data",
            )
        self.assertEqual(r.status_code, 302)
        name = write.call_args.args[0]
        self.assertEqual(name, "2025/Big_Co/my_note.pdf")

    def test_production_requires_secret_key(self):
        with mock.patch.dict(os.environ, {"APP_ENV": "production", "SECRET_KEY": ""}):
            with self.assertRaises(RuntimeError):
                app_module.create_app()


class JsonAndPdfTests(unittest.TestCase):
    def test_json_with_fences_and_chatter(self):
        self.assertEqual(parse_json_text('```json\n{"a": 1}\n```'), {"a": 1})
        self.assertEqual(parse_json_text('Sure! Here it is: {"a": {"b": 2}} Hope that helps.'), {"a": {"b": 2}})
        for bad in ("", "no json here", "[1, 2]"):
            with self.assertRaises(ValueError):
                parse_json_text(bad)

    def test_pdf_text_has_page_markers_and_respects_limit(self):
        pdf = make_pdf(["Alpha beta gamma", "Delta epsilon"])
        text = pdf_to_text(pdf)
        self.assertIn("[page 1]", text)
        self.assertIn("Alpha beta gamma", text)
        self.assertIn("[page 2]", text)
        self.assertLessEqual(len(pdf_to_text(pdf, max_chars=20)), 20)

    def test_pdf_without_text_is_a_clear_error(self):
        with self.assertRaises(NoTextError):
            pdf_to_text(make_pdf([""]))


class ExtractTests(unittest.TestCase):
    ANSWER = ('{"title": "T", "findings": [{"theme_hint": "Cost pressure", "direction": "Negative", '
              '"severity": "HIGH", "evidence_text": "costs are rising", "page_ref": "n/a", "confidence": "0.8"}]}')

    def test_extract_document_cleans_model_output(self):
        with mock.patch.object(extract.llm, "complete", return_value=self.ANSWER) as complete:
            result = extract.extract_document("[page 1]\ncosts are rising", source="Acme", year=2026)
        finding = result.findings[0]
        self.assertEqual((finding.direction, finding.severity, finding.page_ref, finding.confidence),
                         ("negative", "high", None, 0.8))
        self.assertIn("costs are rising", complete.call_args.args[0])
        self.assertIn("Acme", complete.call_args.args[0])

    def test_read_object_uses_path_for_source_and_year(self):
        pdf = make_pdf(["Costs are rising"])
        with mock.patch.object(extract.storage, "read_object_bytes", return_value=pdf), \
             mock.patch.object(extract.llm, "complete", return_value=self.ANSWER):
            _, meta = extract.read_object("2025/Acme_Research/n.pdf")
        self.assertEqual((meta.year, meta.source), (2025, "Acme Research"))
        with self.assertRaises(ValueError):
            extract.read_object("2025/Acme/readme.txt")

    def test_empty_model_answer_is_an_error(self):
        with mock.patch.object(extract.llm, "complete", return_value=""):
            with self.assertRaises(ValueError):
                extract.extract_document("text", source="s", year=2026)


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
            out = orchestrator.process_document("2026/Acme/n.pdf")
        self.assertEqual(out["findings"], 2)
        self.assertEqual(len(deleted), 2)  # old document + findings removed first
        self.assertEqual([r["raw_label"] for r in loaded[orchestrator.config.T_FINDINGS]], ["Cost"])
        self.assertEqual(loaded[orchestrator.config.T_DOCUMENTS][0]["object_path"], "2026/Acme/n.pdf")

    def test_handle_event_runs_refresh_for_the_document_year(self):
        with mock.patch.object(orchestrator, "process_document", return_value={"year": 2025}), \
             mock.patch.object(orchestrator, "run_after_steps", return_value={"ok": 1}) as after, \
             mock.patch.object(orchestrator.config, "AUTO_REFRESH", True):
            out = orchestrator.handle_event({"name": "2025/A/x.pdf"})
        after.assert_called_once_with(2025)
        self.assertEqual(out["status"], "ok")

    def test_parse_new_files_skips_known_documents_and_survives_failures(self):
        names = ["2026/A/one.pdf", "2026/A/two.pdf", "2025/B/three.pdf"]
        known = [{"doc_id": orchestrator.build_doc_id("2026/A/one.pdf")}]

        def fake_process(name):
            if "three" in name:
                raise RuntimeError("bad pdf")
            return {"year": 2026}

        with mock.patch.object(orchestrator.storage, "list_pdfs", return_value=names), \
             mock.patch.object(orchestrator.store, "query", return_value=known), \
             mock.patch.object(orchestrator, "process_document", side_effect=fake_process), \
             mock.patch.object(orchestrator, "run_after_steps", return_value={}) as after, \
             mock.patch.object(orchestrator.config, "AUTO_REFRESH", True):
            out = orchestrator.parse_new_files()
        self.assertEqual((out["found"], out["new"], out["parsed"]), (3, 2, 1))
        self.assertEqual(out["failed"][0]["object_name"], "2025/B/three.pdf")
        after.assert_called_once_with(2026)  # only the year that changed


if __name__ == "__main__":
    unittest.main()
