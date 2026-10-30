"""Step 4 - one score row per theme for the year (maths lives in scoring.py)."""

from __future__ import annotations

from . import config, store
from .scoring import score_themes


def aggregate_year(year: int) -> dict:
    signals = store.query(
        f"SELECT * FROM {store.table_id(config.T_SIGNALS)} WHERE period_year = :year", year=year
    )
    rows = score_themes(signals, year, computed_at=store.now_iso())
    store.replace_scope(config.T_SCORES, year, rows)
    return {"year": year, "themes_scored": len(rows)}
