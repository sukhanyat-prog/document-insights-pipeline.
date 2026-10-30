"""Google Cloud clients. Credentials are resolved once and shared.

Order:
  1. GCP_SERVICE_ACCOUNT_JSON       service-account JSON held in an env var / secret
  2. GOOGLE_APPLICATION_CREDENTIALS path to a key file
  3. secrets/service-account.json   local development only (git-ignored)
  4. Application Default Credentials (the Cloud Run service account) - recommended in production
"""

from __future__ import annotations

import json
import os
from functools import lru_cache
from pathlib import Path

from . import config

_SCOPES = ["https://www.googleapis.com/auth/cloud-platform"]


@lru_cache(maxsize=1)
def credentials():
    from google.oauth2 import service_account

    raw = os.environ.get("GCP_SERVICE_ACCOUNT_JSON")
    if raw:
        return service_account.Credentials.from_service_account_info(json.loads(raw), scopes=_SCOPES)

    key_path = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
    if key_path and Path(key_path).is_file():
        return service_account.Credentials.from_service_account_file(key_path, scopes=_SCOPES)

    if config.LOCAL_KEY_FILE.is_file():
        return service_account.Credentials.from_service_account_file(str(config.LOCAL_KEY_FILE), scopes=_SCOPES)

    import google.auth

    creds, _ = google.auth.default(scopes=_SCOPES)
    return creds


@lru_cache(maxsize=1)
def bq_client():
    from google.cloud import bigquery

    return bigquery.Client(project=config.GOOGLE_CLOUD_PROJECT, credentials=credentials())


@lru_cache(maxsize=1)
def gcs_client():
    from google.cloud import storage

    return storage.Client(project=config.GOOGLE_CLOUD_PROJECT, credentials=credentials())


@lru_cache(maxsize=1)
def genai_client():
    from google import genai

    return genai.Client(
        vertexai=True,
        project=config.GOOGLE_CLOUD_PROJECT,
        location=config.GOOGLE_CLOUD_LOCATION,
        credentials=credentials(),
    )
