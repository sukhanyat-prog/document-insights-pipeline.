"""PDF bytes -> plain text with [page N] markers (the models here read text, not PDF files)."""

from __future__ import annotations

import io

from pypdf import PdfReader

from . import config


class NoTextError(ValueError):
    """The PDF has no text layer (for example a scan)."""


def pdf_to_text(pdf_bytes: bytes, max_chars: int | None = None) -> str:
    limit = max_chars or config.MAX_DOC_CHARS
    reader = PdfReader(io.BytesIO(pdf_bytes))
    parts: list[str] = []
    total = 0
    for number, page in enumerate(reader.pages, start=1):
        text = (page.extract_text() or "").strip()
        if not text:
            continue
        chunk = f"[page {number}]\n{text}"
        parts.append(chunk)
        total += len(chunk)
        if total >= limit:
            break
    if not parts:
        raise NoTextError("No extractable text in this PDF (scanned image?). Run OCR first.")
    return "\n\n".join(parts)[:limit]
