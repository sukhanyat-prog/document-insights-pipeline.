"""Step 1 - read one document from Cloud Storage and extract findings with Gemini."""

from __future__ import annotations

import logging

from . import config
from .clients import gcs_client, genai_client
from .models import DocumentExtraction
from .paths import ObjectMeta, parse_object_path
from .prompts import EXTRACTION_PROMPT

logger = logging.getLogger(__name__)

# Describe what the findings are about; used inside EXTRACTION_PROMPT.
DOMAIN_DESCRIPTION = "recurring themes, risks and signals that matter to the business"


def download_bytes(bucket_name: str, object_name: str) -> bytes:
    blob = gcs_client().bucket(bucket_name).blob(object_name)
    if not blob.exists():
        raise FileNotFoundError(f"Object not found: gs://{bucket_name}/{object_name}")
    return blob.download_as_bytes()


def blob_metadata(bucket_name: str, object_name: str) -> dict:
    blob = gcs_client().bucket(bucket_name).blob(object_name)
    blob.reload()
    return dict(blob.metadata or {})


def extract_document(pdf_bytes: bytes, *, source: str, year: int) -> DocumentExtraction:
    """Send the PDF and the prompt to Gemini and validate the JSON answer."""
    from google.genai import types

    prompt = EXTRACTION_PROMPT.format(domain_description=DOMAIN_DESCRIPTION, source=source or "unknown", year=year)
    response = genai_client().models.generate_content(
        model=config.GEMINI_MODEL,
        contents=[
            types.Content(
                role="user",
                parts=[
                    types.Part.from_bytes(data=pdf_bytes, mime_type="application/pdf"),
                    types.Part.from_text(text=prompt),
                ],
            )
        ],
        config=types.GenerateContentConfig(
            temperature=0.1,
            response_mime_type="application/json",
            response_schema=DocumentExtraction,
        ),
    )
    if not response.text:
        raise ValueError("Gemini returned an empty response")
    extraction = DocumentExtraction.model_validate_json(response.text)
    logger.info("Extracted %d findings", len(extraction.findings))
    return extraction


def read_object(bucket_name: str, object_name: str) -> tuple[DocumentExtraction, ObjectMeta]:
    """Download + extract one object. Blob metadata (`source`, `year`) overrides the path when present."""
    if not object_name.lower().endswith(".pdf"):
        raise ValueError(f"Not a PDF: {object_name}")

    meta = parse_object_path(object_name)
    custom = blob_metadata(bucket_name, object_name)
    source = custom.get("source") or meta.source
    try:
        year = int(custom.get("year") or meta.year)
    except ValueError:
        year = meta.year
    meta = ObjectMeta(year=year, source=source, filename=meta.filename)

    extraction = extract_document(download_bytes(bucket_name, object_name), source=meta.source, year=meta.year)
    return extraction, meta
