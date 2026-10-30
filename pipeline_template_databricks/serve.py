"""Start gunicorn on the port the platform gives us (Databricks Apps sets DATABRICKS_APP_PORT)."""

import os

port = os.environ.get("DATABRICKS_APP_PORT") or os.environ.get("PORT") or "8000"
os.execvp(
    "gunicorn",
    ["gunicorn", "--bind", f"0.0.0.0:{port}", "--workers", "2", "--threads", "4", "--timeout", "900", "app:app"],
)
