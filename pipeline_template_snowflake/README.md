# Pipeline template (Snowflake): documents -> findings -> themes -> scores -> comparison -> dashboard

The same template as `../pipeline_template` (GCP), rebuilt on Snowflake services. Same flow, same module names, same tests.

1. People or systems drop **PDF documents** into a Snowflake **internal stage**.
2. **Snowflake Cortex** (`SNOWFLAKE.CORTEX.COMPLETE`) reads each document's text and returns structured findings. Document text stays inside Snowflake.
3. Free-text labels are **consolidated** into a short list of canonical themes.
4. Themes are **scored**, then **compared with your own reference table**.
5. A **Flask dashboard**, hosted on **Snowpark Container Services**, shows scores, comparison status and blind spots.

Everything project-specific lives in `.env` (or the service spec when hosted), `pipeline/prompts.py`, `pipeline/models.py` and `pipeline/schemas.py`.

```
 PDF in stage --(scheduled / manual: parse-new)--> 1 extract    -> tpl_documents, tpl_findings
                                                   2 consolidate  labels -> <= MAX_THEMES themes -> tpl_themes
                                                   3 normalize    findings + themes -> signals   -> tpl_signals
                                                   4 aggregate    signals -> score 0-100 + band  -> tpl_scores
                                                   5 compare      scores vs tpl_reference        -> tpl_comparison
                                                   dashboard (container service) reads the tables
```

## GCP -> Snowflake mapping

| Concern | GCP template | This template |
|---|---|---|
| Document storage | Cloud Storage bucket | Internal stage `@DB.SCHEMA.DOCUMENTS` with server-side encryption (`pipeline/storage.py`) |
| Tables | BigQuery | Snowflake tables through a Snowpark session (`pipeline/clients.py`, `store.py`) |
| Model | Gemini on Vertex AI reads the PDF | Cortex `COMPLETE(model, prompt)` (`pipeline/llm.py`). It reads **text**, so `pipeline/pdf_text.py` extracts it with `pypdf` |
| Event | Eventarc POST to `/event` | **Polling**: `parse-new` from a schedule or the `/process-new` button. `/event` works if you post to it yourself |
| Hosting | Cloud Run + Docker | Docker image on Snowpark Container Services (`Dockerfile`, `deploy/*.sql`) |
| Secret | Secret Manager | Snowflake `SECRET` object exposed as `SECRET_KEY` |
| Permissions | IAM roles | Snowflake role and grants (`deploy/setup.sql`) |
| Source and year | blob metadata or path | **path only**: `<year>/<source>/<file>.pdf` |

## Quick start (local)

```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env             # set account, user, role, warehouse, database, schema
# run deploy/setup.sql once in a worksheet (role, database, warehouse, Cortex grant)

python scripts/run_pipeline.py setup                  # schema, stage, tables
python scripts/run_pipeline.py load-reference --csv examples/reference_example.csv --year 2026
python scripts/run_pipeline.py parse 2026/Some_Source/file.pdf
python scripts/run_pipeline.py parse-new              # parse every PDF not yet in the documents table
python scripts/run_pipeline.py after --year 2026      # steps 2-5
python app.py                                         # http://localhost:8080/
```

Run the tests (no account needed): `python -m unittest discover -s tests -v`

## What is where

| Path | What it does | Change it when |
|---|---|---|
| `.env` / `pipeline/config.py` | account, database, schema, stage, warehouse, Cortex model, tables, thresholds | every new project |
| `pipeline/schemas.py` | every table and column (portable types) | you add or rename fields |
| `pipeline/models.py`, `prompts.py` | the JSON the model returns; the prompts | you extract different things |
| `pipeline/clients.py` | connection and authentication (SPCS token, key pair, browser SSO, password) | auth method changes |
| `pipeline/store.py` | SQL helpers: `:name` to `?` parameters, insert via JSON payload, delete-then-load, DDL | rarely |
| `pipeline/storage.py` | stage put, get, list | other storage |
| `pipeline/llm.py` | one function, `complete(prompt)` | another model |
| `pipeline/pdf_text.py`, `jsonutil.py` | PDF to text; tolerant JSON parsing | scanned PDFs (add OCR) |
| `pipeline/extract.py` | step 1 (`DOMAIN_DESCRIPTION` at the top) | other input types |
| `consolidate.py`, `normalize.py`, `scoring.py`, `aggregate.py`, `compare.py` | steps 2-5 | your own rules |
| `pipeline/orchestrator.py` | runs the steps; `handle_event`, `parse_new_files` | add or remove a step |
| `pipeline/web.py`, `app.py`, `templates/`, `static/` | Flask app | new pages |
| `Dockerfile`, `.dockerignore` | image for the container service | different base |
| `deploy/setup.sql`, `service.sql`, `deploy.sh` | role, pool, repository, secret; the service; build and push | environment |
| `tests/` | offline tests with a fake model and fake store | whenever you change logic |

Step-by-step guide: [`docs/ADAPTING.md`](docs/ADAPTING.md).

## Endpoints

| Method | Path (under `URL_PATH_PREFIX`) | Purpose |
|---|---|---|
| GET | `/` , `/api/dashboard` | dashboard, and its data as JSON (`?year=`) |
| GET, POST | `/upload` | upload a PDF to `<year>/<source>/<file>.pdf` on the stage |
| POST | `/process-new` | browser button: parse every new PDF, then refresh |
| POST | `/event` | `{"name": "2026/Source/file.pdf"}`: parse that file, then steps 2-5 for its year |
| POST | `/run-new` | same as `parse-new` for a scheduler |
| POST | `/run?year=` | re-run steps 2-5 |
| GET | `/health` | liveness |

`/event`, `/run-new` and `/run` are CSRF-exempt. The app has **no login of its own**: reach it only through the Snowflake-authenticated service endpoint and keep it private.

## Deploy (Snowpark Container Services)

1. Run `deploy/setup.sql` as ACCOUNTADMIN (edit names; paste a generated key into the secret).
2. `python scripts/run_pipeline.py setup` to create the stage and tables.
3. `bash deploy/deploy.sh` builds the image, pushes it to the image repository and creates the service from `deploy/service.sql`. This needs Docker and the Snowflake CLI.
4. Open the URL from `SHOW ENDPOINTS IN SERVICE ...`.
5. Parsing new files: schedule `python scripts/run_pipeline.py parse-new` (a task that runs a job service; the example at the bottom of `service.sql` is commented out) or use the dashboard's button.

## Behaviour notes

- **Idempotent:** parsing a file again replaces its rows; steps 2-5 rewrite one year at a time.
- **Cap and floor:** at most `MAX_THEMES` themes; a signal counts only if finding confidence x mapping confidence >= `CONFIDENCE_FLOOR`.
- **Text, not images:** a PDF with no extractable text fails with a clear message and is listed in `failed`. Text beyond `MAX_DOC_CHARS` is cut; check your Cortex model's context window.
- **Column names:** Snowflake returns upper-case names; `store` lower-cases them so the code matches the other templates.
- **Fallback:** if the consolidation call fails, labels are grouped by spelling.

## Not verified against a live account

Logic, Flask routes, SQL generation, parameter conversion and event handling were tested offline. These were written from the documentation and **have not been run on Snowflake**; check them in a sandbox first:

- Snowpark `session.sql(stmt, params=[...])` with `?` placeholders on your connector version, and the `FLATTEN(PARSE_JSON(?))` insert.
- `SNOWFLAKE.CORTEX.COMPLETE` availability in your region, the model name, and its context size.
- Stage `LIST` output format, `put_stream` / `get_stream` behaviour.
- The service specification, secret reference and endpoint syntax in `deploy/service.sql`, and the task example for scheduling.
