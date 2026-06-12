#!/usr/bin/env bash
#
# Deploy the Hedge Fund AI Agent Council backend to GCP:
#   Cloud Run (service) + Cloud SQL (Postgres) + Secret Manager + Vertex AI (Gemini).
#
# This is a runbook, not magic — read it, set the vars below, and run it once. It is
# safe to re-run: resource-creation steps tolerate "already exists". You must be
# authenticated (`gcloud auth login`) with billing enabled on the project.
#
# Reasoning auth: Gemini on Vertex AI uses the Cloud Run service account via ADC —
# there are NO LLM API keys. We just grant that account roles/aiplatform.user.
set -euo pipefail

# --- Config (edit these) -----------------------------------------------------
PROJECT_ID="${PROJECT_ID:-your-project-id}"
REGION="${REGION:-us-central1}"             # Cloud Run + Cloud SQL region
SERVICE="${SERVICE:-council-api}"
SQL_INSTANCE="${SQL_INSTANCE:-council-db}"
DB_NAME="${DB_NAME:-council}"
DB_USER="${DB_USER:-council}"
DB_PASSWORD="${DB_PASSWORD:?set DB_PASSWORD to a strong password}"
EXA_API_KEY="${EXA_API_KEY:?set EXA_API_KEY}"
YOUTUBE_API_KEY="${YOUTUBE_API_KEY:?set YOUTUBE_API_KEY}"
GEMINI_MODEL="${GEMINI_MODEL:-gemini-2.5-pro}"
# Vertex region for Gemini — defaults to REGION, but override if your REGION doesn't
# serve the model (e.g. VERTEX_LOCATION=us-central1 for the widest model coverage).
VERTEX_LOCATION="${VERTEX_LOCATION:-$REGION}"
# -----------------------------------------------------------------------------

CONNECTION_NAME="${PROJECT_ID}:${REGION}:${SQL_INSTANCE}"
DATABASE_URL="postgresql+psycopg://${DB_USER}:${DB_PASSWORD}@/${DB_NAME}?host=/cloudsql/${CONNECTION_NAME}"

gcloud config set project "${PROJECT_ID}"

echo "==> Enabling APIs"
gcloud services enable \
  run.googleapis.com sqladmin.googleapis.com aiplatform.googleapis.com \
  artifactregistry.googleapis.com secretmanager.googleapis.com cloudbuild.googleapis.com

echo "==> Cloud SQL (Postgres 16)"
gcloud sql instances create "${SQL_INSTANCE}" \
  --database-version=POSTGRES_16 --tier=db-f1-micro --region="${REGION}" \
  2>/dev/null || echo "    instance exists, skipping"
gcloud sql databases create "${DB_NAME}" --instance="${SQL_INSTANCE}" \
  2>/dev/null || echo "    database exists, skipping"
gcloud sql users create "${DB_USER}" --instance="${SQL_INSTANCE}" --password="${DB_PASSWORD}" \
  2>/dev/null || gcloud sql users set-password "${DB_USER}" --instance="${SQL_INSTANCE}" --password="${DB_PASSWORD}"

echo "==> Secrets"
upsert_secret() {  # name, value
  if gcloud secrets describe "$1" >/dev/null 2>&1; then
    printf '%s' "$2" | gcloud secrets versions add "$1" --data-file=-
  else
    printf '%s' "$2" | gcloud secrets create "$1" --data-file=-
  fi
}
upsert_secret EXA_API_KEY     "${EXA_API_KEY}"
upsert_secret YOUTUBE_API_KEY "${YOUTUBE_API_KEY}"
upsert_secret DATABASE_URL    "${DATABASE_URL}"

echo "==> Deploy to Cloud Run (builds the Dockerfile via Cloud Build)"
# The Cloud Run revision runs as a service account that must read the secrets AT DEPLOY TIME,
# so grant its roles BEFORE deploying (granting after the deploy is too late — the deploy 403s
# on the secrets). Defaults to the project's compute SA; override with SERVICE_ACCOUNT=...
echo "==> Granting the Cloud Run service account Vertex AI + Cloud SQL + Secret access"
PROJECT_NUMBER="$(gcloud projects describe "${PROJECT_ID}" --format='value(projectNumber)')"
SA="${SERVICE_ACCOUNT:-${PROJECT_NUMBER}-compute@developer.gserviceaccount.com}"
for role in roles/aiplatform.user roles/cloudsql.client roles/secretmanager.secretAccessor; do
  gcloud projects add-iam-policy-binding "${PROJECT_ID}" \
    --member="serviceAccount:${SA}" --role="${role}" >/dev/null
done
# IAM changes can take a few seconds to propagate before the deploy can read the secrets.
sleep 10

# --max-instances=1: app/jobs.py holds streaming-job state in process memory, so SSE
#                    reconnect must land on the same instance.
# --no-cpu-throttling: discovery runs work in background threads after the response
#                      starts; Cloud Run would otherwise freeze CPU between requests.
# --timeout=3600: long-lived SSE streams.
gcloud run deploy "${SERVICE}" \
  --source . --region "${REGION}" --allow-unauthenticated \
  --service-account="${SA}" \
  --add-cloudsql-instances="${CONNECTION_NAME}" \
  --min-instances=1 --max-instances=1 --no-cpu-throttling --timeout=3600 \
  --set-env-vars="APP_ENV=prod,GCP_PROJECT=${PROJECT_ID},VERTEX_LOCATION=${VERTEX_LOCATION},GEMINI_MODEL=${GEMINI_MODEL}" \
  --set-secrets="EXA_API_KEY=EXA_API_KEY:latest,YOUTUBE_API_KEY=YOUTUBE_API_KEY:latest,DATABASE_URL=DATABASE_URL:latest"

cat <<EOF

==> Done. Service URL:
    $(gcloud run services describe "${SERVICE}" --region "${REGION}" --format='value(status.url)')

One-time schema bootstrap (run once against Cloud SQL) via the Cloud SQL Auth Proxy.
NOTE: bind the proxy to a NON-5432 port (e.g. 5434) — a local Postgres on 5432 will
otherwise shadow it and you'll init the wrong database. In one terminal:
    cloud-sql-proxy --port 5434 ${CONNECTION_NAME}
then in another (one line; export so it outranks any .env):
    export DATABASE_URL='postgresql+psycopg://${DB_USER}:THE_PASSWORD@127.0.0.1:5434/${DB_NAME}' && uv run python -m scripts.init_db
Or run scripts/init_db.py as a Cloud Run Job with the same DATABASE_URL secret + Cloud SQL connection.
EOF
