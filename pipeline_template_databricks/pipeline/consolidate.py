"""Step 2 - consolidate free-text labels into at most MAX_THEMES canonical themes.

Flow for one year:
  1. count the raw labels in the findings table
  2. ask Gemini to group the most frequent labels (optional preferred names guide it)
  3. `build_mapping` (pure, tested) checks the answer: every label mapped once, names snapped to
     the preferred vocabulary, leftovers fuzzy-matched, then the cap is enforced by merging the
     smallest themes into their closest neighbour
  4. write raw_label -> canonical_theme rows to the themes table

If the model call fails, labels are grouped by normalised spelling and the cap still applies,
so the pipeline always finishes.
"""

from __future__ import annotations

import difflib
import json
import logging
import re
from collections import Counter
from typing import Callable

from . import config, store
from . import llm
from .jsonutil import parse_json_text
from .prompts import CONSOLIDATION_PROMPT

logger = logging.getLogger(__name__)

Mapping = dict[str, tuple[str, float, str]]  # raw_label -> (canonical, confidence, method)


def normalize_label(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (text or "").lower()).strip()


def _ratio(a: str, b: str) -> float:
    return difflib.SequenceMatcher(None, normalize_label(a), normalize_label(b)).ratio()


def load_preferred() -> list[str]:
    path = config.PREFERRED_THEMES_FILE
    if not path.is_file():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    names = data.get("themes", data) if isinstance(data, dict) else data
    return [str(n).strip() for n in names if str(n).strip()]


def snap_to_preferred(name: str, preferred: list[str], cutoff: float = 0.85) -> tuple[str, bool]:
    """Return (name, snapped). A close match to a preferred name is replaced by that preferred name."""
    best, best_score = None, 0.0
    for candidate in preferred:
        score = _ratio(name, candidate)
        if score > best_score:
            best, best_score = candidate, score
    if best and best_score >= cutoff:
        return best, True
    return name.strip(), False


def build_mapping(
    label_counts: dict[str, int],
    groups: list[dict],
    preferred: list[str] | None = None,
    max_themes: int = 25,
) -> Mapping:
    """Turn the model's groups into a complete raw_label -> canonical mapping that respects the cap."""
    preferred = preferred or []
    by_norm = {normalize_label(label): label for label in label_counts}
    mapping: Mapping = {}

    # 1. model groups (each label used once; unknown labels in the answer are ignored)
    for group in groups or []:
        canonical = str(group.get("canonical", "")).strip()
        if not canonical:
            continue
        canonical, snapped = snap_to_preferred(canonical, preferred)
        for member in group.get("members", []):
            raw = by_norm.get(normalize_label(str(member)))
            if raw is None or raw in mapping:
                continue
            mapping[raw] = (canonical, 0.95 if snapped else 0.9, "preferred" if snapped else "llm")

    # 2. labels the model skipped: nearest existing canonical, else a theme of their own
    known = sorted({c for c, _, _ in mapping.values()})
    for raw in sorted(label_counts, key=lambda k: -label_counts[k]):
        if raw in mapping:
            continue
        near = max(known, key=lambda c: _ratio(raw, c), default=None)
        if near and _ratio(raw, near) >= 0.6:
            mapping[raw] = (near, 0.7, "fuzzy")
        else:
            name, snapped = snap_to_preferred(raw.strip().title(), preferred)
            mapping[raw] = (name, 0.6, "preferred" if snapped else "unmapped")
            if name not in known:
                known.append(name)

    # 3. enforce the cap: merge the lightest themes into their closest kept theme
    weight: Counter[str] = Counter()
    for raw, (canonical, _, _) in mapping.items():
        weight[canonical] += label_counts.get(raw, 0)
    if len(weight) > max_themes:
        keep = [name for name, _ in weight.most_common(max_themes)]
        for raw, (canonical, conf, method) in list(mapping.items()):
            if canonical in keep:
                continue
            target = max(keep, key=lambda k: _ratio(canonical, k))
            mapping[raw] = (target, min(conf, 0.5), "cap_merge")
    return mapping


def fallback_groups(label_counts: dict[str, int]) -> list[dict]:
    """No model: group labels that only differ by case or punctuation."""
    groups: dict[str, list[str]] = {}
    for raw in sorted(label_counts, key=lambda k: -label_counts[k]):
        groups.setdefault(normalize_label(raw), []).append(raw)
    return [{"canonical": members[0].strip().title(), "members": members} for members in groups.values()]


def ask_model(label_counts: dict[str, int], preferred: list[str]) -> list[dict]:
    top = sorted(label_counts, key=lambda k: -label_counts[k])[: config.MAX_LABELS_FOR_LLM]
    preferred_block = (
        "- Prefer these names when a group fits one of them: " + "; ".join(preferred) if preferred else ""
    )
    prompt = CONSOLIDATION_PROMPT.format(
        max_themes=config.MAX_THEMES,
        preferred_block=preferred_block,
        labels="\n".join(f"- {label} ({label_counts[label]})" for label in top),
    )
    return parse_json_text(llm.complete(prompt)).get("groups", [])


def consolidate_year(year: int, model: Callable[[dict[str, int], list[str]], list[dict]] | None = ask_model) -> dict:
    """Rebuild the themes table for one year from the findings table."""
    rows = store.query(
        f"SELECT raw_label, COUNT(*) AS n FROM {store.table_id(config.T_FINDINGS)} "
        "WHERE period_year = :year AND raw_label IS NOT NULL GROUP BY raw_label",
        year=year,
    )
    label_counts = {r["raw_label"]: int(r["n"]) for r in rows if (r["raw_label"] or "").strip()}
    if not label_counts:
        store.replace_scope(config.T_THEMES, year, [])
        return {"year": year, "labels": 0, "themes": 0}

    preferred = load_preferred()
    try:
        groups = model(label_counts, preferred) if model else fallback_groups(label_counts)
    except Exception:
        logger.exception("Consolidation model call failed; grouping by spelling instead")
        groups = fallback_groups(label_counts)

    mapping = build_mapping(label_counts, groups, preferred, config.MAX_THEMES)
    stamp = store.now_iso()
    out = [
        {"period_year": year, "raw_label": raw, "canonical_theme": canonical,
         "mapping_confidence": conf, "mapping_method": method, "created_at": stamp}
        for raw, (canonical, conf, method) in mapping.items()
    ]
    store.replace_scope(config.T_THEMES, year, out)
    return {"year": year, "labels": len(label_counts), "themes": len({m[0] for m in mapping.values()})}
