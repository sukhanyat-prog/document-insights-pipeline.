"""Runs the steps in order. Used by the web app (`/event`, `/run`, `/run-new`) and by scripts/run_pipeline.py.

  1 process_document  PDF -> documents + findings        (one object, idempotent)
  2 consolidate_year  findings -> themes
  3 normalize_year    findings + themes -> signals
  4 aggregate_year    signals -> scores
  5 compare_year      scores + reference -> comparison

`parse_new_files` is the "event" for platforms without push notifications: list the storage location, parse
whatever is not in the documents table yet, then run steps 2-5 for the years that changed.
"""

from __future__ import annotations

import logging
from datetime import date

from . import config, storage, store
from .aggregate import aggregate_year
from .compare import compare_year
from .consolidate import consolidate_year
from .extract import read_object
from .normalize import normalize_year
from .paths import build_doc_id, extract_object_name, parse_object_path

logger = logging.getLogger(__name__)


def _iso_date(value: str | None) -> str | None:
    try:
        return date.fromisoformat(value[:10]).isoformat() if value else None
    except ValueError:
        return None


def process_document(object_name: str) -> dict:
    """Parse one object and replace its rows. Safe to run twice for the same file."""
    doc_id = build_doc_id(object_name)
    store.log_status(doc_id, object_name, "started")
    try:
        extraction, meta = read_object(object_name)
        stamp = store.now_iso()

        store.delete_where(config.T_DOCUMENTS, "doc_id = :doc_id", doc_id=doc_id)
        store.delete_where(config.T_FINDINGS, "doc_id = :doc_id", doc_id=doc_id)
        store.load_rows(
            config.T_DOCUMENTS,
            [{
                "doc_id": doc_id, "source": meta.source, "period_year": meta.year,
                "object_path": object_name, "title": extraction.title,
                "summary": extraction.summary, "document_date": _iso_date(extraction.document_date),
                "findings_count": len(extraction.findings), "parsed_at": stamp,
            }],
        )
        store.load_rows(
            config.T_FINDINGS,
            [{
                "doc_id": doc_id, "source": meta.source, "period_year": meta.year,
                "raw_label": f.theme_hint.strip(), "direction": f.direction, "severity": f.severity,
                "evidence_text": f.evidence_text[:500], "page_ref": f.page_ref,
                "confidence": f.confidence, "created_at": stamp,
            } for f in extraction.findings if f.theme_hint.strip()],
        )
        store.log_status(doc_id, object_name, "parsed", f"{len(extraction.findings)} findings")
        return {"doc_id": doc_id, "year": meta.year, "source": meta.source, "findings": len(extraction.findings)}
    except Exception as exc:
        logger.exception("Parse failed for %s", object_name)
        store.log_status(doc_id, object_name, "error", str(exc))
        raise


def run_after_steps(year: int, *, with_comparison: bool = True) -> dict:
    """Steps 2-5 for one year. Each step rewrites that year only."""
    result = {
        "consolidate": consolidate_year(year),
        "normalize": normalize_year(year),
        "aggregate": aggregate_year(year),
    }
    if with_comparison:
        result["compare"] = compare_year(year)
    return result


def handle_event(payload: dict) -> dict:
    """Manual / scheduler / job entry point: {"name": "2026/Acme/note.pdf"}."""
    object_name = extract_object_name(payload)
    if not object_name.lower().endswith(".pdf"):
        return {"status": "ignored", "object_name": object_name, "reason": "not a PDF"}

    parsed = process_document(object_name)
    result = {"status": "ok", "parsed": parsed}
    if config.AUTO_REFRESH:
        result["refresh"] = run_after_steps(parsed["year"])
    return result


def parse_new_files(year: int | None = None) -> dict:
    """Parse every PDF in storage that has no row in the documents table, then refresh the affected years."""
    prefix = f"{year}/" if year else ""
    names = storage.list_pdfs(prefix)
    done = {r["doc_id"] for r in store.query(f"SELECT doc_id FROM {store.table_id(config.T_DOCUMENTS)}")}
    todo = [n for n in names if build_doc_id(n) not in done]

    parsed, failed, years = [], [], set()
    for name in todo:
        try:
            parsed.append(process_document(name))
            years.add(parse_object_path(name).year)
        except Exception as exc:  # keep going; the status table has the detail
            failed.append({"object_name": name, "error": str(exc)})

    refreshed = {}
    if config.AUTO_REFRESH:
        for y in sorted(years):
            refreshed[y] = run_after_steps(y)
    return {"found": len(names), "new": len(todo), "parsed": len(parsed), "failed": failed, "refreshed_years": sorted(refreshed)}
