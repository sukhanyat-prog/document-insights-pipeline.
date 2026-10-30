#!/usr/bin/env bash
# Deploy the dashboard as a Databricks App and the file-arrival job as a bundle.
# Needs the Databricks CLI (>= 0.250) logged in:  databricks auth login --host https://<workspace>
# Usage: APP=pipeline-template WORKSPACE_DIR=/Workspace/Users/you@company.com/pipeline-template bash deploy/deploy.sh
set -euo pipefail

APP="${APP:-pipeline-template}"
WORKSPACE_DIR="${WORKSPACE_DIR:?set WORKSPACE_DIR to a workspace folder, e.g. /Workspace/Users/you@company.com/pipeline-template}"

# 1. Create the schema, volume and tables once (uses your own login, needs .env or env vars)
python scripts/run_pipeline.py setup

# 2. Upload the source and create / update the app
databricks sync . "$WORKSPACE_DIR" --full
databricks apps get "$APP" >/dev/null 2>&1 || databricks apps create "$APP"
echo "Now add the app resources in the UI (sql-warehouse, secret-key as named in app.yaml) and run deploy/grants.sql"
databricks apps deploy "$APP" --source-code-path "$WORKSPACE_DIR"

# 3. Job that parses new files when they arrive in the volume
databricks bundle deploy -t dev
