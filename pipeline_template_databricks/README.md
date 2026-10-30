# Pipeline template (Databricks): documents -> findings -> themes -> scores -> comparison -> dashboard

The same template as `../pipeline_template` (GCP), rebuilt on Databricks services. Same flow, same module names, same tests.

1. People or systems drop **PDF documents** into a **Unity Catalog volume**.
2. A **model-serving endpoint** (Foundation Model API or your own) reads each document's text and returns structured findings.
3. Free-text labels are **consolidated** into a short list of canonical themes.
4. Themes are **scored**, then **compared with your own reference table**.
5. A **Flask dashboard**, hosted as a **Databricks App**, shows scores, comparison status and blind spots.

Everything project-specific lives in `.env` (or `app.yaml` when hosted), `pipeline/prompts.py`, `pipeline/models.py` and `pipeline/schemas.py`.

```
 PDF in volume --(job file-arrival trigger: parse-new)--> 1 extract    -> tpl_documents, tpl_findings
                                                          2 consolidate  labels -> <= MAX_THEMES themes -> tpl_themes
                                                          3 normalize    findings + themes -> signals   -> tpl_signals
                                                          4 aggregate    signals -> score 0-100 + band  -> tpl_scores
                                                          5 compare      scores vs tpl_reference        -> tpl_comparison
                                                          dashboard (Databricks App) reads the Delta tables
```

## GCP -> Databricks mapping

| Concern | GCP template | This template |
|---|---|---|
| Document storage | Cloud Storage bucket | Unity Catalog volume `/Volumes/<catalog>/<schema>/<volume>` (Files API in `pipeline/storage.py`) |
| Tables | BigQuery | Delta tables in `<catalog>.<schema>`, queried through a SQL warehouse (`pipeline/clients.py`, `store.py`) |
| Model | Gemini on Vertex AI reads the PDF | Serving endpoint via the OpenAI-compatible client (`pipeline/llm.py`). It reads **text**, so `pipeline/pdf_text.py` extracts it with `pypdf` |
| Event | Eventarc POST to `/event` | Job **file-arrival trigger** runs `parse-new` (`databricks.yml`). `/event` still works if you post to it yourself |
| Hosting | Cloud Run + Docker | Databricks Apps (`app.yaml`, `serve.py`), no Docker |
| Secret | Secret Manager | App resource of type secret, exposed as `SECRET_KEY` |
| Permissions | IAM roles | Unity Catalog grants (`deploy/grants.sql`) for the app's service principal |
| Source and year | blob metadata or path | **path only**: `<year>/<source>/<file>.pdf` |

## Quick start (local)

```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env             # set host, warehouse id, catalog, schema, volume, endpoint
databricks auth login --host https://<workspace>      # or DATABRICKS_TOKEN in .env (never commit it)

python scripts/run_pipeline.py setup                  # schema, volume, tables
python scripts/run_pipeline.py load-reference --csv examples/reference_example.csv --year 2026
python scripts/run_pipeline.py parse 2026/Some_Source/file.pdf
python scripts/run_pipeline.py parse-new              # parse every PDF not yet in the documents table
python scripts/run_pipeline.py after --year 2026      # steps 2-5
python app.py                                         # http://localhost:8080/
```

Run the tests (no workspace needed): `python -m unittest discover -s tests -v`

## What is where

| Path | What it does | Change it when |
|---|---|---|
| `.env` / `pipeline/config.py` | catalog, schema, volume, warehouse, endpoint, table names, thresholds | every new project |
| `pipeline/schemas.py` | every table and column (portable types) | you add or rename fields |
| `pipeline/models.py`, `prompts.py` | the JSON the model returns; the prompts | you extract different things |
| `pipeline/clients.py` | auth, SQL warehouse connection, OpenAI-compatible client | auth method changes |
| `pipeline/store.py` | SQL helpers: insert via JSON payload, delete-then-load, DDL | rarely |
| `pipeline/storage.py` | volume read, write, list | other storage |
| `pipeline/llm.py` | one function, `complete(prompt)` | another model API |
| `pipeline/pdf_text.py`, `jsonutil.py` | PDF to text; tolerant JSON parsing | scanned PDFs (add OCR) |
| `pipeline/extract.py` | step 1 (`DOMAIN_DESCRIPTION` at the top) | other input types |
| `consolidate.py`, `normalize.py`, `scoring.py`, `aggregate.py`, `compare.py` | steps 2-5 | your own rules |
| `pipeline/orchestrator.py` | runs the steps; `handle_event`, `parse_new_files` | add or remove a step |
| `pipeline/web.py`, `app.py`, `templates/`, `static/` | Flask app | new pages |
| `app.yaml`, `serve.py` | Databricks Apps run command and environment | different env |
| `databricks.yml` | job with the file-arrival trigger (asset bundle) | cluster, schedule |
| `deploy/grants.sql`, `deploy/deploy.sh` | grants; one-shot deploy | environment |
| `tests/` | offline tests with a fake model and fake store | whenever you change logic |

Step-by-step guide: [`docs/ADAPTING.md`](docs/ADAPTING.md).

## Endpoints

| Method | Path (under `URL_PATH_PREFIX`) | Purpose |
|---|---|---|
| GET | `/` , `/api/dashboard` | dashboard, and its data as JSON (`?year=`) |
| GET, POST | `/upload` | upload a PDF to `<year>/<source>/<file>.pdf` in the volume |
| POST | `/process-new` | browser button: parse every new PDF, then refresh |
| POST | `/event` | `{"name": "2026/Source/file.pdf"}`: parse that file, then steps 2-5 for its year |
| POST | `/run-new` | same as `parse-new` for a scheduler |
| POST | `/run?year=` | re-run steps 2-5 (e.g. after a new reference table) |
| GET | `/health` | liveness |

`/event`, `/run-new` and `/run` are CSRF-exempt. The app has **no login of its own**: Databricks Apps puts workspace authentication in front of it, so keep it that way and do not expose it elsewhere.

## Deploy

1. Create a SQL warehouse; note its id. Put it in `.env`.
2. `python scripts/run_pipeline.py setup`.
3. `deploy/deploy.sh` syncs the code, creates and deploys the app and deploys the bundle. In the app's settings add the resources named in `app.yaml` (`sql-warehouse`, `secret-key`).
4. Run `deploy/grants.sql` (edit the principal name) so the app's service principal can use the schema, volume and warehouse.
5. Edit `databricks.yml` (host, node type, runtime) before `databricks bundle deploy`.

## Behaviour notes

- **Idempotent:** parsing a file again replaces its rows; steps 2-5 rewrite one year at a time.
- **Cap and floor:** at most `MAX_THEMES` themes; a signal counts only if finding confidence x mapping confidence >= `CONFIDENCE_FLOOR`.
- **Text, not images:** a PDF with no extractable text (a scan) fails with a clear message and is listed in `failed`; add OCR in `pdf_text.py` if you need it. Text beyond `MAX_DOC_CHARS` is cut.
- **Fallback:** if the consolidation call fails, labels are grouped by spelling so the run still finishes.

## Not verified against a live workspace

The logic, Flask routes, SQL generation and the file-listing and event handling were tested offline. These parts were written from the documentation and **have not been run on Databricks**; check them in a sandbox first:

- `app.yaml` `valueFrom` resource names, and how your workspace exposes the warehouse id and secret.
- `databricks.yml` job syntax, the file-arrival trigger URL and the node type.
- Whether your serving endpoint accepts `response_format` (set `LLM_JSON_MODE=false` if not) and its context size versus `MAX_DOC_CHARS`.
- The `from_json(...)` insert form against your runtime, and Files API calls on your SDK version.
