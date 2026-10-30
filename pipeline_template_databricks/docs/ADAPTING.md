# Adapting the Databricks template to a new project

Work top to bottom. Steps 1-4 give a first run; the rest tune it.

## 1. Copy and rename

```powershell
Copy-Item -Recurse pipeline_template_databricks my_new_pipeline
cd my_new_pipeline
git init -b main
```

Set `APP_NAME` and `APP_TITLE` in `.env`. The Python package is called `pipeline`; renaming it is optional (update imports in `app.py`, `scripts/run_pipeline.py`, `serve.py` and `tests/`).

## 2. Point it at your workspace

| Setting | Meaning |
|---|---|
| `DATABRICKS_HOST`, `DATABRICKS_CONFIG_PROFILE` or `DATABRICKS_TOKEN` | local login only. Inside Apps and Jobs credentials are automatic |
| `DATABRICKS_WAREHOUSE_ID` (or `DATABRICKS_HTTP_PATH`) | SQL warehouse that runs every query |
| `DBX_CATALOG`, `DBX_SCHEMA` | where the tables live; one schema per pipeline keeps them isolated |
| `DBX_VOLUME` | volume that receives the PDFs: `/Volumes/<catalog>/<schema>/<volume>` |
| `TABLE_PREFIX` | prefix for all eight tables; or override one table with `T_FINDINGS=...` |
| `LLM_ENDPOINT` | serving endpoint name; `LLM_JSON_MODE=false` if it rejects `response_format`; `MAX_DOC_CHARS` must fit its context window |
| `URL_PATH_PREFIX` | e.g. `/vendor-pipeline` when apps share a domain |
| `DEFAULT_YEAR`, `SOURCES_TOTAL` | default year; expected number of sources (0 = count what is found) |

Then `python scripts/run_pipeline.py setup` creates the schema, volume and tables.

## 3. Decide what a "finding" is

1. `pipeline/prompts.py`: rewrite `EXTRACTION_PROMPT` (it receives `{domain_description}`, `{source}`, `{year}`, `{document_text}`; keep the JSON example's doubled braces).
2. `pipeline/extract.py`: set `DOMAIN_DESCRIPTION`.
3. `pipeline/models.py`: add or remove fields on `Finding`.
4. For a new field add the column in `pipeline/schemas.py` and carry it through `orchestrator.process_document` and `normalize.build_signals`. `store.ensure_tables()` adds missing columns, so re-running `setup` is safe.

## 4. Decide how themes are named

Put preferred names in `data/preferred_themes.json` (empty list = let the model choose). `MAX_THEMES` caps the list. Rewrite `CONSOLIDATION_PROMPT` if your labels are not short phrases.

## 5. Decide how things are scored

`pipeline/scoring.py` holds the formula and bands; tune with `SCORE_WEIGHT_*`, `BAND_*_MIN`, `CONFIDENCE_FLOOR` in `.env`, and `SEVERITY_WEIGHTS` in `config.py`.

## 6. Decide what you compare against

Load a CSV with `canonical_theme, reference_value (0-100), owner`:

```powershell
python scripts/run_pipeline.py load-reference --csv my_reference.csv --year 2026
python scripts/run_pipeline.py after --year 2026
```

Statuses: `aligned`, `external_higher`, `external_lower`, `not_in_reference`, `not_in_external` (blind spot). Change `compare_scores` for other rules.

## 7. Volume layout

Default `<year>/<source>/<file>.pdf`. Source and year come only from the path (volumes carry no per-file metadata). Change `paths.parse_object_path` and `build_object_path` for another layout. Keep file names free of spaces; the upload page sanitises them.

## 8. How new files are noticed

- **Job trigger (default):** `databricks.yml` defines a job with a file-arrival trigger that runs `parse-new`: it lists the volume, parses every PDF whose id is not in the documents table, then refreshes each affected year. `max_concurrent_runs: 1` keeps runs sequential.
- **Button:** `/process-new` on the upload page does the same on demand.
- **Push:** anything that can POST `{"name": "<year>/<source>/<file>.pdf"}` to `/event` also works.

## 9. Dashboard

`templates/dashboard.html` is HTML plus a little JavaScript reading `/api/dashboard`. Add data in `pipeline/dashboard.py`, display it in the template, style it in `static/app.css`.

## 10. Other input types

Only `pdf_text.py` and `extract.py` know about PDFs. For Word, HTML or text, replace `pdf_to_text` and the `.pdf` checks in `extract.read_object` and `storage.list_pdfs`. For scanned PDFs add OCR (for example `ai_parse_document` or a library) inside `pdf_to_text`.

## 11. Test, commit, deploy

```powershell
python -m unittest discover -s tests -v
git add . ; git status          # no .env, no tokens
git commit -m "Initial pipeline"
bash deploy/deploy.sh
```

## Checklist before the first real run

- [ ] `.env` is correct and is not listed by `git status`
- [ ] `setup` created the tables; reference CSV loaded
- [ ] one PDF parsed with `parse <year>/<source>/<file>.pdf`, then `after --year ...`; the dashboard shows it
- [ ] the app's service principal has the grants in `deploy/grants.sql`
- [ ] `app.yaml` resources (`sql-warehouse`, `secret-key`) are attached in the Apps UI
- [ ] the file-arrival job ran once after you added a test file
- [ ] a prompt-length check: a large PDF fits the endpoint's context (`MAX_DOC_CHARS`)
