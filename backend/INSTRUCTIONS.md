# Testing Instructions — Discovery + Data Engineering Backend

This is the Layer 1 (Discovery) + Layer 2 (Data Engineering) backend of the Hedge Fund
AI Agent Council. It turns a research topic into clean, labelled, source-anchored rows in
Postgres, using Gemini on Vertex AI for reasoning.

---

## 1. Prerequisites

- **uv** (Python package manager) — https://docs.astral.sh/uv/
- **GCP Application Default Credentials** for Gemini on Vertex AI — run
  `gcloud auth application-default login` (no API keys). Set `GCP_PROJECT` in `.env`, and
  enable the Vertex AI API (`gcloud services enable aiplatform.googleapis.com`).
- A **Postgres** to connect to — local via `docker compose up -d` (see `docker-compose.yml`),
  or Cloud SQL. Set the connection string as `DATABASE_URL` in `backend/.env`.

> All commands below are run from the `backend/` directory unless stated otherwise.

---

## 2. One-time setup

```bash
uv sync                 # install dependencies
```

Config is layered by `APP_ENV` (defaults to `local` → loads `.env.local`; set `APP_ENV=prod`
→ `.env.prod`). For local dev, copy the local template and fill it in:

```bash
cp .env.local.example .env.local
```

Set `GCP_PROJECT`, keep `VERTEX_LOCATION` / `GEMINI_MODEL`, and point `DATABASE_URL` at the
local Postgres (the default in the template). Add `EXA_API_KEY` for live web discovery —
without it the web branch is skipped gracefully but returns no results.

> **Prod** config lives in Cloud Run (`--set-env-vars` / `--set-secrets`, set by `deploy.sh`
> with `APP_ENV=prod`); no `.env.prod` is shipped — OS env overrides any file. `.env.prod.example`
> is a template for prod-like local runs only. Never commit real secrets.
>
> `deploy.sh` takes a phase: `provision` (one-time — APIs, Cloud SQL, secrets, IAM),
> `deploy` (repeatable — build & ship the code), or `all` (fresh project; the default).
> Use `./deploy.sh deploy` for day-to-day redeploys.

---

## 3. Run the server

Reasoning uses Application Default Credentials, so make sure you've run
`gcloud auth application-default login` first, then:

```
uv run uvicorn app.main:app --reload
```

- Server: **http://localhost:8000**
- Interactive API docs (try endpoints in the browser): **http://localhost:8000/docs**

Quick health check (in another terminal):

```bash
curl http://localhost:8000/health
# {"status":"ok"}
```

---

## 4. The API test flow

### Path A — One-shot (simplest)

`POST /discover` → `POST /dataeng/process` → `GET /items`

**Step 1 — Discover** (Gemini refines the query, then fans out to Exa + YouTube):

```bash
curl -s -X POST http://localhost:8000/discover \
  -H 'Content-Type: application/json' \
  -d '{"query":"meta company","mode":"auto_proceed","max_results":5}'
```

Returns a `DiscoveryResult` `{query, original_query, items[], skipped[]}`.

**Step 2 — Process** (clean → label → theme → guardrail → persist to Postgres):

```bash
curl -s -X POST http://localhost:8000/discover \
  -H 'Content-Type: application/json' \
  -d '{"query":"meta company","mode":"auto_proceed","max_results":5}' \
| curl -s -X POST http://localhost:8000/dataeng/process \
  -H 'Content-Type: application/json' --data-binary @-
```

Returns a `DataEngReport` `{persisted, failed, failures[]}`.

**Step 3 — Read back** the stored rows:

```bash
curl -s 'http://localhost:8000/items?stream=MICRO&limit=10'
```

### Path B — Interactive (human-in-the-loop)

`POST /discover` (interactive) → `Clarify` → `POST /discover/clarify` → process → items

**Step 1 — Discover with a vague query:**

```bash
curl -s -X POST http://localhost:8000/discover \
  -H 'Content-Type: application/json' \
  -d '{"query":"meta","mode":"interactive","max_results":5}'
```

If ambiguous, returns a `Clarify` payload `{original_query, questions[], round}` instead
of results (no fan-out yet).

**Step 2 — Answer with a sharper query** (increment `round` each time):

```bash
curl -s -X POST http://localhost:8000/discover/clarify \
  -H 'Content-Type: application/json' \
  -d '{"clarified_query":"Meta Platforms (META) stock outlook","round":1,"mode":"interactive","max_results":5}'
```

Returns a `DiscoveryResult`. (Clarification is capped at 2 rounds, after that it proceeds
automatically.)

**Step 3 — Process** the clarified result into Postgres (pipe `/discover/clarify` straight
into `/dataeng/process`):

```bash
curl -s -X POST http://localhost:8000/discover/clarify \
  -H 'Content-Type: application/json' \
  -d '{"clarified_query":"Meta Platforms (META) stock outlook","round":1,"mode":"interactive","max_results":5}' \
| curl -s -X POST http://localhost:8000/dataeng/process \
  -H 'Content-Type: application/json' --data-binary @-
```

Returns a `DataEngReport` `{persisted, failed, failures[]}`.

**Step 4 — Read back** the stored rows:

```bash
curl -s 'http://localhost:8000/items?ticker=$META&limit=10'
```

---

## 5. Endpoint reference

| Method | Path                | Purpose                                                             | Returns                        |
| ------ | ------------------- | ------------------------------------------------------------------- | ------------------------------ |
| GET    | `/health`           | liveness check                                                      | `{status}`                     |
| POST   | `/discover`         | refine query → fan out (Exa + YouTube)                              | `DiscoveryResult` or `Clarify` |
| POST   | `/discover/clarify` | resume after clarifying questions                                   | `DiscoveryResult` or `Clarify` |
| POST   | `/dataeng/process`  | clean + label + theme + persist                                     | `DataEngReport`                |
| GET    | `/items`            | read persisted rows (filters: `stream`, `theme`, `ticker`, `limit`) | `list[CleanedItem]`            |
| GET    | `/discover?query=`  | plain fan-out, no LLM (quick test, no GCP needed)                   | `DiscoveryResult`              |

**Key request fields**

- `mode`: `"auto_proceed"` (skip clarification, one-shot) or `"interactive"` (ask when ambiguous). Default is interactive.
- `max_results`: 1–50 results per source.
- `/items` filters: `stream=MICRO|MACRO`, `theme=Solar` (etc.), `ticker=$META`.

---

## 6. Inspecting the database directly (DBeaver / psql)

The data lives in Postgres (see `DATABASE_URL` in `.env`):

- **Local:** `localhost:5433`, database/user `council`, password `council` (from `docker-compose.yml`).
- **Cloud SQL:** connect via the Cloud SQL Auth Proxy, or from Cloud Run over the
  `/cloudsql/PROJECT:REGION:INSTANCE` socket.

Table: `cleaned_items` (schema `public`).

---

## 7. Run the tests

```bash
uv run pytest        # unit tests; no network or DB needed (the LLM + DB are mocked)
```

---

## 8. Troubleshooting

- **DB connection refused** → for local dev make sure Postgres is up (`docker compose up -d`);
  for Cloud SQL make sure the Auth Proxy is running (or that Cloud Run has the
  `--add-cloudsql-instances` flag and the service account has `roles/cloudsql.client`).
- **Cloud SQL instance is `SUSPENDED` / `Connection refused` on the `/cloudsql/...` socket**
  → check `gcloud sql instances list`. If the state is `SUSPENDED`, the instance is switched
  off and **no** app change will help. The usual cause on this project: the instance was
  created through the Console's **Cloud SQL free trial**, which lasts exactly 30 days,
  provisions an oversized Enterprise Plus machine, and is auto-suspended the hour it expires.
  There is no convert/upgrade path afterwards and the free-trial quota is 1 per project and
  not adjustable — check it under *IAM & Admin → Quotas → Cloud SQL Admin API*. A suspended
  instance is also what produces the 429 below, because the Cloud Run SQL socket keeps
  retrying `cloudsql.instances.connect` against a dead instance.
  **Always create the instance with `./deploy.sh provision`, never the free-trial flow.**
  Suspended instances are eventually deleted, so if backups were off, the data is gone.
- **`429` / `rateLimitExceeded` from the Cloud SQL Admin API** → `sqladmin.googleapis.com`
  has a per-project, **per-minute** request quota shared by everything that administers the
  instance. Ordinary SQL queries don't count against it — the app talks to the
  `/cloudsql/...` socket via psycopg, so a healthy service spends none of it. The callers
  that do are: `deploy.sh provision`, `init_db_job.sh`, a local `cloud-sql-proxy`, and the
  Cloud Run SQL socket (which re-fetches an ephemeral cert on **every container start**).
  - For routine code changes run `./deploy.sh deploy`, not the full script — it makes zero
    Cloud SQL Admin calls. Provisioning is one-time-per-environment.
  - Run **one** long-lived Auth Proxy. Restarting it in a loop re-fetches certs each time.
  - If it happens with nothing but the app running, suspect a container restart loop —
    each restart costs two admin calls. Check with:
    ```bash
    gcloud run revisions list --service council-api --region "$REGION"
    gcloud logging read 'protoPayload.serviceName="sqladmin.googleapis.com"' --limit 50 \
      --format='table(timestamp,protoPayload.methodName,protoPayload.authenticationInfo.principalEmail)'
    ```
  - The quota window is a minute — waiting it out is usually enough. The scripts now back
    off and retry (2/4/8/16s) on their own, and **abort loudly** rather than mistaking a
    throttle for "already exists".
- **`PermissionDenied` / `403` from Vertex** → run `gcloud auth application-default login`,
  confirm `GCP_PROJECT` is set, the Vertex AI API is enabled, and (on Cloud Run) the service
  account has `roles/aiplatform.user`. A `404` usually means the `GEMINI_MODEL` id isn't
  available in `VERTEX_LOCATION`.
- **`EXA_API_KEY not set` in `skipped`** → add the Exa key to `backend/.env` and restart.
- **No results, both sources skipped** → expected if neither `EXA_API_KEY` nor
  `YOUTUBE_API_KEY` is set; the run still succeeds, just with empty `items`.
- **An item shows up in `failed` with "cleaned text not found in source"** → the
  anti-fabrication guardrail dropped it (the cleaned text wasn't grounded in the source).
  This is intended safety behaviour, not a crash.

---

## 9. What to look for when testing

A successful end-to-end run should show:

1. `POST /discover` returns real web sources with the query **refined** by Gemini
   (`original_query` vs `query` differ).
2. `POST /dataeng/process` reports `persisted > 0`.
3. `GET /items` returns rows with sensible `stream` (MACRO/MICRO), `industry`, `themes`
   (e.g. Solar, Technology), and resolved `entities` (e.g. `$META`).
4. Every stored item has a `source_url` — nothing is "orphan" / unsourced.
