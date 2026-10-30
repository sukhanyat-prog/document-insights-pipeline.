"""
Flask entry point (gunicorn target: app:app).

Local run:
    pip install -r requirements.txt
    copy .env.example .env         # then edit the names
    python app.py                  # http://localhost:8080/

Endpoints (all under URL_PATH_PREFIX, default ""):
    GET  /                dashboard
    GET  /api/dashboard   same data as JSON (?year=2026)
    GET  /upload  POST /upload    upload a PDF into the storage location
    POST /process-new     (browser button) parse every PDF not parsed yet
    POST /event           parse one object: {"name": "2026/Source/file.pdf"}
    POST /run-new         parse everything not parsed yet (for schedulers / jobs), ?year= optional
    POST /run             re-run steps 2-5 for ?year=
    GET  /health          liveness probe
"""

from __future__ import annotations

import logging
import os

from flask import Flask
from flask_wtf import CSRFProtect

from pipeline import config
from pipeline.web import MACHINE_VIEWS, bp

logging.basicConfig(level=logging.INFO)


def create_app() -> Flask:
    app = Flask(__name__)

    secret = os.environ.get("SECRET_KEY", "").strip()
    if not secret or secret == "change-me":
        if os.environ.get("APP_ENV", "").lower() == "production":
            raise RuntimeError("SECRET_KEY must be set to a strong random value in production.")
        secret = "dev-only-key"
    app.secret_key = secret
    app.config["MAX_CONTENT_LENGTH"] = 50 * 1024 * 1024

    csrf = CSRFProtect(app)
    app.register_blueprint(bp, url_prefix=config.URL_PATH_PREFIX or None)
    for view in MACHINE_VIEWS:
        csrf.exempt(view)

    @app.get("/health")
    def health():
        return {"status": "ok", "app": config.APP_NAME, "tables_prefix": config.TABLE_PREFIX}

    return app


app = create_app()

if __name__ == "__main__":
    # Local run only. In production a real server runs app:app (see Dockerfile / serve.py). Debug is opt-in.
    port = int(os.environ.get("DATABRICKS_APP_PORT") or os.environ.get("PORT") or 8080)
    app.run(host="0.0.0.0", port=port, debug=os.environ.get("FLASK_DEBUG") == "1")
