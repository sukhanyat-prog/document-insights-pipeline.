"""Databricks clients. Authentication comes from the Databricks SDK's unified auth:

  * inside Databricks Apps / Jobs / notebooks: automatic (the app's service principal, or the job identity)
  * locally: DATABRICKS_HOST + DATABRICKS_TOKEN, or DATABRICKS_CONFIG_PROFILE (databricks auth login)

Nothing in this repository holds a token.
"""

from __future__ import annotations

import logging
import threading
from functools import lru_cache

from . import config

logger = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def sdk_config():
    from databricks.sdk.core import Config

    return Config()


@lru_cache(maxsize=1)
def workspace_client():
    from databricks.sdk import WorkspaceClient

    return WorkspaceClient(config=sdk_config())


@lru_cache(maxsize=1)
def llm_client():
    """OpenAI-compatible client for Databricks model serving (needs the `openai` package)."""
    return workspace_client().serving_endpoints.get_open_ai_client()


# --- SQL warehouse connection (one shared connection, re-opened if it breaks) -----------------------------
_lock = threading.RLock()
_connection = None


def _connect():
    from databricks import sql

    if not config.HTTP_PATH:
        raise RuntimeError("Set DATABRICKS_WAREHOUSE_ID (or DATABRICKS_HTTP_PATH) to a SQL warehouse.")
    cfg = sdk_config()
    return sql.connect(
        server_hostname=cfg.host.replace("https://", "").rstrip("/"),
        http_path=config.HTTP_PATH,
        credentials_provider=lambda: cfg.authenticate,
    )


def run_sql(statement: str, params: dict | None = None, fetch: bool = True) -> list[dict]:
    """Execute one statement with :named parameters. Returns rows as dicts (empty list when nothing is returned)."""
    global _connection
    with _lock:
        for attempt in (1, 2):
            try:
                if _connection is None:
                    _connection = _connect()
                with _connection.cursor() as cur:
                    cur.execute(statement, params or {})
                    if not fetch or cur.description is None:
                        return []
                    names = [d[0] for d in cur.description]
                    return [dict(zip(names, row)) for row in cur.fetchall()]
            except Exception as exc:
                # Statement errors (bad SQL, permissions) are raised as they are. Only a broken connection is
                # retried, once, on a fresh connection.
                broken = type(exc).__name__ in _CONNECTION_ERRORS
                if broken:
                    try:
                        if _connection is not None:
                            _connection.close()
                    except Exception:
                        pass
                    _connection = None
                if not broken or attempt == 2:
                    raise
                logger.warning("SQL connection problem; reconnecting once", exc_info=True)
    return []


_CONNECTION_ERRORS = {"OperationalError", "RequestError", "InterfaceError", "ConnectionError"}
