"""Thin BigQuery helpers. All SQL values go through query parameters; table names come from config only."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from . import config
from .clients import bq_client
from .schemas import TABLES, schema_for

logger = logging.getLogger(__name__)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def table_id(table: str) -> str:
    return f"{config.GOOGLE_CLOUD_PROJECT}.{config.BQ_DATASET}.{table}"


def _param(name: str, value: Any):
    from google.cloud import bigquery

    if isinstance(value, bool):
        kind = "BOOL"
    elif isinstance(value, int):
        kind = "INT64"
    elif isinstance(value, float):
        kind = "FLOAT64"
    else:
        kind, value = "STRING", None if value is None else str(value)
    return bigquery.ScalarQueryParameter(name, kind, value)


def query(sql: str, **params: Any) -> list[dict]:
    """Run SQL with @named parameters and return rows as dicts."""
    from google.cloud import bigquery

    job_config = bigquery.QueryJobConfig(query_parameters=[_param(k, v) for k, v in params.items()])
    result = bq_client().query(sql, job_config=job_config).result()
    return [dict(row.items()) for row in result]


def load_rows(table: str, rows: list[dict]) -> int:
    """Append rows with a load job (not streaming), so they can be deleted again straight away."""
    from google.cloud import bigquery

    if not rows:
        return 0
    job_config = bigquery.LoadJobConfig(
        schema=schema_for(table),
        write_disposition=bigquery.WriteDisposition.WRITE_APPEND,
        source_format=bigquery.SourceFormat.NEWLINE_DELIMITED_JSON,
    )
    bq_client().load_table_from_json(rows, table_id(table), job_config=job_config).result()
    return len(rows)


def delete_where(table: str, where: str, **params: Any) -> None:
    """DELETE FROM table WHERE <where>; `where` must only use @named parameters."""
    query(f"DELETE FROM `{table_id(table)}` WHERE {where}", **params)


def replace_scope(table: str, year: int, rows: list[dict]) -> int:
    """Idempotent rewrite of one year of a derived table."""
    delete_where(table, "period_year = @year", year=year)
    return load_rows(table, rows)


def log_status(doc_id: str, object_name: str, status: str, message: str = "") -> None:
    try:
        load_rows(
            config.T_STATUS,
            [{"doc_id": doc_id, "object_name": object_name, "status": status,
              "message": message[:1000], "updated_at": now_iso()}],
        )
    except Exception:  # logging must never break the pipeline
        logger.exception("Could not write status row for %s", object_name)


def ensure_tables() -> None:
    """Create the dataset and tables if missing, and add any columns that are missing."""
    from google.cloud import bigquery

    client = bq_client()
    dataset = bigquery.Dataset(f"{config.GOOGLE_CLOUD_PROJECT}.{config.BQ_DATASET}")
    dataset.location = config.BQ_LOCATION
    client.create_dataset(dataset, exists_ok=True)

    for name in TABLES:
        ref = table_id(name)
        try:
            table = client.get_table(ref)
        except Exception:
            client.create_table(bigquery.Table(ref, schema=schema_for(name)))
            print(f"created {name}")
            continue
        existing = {f.name for f in table.schema}
        missing = [f for f in schema_for(name) if f.name not in existing]
        if missing:
            table.schema = list(table.schema) + missing
            client.update_table(table, ["schema"])
            print(f"patched {name}: +{', '.join(f.name for f in missing)}")
        else:
            print(f"exists  {name}")
