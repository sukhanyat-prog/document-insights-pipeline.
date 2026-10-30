"""Step 5 - compare each theme score with your own reference table (internal view, baseline, target...).

Load the reference with `python scripts/run_pipeline.py load-reference --csv file.csv --year 2026`
(columns: canonical_theme, reference_value 0-100, owner).
"""

from __future__ import annotations

import difflib

from . import config, store
from .consolidate import normalize_label
from .scoring import BAND_ORDER, band_for


def _match_reference(theme: str, reference: dict[str, dict]) -> dict | None:
    key = normalize_label(theme)
    if key in reference:
        return reference[key]
    best = difflib.get_close_matches(key, list(reference), n=1, cutoff=0.8)
    return reference[best[0]] if best else None


def compare_scores(scores: list[dict], reference_rows: list[dict], year: int, computed_at: str | None = None) -> list[dict]:
    reference = {normalize_label(r["canonical_theme"]): r for r in reference_rows}
    used: set[str] = set()
    out = []

    for s in scores:
        ref = _match_reference(s["canonical_theme"], reference)
        if ref is None:
            out.append(_row(year, s["canonical_theme"], s["score"], s["band"], None, None, None,
                            "not_in_reference", "Seen externally, absent from the reference table", computed_at))
            continue
        used.add(normalize_label(ref["canonical_theme"]))
        ref_value = float(ref["reference_value"])
        ref_band = band_for(ref_value)
        gap = round(s["score"] - ref_value, 1)
        diff = BAND_ORDER[s["band"]] - BAND_ORDER[ref_band]
        status = "aligned" if diff == 0 else ("external_higher" if diff > 0 else "external_lower")
        detail = {
            "aligned": f"Both {s['band']}",
            "external_higher": f"External {s['band']} vs reference {ref_band}",
            "external_lower": f"External {s['band']} vs reference {ref_band}",
        }[status]
        out.append(_row(year, s["canonical_theme"], s["score"], s["band"], ref_value, ref_band, gap, status, detail, computed_at))

    for key, ref in reference.items():  # blind spots: in the reference, not seen in the documents
        if key in used:
            continue
        ref_value = float(ref["reference_value"])
        out.append(_row(year, ref["canonical_theme"], None, None, ref_value, band_for(ref_value), None,
                        "not_in_external", "In the reference table, not found in the documents", computed_at))
    return out


def _row(year, theme, score, band, ref_value, ref_band, gap, status, detail, computed_at):
    return {
        "period_year": year,
        "canonical_theme": theme,
        "score": score,
        "band": band,
        "reference_value": ref_value,
        "reference_band": ref_band,
        "gap": gap,
        "status": status,
        "detail": detail,
        "computed_at": computed_at,
    }


def compare_year(year: int) -> dict:
    scores = store.query(f"SELECT * FROM {store.table_id(config.T_SCORES)} WHERE period_year = :year", year=year)
    reference = store.query(f"SELECT * FROM {store.table_id(config.T_REFERENCE)} WHERE period_year = :year", year=year)
    rows = compare_scores(scores, reference, year, computed_at=store.now_iso())
    store.replace_scope(config.T_COMPARISON, year, rows)
    return {"year": year, "rows": len(rows), "reference_rows": len(reference)}


def load_reference_csv(path: str, year: int) -> int:
    """Replace the reference rows for a year from a CSV (canonical_theme, reference_value, owner)."""
    import csv

    stamp = store.now_iso()
    rows = []
    with open(path, newline="", encoding="utf-8-sig") as handle:
        for rec in csv.DictReader(handle):
            theme = (rec.get("canonical_theme") or "").strip()
            if not theme:
                continue
            rows.append(
                {
                    "period_year": year,
                    "canonical_theme": theme,
                    "reference_value": float(rec["reference_value"]),
                    "owner": (rec.get("owner") or "").strip() or None,
                    "loaded_at": stamp,
                }
            )
    store.replace_scope(config.T_REFERENCE, year, rows)
    return len(rows)
