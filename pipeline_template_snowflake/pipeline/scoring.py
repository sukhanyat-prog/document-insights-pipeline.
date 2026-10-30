"""Score formula and bands. Pure functions - change the maths here.

    coverage  = sources citing the theme / total sources            (0..1)
    intensity = average severity weight / highest weight            (0..1)
    score     = 100 x (W_COVERAGE x coverage + W_INTENSITY x intensity)

Bands: High >= BAND_HIGH_MIN, Medium >= BAND_MEDIUM_MIN, otherwise Low.
"""

from __future__ import annotations

from collections import Counter, defaultdict

from . import config

BAND_ORDER = {"Low": 0, "Medium": 1, "High": 2}


def band_for(score: float | None) -> str | None:
    if score is None:
        return None
    if score >= config.BAND_HIGH_MIN:
        return "High"
    if score >= config.BAND_MEDIUM_MIN:
        return "Medium"
    return "Low"


def score_value(coverage: float, intensity: float) -> float:
    raw = 100.0 * (config.SCORE_WEIGHT_COVERAGE * coverage + config.SCORE_WEIGHT_INTENSITY * intensity)
    return round(max(0.0, min(100.0, raw)), 1)


def score_themes(signals: list[dict], year: int, sources_total: int | None = None, computed_at: str | None = None) -> list[dict]:
    """One row per theme from the signals that count. `sources_total` defaults to SOURCES_TOTAL, then to the
    number of distinct sources seen in this year's signals."""
    counted = [s for s in signals if s.get("counted")]
    all_sources = {s["source"] for s in signals if s.get("source")}
    total = sources_total or config.SOURCES_TOTAL or len(all_sources) or 1
    max_weight = max(config.SEVERITY_WEIGHTS.values())

    by_theme: dict[str, list[dict]] = defaultdict(list)
    for s in counted:
        by_theme[s["canonical_theme"]].append(s)

    rows = []
    for theme, items in by_theme.items():
        sources = {i["source"] for i in items if i.get("source")}
        coverage = min(len(sources) / total, 1.0)
        avg_sev = sum(i["severity_weight"] for i in items) / len(items)
        directions = Counter(i["direction"] for i in items)
        score = score_value(coverage, avg_sev / max_weight)
        rows.append(
            {
                "period_year": year,
                "canonical_theme": theme,
                "sources_count": len(sources),
                "sources_total": total,
                "sources_citing": f"{len(sources)} of {total}",
                "mention_count": len(items),
                "avg_severity": round(avg_sev, 2),
                "score": score,
                "band": band_for(score),
                "direction": directions.most_common(1)[0][0],
                "avg_confidence": round(sum(i["confidence"] for i in items) / len(items), 3),
                "computed_at": computed_at,
            }
        )
    rows.sort(key=lambda r: (-r["score"], -r["mention_count"], r["canonical_theme"]))
    return rows
