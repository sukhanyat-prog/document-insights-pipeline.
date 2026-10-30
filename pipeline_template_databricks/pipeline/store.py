"""Delta table helpers (Databricks SQL warehouse).

SQL uses :named parameters. Table names come from config only; every value goes through parameters.
Rows are inserted as one JSON string parameter that is parsed and CAST to the column types inside the
warehouse, so no type juggling happens on the Python side.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from . import config
from .clients import run_sql
from .schemas import TABLES

logger = logging.getLogger(__name__)

SQL_TYPES = {
    "STRING": "STRING",
    "INTEGER": "BIGINT",
    "FLOAT": "DOUBLE",
    "BOOLEAN": "BOOLEAN",
    "DATE": "DATE",
    "TIMESTAMP": "TIMESTAMP",
}
INSERT_CHUNK = 500


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def table_id(table: str) -> str:
    return f"{config.DBX_CATALOG}.{config.DBX_SCHEMA}.{table}"


def clean_row(row: dict) -> dict:
    """Plain Python values: Decimal -> int/float so JSON responses stay numeric."""
    out = {}
    for key, value in row.items():
        if isinstance(value, Decimal):
            value = int(value) if value == value.to_integral_value() else float(value)
        out[key] = value
    return out


def query(sql: str, **params: Any) -> list[dict]:
    """Run SQL with :named parameters and return rows as dicts."""
    return [clean_row(r) for r in run_sql(sql, params)]


# --- inserts -------------------------------------------------------------------------------------------------
def _text(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def rows_payload(table: str, rows: list[dict]) -> str:
    """JSON array of the table's columns, every value as text (or null); extra keys in `rows` are ignored."""
    columns = [name for name, _ in TABLES[table]]
    return json.dumps([{c: _text(r.get(c)) for c in columns} for r in rows])


def insert_sql(table: str) -> str:
    columns = TABLES[table]
    struct = ", ".join(f"{name}: STRING" for name, _ in columns)
    select = ", ".join(f"CAST(r.{name} AS {SQL_TYPES[kind]})" for name, kind in columns)
    names = ", ".join(name for name, _ in columns)
    return (
        f"INSERT INTO {table_id(table)} ({names}) "
        f"SELECT {select} "
        f"FROM (SELECT explode(from_json(:payload, 'ARRAY<STRUCT<{struct}>>')) AS r)"
    )


def load_rows(table: str, rows: list[dict]) -> int:
    if not rows:
        return 0
    sql = insert_sql(table)
    for start in range(0, len(rows), INSERT_CHUNK):
        run_sql(sql, {"payload": rows_payload(table, rows[start : start + INSERT_CHUNK])}, fetch=False)
    return len(rows)


def delete_where(table: str, where: str, **params: Any) -> None:
    """DELETE FROM table WHERE <where>; `where` must only use :named parameters."""
    run_sql(f"DELETE FROM {table_id(table)} WHERE {where}", params, fetch=False)


def replace_scope(table: str, year: int, rows: list[dict]) -> int:
    """Idempotent rewrite of one year of a derived table (delete, then insert)."""
    delete_where(table, "period_year = :year", year=year)
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


# --- setup ---------------------------------------------------------------------------------------------------
def ddl_for(table: str) -> str:
    cols = ", ".join(f"{name} {SQL_TYPES[kind]}" for name, kind in TABLES[table])
    return f"CREATE TABLE IF NOT EXISTS {table_id(table)} ({cols}) USING DELTA"


def ensure_tables() -> None:
    """Create the schema, volume and tables if missing, and add any columns that are missing."""
    run_sql(f"CREATE SCHEMA IF NOT EXISTS {config.DBX_CATALOG}.{config.DBX_SCHEMA}", fetch=False)
    run_sql(f"CREATE VOLUME IF NOT EXISTS {config.DBX_CATALOG}.{config.DBX_SCHEMA}.{config.DBX_VOLUME}", fetch=False)
    for name, columns in TABLES.items():
        run_sql(ddl_for(name), fetch=False)
        existing = {r["col_name"].lower() for r in run_sql(f"DESCRIBE TABLE {table_id(name)}") if r.get("col_name")}
        missing = [(c, k) for c, k in columns if c.lower() not in existing]
        if missing:
            adds = ", ".join(f"{c} {SQL_TYPES[k]}" for c, k in missing)
            run_sql(f"ALTER TABLE {table_id(name)} ADD COLUMNS ({adds})", fetch=False)
            print(f"patched {name}: +{', '.join(c for c, _ in missing)}")
        else:
            print(f"ready   {name}")
