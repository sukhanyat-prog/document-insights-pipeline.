# Adapting the template to a new project

Work top to bottom. Steps 1-4 are enough to get a first run; the rest tune it.

## 1. Copy and rename

```powershell
Copy-Item -Recurse pipeline_template my_new_pipeline
cd my_new_pipeline
git init -b main
```

Set `APP_NAME` and `APP_TITLE` in `.env`. The Python package is called `pipeline`; renaming it is optional (if you do, update the imports in `app.py`, `scripts/run_pipeline.py` and `tests/`).

## 2. Point it at your cloud resources (`.env`)

| Setting | Meaning |
|---|---|
| `GOOGLE_CLOUD_PROJECT`, `GOOGLE_CLOUD_LOCATION` | project and region (BigQuery, Vertex AI) |
| `GCS_BUCKET` | bucket that receives the documents |
| `BQ_DATASET` | dataset for this project's tables (one dataset per pipeline keeps them isolated) |
| `TABLE_PREFIX` | prefix for all eight tables, e.g. `vend_`; or override one table with `T_FINDINGS=...` |
| `URL_PATH_PREFIX` | e.g. `/vendor-pipeline` when several apps share one domain |
| `DEFAULT_YEAR`, `SOURCES_TOTAL` | default year; how many sources you expect (`5 of 9` style coverage). 0 = count what is found |

Then `python scripts/run_pipeline.py setup` creates the dataset and tables.

## 3. Decide what a "finding" is

1. `pipeline/prompts.py` - rewrite `EXTRACTION_PROMPT` for your documents (what to extract, how to word the quote rule).
2. `pipeline/extract.py` - set `DOMAIN_DESCRIPTION`.
3. `pipeline/models.py` - add or remove fields on `Finding` (for example `amount`, `region`, `product`).
4. If you added a field, add the column in `pipeline/schemas.py` (`T_FINDINGS`, and `T_SIGNALS` if you need it later) and carry it through in `orchestrator.process_document` and `normalize.build_signals`.

`store.ensure_tables()` adds new columns to existing tables, so re-running `setup` is safe.

## 4. Decide how themes are named

- Put your preferred names in `data/preferred_themes.json`. The model is shown them and close matches are snapped to them. Leave the list empty to let the model choose.
- `MAX_THEMES` caps the number of canonical themes. Rewrite `CONSOLIDATION_PROMPT` if your labels are not short phrases.

## 5. Decide how things are scored

- `pipeline/scoring.py`: the formula (coverage x intensity by default) and the bands. Change the weights with `SCORE_WEIGHT_*` and thresholds with `BAND_*_MIN` in `.env`, or edit `score_value` for something different.
- `CONFIDENCE_FLOOR`: signals under it are stored with `counted = false` and do not score.
- `SEVERITY_WEIGHTS` in `config.py`: map the model's severity words to numbers.

## 6. Decide what you compare against

The reference table is whatever you want the external view measured against. Provide a CSV with `canonical_theme, reference_value (0-100), owner` and load it:

```powershell
python scripts/run_pipeline.py load-reference --csv my_reference.csv --year 2026
python scripts/run_pipeline.py after --year 2026
```

Status values written by `pipeline/compare.py`: `aligned`, `external_higher`, `external_lower`, `not_in_reference` (seen in documents, missing from your table), `not_in_external` (blind spot: in your table, not found in documents). To compare on something other than a single number, change `compare_scores`.

## 7. Bucket layout

The default is `<year>/<source>/<file>.pdf`. Change `paths.parse_object_path` and `paths.build_object_path` for another layout. A blob's custom metadata (`source`, `year`) overrides what is read from the path; the upload page sets both.

## 8. Dashboard

`templates/dashboard.html` is plain HTML and a little JavaScript reading `/api/dashboard`. Add charts by extending `pipeline/dashboard.py` (queries) and the template. Colours and layout are in `static/app.css`.

## 9. Other input types

Only `pipeline/extract.py` knows about PDFs. For Word, HTML or plain text, replace `extract_document` and the `.pdf` checks in `extract.read_object` and `orchestrator.handle_event`; everything after step 1 works on findings and is unchanged.

## 10. Test, commit, deploy

```powershell
python -m unittest discover -s tests -v      # keep tests green; edit them when you change logic
git add . ; git status                        # check that no .env, secrets/ or key files are listed
git commit -m "Initial pipeline"
bash deploy/deploy.sh                         # edit the variables at the top first
```

## Checklist before the first real run

- [ ] `.env` has the right project, bucket, dataset; `.env` is not in `git status`
- [ ] `setup` created the tables; reference CSV loaded
- [ ] one document parsed with `parse gs://...`, then `after --year ...`; dashboard shows it
- [ ] `SECRET_KEY` stored in Secret Manager; service is not publicly invokable
- [ ] Eventarc trigger points at `/event`; worker concurrency 1, max instances 1
