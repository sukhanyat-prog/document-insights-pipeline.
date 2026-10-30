"""Steps 2-5 end to end against an in-memory stand-in for BigQuery (no network)."""

import unittest
from unittest import mock

from pipeline import aggregate, compare, config, consolidate, normalize, orchestrator, store


class FakeBigQuery:
    """query() returns the rows of whichever table the SQL mentions; replace_scope() stores rows."""

    def __init__(self, tables):
        self.tables = {name: list(rows) for name, rows in tables.items()}

    def query(self, sql, **params):
        year = params.get("year")
        for name, rows in self.tables.items():
            if f".{name}`" in sql:
                rows = [r for r in rows if year is None or r.get("period_year") in (None, year)]
                if "GROUP BY raw_label" in sql:
                    counts = {}
                    for r in rows:
                        counts[r["raw_label"]] = counts.get(r["raw_label"], 0) + 1
                    return [{"raw_label": k, "n": v} for k, v in counts.items()]
                return rows
        return []

    def replace_scope(self, table, year, rows):
        self.tables[table] = [r for r in self.tables.get(table, []) if r.get("period_year") != year] + rows
        return len(rows)


def finding(doc, source, label, severity="high", conf=0.9):
    return {"doc_id": doc, "source": source, "period_year": 2026, "raw_label": label, "direction": "negative",
            "severity": severity, "confidence": conf, "evidence_text": "q", "page_ref": 1}


class FlowTests(unittest.TestCase):
    def setUp(self):
        self.bq = FakeBigQuery({
            config.T_FINDINGS: [
                finding("d1", "A", "cost pressure"), finding("d2", "B", "Cost Pressures"),
                finding("d3", "C", "margin squeeze"), finding("d4", "A", "new regulation", "medium"),
                finding("d5", "B", "weak signal", conf=0.3),
            ],
            config.T_REFERENCE: [
                {"period_year": 2026, "canonical_theme": "Cost Pressure", "reference_value": 30},
                {"period_year": 2026, "canonical_theme": "Cyber Attack", "reference_value": 80},
            ],
        })
        patches = [
            mock.patch.object(store, "query", side_effect=self.bq.query),
            mock.patch.object(store, "replace_scope", side_effect=self.bq.replace_scope),
        ]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)

    def test_consolidate_then_score_then_compare(self):
        groups = [
            {"canonical": "Cost Pressure", "members": ["cost pressure", "Cost Pressures", "margin squeeze"]},
            {"canonical": "Regulation", "members": ["new regulation"]},
        ]
        summary = consolidate.consolidate_year(2026, model=lambda labels, preferred: groups)
        self.assertEqual(summary["labels"], 5)
        themes = {t["raw_label"]: t["canonical_theme"] for t in self.bq.tables[config.T_THEMES]}
        self.assertEqual(themes["margin squeeze"], "Cost Pressure")
        self.assertIn("weak signal", themes)  # skipped by the model, still mapped

        out = normalize.normalize_year(2026)
        self.assertEqual(out["signals"], 5)
        self.assertLess(out["counted"], out["signals"])  # the 0.3-confidence finding is below the floor

        self.assertEqual(aggregate.aggregate_year(2026)["themes_scored"], 2)
        scores = {s["canonical_theme"]: s for s in self.bq.tables[config.T_SCORES]}
        self.assertEqual(scores["Cost Pressure"]["sources_citing"], "3 of 3")
        self.assertEqual(scores["Cost Pressure"]["mention_count"], 3)

        compare.compare_year(2026)
        status = {c["canonical_theme"]: c["status"] for c in self.bq.tables[config.T_COMPARISON]}
        self.assertEqual(status["Cost Pressure"], "external_higher")
        self.assertEqual(status["Regulation"], "not_in_reference")
        self.assertEqual(status["Cyber Attack"], "not_in_external")  # blind spot

    def test_model_failure_falls_back_and_still_finishes(self):
        def broken(labels, preferred):
            raise RuntimeError("model down")

        summary = consolidate.consolidate_year(2026, model=broken)
        self.assertGreater(summary["themes"], 0)

    def test_empty_year_is_harmless(self):
        self.bq.tables[config.T_FINDINGS] = []
        self.assertEqual(consolidate.consolidate_year(2026)["themes"], 0)

    def test_run_after_steps_calls_all_steps(self):
        with mock.patch.object(orchestrator, "consolidate_year", return_value={}) as c, \
             mock.patch.object(orchestrator, "normalize_year", return_value={}) as n, \
             mock.patch.object(orchestrator, "aggregate_year", return_value={}) as a, \
             mock.patch.object(orchestrator, "compare_year", return_value={}) as p:
            orchestrator.run_after_steps(2026)
        for step in (c, n, a, p):
            step.assert_called_once_with(2026)


if __name__ == "__main__":
    unittest.main()
