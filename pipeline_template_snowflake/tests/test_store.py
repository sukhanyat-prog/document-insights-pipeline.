"""Snowflake-specific helpers: parameter conversion, SQL generation, row cleaning, stage listing. No account needed."""

import json
import unittest
from decimal import Decimal
from unittest import mock

from pipeline import config, storage, store
from pipeline.schemas import TABLES


class StoreSqlTests(unittest.TestCase):
    def test_named_parameters_become_qmarks_in_order(self):
        sql, values = store.to_qmark("SELECT 1 WHERE a = :year AND b = :doc AND c = :year", {"year": 2026, "doc": "d"})
        self.assertEqual(sql, "SELECT 1 WHERE a = ? AND b = ? AND c = ?")
        self.assertEqual(values, [2026, "d", 2026])

    def test_casts_and_json_paths_are_left_alone(self):
        sql, values = store.to_qmark("SELECT v:x::VARCHAR FROM t WHERE a = :a", {"a": 1})
        self.assertEqual(sql, "SELECT v:x::VARCHAR FROM t WHERE a = ?")
        self.assertEqual(values, [1])

    def test_missing_parameter_is_an_error(self):
        with self.assertRaises(KeyError):
            store.to_qmark("SELECT :nope", {})

    def test_table_id_is_three_part(self):
        self.assertEqual(store.table_id("t"), f"{config.SNOWFLAKE_DATABASE}.{config.SNOWFLAKE_SCHEMA}.t")

    def test_ddl_covers_every_column(self):
        ddl = store.ddl_for(config.T_SCORES)
        for column, _ in TABLES[config.T_SCORES]:
            self.assertIn(column, ddl)
        self.assertIn("score FLOAT", ddl)
        self.assertIn("period_year NUMBER(38,0)", ddl)
        self.assertIn("computed_at TIMESTAMP_NTZ", ddl)

    def test_insert_sql_casts_every_column(self):
        sql = store.insert_sql(config.T_SIGNALS)
        self.assertIn("PARSE_JSON(?)", sql)
        self.assertIn("f.value:counted::BOOLEAN", sql)
        self.assertIn("f.value:created_at::TIMESTAMP_NTZ", sql)

    def test_rows_payload_is_text_and_ignores_extra_keys(self):
        rows = [{"doc_id": "d", "counted": False, "confidence": 0.5, "page_ref": None, "junk": 1}]
        payload = json.loads(store.rows_payload(config.T_SIGNALS, rows))
        self.assertEqual(payload[0]["counted"], "false")
        self.assertIsNone(payload[0]["page_ref"])
        self.assertNotIn("junk", payload[0])

    def test_timestamp_has_no_offset(self):
        self.assertNotIn("+", store.now_iso())

    def test_rows_get_lowercase_keys_and_plain_numbers(self):
        row = store.clean_row({"DOC_ID": "d", "N": Decimal("3"), "SCORE": 12.5})
        self.assertEqual(row, {"doc_id": "d", "n": 3, "score": 12.5})
        self.assertIsInstance(row["n"], int)

    def test_query_converts_parameters_before_running(self):
        with mock.patch.object(store, "run_sql", return_value=[{"X": 1}]) as run:
            out = store.query("SELECT x FROM t WHERE y = :y", y=5)
        run.assert_called_once_with("SELECT x FROM t WHERE y = ?", [5])
        self.assertEqual(out, [{"x": 1}])

    def test_load_rows_chunks_and_replace_scope_deletes_first(self):
        calls = []
        with mock.patch.object(store, "run_sql", side_effect=lambda sql, params=None: calls.append((sql, params)) or []):
            n = store.replace_scope(config.T_SCORES, 2026, [{"canonical_theme": f"t{i}"} for i in range(1200)])
        self.assertEqual(n, 1200)
        self.assertTrue(calls[0][0].startswith("DELETE FROM"))
        self.assertEqual(calls[0][1], [2026])
        self.assertEqual(len(calls), 1 + 3)


class StorageTests(unittest.TestCase):
    def test_stage_path(self):
        self.assertEqual(storage.stage_path("2026/A/n.pdf"), f"@{config.STAGE_FQN}/2026/A/n.pdf")
        self.assertEqual(storage.stage_path(), f"@{config.STAGE_FQN}")

    def test_list_pdfs_strips_the_stage_name(self):
        rows = [{"name": "documents/2026/A/b.pdf"}, {"name": "documents/2026/A/c.csv"}, {"name": "documents/2025/B/a.PDF"}]
        with mock.patch.object(storage, "run_sql", return_value=rows) as run:
            self.assertEqual(storage.list_pdfs("2026"), ["2025/B/a.PDF", "2026/A/b.pdf"])
        self.assertIn(f"LIST @{config.STAGE_FQN}/2026/", run.call_args.args[0])


if __name__ == "__main__":
    unittest.main()
