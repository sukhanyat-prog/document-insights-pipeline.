"""Documents live on an internal stage:  @<database>.<schema>.<stage>/<year>/<source>/<file>.pdf

Object names used everywhere else in the code are relative to the stage root (``2026/Acme/note.pdf``).
The stage is created with server-side encryption so files can be read back as streams.
"""

from __future__ import annotations

import io

from . import config
from .clients import run_sql, session


def stage_path(object_name: str = "") -> str:
    suffix = object_name.lstrip("/")
    return f"@{config.STAGE_FQN}/{suffix}" if suffix else f"@{config.STAGE_FQN}"


def location_label() -> str:
    return stage_path()


def read_object_bytes(object_name: str) -> bytes:
    stream = session().file.get_stream(stage_path(object_name))
    try:
        return stream.read()
    finally:
        stream.close()


def write_object(object_name: str, data: bytes) -> str:
    path = stage_path(object_name)
    session().file.put_stream(io.BytesIO(data), path, auto_compress=False, overwrite=True)
    return path


def list_pdfs(prefix: str = "") -> list[str]:
    """All .pdf object names under `prefix`, relative to the stage root."""
    target = stage_path(prefix.rstrip("/") + "/" if prefix else "")
    found = []
    for row in run_sql(f"LIST {target}"):
        name = row["name"]  # "<stage_name>/<year>/<source>/<file>.pdf"
        if name.lower().endswith(".pdf"):
            found.append(name.split("/", 1)[1] if "/" in name else name)
    return sorted(found)
