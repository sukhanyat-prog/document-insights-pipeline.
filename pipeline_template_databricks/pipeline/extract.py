"""Step 1 - read one document from the volume, extract its text, and ask the model for findings."""

from __future__ import annotations

import logging

from . import llm, storage
from .jsonutil import parse_json_text
from .models import DocumentExtraction
from .paths import ObjectMeta, parse_object_path
from .pdf_text import pdf_to_text
from .prompts import EXTRACTION_PROMPT

logger = logging.getLogger(__name__)

# Describe what the findings are about; used inside EXTRACTION_PROMPT.
DOMAIN_DESCRIPTION = "recurring themes, risks and signals that matter to the business"


def extract_document(text: str, *, source: str, year: int) -> DocumentExtraction:
    """Send the document text and the prompt to the model and validate the JSON answer."""
    prompt = EXTRACTION_PROMPT.format(
        domain_description=DOMAIN_DESCRIPTION, source=source or "unknown", year=year, document_text=text
    )
    extraction = DocumentExtraction.model_validate(parse_json_text(llm.complete(prompt)))
    logger.info("Extracted %d findings", len(extraction.findings))
    return extraction


def read_object(object_name: str) -> tuple[DocumentExtraction, ObjectMeta]:
    """Read + extract one object. Source and year come from the path (<year>/<source>/<file>.pdf)."""
    if not object_name.lower().endswith(".pdf"):
        raise ValueError(f"Not a PDF: {object_name}")
    meta = parse_object_path(object_name)
    text = pdf_to_text(storage.read_object_bytes(object_name))
    return extract_document(text, source=meta.source, year=meta.year), meta
