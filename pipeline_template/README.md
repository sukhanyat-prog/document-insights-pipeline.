# Pipeline template: documents -> findings -> themes -> scores -> comparison -> dashboard

A plain, working starting point for any project with this shape:

1. People or systems drop **PDF documents** into a Cloud Storage bucket.
2. **Gemini** (Vertex AI) reads each document and returns structured findings.
3. Free-text labels are **consolidated** into a short list of canonical themes.
4. Themes are **scored**, then **compared with your own reference table** (internal view, baseline, target).
5. A **Flask dashboard** shows scores, comparison status and blind spots.

Everything project-specific is in `.env`, `pipeline/prompts.py`, `pipeline/models.py` and `pipeline/schemas.py`.

```
 PDF in bucket --(Eventarc POST /event)--> 1 extract --> tpl_documents, tpl_findings
                                           2 consolidate  raw labels -> <= MAX_THEMES themes   -> tpl_themes
                                           3 normalize    findings + themes -> signals          -> tpl_signals
                                           4 aggregate    signals -> score 0-100 + band         -> tpl_scores
                                           5 compare      scores vs tpl_reference               -> tpl_comparison
                                           dashboard      reads tpl_scores / tpl_comparison / tpl_documents
```

## Quick start

```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env                       # edit project, bucket, dataset, table prefix
gcloud auth application-default login        # or set GOOGLE_APPLICATION_CREDENTIALS (key kept outside git)

python scripts/run_pipeline.py setup                          # creates the dataset and tables
python scripts/run_pipeline.py load-reference --csv examples/reference_example.csv --year 2026
python scripts/run_pipeline.py parse gs://YOUR_BUCKET/2026/Some_Source/file.pdf
python scripts/run_pipeline.py after --year 2026              # steps 2-5
python app.py                                                 # http://localhost:8080/
```

Run the tests (no cloud access needed): `python -m unittest discover -s tests -v`

## What is where

| Path | What it does | Change it when |
|---|---|---|
| `.env` / `pipeline/config.py` | project, bucket, dataset, table names, thresholds, URL prefix | every new project |
| `pipeline/schemas.py` | every table and column | you add or rename fields |
| `pipeline/models.py` | the JSON the model must return per document | you extract different things |
| `pipeline/prompts.py` | extraction and consolidation prompts | always: write for your domain |
| `pipeline/extract.py` | step 1: GCS -> Gemini -> validated findings (`DOMAIN_DESCRIPTION` at the top) | other input types (Word, HTML...) |
| `pipeline/consolidate.py` | step 2: label grouping, preferred names, theme cap | rarely |
| `pipeline/normalize.py` | step 3: findings -> signals, confidence floor | rarely |
| `pipeline/scoring.py` + `aggregate.py` | step 4: score formula, bands | your own scoring |
| `pipeline/compare.py` | step 5: compare with the reference table | different comparison rules |
| `pipeline/orchestrator.py` | runs the steps; `handle_event` for Eventarc | add or remove a step |
| `pipeline/web.py`, `app.py` | routes, CSRF, health | new pages |
| `templates/`, `static/app.css` | dashboard and upload pages | branding, charts |
| `data/preferred_themes.json` | optional preferred theme names | every new project |
| `scripts/run_pipeline.py` | command-line runner | new commands |
| `deploy/deploy.sh` | Cloud Run + IAM + secret + Eventarc commands | different environment |
| `.github/workflows/ci.yml` | compile + unit tests on every push | add deploy |
| `tests/` | offline tests (fake Gemini, fake BigQuery) | whenever you change logic |

Step-by-step adaptation guide: [`docs/ADAPTING.md`](docs/ADAPTING.md).

## Endpoints

| Method | Path (under `URL_PATH_PREFIX`) | Purpose |
|---|---|---|
| GET | `/` | dashboard (`?year=`) |
| GET | `/api/dashboard` | dashboard data as JSON |
| GET, POST | `/upload` | upload a PDF to `gs://BUCKET/<year>/<source>/<file>.pdf` |
| POST | `/event` | Cloud Storage event: parse the PDF, then run steps 2-5 for its year (`AUTO_REFRESH`) |
| POST | `/run?year=` | re-run steps 2-5, e.g. after loading a new reference table |
| GET | `/health` | liveness (outside the prefix) |

`/event` and `/run` are CSRF-exempt because Eventarc and schedulers have no browser session. The app has **no login**: deploy with `--no-allow-unauthenticated` and put users behind IAP or your SSO proxy.

## Deploy (Cloud Run)

`bash deploy/deploy.sh` (after editing the variables at the top) creates the service account with its roles, a `SECRET_KEY` in Secret Manager, deploys the service, and prints the Eventarc trigger command. Key points:

- The container uses the **service account** (Application Default Credentials). No key file is built into the image.
- `APP_ENV=production` (set by the Dockerfile) makes `SECRET_KEY` mandatory.
- The worker that receives `/event` runs with **concurrency 1 and max instances 1**, so documents are processed one at a time and the per-year rewrites cannot overlap.
- For a busy dashboard, deploy the same image a second time as a read-mostly service (`--concurrency 80`, no Eventarc trigger).

## Notes on behaviour

- **Idempotent:** parsing a file twice replaces its rows. Steps 2-5 rewrite one year at a time. Rows are written with load jobs (not streaming inserts), so they can be deleted immediately afterwards.
- **Cap and floor:** at most `MAX_THEMES` canonical themes; a signal counts only if finding confidence x mapping confidence is at least `CONFIDENCE_FLOOR`. Themes created by merging past the cap carry low mapping confidence by design.
- **Fallback:** if the consolidation model call fails, labels are grouped by spelling so the run still finishes.
- **Not verified here:** the template was tested offline (logic, Flask routes, fake Gemini, fake store). Run `setup` and one real document in a non-production project before relying on it.
