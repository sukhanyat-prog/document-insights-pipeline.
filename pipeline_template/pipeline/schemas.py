"""BigQuery table definitions: the single place to add or rename columns.

Each table is a list of (column, BigQuery type). `store.ensure_tables()` creates
missing tables and adds missing columns, and every load job uses these schemas.
"""

from __future__ import annotations

from . import config

TABLES: dict[str, list[tuple[str, str]]] = {
    config.T_DOCUMENTS: [
        ("doc_id", "STRING"),
        ("source", "STRING"),            # who published it (publisher, vendor, team...)
        ("period_year", "INTEGER"),
        ("gcs_uri", "STRING"),
        ("title", "STRING"),
        ("summary", "STRING"),
        ("document_date", "DATE"),
        ("findings_count", "INTEGER"),
        ("parsed_at", "TIMESTAMP"),
    ],
    config.T_FINDINGS: [
        ("doc_id", "STRING"),
        ("source", "STRING"),
        ("period_year", "INTEGER"),
        ("raw_label", "STRING"),         # free-text theme label chosen by the LLM
        ("direction", "STRING"),
        ("severity", "STRING"),
        ("evidence_text", "STRING"),
        ("page_ref", "INTEGER"),
        ("confidence", "FLOAT"),
        ("created_at", "TIMESTAMP"),
    ],
    config.T_THEMES: [
        ("period_year", "INTEGER"),
        ("raw_label", "STRING"),
        ("canonical_theme", "STRING"),
        ("mapping_confidence", "FLOAT"),
        ("mapping_method", "STRING"),    # llm | preferred | fuzzy | cap_merge | unmapped
        ("created_at", "TIMESTAMP"),
    ],
    config.T_SIGNALS: [
        ("doc_id", "STRING"),
        ("source", "STRING"),
        ("period_year", "INTEGER"),
        ("canonical_theme", "STRING"),
        ("direction", "STRING"),
        ("severity_weight", "INTEGER"),
        ("confidence", "FLOAT"),         # finding confidence x mapping confidence
        ("counted", "BOOLEAN"),          # confidence >= CONFIDENCE_FLOOR
        ("evidence_text", "STRING"),
        ("page_ref", "INTEGER"),
        ("created_at", "TIMESTAMP"),
    ],
    config.T_SCORES: [
        ("period_year", "INTEGER"),
        ("canonical_theme", "STRING"),
        ("sources_count", "INTEGER"),
        ("sources_total", "INTEGER"),
        ("sources_citing", "STRING"),    # "5 of 9"
        ("mention_count", "INTEGER"),
        ("avg_severity", "FLOAT"),
        ("score", "FLOAT"),              # 0-100
        ("band", "STRING"),              # High | Medium | Low
        ("direction", "STRING"),
        ("avg_confidence", "FLOAT"),
        ("computed_at", "TIMESTAMP"),
    ],
    config.T_REFERENCE: [
        ("period_year", "INTEGER"),
        ("canonical_theme", "STRING"),
        ("reference_value", "FLOAT"),    # same 0-100 scale as score
        ("owner", "STRING"),
        ("loaded_at", "TIMESTAMP"),
    ],
    config.T_COMPARISON: [
        ("period_year", "INTEGER"),
        ("canonical_theme", "STRING"),
        ("score", "FLOAT"),
        ("band", "STRING"),
        ("reference_value", "FLOAT"),
        ("reference_band", "STRING"),
        ("gap", "FLOAT"),                # score - reference_value
        ("status", "STRING"),            # aligned | external_higher | external_lower | not_in_reference | not_in_external
        ("detail", "STRING"),
        ("computed_at", "TIMESTAMP"),
    ],
    config.T_STATUS: [
        ("doc_id", "STRING"),
        ("object_name", "STRING"),
        ("status", "STRING"),            # started | parsed | error | ignored
        ("message", "STRING"),
        ("updated_at", "TIMESTAMP"),
    ],
}


def schema_for(table: str):
    from google.cloud import bigquery

    return [bigquery.SchemaField(name, kind) for name, kind in TABLES[table]]
