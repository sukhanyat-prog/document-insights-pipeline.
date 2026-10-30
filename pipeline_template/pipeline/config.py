"""
All project-specific settings live here (and in .env).

To reuse this template for another project, change the values in `.env`
(project, bucket, dataset, table prefix, thresholds). You should not need to
edit this file unless you add a new setting.
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parent.parent
load_dotenv(ROOT_DIR / ".env")


def _int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, default))
    except (TypeError, ValueError):
        return default


def _float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, default))
    except (TypeError, ValueError):
        return default


# --- Identity ---------------------------------------------------------------
APP_NAME = os.getenv("APP_NAME", "pipeline-template")
APP_TITLE = os.getenv("APP_TITLE", "Document Insights Pipeline")
# URL prefix for every page and endpoint ("" = root). Example: "/my-pipeline"
URL_PATH_PREFIX = os.getenv("URL_PATH_PREFIX", "").rstrip("/")

# --- Google Cloud -----------------------------------------------------------
GOOGLE_CLOUD_PROJECT = os.getenv("GOOGLE_CLOUD_PROJECT", "your-gcp-project")
GOOGLE_CLOUD_LOCATION = os.getenv("GOOGLE_CLOUD_LOCATION", "us-central1")
GCS_BUCKET = os.getenv("GCS_BUCKET", "your-bucket")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")

# Local development only; never committed (see .gitignore). In Cloud Run the
# service account is used automatically.
LOCAL_KEY_FILE = ROOT_DIR / "secrets" / "service-account.json"

# --- BigQuery ---------------------------------------------------------------
BQ_DATASET = os.getenv("BQ_DATASET", "PIPELINE_TEMPLATE")
BQ_LOCATION = os.getenv("BQ_LOCATION", GOOGLE_CLOUD_LOCATION)
TABLE_PREFIX = os.getenv("TABLE_PREFIX", "tpl_")

T_DOCUMENTS = os.getenv("T_DOCUMENTS", f"{TABLE_PREFIX}documents")      # one row per parsed document
T_FINDINGS = os.getenv("T_FINDINGS", f"{TABLE_PREFIX}findings")         # raw statements extracted by the LLM
T_THEMES = os.getenv("T_THEMES", f"{TABLE_PREFIX}themes")               # raw label -> canonical theme mapping
T_SIGNALS = os.getenv("T_SIGNALS", f"{TABLE_PREFIX}signals")            # findings mapped to canonical themes
T_SCORES = os.getenv("T_SCORES", f"{TABLE_PREFIX}scores")               # one row per theme per year
T_REFERENCE = os.getenv("T_REFERENCE", f"{TABLE_PREFIX}reference")      # your internal / baseline values (you load it)
T_COMPARISON = os.getenv("T_COMPARISON", f"{TABLE_PREFIX}comparison")   # scores compared with the reference
T_STATUS = os.getenv("T_STATUS", f"{TABLE_PREFIX}status")               # processing log

# --- Pipeline behaviour -----------------------------------------------------
DEFAULT_YEAR = _int("DEFAULT_YEAR", 2026)
MAX_THEMES = _int("MAX_THEMES", 25)                    # cap on canonical themes
MAX_LABELS_FOR_LLM = _int("MAX_LABELS_FOR_LLM", 400)   # most frequent raw labels sent to the consolidation prompt
CONFIDENCE_FLOOR = _float("CONFIDENCE_FLOOR", 0.55)    # signals below this are stored but not counted
SOURCES_TOTAL = _int("SOURCES_TOTAL", 0)               # expected number of sources (0 = count distinct in data)
AUTO_REFRESH = os.getenv("AUTO_REFRESH", "true").lower() in {"1", "true", "yes"}  # run steps 2-5 after each parse

# Preferred theme names (optional). Consolidation snaps close matches to these.
PREFERRED_THEMES_FILE = Path(os.getenv("PREFERRED_THEMES_FILE", str(ROOT_DIR / "data" / "preferred_themes.json")))

# Scoring (see pipeline/scoring.py)
SEVERITY_WEIGHTS = {"high": 3, "medium": 2, "low": 1}
SCORE_WEIGHT_COVERAGE = _float("SCORE_WEIGHT_COVERAGE", 0.6)
SCORE_WEIGHT_INTENSITY = _float("SCORE_WEIGHT_INTENSITY", 0.4)
BAND_HIGH_MIN = _float("BAND_HIGH_MIN", 70)
BAND_MEDIUM_MIN = _float("BAND_MEDIUM_MIN", 40)
