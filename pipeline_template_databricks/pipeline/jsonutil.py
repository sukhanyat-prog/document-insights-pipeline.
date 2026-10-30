"""Parse JSON out of a model answer (handles ```json fences and text before/after the object)."""

from __future__ import annotations

import json
import re


def parse_json_text(text: str) -> dict:
    if not text or not text.strip():
        raise ValueError("The model returned an empty answer")
    cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip(), flags=re.IGNORECASE)
    try:
        value = json.loads(cleaned)
    except json.JSONDecodeError:
        start, end = cleaned.find("{"), cleaned.rfind("}")
        if start == -1 or end <= start:
            raise ValueError("The model answer does not contain a JSON object") from None
        value = json.loads(cleaned[start : end + 1])
    if not isinstance(value, dict):
        raise ValueError("Expected a JSON object")
    return value
