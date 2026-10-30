# The three implementations: GCP, Databricks, Snowflake

`pipeline_template/` (GCP), `pipeline_template_databricks/` and `pipeline_template_snowflake/` implement the same flow with the same module names:

documents -> LLM findings -> consolidated themes (capped) -> normalized signals (confidence floor) -> score and band -> comparison with a reference table -> Flask dashboard.

Steps 2-5 (`consolidate`, `normalize`, `scoring`/`aggregate`, `compare`) and the Flask pages are the same logic in all three. Only the platform edge changes: where files live, where tables live, which model is called, how new files are noticed and where the app runs.

## Side by side

| | GCP (`pipeline_template`) | Databricks | Snowflake |
|---|---|---|---|
| Files | Cloud Storage bucket | Unity Catalog volume | Internal stage |
| Tables | BigQuery | Delta tables via SQL warehouse | Snowflake tables via Snowpark |
| Model input | the **PDF itself** (Gemini reads it) | **text** extracted with `pypdf` | **text** extracted with `pypdf` |
| Model | Gemini on Vertex AI | serving endpoint (OpenAI-compatible) | Cortex `COMPLETE` |
| New-file trigger | Eventarc POST to `/event` | job file-arrival trigger running `parse-new` | schedule or button running `parse-new` (`/event` also accepted) |
| Hosting | Cloud Run (Docker) | Databricks Apps (no Docker) | Snowpark Container Services (Docker) |
| Secret | Secret Manager | app secret resource | Snowflake `SECRET` |
| Access control | IAM, IAP | workspace auth in front of the app, UC grants | Snowflake roles and service endpoint roles |
| Source / year | blob metadata or path | path | path |
| Insert technique | BigQuery load job | one JSON parameter parsed in SQL (`from_json` + `explode`) | one JSON parameter parsed in SQL (`PARSE_JSON` + `FLATTEN`) |
| Local login | `gcloud auth application-default login` | `databricks auth login` or token | browser SSO, key pair or password |
| Offline tests | 29 | 43 | 48 |

## Things that differ in behaviour

- **Scanned PDFs.** Gemini can read page images; the other two templates read text only, so a scan fails with a clear message until you add OCR to `pipeline/pdf_text.py`.
- **Long documents.** The Databricks and Snowflake templates cut text at `MAX_DOC_CHARS`; check it against your model's context window. The GCP template sends the whole file.
- **JSON reliability.** Text models sometimes wrap JSON in prose or code fences; `pipeline/jsonutil.py` tolerates that. Validators in `models.py` clamp confidence and normalise `direction` and `severity`.
- **Event model.** Only GCP pushes events. The other two poll for files that are not yet in the documents table, so a failed file is retried on the next run.
- **Concurrency.** All three assume one writer at a time per year (GCP: Cloud Run concurrency 1; Databricks: `max_concurrent_runs: 1`; Snowflake: one service instance).

## Choosing

- Data and teams already on one platform: use that platform's template; document text then stays in it.
- Need to read scanned or image-heavy PDFs without extra work: GCP (Gemini reads the file).
- Need the app to run without building a Docker image: Databricks Apps.

## Status

Offline tests pass for all three (fake model, fake store, Flask test client). The Databricks and Snowflake variants have **not been run on live services**; each README lists the specific calls to check first.
