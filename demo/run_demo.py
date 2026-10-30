"""
Demo: the template's real pipeline steps and Flask dashboard, running on fictional data.

No cloud account, no model calls, no keys. Only the storage layer is replaced by an in-memory stand-in;
consolidation, normalisation, scoring and comparison are the same code the deployed pipeline runs.

    pip install -r pipeline_template/requirements.txt
    python demo/run_demo.py            # http://localhost:8080/
"""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
TEMPLATE = HERE.parent / "pipeline_template"
sys.path.insert(0, str(TEMPLATE))
sys.path.insert(0, str(HERE))

os.environ.setdefault("APP_TITLE", "Document Insights Pipeline - demo (fictional data)")
os.environ.setdefault("DEFAULT_YEAR", "2026")
os.environ.setdefault("SOURCES_TOTAL", "6")
os.environ.pop("URL_PATH_PREFIX", None)

import sample_data  # noqa: E402
from pipeline import aggregate, compare, config, consolidate, normalize, store  # noqa: E402

logger = logging.getLogger("demo")


class MemoryStore:
    """Answers the handful of queries the pipeline and dashboard run, from Python lists."""

    def __init__(self) -> None:
        self.tables: dict[str, list[dict]] = {}

    def replace_scope(self, table: str, year: int, rows: list[dict]) -> int:
        kept = [r for r in self.tables.get(table, []) if r.get("period_year") != year]
        self.tables[table] = kept + [dict(r) for r in rows]
        return len(rows)

    def query(self, sql: str, **params):
        year = params.get("year")
        for name, rows in self.tables.items():
            if f".{name}`" not in sql:
                continue
            if "SELECT DISTINCT period_year" in sql:
                return [{"period_year": y} for y in sorted({r["period_year"] for r in rows}, reverse=True)]
            rows = [r for r in rows if year is None or r.get("period_year") in (None, year)]
            if "GROUP BY raw_label" in sql:
                counts: dict[str, int] = {}
                for r in rows:
                    counts[r["raw_label"]] = counts.get(r["raw_label"], 0) + 1
                return [{"raw_label": k, "n": v} for k, v in counts.items()]
            if name == config.T_SCORES:
                rows = sorted(rows, key=lambda r: -r["score"])
            elif name == config.T_COMPARISON:
                rows = sorted(rows, key=lambda r: -(r["score"] if r.get("score") is not None else -1))
            elif name == config.T_DOCUMENTS:
                rows = sorted(rows, key=lambda r: r["parsed_at"], reverse=True)
            return [dict(r) for r in rows]
        return []


def seed(memory: MemoryStore) -> None:
    """Load the fictional documents and findings, then run steps 2-5 for each year."""
    for year in sample_data.YEARS:
        documents, findings = sample_data.build(year)
        memory.replace_scope(config.T_DOCUMENTS, year, documents)
        memory.replace_scope(config.T_FINDINGS, year, findings)
        memory.replace_scope(config.T_REFERENCE, year, sample_data.reference_rows(year))
        logger.info("%s: %d documents, %d findings", year, len(documents), len(findings))

        logger.info("2 consolidate %s", consolidate.consolidate_year(year, model=sample_data.label_groups))
        logger.info("3 normalize   %s", normalize.normalize_year(year))
        logger.info("4 aggregate   %s", aggregate.aggregate_year(year))
        logger.info("5 compare     %s", compare.compare_year(year))


def create_demo_app():
    memory = MemoryStore()
    patches = [
        mock.patch.object(store, "query", side_effect=memory.query),
        mock.patch.object(store, "replace_scope", side_effect=memory.replace_scope),
    ]
    for p in patches:
        p.start()
    seed(memory)

    import app as template_app  # the template's own Flask app

    flask_app = template_app.create_app()

    def upload_disabled(*_args, **_kwargs):
        return "Uploads are disabled in the demo (no storage is connected).", 403

    flask_app.view_functions["pipeline.upload"] = upload_disabled
    flask_app.view_functions["pipeline.upload_page"] = upload_disabled
    flask_app.demo_store = memory
    return flask_app


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    demo_app = create_demo_app()
    port = int(os.environ.get("PORT", 8080))
    print(f"\nDemo dashboard: http://localhost:{port}/   (Ctrl+C to stop)\n")
    demo_app.run(host="127.0.0.1", port=port)
