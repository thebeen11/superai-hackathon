#!/usr/bin/env bash
#
# Run the one-off schema bootstrap (scripts/init_db.py) INSIDE GCP as a Cloud Run Job,
# so no local Cloud SQL Auth Proxy is needed. Reuses the image the Cloud Run SERVICE is
# currently running, so the job's table definitions match the deployed code exactly
# (redeploy the service first so newly-added tables — e.g. prompt_overrides for the
# Agent Console — are present). Safe to re-run: create_all only adds missing tables, and
# the job is upserted.
#
# Prereqs: the service is deployed, and its service account already has cloudsql.client +
# secretAccessor (granted in deploy.sh). DATABASE_URL secret + Cloud SQL instance exist.
set -euo pipefail

# shellcheck source=_gcloud_lib.sh
source "$(dirname "${BASH_SOURCE[0]}")/_gcloud_lib.sh"

# --- Config (mirror deploy.sh) -----------------------------------------------
PROJECT_ID="${PROJECT_ID:-your-project-id}"
REGION="${REGION:-asia-southeast1}"        # must match deploy.sh — that's where everything is
SERVICE="${SERVICE:-council-api}"          # image + service account come from this service
SQL_INSTANCE="${SQL_INSTANCE:-council-db}"
JOB="${JOB:-init-db}"
# -----------------------------------------------------------------------------

CONNECTION_NAME="${PROJECT_ID}:${REGION}:${SQL_INSTANCE}"

gcloud config set project "${PROJECT_ID}"

# Reuse the deployed service's exact image + service account, so the job runs the same
# code (and already-authorized identity) as the live API.
retry_gcloud_read 5 -- run services describe "${SERVICE}" --region "${REGION}" \
  --format='value(spec.template.spec.containers[0].image)' \
  || die "could not read the image of service '${SERVICE}' — is it deployed?"
IMAGE="${GCLOUD_STDOUT}"

if [[ -n "${SERVICE_ACCOUNT:-}" ]]; then
  SA="${SERVICE_ACCOUNT}"
else
  retry_gcloud_read 5 -- run services describe "${SERVICE}" --region "${REGION}" \
    --format='value(spec.template.spec.serviceAccountName)' \
    || die "could not read the service account of service '${SERVICE}'"
  SA="${GCLOUD_STDOUT}"
fi
echo "==> Using image: ${IMAGE}"
echo "==> Using service account: ${SA}"

echo "==> Deploying Cloud Run Job '${JOB}'"
# --command/--args override the image CMD to run the bootstrap instead of uvicorn.
# WORKDIR is /app, so `python -m scripts.init_db` imports app.* and scripts.* cleanly.
# --set-cloudsql-instances validates the instance through the Cloud SQL Admin API, so this
# call shares the same per-project quota as deploy.sh — hence the backoff.
retry_gcloud 5 -- run jobs deploy "${JOB}" \
  --image "${IMAGE}" --region "${REGION}" \
  --service-account="${SA}" \
  --set-cloudsql-instances="${CONNECTION_NAME}" \
  --set-env-vars="APP_ENV=prod,GCP_PROJECT=${PROJECT_ID}" \
  --set-secrets="DATABASE_URL=DATABASE_URL:latest" \
  --command=python \
  --args=-m,scripts.init_db \
  --max-retries=0 --task-timeout=300s \
  || die "could not deploy Cloud Run Job '${JOB}'"

echo "==> Executing the job (waits for completion, streams the result)"
# --wait polls the execution; a throttled poll is retried rather than failing the run.
retry_gcloud 5 -- run jobs execute "${JOB}" --region "${REGION}" --wait \
  || die "Cloud Run Job '${JOB}' failed — see: gcloud run jobs executions list --job ${JOB} --region ${REGION}"

echo
echo "==> Done. To inspect logs of the last run:"
echo "    gcloud run jobs executions list --job ${JOB} --region ${REGION}"
