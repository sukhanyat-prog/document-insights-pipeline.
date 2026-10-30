"""Snowflake session (Snowpark). One shared session, re-created if the token expires.

Authentication, in order:
  1. Snowpark Container Services: the OAuth token file /snowflake/session/token (automatic, nothing to configure)
  2. SNOWFLAKE_PRIVATE_KEY_PATH (+ optional SNOWFLAKE_PRIVATE_KEY_PASSPHRASE)  key-pair auth
  3. SNOWFLAKE_AUTHENTICATOR=externalbrowser                                    SSO, for local development
  4. SNOWFLAKE_PASSWORD                                                         local development only (.env, never committed)
"""

from __future__ import annotations

import logging
import os
import threading
from pathlib import Path

from . import config

logger = logging.getLogger(__name__)

SPCS_TOKEN_FILE = Path("/snowflake/session/token")


def connection_params() -> dict:
    params = {
        "database": config.SNOWFLAKE_DATABASE,
        "schema": config.SNOWFLAKE_SCHEMA,
    }
    if config.SNOWFLAKE_WAREHOUSE:
        params["warehouse"] = config.SNOWFLAKE_WAREHOUSE
    if config.SNOWFLAKE_ROLE:
        params["role"] = config.SNOWFLAKE_ROLE

    if SPCS_TOKEN_FILE.is_file():
        params.update(
            host=os.environ["SNOWFLAKE_HOST"],
            account=os.environ["SNOWFLAKE_ACCOUNT"],
            authenticator="oauth",
            token=SPCS_TOKEN_FILE.read_text().strip(),
        )
        return params

    if not config.SNOWFLAKE_ACCOUNT or not config.SNOWFLAKE_USER:
        raise RuntimeError("Set SNOWFLAKE_ACCOUNT and SNOWFLAKE_USER (see .env.example).")
    params.update(account=config.SNOWFLAKE_ACCOUNT, user=config.SNOWFLAKE_USER)

    key_path = os.getenv("SNOWFLAKE_PRIVATE_KEY_PATH")
    if key_path:
        params["private_key"] = _load_private_key(key_path, os.getenv("SNOWFLAKE_PRIVATE_KEY_PASSPHRASE"))
    elif os.getenv("SNOWFLAKE_AUTHENTICATOR"):
        params["authenticator"] = os.environ["SNOWFLAKE_AUTHENTICATOR"]
    elif os.getenv("SNOWFLAKE_PASSWORD"):
        params["password"] = os.environ["SNOWFLAKE_PASSWORD"]
    else:
        raise RuntimeError("No Snowflake credentials: set a key path, an authenticator, or SNOWFLAKE_PASSWORD.")
    return params


def _load_private_key(path: str, passphrase: str | None) -> bytes:
    from cryptography.hazmat.primitives import serialization

    key = serialization.load_pem_private_key(
        Path(path).read_bytes(), password=passphrase.encode() if passphrase else None
    )
    return key.private_bytes(
        encoding=serialization.Encoding.DER,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )


_lock = threading.RLock()
_session = None


def session():
    global _session
    with _lock:
        if _session is None:
            from snowflake.snowpark import Session

            _session = Session.builder.configs(connection_params()).create()
        return _session


def reset_session() -> None:
    global _session
    with _lock:
        try:
            if _session is not None:
                _session.close()
        except Exception:
            pass
        _session = None


_EXPIRED = ("token has expired", "session no longer exists", "authentication token")


def run_sql(statement: str, params: list | None = None) -> list[dict]:
    """Execute one statement with ? placeholders. Returns rows as dicts with lower-case keys."""
    with _lock:
        for attempt in (1, 2):
            try:
                rows = session().sql(statement, params=params or None).collect()
                return [{k.lower(): v for k, v in row.as_dict().items()} for row in rows]
            except Exception as exc:
                if attempt == 2 or not any(m in str(exc).lower() for m in _EXPIRED):
                    raise
                logger.warning("Snowflake session expired; reconnecting once")
                reset_session()
    return []
