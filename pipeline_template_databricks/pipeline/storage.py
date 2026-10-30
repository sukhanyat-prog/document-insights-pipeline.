"""Documents live in a Unity Catalog volume:  /Volumes/<catalog>/<schema>/<volume>/<year>/<source>/<file>.pdf

Object names used everywhere else in the code are relative to the volume root (``2026/Acme/note.pdf``).
Access goes through the Databricks SDK Files API, so it works from Databricks Apps, Jobs and locally.
"""

from __future__ import annotations

import io

from . import config
from .clients import workspace_client


def volume_path(object_name: str) -> str:
    return f"{config.VOLUME_ROOT}/{object_name.lstrip('/')}"


def location_label() -> str:
    return config.VOLUME_ROOT


def read_object_bytes(object_name: str) -> bytes:
    response = workspace_client().files.download(volume_path(object_name))
    return response.contents.read()


def write_object(object_name: str, data: bytes) -> str:
    path = volume_path(object_name)
    workspace_client().files.upload(path, io.BytesIO(data), overwrite=True)
    return path


def list_pdfs(prefix: str = "") -> list[str]:
    """All .pdf object names under `prefix` (recursive), relative to the volume root."""
    root = volume_path(prefix).rstrip("/")
    found: list[str] = []
    stack = [root]
    while stack:
        directory = stack.pop()
        for entry in workspace_client().files.list_directory_contents(directory):
            if entry.is_directory:
                stack.append(entry.path)
            elif entry.path.lower().endswith(".pdf"):
                found.append(entry.path[len(config.VOLUME_ROOT) + 1 :])
    return sorted(found)
