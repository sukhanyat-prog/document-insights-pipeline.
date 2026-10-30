"""Flask blueprint: dashboard page + JSON API, upload page, and the machine endpoints (event, run)."""

from __future__ import annotations

import logging
from datetime import date

from flask import Blueprint, flash, jsonify, redirect, render_template, request, url_for

from . import config, dashboard
from .orchestrator import handle_event as run_event, run_after_steps
from .paths import build_object_path

logger = logging.getLogger(__name__)

bp = Blueprint("pipeline", __name__, template_folder="../templates")


@bp.context_processor
def _globals():
    return {"url_prefix": config.URL_PATH_PREFIX, "app_title": config.APP_TITLE}


def _year_arg() -> int:
    try:
        return int(request.args.get("year", config.DEFAULT_YEAR))
    except ValueError:
        return config.DEFAULT_YEAR


@bp.get("/")
def dashboard_page():
    year = _year_arg()
    try:
        years = dashboard.available_years()
    except Exception:
        logger.exception("Could not list years")
        years = [year]
    return render_template("dashboard.html", year=year, years=years)


@bp.get("/api/dashboard")
def dashboard_api():
    return jsonify(dashboard.fetch_dashboard(_year_arg()))


@bp.get("/upload")
def upload_page():
    return render_template("upload.html", year=config.DEFAULT_YEAR, bucket=config.GCS_BUCKET)


@bp.post("/upload")
def upload():
    from .clients import gcs_client

    pdf = request.files.get("file")
    source = (request.form.get("source") or "").strip()
    if not pdf or not pdf.filename or not pdf.filename.lower().endswith(".pdf"):
        flash("Choose a PDF file.", "error")
        return redirect(url_for("pipeline.upload_page"))
    if not source:
        flash("Enter the source (publisher / team).", "error")
        return redirect(url_for("pipeline.upload_page"))
    try:
        year = int(request.form.get("year") or config.DEFAULT_YEAR)
    except ValueError:
        year = config.DEFAULT_YEAR or date.today().year

    object_name = build_object_path(year, source, pdf.filename)
    blob = gcs_client().bucket(config.GCS_BUCKET).blob(object_name)
    blob.metadata = {"source": source, "year": str(year)}
    blob.upload_from_file(pdf.stream, content_type="application/pdf")
    flash(f"Uploaded to gs://{config.GCS_BUCKET}/{object_name}. Processing starts automatically.", "ok")
    return redirect(url_for("pipeline.upload_page"))


@bp.post("/event")
def event_endpoint():
    """Eventarc target. 400 = bad payload (do not retry); any other failure -> 500 so Eventarc retries."""
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify({"error": "expected a JSON object"}), 400
    try:
        return jsonify(run_event(payload))
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    except Exception as exc:
        logger.exception("Event failed")
        return jsonify({"error": str(exc)}), 500


@bp.post("/run")
def run_endpoint():
    """Re-run steps 2-5 for a year, e.g. after loading a new reference table."""
    try:
        return jsonify(run_after_steps(_year_arg()))
    except Exception as exc:
        logger.exception("Run failed")
        return jsonify({"error": str(exc)}), 500


MACHINE_VIEWS = (event_endpoint, run_endpoint)  # CSRF-exempt (called by Eventarc / schedulers, not browsers)
