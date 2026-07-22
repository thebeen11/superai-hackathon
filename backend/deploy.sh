#!/usr/bin/env bash
#
# Deploy the Hedge Fund AI Agent Council backend to GCP:
#   Cloud Run (service) + Cloud SQL (Postgres) + Secret Manager + Vertex AI (Gemini).
#
# This is a runbook, not magic — read it, set the vars below, and run it. You must be
# authenticated (`gcloud auth login`) with billing enabled on the project.
#
# Usage:
#   ./deploy.sh provision   one-time: enable APIs, create Cloud SQL + secrets + IAM
#   ./deploy.sh deploy      repeatable: build & deploy the code, upsert the scheduler
#   ./deploy.sh all         both, for a fresh project (default when no phase is given)
#
# Prefer `./deploy.sh deploy` for day-to-day redeploys. It makes ZERO Cloud SQL Admin API
# calls, which matters because that API has a per-project, per-minute quota shared with the
# Cloud Run SQL socket — blow through it and you get 429 / rateLimitExceeded.
#
# Reasoning auth: Gemini on Vertex AI uses the Cloud Run service account via ADC —
# there are NO LLM API keys. We just grant that account roles/aiplatform.user.
set -euo pipefail

# shellcheck source=_gcloud_lib.sh
source "$(dirname "${BASH_SOURCE[0]}")/_gcloud_lib.sh"

PHASE="${1:-all}"
case "${PHASE}" in
  provision|deploy|all) ;;
  *) echo "usage: $0 [provision|deploy|all]" >&2; exit 2 ;;
esac

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

REQUIRED_APIS=(
  run.googleapis.com sqladmin.googleapis.com aiplatform.googleapis.com
  artifactregistry.googleapis.com secretmanager.googleapis.com cloudbuild.googleapis.com
  cloudscheduler.googleapis.com
)

gcloud config set project "${PROJECT_ID}"

# --- provision ---------------------------------------------------------------
# Everything here is one-time-per-environment. Keeping it out of the redeploy path is what
# stops routine deploys from spending Cloud SQL Admin API quota.
provision() {
  echo "==> Enabling APIs"
  # `services enable` is slow and pointless once enabled, so diff against what's on first.
  local enabled missing=()
  if ! gcloud_read services list --enabled --format='value(config.name)'; then
    die "could not list enabled services"
  fi
  enabled="${GCLOUD_STDOUT}"
  local api
  for api in "${REQUIRED_APIS[@]}"; do
    printf '%s\n' "${enabled}" | grep -qx "${api}" || missing+=("${api}")
  done
  if [[ ${#missing[@]} -eq 0 ]]; then
    echo "    all ${#REQUIRED_APIS[@]} APIs already enabled, skipping"
  else
    echo "    enabling: ${missing[*]}"
    retry_gcloud 5 -- services enable "${missing[@]}" || die "failed to enable APIs"
  fi

  echo "==> Cloud SQL (Postgres 16)"
  # Check-then-create, never create-and-swallow: `2>/dev/null || echo "exists"` reports a
  # 429 as success and then deploys against an instance that may not be there.
  if resource_exists sql instances describe "${SQL_INSTANCE}" --format='value(name)'; then
    echo "    instance '${SQL_INSTANCE}' already exists"
  else
    echo "    creating instance '${SQL_INSTANCE}'"
    retry_gcloud 5 -- sql instances create "${SQL_INSTANCE}" \
      --database-version=POSTGRES_16 --tier=db-f1-micro --region="${REGION}" \
      || [[ "$(gcloud_status)" == ALREADY_EXISTS ]] \
      || die "could not create Cloud SQL instance '${SQL_INSTANCE}'"
  fi

  if resource_exists sql databases describe "${DB_NAME}" --instance="${SQL_INSTANCE}" --format='value(name)'; then
    echo "    database '${DB_NAME}' already exists"
  else
    echo "    creating database '${DB_NAME}'"
    retry_gcloud 5 -- sql databases create "${DB_NAME}" --instance="${SQL_INSTANCE}" \
      || [[ "$(gcloud_status)" == ALREADY_EXISTS ]] \
      || die "could not create database '${DB_NAME}'"
  fi

  # One read decides which single write to make. The old `users create || users set-password`
  # chain fired a SECOND admin write the instant the first was throttled, compounding the 429.
  echo "    checking user '${DB_USER}'"
  retry_gcloud_read 5 -- sql users list --instance="${SQL_INSTANCE}" --format='value(name)' \
    || die "could not list Cloud SQL users on '${SQL_INSTANCE}'"
  if printf '%s\n' "${GCLOUD_STDOUT}" | grep -qx "${DB_USER}"; then
    echo "    user exists, setting password"
    retry_gcloud 5 -- sql users set-password "${DB_USER}" --instance="${SQL_INSTANCE}" \
      --password="${DB_PASSWORD}" || die "could not set password for '${DB_USER}'"
  else
    echo "    creating user '${DB_USER}'"
    retry_gcloud 5 -- sql users create "${DB_USER}" --instance="${SQL_INSTANCE}" \
      --password="${DB_PASSWORD}" || die "could not create user '${DB_USER}'"
  fi

  echo "==> Secrets"
  upsert_secret EXA_API_KEY     "${EXA_API_KEY}"
  upsert_secret YOUTUBE_API_KEY "${YOUTUBE_API_KEY}"
  upsert_secret DATABASE_URL    "${DATABASE_URL}"

  # The Cloud Run revision runs as a service account that must read the secrets AT DEPLOY TIME,
  # so grant its roles BEFORE deploying (granting after the deploy is too late — the deploy 403s
  # on the secrets). Defaults to the project's compute SA; override with SERVICE_ACCOUNT=...
  echo "==> Granting the Cloud Run service account Vertex AI + Cloud SQL + Secret access"
  local role
  for role in roles/aiplatform.user roles/cloudsql.client roles/secretmanager.secretAccessor; do
    retry_gcloud 5 -- projects add-iam-policy-binding "${PROJECT_ID}" \
      --member="serviceAccount:$(service_account)" --role="${role}" >/dev/null \
      || die "could not grant ${role}"
  done
  # IAM changes can take a few seconds to propagate before the deploy can read the secrets.
  sleep 10
}

upsert_secret() {  # name, value
  if gcloud secrets describe "$1" >/dev/null 2>&1; then
    printf '%s' "$2" | gcloud secrets versions add "$1" --data-file=-
  else
    printf '%s' "$2" | gcloud secrets create "$1" --data-file=-
  fi
}

# Resolved once and memoised — this is a projects.get, not a sqladmin call, but there's no
# reason to repeat it per IAM role.
_SA=""
service_account() {
  if [[ -z "${_SA}" ]]; then
    if [[ -n "${SERVICE_ACCOUNT:-}" ]]; then
      _SA="${SERVICE_ACCOUNT}"
    else
      gcloud_read projects describe "${PROJECT_ID}" --format='value(projectNumber)' \
        || die "could not read project number for '${PROJECT_ID}'"
      _SA="${GCLOUD_STDOUT}-compute@developer.gserviceaccount.com"
    fi
  fi
  printf '%s' "${_SA}"
}

# --- deploy ------------------------------------------------------------------
# The repeatable path. Touches Cloud Run, Cloud Build and Cloud Scheduler — no `gcloud sql`.
deploy() {
  echo "==> Deploy to Cloud Run (builds the Dockerfile via Cloud Build)"
  # --max-instances=1: app/jobs.py holds streaming-job state in process memory, so SSE
  #                    reconnect must land on the same instance.
  # --no-cpu-throttling: discovery runs work in background threads after the response
  #                      starts; Cloud Run would otherwise freeze CPU between requests.
  # --timeout=3600: long-lived SSE streams.
  # --add-cloudsql-instances mounts the /cloudsql socket. This is the one Cloud SQL touch
  # in this phase, and it's a Cloud Run flag, not a sqladmin write.
  gcloud run deploy "${SERVICE}" \
    --source . --region "${REGION}" --allow-unauthenticated \
    --service-account="$(service_account)" \
    --add-cloudsql-instances="${CONNECTION_NAME}" \
    --min-instances=1 --max-instances=1 --no-cpu-throttling --timeout=3600 \
    --set-env-vars="APP_ENV=prod,GCP_PROJECT=${PROJECT_ID},VERTEX_LOCATION=${VERTEX_LOCATION},GEMINI_MODEL=${GEMINI_MODEL}" \
    --set-secrets="EXA_API_KEY=EXA_API_KEY:latest,YOUTUBE_API_KEY=YOUTUBE_API_KEY:latest,DATABASE_URL=DATABASE_URL:latest"

  echo "==> Cloud Scheduler: daily crawl (00:30 UTC, crawls yesterday's news)"
  gcloud_read run services describe "${SERVICE}" --region "${REGION}" --format='value(status.url)' \
    || die "could not read the URL of service '${SERVICE}'"
  SERVICE_URL="${GCLOUD_STDOUT}"
  # The service is deployed --allow-unauthenticated, so a plain HTTP target works. If you
  # later require auth, add:  --oidc-service-account-email="$(service_account)" --oidc-token-audience="${SERVICE_URL}"
  local verb=create
  gcloud scheduler jobs describe daily-crawl --location "${REGION}" >/dev/null 2>&1 && verb=update
  gcloud scheduler jobs "${verb}" http daily-crawl --location "${REGION}" \
    --schedule="30 0 * * *" --time-zone="Etc/UTC" \
    --uri="${SERVICE_URL}/crawl/daily" --http-method=POST \
    --attempt-deadline=1800s
}

# --- run ---------------------------------------------------------------------
# `if` rather than `[[ ... ]] && provision`: under `set -e` a false test makes the whole
# AND-list return 1, which would abort the script on the very first skipped phase.
if [[ "${PHASE}" == provision || "${PHASE}" == all ]]; then provision; fi
if [[ "${PHASE}" == deploy    || "${PHASE}" == all ]]; then deploy;    fi

if [[ "${PHASE}" == provision ]]; then
  cat <<EOF

==> Provisioning done. Now deploy the code:
    ./deploy.sh deploy
EOF
  exit 0
fi

cat <<EOF

==> Done. Service URL:
    ${SERVICE_URL}

For subsequent code changes use \`./deploy.sh deploy\` — it skips provisioning entirely and
spends no Cloud SQL Admin API quota.

One-time schema bootstrap: run ./init_db_job.sh (runs scripts/init_db.py as a Cloud Run Job
inside GCP, no local proxy needed).

Alternatively, via the Cloud SQL Auth Proxy. NOTE: bind the proxy to a NON-5432 port
(e.g. 5434) — a local Postgres on 5432 will otherwise shadow it and you'll init the wrong
database. Run ONE long-lived proxy; restarting it in a loop re-fetches ephemeral certs from
the Cloud SQL Admin API and will eventually trip the same 429. In one terminal:
    cloud-sql-proxy --port 5434 ${CONNECTION_NAME}
then in another (one line; export so it outranks any .env):
    export DATABASE_URL='postgresql+psycopg://${DB_USER}:THE_PASSWORD@127.0.0.1:5434/${DB_NAME}' && uv run python -m scripts.init_db
EOF
