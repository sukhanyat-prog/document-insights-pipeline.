"""Step 3 - map every finding to its canonical theme and decide whether it counts."""

from __future__ import annotations

from . import config, store


def build_signals(findings: list[dict], mapping: dict[str, tuple[str, float]], floor: float | None = None) -> list[dict]:
    """
    findings : rows of the findings table
    mapping  : raw_label -> (canonical_theme, mapping_confidence)
    A signal's confidence is finding confidence x mapping confidence; it only counts when it
    reaches the confidence floor. Findings whose label has no mapping are skipped.
    """
    floor = config.CONFIDENCE_FLOOR if floor is None else floor
    stamp = store.now_iso()
    signals = []
    for f in findings:
        target = mapping.get(f.get("raw_label"))
        if not target:
            continue
        canonical, map_conf = target
        confidence = round(float(f.get("confidence") or 0.0) * float(map_conf), 4)
        signals.append(
            {
                "doc_id": f["doc_id"],
                "source": f.get("source"),
                "period_year": f["period_year"],
                "canonical_theme": canonical,
                "direction": f.get("direction") or "neutral",
                "severity_weight": config.SEVERITY_WEIGHTS.get((f.get("severity") or "medium").lower(), 2),
                "confidence": confidence,
                "counted": confidence >= floor,
                "evidence_text": f.get("evidence_text"),
                "page_ref": f.get("page_ref"),
                "created_at": stamp,
            }
        )
    return signals


def normalize_year(year: int) -> dict:
    findings = store.query(
        f"SELECT * FROM `{store.table_id(config.T_FINDINGS)}` WHERE period_year = @year", year=year
    )
    themes = store.query(
        f"SELECT raw_label, canonical_theme, mapping_confidence "
        f"FROM `{store.table_id(config.T_THEMES)}` WHERE period_year = @year",
        year=year,
    )
    mapping = {t["raw_label"]: (t["canonical_theme"], float(t["mapping_confidence"] or 0.0)) for t in themes}
    signals = build_signals(findings, mapping)
    store.replace_scope(config.T_SIGNALS, year, signals)
    return {"year": year, "signals": len(signals), "counted": sum(1 for s in signals if s["counted"])}
