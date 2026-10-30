"""Runs the steps in order. Used by the web app (`/event`, `/run`) and by scripts/run_pipeline.py.

  1 process_document  PDF -> documents + findings        (one object, idempotent)
  2 consolidate_year  findings -> themes
  3 normalize_year    findings + themes -> signals
  4 aggregate_year    signals -> scores
  5 compare_year      scores + reference -> comparison
"""

from __future__ import annotations

import logging
from datetime import date

from . import config, store
from .aggregate import aggregate_year
from .compare import compare_year
from .consolidate import consolidate_year
from .extract import read_object
from .normalize import normalize_year
from .paths import build_doc_id, extract_storage_object

logger = logging.getLogger(__name__)


def _iso_date(value: str | None) -> str | None:
    try:
        return date.fromisoformat(value[:10]).isoformat() if value else None
    except ValueError:
        return None


def process_document(bucket: str, object_name: str) -> dict:
    """Parse one object and replace its rows. Safe to run twice for the same file."""
    doc_id = build_doc_id(object_name)
    store.log_status(doc_id, object_name, "started")
    try:
        extraction, meta = read_object(bucket, object_name)
        stamp = store.now_iso()

        store.delete_where(config.T_DOCUMENTS, "doc_id = @doc_id", doc_id=doc_id)
        store.delete_where(config.T_FINDINGS, "doc_id = @doc_id", doc_id=doc_id)
        store.load_rows(
            config.T_DOCUMENTS,
            [{
                "doc_id": doc_id, "source": meta.source, "period_year": meta.year,
                "gcs_uri": f"gs://{bucket}/{object_name}", "title": extraction.title,
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
    """Eventarc / Pub/Sub / manual JSON entry point."""
    bucket, object_name = extract_storage_object(payload)
    if not object_name.lower().endswith(".pdf"):
        return {"status": "ignored", "object_name": object_name, "reason": "not a PDF"}

    parsed = process_document(bucket, object_name)
    result = {"status": "ok", "parsed": parsed}
    if config.AUTO_REFRESH:
        result["refresh"] = run_after_steps(parsed["year"])
    return result
