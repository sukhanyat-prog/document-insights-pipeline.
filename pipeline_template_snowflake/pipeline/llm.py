"""Model calls. One function, `complete(prompt)`, returns the model's text answer.

Uses Snowflake Cortex (SNOWFLAKE.CORTEX.COMPLETE), so the document text never leaves Snowflake.
The role running the app needs the SNOWFLAKE.CORTEX_USER database role. Change CORTEX_MODEL in .env to switch models.
"""

from __future__ import annotations

from . import config
from .clients import run_sql

SYSTEM = "You are a careful analyst. Answer with a single JSON object and nothing else."


def complete(prompt: str, system: str = SYSTEM) -> str:
    rows = run_sql(
        "SELECT SNOWFLAKE.CORTEX.COMPLETE(?, ?) AS answer",
        [config.CORTEX_MODEL, f"{system}\n\n{prompt}"],
    )
    return str(rows[0]["answer"]) if rows and rows[0].get("answer") is not None else ""
