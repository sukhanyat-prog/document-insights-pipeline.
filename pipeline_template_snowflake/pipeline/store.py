"""Snowflake table helpers.

SQL in the rest of the code uses :named parameters; `to_qmark` turns them into Snowflake's `?` placeholders.
Table names come from config only; every value goes through parameters. Rows are inserted as one JSON string
parameter that is parsed and cast to the column types inside Snowflake.
"""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from . import config
from .clients import run_sql
from .schemas import TABLES

logger = logging.getLogger(__name__)

SQL_TYPES = {
    "STRING": "VARCHAR",
    "INTEGER": "NUMBER(38,0)",
    "FLOAT": "FLOAT",
    "BOOLEAN": "BOOLEAN",
    "DATE": "DATE",
    "TIMESTAMP": "TIMESTAMP_NTZ",
}
INSERT_CHUNK = 500
_NAMED = re.compile(r"(?<![:\w]):([A-Za-z_]\w*)")


def now_iso() -> str:
    """UTC wall-clock time without an offset (the column type is TIMESTAMP_NTZ)."""
    return datetime.now(timezone.utc).replace(tzinfo=None).isoformat()


def table_id(table: str) -> str:
    return f"{config.SNOWFLAKE_DATABASE}.{config.SNOWFLAKE_SCHEMA}.{table}"


def to_qmark(sql: str, params: dict[str, Any]) -> tuple[str, list]:
    """Replace :name with ? and return the values in order of appearance (a name may repeat)."""
    values: list = []

    def swap(match: re.Match) -> str:
        name = match.group(1)
        if name not in params:
            raise KeyError(f"No value for :{name}")
        values.append(params[name])
        return "?"

    return _NAMED.sub(swap, sql), values


def clean_row(row: dict) -> dict:
    """Plain Python values: Decimal -> int/float so JSON responses stay numeric."""
    out = {}
    for key, value in row.items():
        if isinstance(value, Decimal):
            value = int(value) if value == value.to_integral_value() else float(value)
        out[key.lower()] = value
    return out


def query(sql: str, **params: Any) -> list[dict]:
    """Run SQL with :named parameters and return rows as dicts (lower-case keys)."""
    statement, values = to_qmark(sql, params)
    return [clean_row(r) for r in run_sql(statement, values)]


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
    names = ", ".join(name for name, _ in columns)
    select = ", ".join(f"f.value:{name}::{SQL_TYPES[kind]}" for name, kind in columns)
    return (
        f"INSERT INTO {table_id(table)} ({names}) "
        f"SELECT {select} FROM TABLE(FLATTEN(INPUT => PARSE_JSON(?))) f"
    )


def load_rows(table: str, rows: list[dict]) -> int:
    if not rows:
        return 0
    sql = insert_sql(table)
    for start in range(0, len(rows), INSERT_CHUNK):
        run_sql(sql, [rows_payload(table, rows[start : start + INSERT_CHUNK])])
    return len(rows)


def delete_where(table: str, where: str, **params: Any) -> None:
    """DELETE FROM table WHERE <where>; `where` must only use :named parameters."""
    statement, values = to_qmark(f"DELETE FROM {table_id(table)} WHERE {where}", params)
    run_sql(statement, values)


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
    return f"CREATE TABLE IF NOT EXISTS {table_id(table)} ({cols})"


def ensure_tables() -> None:
    """Create the schema, stage and tables if missing, and add any columns that are missing."""
    run_sql(f"CREATE SCHEMA IF NOT EXISTS {config.SNOWFLAKE_DATABASE}.{config.SNOWFLAKE_SCHEMA}")
    run_sql(
        f"CREATE STAGE IF NOT EXISTS {config.STAGE_FQN} "
        "DIRECTORY = (ENABLE = TRUE) ENCRYPTION = (TYPE = 'SNOWFLAKE_SSE')"
    )
    for name, columns in TABLES.items():
        run_sql(ddl_for(name))
        existing = {
            r["column_name"].lower()
            for r in run_sql(
                f"SELECT column_name FROM {config.SNOWFLAKE_DATABASE}.INFORMATION_SCHEMA.COLUMNS "
                "WHERE table_schema = ? AND table_name = ?",
                [config.SNOWFLAKE_SCHEMA.upper(), name.upper()],
            )
        }
        missing = [(c, k) for c, k in columns if c.lower() not in existing]
        for column, kind in missing:
            run_sql(f"ALTER TABLE {table_id(name)} ADD COLUMN {column} {SQL_TYPES[kind]}")
        print(f"patched {name}: +{', '.join(c for c, _ in missing)}" if missing else f"ready   {name}")
