"""
All project-specific settings live here (and in .env).

To reuse this template for another project, change the values in `.env` (database, schema, stage, warehouse,
Cortex model, table prefix, thresholds). You should not need to edit this file unless you add a setting.
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
URL_PATH_PREFIX = os.getenv("URL_PATH_PREFIX", "").rstrip("/")  # "" = root. Example: "/my-pipeline"

# --- Snowflake --------------------------------------------------------------
# Connection settings are read in clients.py. Inside Snowpark Container Services the session token is used
# automatically; locally use a password in .env (never committed), key-pair auth, or SSO (externalbrowser).
SNOWFLAKE_ACCOUNT = os.getenv("SNOWFLAKE_ACCOUNT", "")           # e.g. myorg-myaccount
SNOWFLAKE_USER = os.getenv("SNOWFLAKE_USER", "")
SNOWFLAKE_ROLE = os.getenv("SNOWFLAKE_ROLE", "")
SNOWFLAKE_WAREHOUSE = os.getenv("SNOWFLAKE_WAREHOUSE", "")
SNOWFLAKE_DATABASE = os.getenv("SNOWFLAKE_DATABASE", "PIPELINE_DB")
SNOWFLAKE_SCHEMA = os.getenv("SNOWFLAKE_SCHEMA", "PIPELINE_TEMPLATE")
STAGE_NAME = os.getenv("SNOWFLAKE_STAGE", "DOCUMENTS")           # internal stage that receives the PDFs
CORTEX_MODEL = os.getenv("CORTEX_MODEL", "mistral-large2")       # any model available to SNOWFLAKE.CORTEX.COMPLETE
MAX_DOC_CHARS = _int("MAX_DOC_CHARS", 100_000)                   # text sent to the model per document

STAGE_FQN = f"{SNOWFLAKE_DATABASE}.{SNOWFLAKE_SCHEMA}.{STAGE_NAME}"
LOCATION_PREFIX = f"@{STAGE_FQN}"                                 # stripped from object names in event payloads

# --- Tables (in SNOWFLAKE_DATABASE.SNOWFLAKE_SCHEMA) -------------------------
TABLE_PREFIX = os.getenv("TABLE_PREFIX", "tpl_")

T_DOCUMENTS = os.getenv("T_DOCUMENTS", f"{TABLE_PREFIX}documents")      # one row per parsed document
T_FINDINGS = os.getenv("T_FINDINGS", f"{TABLE_PREFIX}findings")         # raw statements extracted by the model
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

PREFERRED_THEMES_FILE = Path(os.getenv("PREFERRED_THEMES_FILE", str(ROOT_DIR / "data" / "preferred_themes.json")))

# Scoring (see pipeline/scoring.py)
SEVERITY_WEIGHTS = {"high": 3, "medium": 2, "low": 1}
SCORE_WEIGHT_COVERAGE = _float("SCORE_WEIGHT_COVERAGE", 0.6)
SCORE_WEIGHT_INTENSITY = _float("SCORE_WEIGHT_INTENSITY", 0.4)
BAND_HIGH_MIN = _float("BAND_HIGH_MIN", 70)
BAND_MEDIUM_MIN = _float("BAND_MEDIUM_MIN", 40)
