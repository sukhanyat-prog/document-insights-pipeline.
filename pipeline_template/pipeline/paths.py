"""Storage object naming. Default layout:  <year>/<source>/<file>.pdf   e.g. 2026/Acme Research/note.pdf

Change `parse_object_path` if your bucket is organised differently.
"""

from __future__ import annotations

import base64
import json
import re
from dataclasses import dataclass
from datetime import date
from typing import Any

from . import config


@dataclass(frozen=True)
class ObjectMeta:
    year: int
    source: str
    filename: str


def parse_object_path(object_name: str) -> ObjectMeta:
    parts = [p for p in object_name.split("/") if p]
    filename = parts[-1] if parts else object_name
    folders = parts[:-1]

    year = None
    if folders and re.fullmatch(r"(19|20)\d{2}", folders[0]):
        year = int(folders[0])
        folders = folders[1:]
    if year is None:
        year = config.DEFAULT_YEAR or date.today().year

    source = folders[-1].replace("_", " ").strip() if folders else "unknown"
    return ObjectMeta(year=year, source=source or "unknown", filename=filename)


def build_object_path(year: int, source: str, filename: str) -> str:
    safe_source = re.sub(r"[^\w .-]+", "", source).strip().replace(" ", "_").replace("..", "") or "unknown"
    base_name = re.split(r"[\\/]", filename)[-1]  # never let an upload choose a folder
    safe_name = re.sub(r"[^\w .()-]+", "_", base_name).replace("..", "_").strip() or "document.pdf"
    return f"{int(year)}/{safe_source}/{safe_name}"


def build_doc_id(object_name: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "_", object_name).strip("_")[:128]


def extract_storage_object(payload: dict[str, Any]) -> tuple[str, str]:
    """Return (bucket, object_name) from a direct JSON body, a CloudEvent, or a Pub/Sub push message."""
    if not payload:
        raise ValueError("Empty event payload")

    if payload.get("bucket") and payload.get("name"):
        return str(payload["bucket"]), str(payload["name"])

    data = payload.get("data")
    if isinstance(data, dict) and data.get("bucket") and data.get("name"):
        return str(data["bucket"]), str(data["name"])

    message = payload.get("message")
    if isinstance(message, dict) and message.get("data"):
        decoded = json.loads(base64.b64decode(message["data"]).decode("utf-8"))
        if decoded.get("bucket") and decoded.get("name"):
            return str(decoded["bucket"]), str(decoded["name"])

    raise ValueError(f"Could not read a storage object from payload keys: {list(payload)}")
