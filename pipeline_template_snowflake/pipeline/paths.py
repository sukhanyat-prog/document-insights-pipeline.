"""Object naming. Layout:  <year>/<source>/<file>.pdf   e.g. 2026/Acme_Research/note.pdf

Object names are always relative to the storage root (the volume or stage). Change `parse_object_path`
and `build_object_path` if your documents are organised differently.
"""

from __future__ import annotations

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
    """Safe object name for an upload: no spaces, no path tricks."""
    safe_source = re.sub(r"[^\w .-]+", "", source).strip().replace(" ", "_").replace("..", "") or "unknown"
    base_name = re.split(r"[\\/]", filename)[-1]  # never let an upload choose a folder
    safe_name = re.sub(r"[^\w.-]+", "_", base_name).replace("..", "_").strip("_") or "document.pdf"
    return f"{int(year)}/{safe_source}/{safe_name}"


def build_doc_id(object_name: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "_", object_name).strip("_")[:128]


def extract_object_name(payload: dict[str, Any]) -> str:
    """Object name from a JSON body such as {"name": "2026/Acme/note.pdf"}.

    Also accepts "object_name", "path" and {"data": {...}}. A full location prefix
    (config.LOCATION_PREFIX, e.g. /Volumes/cat/schema/vol) is stripped.
    """
    if not payload:
        raise ValueError("Empty event payload")
    for source in (payload, payload.get("data") if isinstance(payload.get("data"), dict) else {}):
        for key in ("name", "object_name", "path"):
            value = source.get(key)
            if value:
                name = str(value)
                prefix = config.LOCATION_PREFIX
                if prefix and name.startswith(prefix):
                    name = name[len(prefix):]
                return name.lstrip("/")
    raise ValueError(f"Could not read an object name from payload keys: {list(payload)}")
