#!/usr/bin/env bash
# Build the image, push it to the Snowflake image repository, and create the service.
# Needs Docker and the Snowflake CLI (`snow`) with a connection configured:  snow connection add
# Usage: ACCOUNT_URL=myorg-myaccount.registry.snowflakecomputing.com CONNECTION=default bash deploy/deploy.sh
set -euo pipefail

REGISTRY="${ACCOUNT_URL:?set ACCOUNT_URL to <org>-<account>.registry.snowflakecomputing.com}"
CONNECTION="${CONNECTION:-default}"
IMAGE="$REGISTRY/pipeline_db/pipeline_template/images/pipeline-template:latest"

# 1. One-time objects (database, role, pool, repository, secret). Edit deploy/setup.sql first.
snow sql -c "$CONNECTION" -f deploy/setup.sql

# 2. Tables and stage
python scripts/run_pipeline.py setup

# 3. Image
snow spcs image-registry login -c "$CONNECTION"
docker build --platform linux/amd64 -t "$IMAGE" .
docker push "$IMAGE"

# 4. Service
snow sql -c "$CONNECTION" -f deploy/service.sql
