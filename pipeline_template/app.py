"""
Flask entry point (gunicorn target: app:app).

Local run:
    pip install -r requirements.txt
    copy .env.example .env         # then edit the project / bucket / dataset names
    python app.py                  # http://localhost:8080/

Endpoints (all under URL_PATH_PREFIX, default ""):
    GET  /                dashboard
    GET  /api/dashboard   same data as JSON (?year=2026)
    GET  /upload  POST /upload    upload a PDF to the bucket
    POST /event           Cloud Storage event (Eventarc) -> parse + refresh
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
        return {"status": "ok", "app": config.APP_NAME, "dataset": config.BQ_DATASET}

    return app


app = create_app()

if __name__ == "__main__":
    # Local run only. In production the container runs gunicorn (see Dockerfile). Debug is opt-in.
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)), debug=os.environ.get("FLASK_DEBUG") == "1")
