# Adapting the Snowflake template to a new project

Work top to bottom. Steps 1-4 give a first run; the rest tune it.

## 1. Copy and rename

```powershell
Copy-Item -Recurse pipeline_template_snowflake my_new_pipeline
cd my_new_pipeline
git init -b main
```

Set `APP_NAME` and `APP_TITLE` in `.env`. The Python package is called `pipeline`; renaming it is optional (update imports in `app.py`, `scripts/run_pipeline.py` and `tests/`).

## 2. Point it at your account

| Setting | Meaning |
|---|---|
| `SNOWFLAKE_ACCOUNT`, `SNOWFLAKE_USER`, `SNOWFLAKE_ROLE`, `SNOWFLAKE_WAREHOUSE` | connection for local runs |
| `SNOWFLAKE_AUTHENTICATOR=externalbrowser` or `SNOWFLAKE_PRIVATE_KEY_PATH` or `SNOWFLAKE_PASSWORD` | pick one. Inside Snowpark Container Services the session token is used automatically. Key files stay outside git |
| `SNOWFLAKE_DATABASE`, `SNOWFLAKE_SCHEMA` | where tables and the stage live; one schema per pipeline keeps them isolated |
| `SNOWFLAKE_STAGE` | internal stage that receives the PDFs |
| `TABLE_PREFIX` | prefix for all eight tables; or override one with `T_FINDINGS=...` |
| `CORTEX_MODEL`, `MAX_DOC_CHARS` | Cortex model name; characters of document text sent per call (must fit the model's context) |
| `URL_PATH_PREFIX` | e.g. `/vendor-pipeline` when apps share a domain |
| `DEFAULT_YEAR`, `SOURCES_TOTAL` | default year; expected number of sources (0 = count what is found) |

Run `deploy/setup.sql` once (role, database, warehouse, Cortex grant), then `python scripts/run_pipeline.py setup` for the schema, stage and tables.

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

## 7. Stage layout

Default `<year>/<source>/<file>.pdf`. Source and year come only from the path. Change `paths.parse_object_path` and `build_object_path` for another layout. File names must not contain spaces (the upload page sanitises them); if you upload with `PUT` yourself, use `AUTO_COMPRESS=FALSE`, otherwise the file lands as `.pdf.gz` and is ignored.

## 8. How new files are noticed

Snowflake has no push event for stage files in this template, so:

- **Button:** `/process-new` on the upload page parses every PDF whose id is not in the documents table, then refreshes each affected year.
- **Schedule:** run `python scripts/run_pipeline.py parse-new` from a task or any scheduler (example at the bottom of `deploy/service.sql`, commented out).
- **Push:** anything that can POST `{"name": "<year>/<source>/<file>.pdf"}` to `/event` also works.

If you want true event-driven processing, a stream on the stage's directory table plus a task is the usual Snowflake pattern; add it once the basics run.

## 9. Dashboard

`templates/dashboard.html` is HTML plus a little JavaScript reading `/api/dashboard`. Add data in `pipeline/dashboard.py`, display it in the template, style it in `static/app.css`.

## 10. Other input types

Only `pdf_text.py` and `extract.py` know about PDFs. For other formats replace `pdf_to_text` and the `.pdf` checks in `extract.read_object` and `storage.list_pdfs`. For scans add OCR inside `pdf_to_text`.

## 11. Test, commit, deploy

```powershell
python -m unittest discover -s tests -v
git add . ; git status          # no .env, no .p8 keys
git commit -m "Initial pipeline"
bash deploy/deploy.sh           # needs Docker and the Snowflake CLI
```

## Checklist before the first real run

- [ ] `.env` is correct and is not listed by `git status`
- [ ] `deploy/setup.sql` ran; the role has `SNOWFLAKE.CORTEX_USER`
- [ ] `setup` created the stage and tables; reference CSV loaded
- [ ] one PDF parsed with `parse <year>/<source>/<file>.pdf`, then `after --year ...`; the dashboard shows it
- [ ] the secret holds a real generated key (not the placeholder); the service endpoint is not exposed beyond intended roles
- [ ] a scheduled or manual `parse-new` ran once after you added a test file
