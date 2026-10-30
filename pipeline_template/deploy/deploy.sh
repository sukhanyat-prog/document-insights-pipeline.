#!/usr/bin/env bash
# One-time / repeatable Cloud Run deployment. Edit the variables, then:  bash deploy/deploy.sh
set -euo pipefail

PROJECT="${PROJECT:-your-gcp-project}"
REGION="${REGION:-us-central1}"
BUCKET="${BUCKET:-your-bucket}"
SERVICE="${SERVICE:-pipeline-template}"
SA_NAME="${SA_NAME:-pipeline-template}"
SA="${SA_NAME}@${PROJECT}.iam.gserviceaccount.com"
DATASET="${DATASET:-PIPELINE_TEMPLATE}"

# 1. Service account and roles (no key file is ever created)
gcloud iam service-accounts create "$SA_NAME" --project "$PROJECT" 2>/dev/null || true
for role in roles/bigquery.dataEditor roles/bigquery.jobUser roles/aiplatform.user; do
  gcloud projects add-iam-policy-binding "$PROJECT" --member "serviceAccount:$SA" --role "$role" --condition=None >/dev/null
done
gcloud storage buckets add-iam-policy-binding "gs://$BUCKET" --member "serviceAccount:$SA" --role roles/storage.objectAdmin >/dev/null

# 2. Secret for Flask sessions / CSRF
if ! gcloud secrets describe "${SERVICE}-secret-key" --project "$PROJECT" >/dev/null 2>&1; then
  python3 -c "import secrets; print(secrets.token_hex(32), end='')" | \
    gcloud secrets create "${SERVICE}-secret-key" --project "$PROJECT" --data-file=-
fi
gcloud secrets add-iam-policy-binding "${SERVICE}-secret-key" --project "$PROJECT" \
  --member "serviceAccount:$SA" --role roles/secretmanager.secretAccessor >/dev/null

# 3. Deploy from source (uses the Dockerfile). Concurrency 1 + one instance keeps event processing serial.
gcloud run deploy "$SERVICE" --project "$PROJECT" --region "$REGION" --source . \
  --service-account "$SA" \
  --set-env-vars "GOOGLE_CLOUD_PROJECT=$PROJECT,GCS_BUCKET=$BUCKET,BQ_DATASET=$DATASET" \
  --set-secrets "SECRET_KEY=${SERVICE}-secret-key:latest" \
  --timeout 900 --concurrency 1 --max-instances 1 --no-allow-unauthenticated

# 4. Eventarc: PDF uploaded -> POST /event
URL=$(gcloud run services describe "$SERVICE" --project "$PROJECT" --region "$REGION" --format 'value(status.url)')
echo "Service: $URL"
echo "Next: grant the Cloud Storage service agent pubsub.publisher and create the trigger:"
cat <<EOF
gcloud eventarc triggers create ${SERVICE}-trigger --project $PROJECT --location $REGION \\
  --destination-run-service $SERVICE --destination-run-region $REGION --destination-run-path /event \\
  --event-filters type=google.cloud.storage.object.v1.finalized --event-filters bucket=$BUCKET \\
  --service-account $SA
EOF
