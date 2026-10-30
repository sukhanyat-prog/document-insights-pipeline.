"""Databricks-specific helpers: SQL generation, row cleaning, storage listing. No workspace needed."""

import json
import unittest
from decimal import Decimal
from types import SimpleNamespace
from unittest import mock

from pipeline import config, storage, store
from pipeline.schemas import TABLES


class StoreSqlTests(unittest.TestCase):
    def test_table_id_is_three_part(self):
        self.assertEqual(store.table_id("t"), f"{config.DBX_CATALOG}.{config.DBX_SCHEMA}.t")

    def test_ddl_covers_every_column_with_delta(self):
        ddl = store.ddl_for(config.T_SCORES)
        self.assertIn("USING DELTA", ddl)
        for column, _ in TABLES[config.T_SCORES]:
            self.assertIn(column, ddl)
        self.assertIn("score DOUBLE", ddl)
        self.assertIn("period_year BIGINT", ddl)

    def test_insert_sql_casts_every_column(self):
        sql = store.insert_sql(config.T_SIGNALS)
        self.assertIn(":payload", sql)
        self.assertIn("from_json", sql)
        self.assertIn("CAST(r.counted AS BOOLEAN)", sql)
        self.assertIn("CAST(r.created_at AS TIMESTAMP)", sql)

    def test_rows_payload_is_text_and_ignores_extra_keys(self):
        rows = [{"doc_id": "d", "counted": True, "confidence": 0.5, "page_ref": None, "junk": 1}]
        payload = json.loads(store.rows_payload(config.T_SIGNALS, rows))
        self.assertEqual(payload[0]["counted"], "true")
        self.assertEqual(payload[0]["confidence"], "0.5")
        self.assertIsNone(payload[0]["page_ref"])
        self.assertNotIn("junk", payload[0])
        self.assertEqual(set(payload[0]), {c for c, _ in TABLES[config.T_SIGNALS]})

    def test_decimal_becomes_plain_number(self):
        row = store.clean_row({"a": Decimal("3"), "b": Decimal("2.5"), "c": "x"})
        self.assertEqual(row, {"a": 3, "b": 2.5, "c": "x"})
        self.assertIsInstance(row["a"], int)

    def test_load_rows_chunks_and_replace_scope_deletes_first(self):
        calls = []
        with mock.patch.object(store, "run_sql", side_effect=lambda sql, params=None, fetch=True: calls.append((sql, params)) or []):
            n = store.replace_scope(config.T_SCORES, 2026, [{"canonical_theme": f"t{i}"} for i in range(1200)])
        self.assertEqual(n, 1200)
        self.assertTrue(calls[0][0].startswith("DELETE FROM"))
        self.assertEqual(calls[0][1], {"year": 2026})
        self.assertEqual(len(calls), 1 + 3)  # delete + 500 + 500 + 200


class StorageTests(unittest.TestCase):
    def test_volume_path(self):
        self.assertEqual(storage.volume_path("2026/A/n.pdf"), f"{config.VOLUME_ROOT}/2026/A/n.pdf")

    def test_list_pdfs_walks_folders_and_returns_relative_names(self):
        root = config.VOLUME_ROOT
        tree = {
            root: [SimpleNamespace(path=f"{root}/2026", is_directory=True),
                   SimpleNamespace(path=f"{root}/notes.txt", is_directory=False)],
            f"{root}/2026": [SimpleNamespace(path=f"{root}/2026/A", is_directory=True)],
            f"{root}/2026/A": [SimpleNamespace(path=f"{root}/2026/A/b.PDF", is_directory=False),
                               SimpleNamespace(path=f"{root}/2026/A/c.csv", is_directory=False)],
        }
        client = SimpleNamespace(files=SimpleNamespace(list_directory_contents=lambda d: tree[d]))
        with mock.patch.object(storage, "workspace_client", return_value=client):
            self.assertEqual(storage.list_pdfs(), ["2026/A/b.PDF"])


if __name__ == "__main__":
    unittest.main()
