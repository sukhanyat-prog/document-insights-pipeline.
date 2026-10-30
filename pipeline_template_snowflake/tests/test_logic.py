"""Offline tests for the pure logic: paths, consolidation, normalisation, scoring, comparison."""

import unittest

from pipeline import config
from pipeline.compare import compare_scores
from pipeline.consolidate import build_mapping, fallback_groups, normalize_label, snap_to_preferred
from pipeline.normalize import build_signals
from pipeline.paths import build_doc_id, build_object_path, extract_object_name, parse_object_path
from pipeline.scoring import band_for, score_themes, score_value


class PathTests(unittest.TestCase):
    def test_year_source_file(self):
        meta = parse_object_path("2026/Acme_Research/note one.pdf")
        self.assertEqual((meta.year, meta.source, meta.filename), (2026, "Acme Research", "note one.pdf"))

    def test_no_year_uses_default(self):
        meta = parse_object_path("Acme/note.pdf")
        self.assertEqual(meta.year, config.DEFAULT_YEAR)
        self.assertEqual(meta.source, "Acme")

    def test_build_object_path_round_trip(self):
        name = build_object_path(2025, "Big Co & Sons", "../evil name.pdf")
        self.assertTrue(name.startswith("2025/Big_Co__Sons/"))
        self.assertNotIn("..", name)
        self.assertNotIn(" ", name)
        self.assertEqual(parse_object_path(name).year, 2025)

    def test_doc_id_is_stable_and_safe(self):
        self.assertEqual(build_doc_id("2026/A b/c.pdf"), "2026_A_b_c_pdf")

    def test_event_payload_shapes(self):
        self.assertEqual(extract_object_name({"name": "2026/A/n.pdf"}), "2026/A/n.pdf")
        self.assertEqual(extract_object_name({"data": {"object_name": "2026/A/n.pdf"}}), "2026/A/n.pdf")
        self.assertEqual(extract_object_name({"path": config.LOCATION_PREFIX + "/2026/A/n.pdf"}), "2026/A/n.pdf")
        with self.assertRaises(ValueError):
            extract_object_name({"nothing": 1})
        with self.assertRaises(ValueError):
            extract_object_name({})


class ConsolidationTests(unittest.TestCase):
    def test_every_label_mapped_once_and_cap_enforced(self):
        labels = {f"theme {i}": 10 - i for i in range(8)}
        groups = [{"canonical": f"Group {i}", "members": [f"theme {i}"]} for i in range(8)]
        mapping = build_mapping(labels, groups, [], max_themes=3)
        self.assertEqual(set(mapping), set(labels))
        self.assertLessEqual(len({c for c, _, _ in mapping.values()}), 3)
        self.assertTrue(any(m == "cap_merge" for _, _, m in mapping.values()))

    def test_skipped_label_is_fuzzy_matched_or_kept(self):
        labels = {"supply chain delays": 5, "regulatory change": 3, "supply chain delay": 1}
        groups = [{"canonical": "Supply chain delays", "members": ["supply chain delays"]}]
        mapping = build_mapping(labels, groups, [], max_themes=10)
        self.assertEqual(mapping["supply chain delay"][0], "Supply chain delays")
        self.assertEqual(mapping["supply chain delay"][2], "fuzzy")
        self.assertIn("regulatory change", mapping)

    def test_unknown_members_in_answer_are_ignored(self):
        mapping = build_mapping({"a": 1}, [{"canonical": "X", "members": ["a", "ghost"]}], [], 5)
        self.assertEqual(set(mapping), {"a"})

    def test_preferred_names_win(self):
        name, snapped = snap_to_preferred("Regulation & Policy", ["Regulation and Policy"])
        self.assertTrue(snapped)
        self.assertEqual(name, "Regulation and Policy")
        mapping = build_mapping({"rules": 2}, [{"canonical": "Regulation & Policy", "members": ["rules"]}],
                                ["Regulation and Policy"], 5)
        self.assertEqual(mapping["rules"][0], "Regulation and Policy")

    def test_fallback_groups_by_spelling(self):
        groups = fallback_groups({"Cost Pressure": 3, "cost pressure!": 1, "Other": 1})
        self.assertEqual(len(groups), 2)
        self.assertEqual(normalize_label("Cost-Pressure!"), "cost pressure")


class NormalizeAndScoreTests(unittest.TestCase):
    def _findings(self):
        return [
            {"doc_id": "d1", "source": "A", "period_year": 2026, "raw_label": "x", "direction": "negative",
             "severity": "high", "confidence": 0.9, "evidence_text": "q1", "page_ref": 1},
            {"doc_id": "d2", "source": "B", "period_year": 2026, "raw_label": "x", "direction": "negative",
             "severity": "medium", "confidence": 0.8, "evidence_text": "q2", "page_ref": 2},
            {"doc_id": "d3", "source": "C", "period_year": 2026, "raw_label": "y", "direction": "neutral",
             "severity": "low", "confidence": 0.9, "evidence_text": "q3", "page_ref": None},
            {"doc_id": "d4", "source": "C", "period_year": 2026, "raw_label": "unmapped", "confidence": 0.9},
        ]

    def test_confidence_floor_and_unmapped_skipped(self):
        signals = build_signals(self._findings(), {"x": ("Theme X", 1.0), "y": ("Theme Y", 0.5)}, floor=0.55)
        self.assertEqual(len(signals), 3)  # the unmapped finding is dropped
        by_theme = {s["canonical_theme"]: s for s in signals if s["doc_id"] in {"d1", "d3"}}
        self.assertTrue(by_theme["Theme X"]["counted"])
        self.assertFalse(by_theme["Theme Y"]["counted"])  # 0.9 x 0.5 = 0.45 < 0.55

    def test_scores(self):
        signals = build_signals(self._findings(), {"x": ("Theme X", 1.0), "y": ("Theme Y", 1.0)}, floor=0.55)
        rows = score_themes(signals, 2026, sources_total=3)
        top = rows[0]
        self.assertEqual(top["canonical_theme"], "Theme X")
        self.assertEqual(top["sources_citing"], "2 of 3")
        self.assertEqual(top["mention_count"], 2)
        coverage, intensity = 2 / 3, ((3 + 2) / 2) / 3
        self.assertAlmostEqual(top["score"], score_value(coverage, intensity), places=1)
        self.assertEqual(top["band"], band_for(top["score"]))

    def test_bands(self):
        self.assertEqual(band_for(config.BAND_HIGH_MIN), "High")
        self.assertEqual(band_for(config.BAND_MEDIUM_MIN), "Medium")
        self.assertEqual(band_for(config.BAND_MEDIUM_MIN - 1), "Low")
        self.assertIsNone(band_for(None))

    def test_uncounted_signals_do_not_score(self):
        signals = [{"counted": False, "canonical_theme": "T", "source": "A", "severity_weight": 3,
                    "direction": "negative", "confidence": 0.1}]
        self.assertEqual(score_themes(signals, 2026), [])


class CompareTests(unittest.TestCase):
    def test_statuses(self):
        scores = [
            {"canonical_theme": "Theme A", "score": 80.0, "band": "High"},
            {"canonical_theme": "Theme B", "score": 20.0, "band": "Low"},
            {"canonical_theme": "Theme C", "score": 50.0, "band": "Medium"},
            {"canonical_theme": "Brand New", "score": 60.0, "band": "Medium"},
        ]
        reference = [
            {"canonical_theme": "theme a", "reference_value": 75},   # same band, fuzzy-equal name
            {"canonical_theme": "Theme B", "reference_value": 50},   # reference higher
            {"canonical_theme": "Theme C", "reference_value": 10},   # external higher
            {"canonical_theme": "Only Internal", "reference_value": 90},
        ]
        rows = {r["canonical_theme"]: r for r in compare_scores(scores, reference, 2026)}
        self.assertEqual(rows["Theme A"]["status"], "aligned")
        self.assertEqual(rows["Theme B"]["status"], "external_lower")
        self.assertEqual(rows["Theme C"]["status"], "external_higher")
        self.assertEqual(rows["Brand New"]["status"], "not_in_reference")
        self.assertEqual(rows["Only Internal"]["status"], "not_in_external")
        self.assertEqual(rows["Theme A"]["gap"], 5.0)


if __name__ == "__main__":
    unittest.main()
