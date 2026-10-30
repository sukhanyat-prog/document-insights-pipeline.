"""Read-only queries behind the dashboard. Return plain dicts so the page and the JSON API share them."""

from __future__ import annotations

from . import config, store


def available_years() -> list[int]:
    rows = store.query(
        f"SELECT DISTINCT period_year FROM {store.table_id(config.T_DOCUMENTS)} "
        "WHERE period_year IS NOT NULL ORDER BY period_year DESC"
    )
    years = [int(r["period_year"]) for r in rows]
    return years or [config.DEFAULT_YEAR]


def fetch_dashboard(year: int) -> dict:
    documents = store.query(
        f"SELECT doc_id, source, title, findings_count, parsed_at "
        f"FROM {store.table_id(config.T_DOCUMENTS)} WHERE period_year = :year ORDER BY parsed_at DESC",
        year=year,
    )
    scores = store.query(
        f"SELECT * FROM {store.table_id(config.T_SCORES)} WHERE period_year = :year ORDER BY score DESC", year=year
    )
    comparison = store.query(
        f"SELECT * FROM {store.table_id(config.T_COMPARISON)} WHERE period_year = :year "
        "ORDER BY IFNULL(score, -1) DESC",
        year=year,
    )
    status_counts: dict[str, int] = {}
    for row in comparison:
        status_counts[row["status"]] = status_counts.get(row["status"], 0) + 1

    return {
        "year": year,
        "app_title": config.APP_TITLE,
        "kpis": {
            "documents": len(documents),
            "sources": len({d["source"] for d in documents if d.get("source")}),
            "themes": len(scores),
            "high_band": sum(1 for s in scores if s.get("band") == "High"),
            "blind_spots": status_counts.get("not_in_external", 0),
        },
        "scores": scores,
        "comparison": comparison,
        "status_counts": status_counts,
        "documents": documents,
    }
